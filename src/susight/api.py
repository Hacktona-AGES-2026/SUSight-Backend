from __future__ import annotations

import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import Field, field_validator, model_validator

from .access import Access
from .artifacts import purge_artifacts
from .policy import POLICY_VERSION
from .tribunal.guards import guard, validate_queue
from .tribunal.models import (
    Cancellation,
    DocumentInput,
    EvidenceReferences,
    EvidenceRegistration,
    EvidenceReview,
    ExamRequestInput,
    ProposalInput,
    QueuePatient,
    Strict,
)
from .tribunal.provider import GeminiProvider
from .tribunal.service import Tribunal
from .tribunal.store import Store


class QueueImport(Strict):
    versao_esperada: int = Field(ge=0)
    pacientes: list[QueuePatient] = Field(min_length=1, max_length=5000)


class Decision(Strict):
    medico: str = Field(min_length=3, max_length=200)
    acao: Literal["aprovar", "rejeitar", "pedir_informacoes"]
    motivo: str = Field(default="", max_length=2000)
    exames: list[ExamRequestInput] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def exams_only_when_asking(self):
        if (self.acao == "pedir_informacoes") != bool(self.exames):
            raise ValueError("Pedir informacoes exige exames; as demais decisoes nao aceitam exames")
        return self

    @field_validator("medico")
    @classmethod
    def named_actor(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Nome do medico obrigatorio")
        return value


class ReferenceVersion(Strict):
    versao_fila: int = Field(ge=1)


def create_app(database=None, provider=None, token=None, start_worker=True, access=None, clock=None):
    # Refuse an unauthenticated clinical API. Config is evaluated at lifespan time.
    configured_token = token if token is not None else os.environ.get("SUSIGHT_API_TOKEN", "")
    identities = access
    if identities is None:
        path = os.environ.get("SUSIGHT_ACCESS_FILE")
        identities = Access.from_file(path) if path else Access(token=configured_token or None)
    store = Store(
        database or os.environ.get("SUSIGHT_DATABASE", "data/susight.sqlite3"),
        **({"clock": clock} if clock else {}),
    )
    tribunal = Tribunal(store, provider or GeminiProvider())

    @asynccontextmanager
    async def lifespan(app):
        if not identities.entries:
            raise RuntimeError(
                "Configure SUSIGHT_ACCESS_FILE ou SUSIGHT_API_TOKEN administrativo com pelo menos 16 caracteres"
            )

        async def maintenance():
            while True:
                store.purge_expired()
                root = os.environ.get("SUSIGHT_ARTIFACT_ROOT")
                if root:
                    await asyncio.to_thread(purge_artifacts, root)
                await asyncio.sleep(30)

        cleanup_task = asyncio.create_task(maintenance()) if start_worker else None
        task = asyncio.create_task(tribunal.worker()) if start_worker else None
        yield
        for background in [task, cleanup_task]:
            if background:
                background.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await background

    app = FastAPI(title="SUSight Backend", version="0.1.0", lifespan=lifespan)
    app.state.store, app.state.tribunal = store, tribunal

    def authenticate(authorization: str | None = Header(default=None)):
        principal = identities.resolve(authorization)
        if principal is None:
            raise HTTPException(401, "Autenticacao necessaria")
        return principal

    def professional(principal):
        if principal.papel not in {"admin", "medico"}:
            raise HTTPException(403, "Operacao restrita ao profissional autorizado")

    def permit_case(sid, principal):
        row = next((r for r in store.queue()[1] if r["solicitacao_id"] == sid), None)
        if row is None or not principal.permits(row):
            raise HTTPException(404, "Caso nao encontrado")
        return row

    principal_dependency = Depends(authenticate)

    def get_proposal(pid):
        try:
            return store.get(pid)
        except KeyError:
            raise HTTPException(404, "Proposta nao encontrada") from None

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/fila", dependencies=[Depends(authenticate)])
    def current_queue(principal=principal_dependency):
        version, rows = store.queue()
        return {
            "politica": POLICY_VERSION,
            "versao": version,
            "pacientes": [r for r in rows if principal.permits(r)],
        }

    @app.put("/fila", dependencies=[Depends(authenticate)])
    def import_queue(payload: QueueImport, principal=principal_dependency):
        if principal.papel != "admin":
            raise HTTPException(403, "Importacao restrita ao administrador")
        try:
            rows = validate_queue([r.model_dump() for r in payload.pacientes])
            version = store.import_queue(rows, payload.versao_esperada, principal.id)
            return {"versao": version, "solicitacoes": len(rows)}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.get("/solicitacoes/{sid}/historico")
    def history(sid: str, principal=principal_dependency):
        # Permission comes from the event's patient link: the trail outlives the imported queue.
        events = store.history(sid)
        if not events or not principal.permits({"paciente_id": events[0]["paciente_id"]}):
            raise HTTPException(404, "Historico nao encontrado")
        return {
            "solicitacao_id": sid,
            "eventos": [
                {
                    "tipo": e["tipo"],
                    "texto": e["texto"],
                    "responsavel": e["actor"],
                    "motivo": e["motivo"],
                    "data_hora": e["created_at"],
                }
                for e in events
            ],
        }

    @app.get("/solicitacoes/{sid}/exames-pedidos")
    def exam_requests(sid: str, principal=principal_dependency):
        rows = store.exam_requests(sid)
        if rows:
            if not principal.permits({"paciente_id": rows[0]["paciente_id"]}):
                raise HTTPException(404, "Pedidos nao encontrados")
        else:
            permit_case(sid, principal)
        return {
            "solicitacao_id": sid,
            "pendentes": sum(r["status"] == "pendente" for r in rows),
            "pedidos": [
                {
                    "pedido_id": r["id"],
                    "exame": r["exame"],
                    "explicacao": r["explicacao"],
                    "situacao": r["status"],
                    "responsavel": r["actor"],
                    "data_hora": r["created_at"],
                }
                for r in rows
            ],
        }

    @app.post("/documentos", status_code=201)
    def register_document(body: DocumentInput, principal=principal_dependency):
        permit_case(body.solicitacao_id, principal)
        try:
            did = store.register_document(body.model_dump(), principal.id)
            return {"documento_id": did, "situacao": "registrado"}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/documentos/{did}")
    def document(did: str, principal=principal_dependency):
        try:
            row = store.document(did)
        except KeyError:
            raise HTTPException(404, "Documento nao encontrado") from None
        permit_case(row["sid"], principal)
        return {"documento_id": did, "documento": row["body"], "expira_epoch": row["expires"]}

    @app.post("/evidencias", status_code=201)
    def register_evidence(body: EvidenceRegistration, principal=principal_dependency):
        try:
            doc = store.document(body.documento_id)
            permit_case(doc["sid"], principal)
            eid = store.register_evidence(body.model_dump(), principal.id)
            return {"evidencia_id": eid, "situacao": "pendente"}
        except KeyError:
            raise HTTPException(404, "Documento nao encontrado") from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/evidencias/{eid}")
    def evidence(eid: str, principal=principal_dependency):
        try:
            row = store.evidence(eid)
        except KeyError:
            raise HTTPException(404, "Evidencia nao encontrada") from None
        permit_case(row["sid"], principal)
        return {
            "evidencia": row["body"],
            "situacao": row["status"],
            "revisor": row["reviewer"],
            "revisado_em": row["reviewed_at"],
            "motivo": row["reason"],
        }

    @app.post("/evidencias/{eid}/revisao")
    def review(eid: str, body: EvidenceReview, principal=principal_dependency):
        professional(principal)
        try:
            row = store.evidence(eid)
            permit_case(row["sid"], principal)
            reviewed = store.review_evidence(eid, body.acao, principal.id, body.justificativa)
            return {"evidencia_id": eid, "situacao": reviewed["status"]}
        except KeyError:
            raise HTTPException(404, "Evidencia nao encontrada") from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.post("/propostas", status_code=201)
    def create_proposal(body: EvidenceReferences, principal=principal_dependency):
        professional(principal)
        permit_case(body.solicitacao_id, principal)
        version, queue = store.queue()
        if version != body.versao_fila:
            raise HTTPException(409, "Versao da fila desatualizada")
        if body.posicao_proposta > len(queue):
            raise HTTPException(422, "Posicao fora da fila")
        try:
            payload = body.model_dump(exclude={"evidencias_ids"})
            payload["evidencias"] = [
                store.approved_payload(eid, body.solicitacao_id) for eid in body.evidencias_ids
            ]
            payload = ProposalInput.model_validate(payload).model_dump()
            pid = store.create(payload)
        except (ValueError, KeyError) as exc:
            raise HTTPException(422, "Proposta ou evidencia invalida: " + str(exc)) from None
        return {"proposta_id": pid, "situacao": "aguardando_tribunal"}

    @app.post("/propostas/{pid}/tribunal", dependencies=[Depends(authenticate)])
    async def invoke(pid: str, principal=principal_dependency):
        professional(principal)
        permit_case(get_proposal(pid)["body"]["solicitacao_id"], principal)
        p = await tribunal.process(pid)
        return {"proposta_id": pid, "situacao": p["status"], "tentativas": p["attempts"]}

    @app.get("/propostas/{pid}/parecer", dependencies=[Depends(authenticate)])
    def opinion(pid: str, principal=principal_dependency):
        professional(principal)
        p = get_proposal(pid)
        permit_case(p["body"]["solicitacao_id"], principal)
        return {
            "proposta_id": pid,
            "situacao": p["status"],
            "parecer": p["opinion"],
            "tentativas": p["attempts"],
            "aviso": p["error"],
        }

    @app.post("/propostas/{pid}/cancelar")
    def cancel(pid: str, body: Cancellation, principal=principal_dependency):
        professional(principal)
        permit_case(get_proposal(pid)["body"]["solicitacao_id"], principal)
        try:
            store.cancel(pid, principal.id, body.justificativa)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return {"proposta_id": pid, "situacao": "cancelada"}

    @app.post("/propostas/{pid}/decisao", dependencies=[Depends(authenticate)])
    def decide(pid: str, payload: Decision, principal=principal_dependency):
        professional(principal)
        p = get_proposal(pid)
        permit_case(p["body"]["solicitacao_id"], principal)
        if p["status"] != "pronta_para_medico":
            raise HTTPException(409, "Proposta nao esta pronta para decisao")
        if payload.acao != "aprovar" and not payload.motivo.strip():
            raise HTTPException(422, "Motivo obrigatorio")
        version, queue = store.queue()
        if version != p["body"]["versao_fila"]:
            raise HTTPException(409, "Fila mudou: nova analise necessaria")
        changed = None
        if payload.acao == "aprovar":
            if p["opinion"]["recomendacao"] == "negar" and not payload.motivo.strip():
                raise HTTPException(422, "Aprovar contra o parecer exige justificativa medica")
            checked = guard(queue, p["body"]["solicitacao_id"], p["opinion"]["posicao"])
            if not checked["liberada"]:
                raise HTTPException(409, "Proposta viola travas")
            changed = [r.copy() for r in queue if r["solicitacao_id"] != p["body"]["solicitacao_id"]]
            patient = next(r.copy() for r in queue if r["solicitacao_id"] == p["body"]["solicitacao_id"])
            changed.insert(checked["posicao"] - 1, patient)
            for i, row in enumerate(changed, 1):
                row["posicao"] = i
            try:
                changed = validate_queue(changed)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from None
        try:
            version = store.decide(
                pid,
                principal.id,
                payload.acao,
                payload.motivo.strip(),
                changed,
                [e.model_dump() for e in payload.exames],
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return {"proposta_id": pid, "situacao": payload.acao, "versao_fila": version}

    return app
