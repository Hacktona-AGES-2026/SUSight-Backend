from __future__ import annotations

import asyncio
import contextlib
import csv
import hashlib
import io
import os
import re
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from pydantic import Field, field_validator, model_validator

from . import extraction
from .access import Access, Principal
from .artifacts import purge_artifacts
from .policy import POLICY_VERSION
from .reassessment import ScoringModel, reassess
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
from .tribunal.store import SESSION_IDLE_SECONDS, AccountLocked, LoginRefused, Store


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


class ContestInput(Strict):
    motivo: str = Field(min_length=3, max_length=2000)


class ConclusionInput(Strict):
    justificativa: str = Field(min_length=3, max_length=2000)


class PreferencesInput(Strict):
    # Only optional notices; "exame_pedido" is rejected as an extra field (spec 005).
    documento_recebido: bool | None = None
    analise_concluida: bool | None = None
    prioridade_validada: bool | None = None


class ContactInput(Strict):
    nome: str = Field(min_length=2, max_length=200)
    parentesco: str = Field(min_length=2, max_length=50)
    telefone: str = Field(pattern=r"^[0-9 ()+-]{8,20}$")


class DeviceInput(Strict):
    plataforma: Literal["ios", "android", "windows"]
    token: str = Field(min_length=8, max_length=500)


def masked_phone(phone):
    digits = re.sub(r"\D", "", phone)
    return "*" * (len(digits) - 4) + digits[-4:]


class FileUpload(Strict):
    solicitacao_id: str = Field(min_length=1, max_length=100)
    tipo_mime: str = Field(max_length=100)
    conteudo_base64: str = Field(max_length=15_000_000)
    termo_versao: str = Field(max_length=100)
    aceite_termo: bool
    pedido_id: str | None = Field(default=None, max_length=100)


class FieldReview(Strict):
    acao: Literal["aprovar", "corrigir", "rejeitar"]
    valor_corrigido: Any = None
    justificativa: str = Field(min_length=3, max_length=2000)

    @model_validator(mode="after")
    def correction_has_value(self):
        if self.acao == "corrigir" and self.valor_corrigido is None:
            raise ValueError("Corrigir exige o valor corrigido")
        return self


ProposalStatus = Literal[
    "aguardando_tribunal",
    "processando",
    "tribunal_indisponivel",
    "pronta_para_medico",
    "aprovar",
    "rejeitar",
    "pedir_informacoes",
    "cancelada",
    "desatualizada",
]


class LoginInput(Strict):
    identificador: str = Field(min_length=1, max_length=100)
    senha: str = Field(min_length=1, max_length=200)


class ReferenceVersion(Strict):
    versao_fila: int = Field(ge=1)


def create_app(
    database=None,
    provider=None,
    token=None,
    start_worker=True,
    access=None,
    clock=None,
    extractor=None,
    scoring=None,
):
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
    app.state.extractor = extractor or extraction.GeminiExtractor()
    app.state.scoring = scoring

    def authenticate(authorization: str | None = Header(default=None)):
        principal = identities.resolve(authorization)
        if principal is None and authorization and authorization.startswith("Bearer "):
            account = store.session(authorization[7:])
            if account:
                principal = Principal(account["id"], account["papel"], frozenset(account["pacientes"]))
        if principal is None:
            raise HTTPException(401, "Autenticacao necessaria")
        return principal

    @app.post("/sessoes")
    def start_session(body: LoginInput):
        try:
            created = store.login(body.identificador, body.senha)
        except AccountLocked:
            raise HTTPException(429, "Muitas tentativas. Tente novamente mais tarde.") from None
        except LoginRefused:
            raise HTTPException(401, "Identificador ou senha invalidos") from None
        return created | {"inatividade_segundos": SESSION_IDLE_SECONDS}

    @app.delete("/sessoes")
    def end_session(authorization: str | None = Header(default=None)):
        if (
            not authorization
            or not authorization.startswith("Bearer ")
            or not store.logout(authorization[7:])
        ):
            raise HTTPException(401, "Sessao nao encontrada")
        return {"encerrada": True}

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
        disputed = store.disputed()
        return {
            "politica": POLICY_VERSION,
            "versao": version,
            # Whole-queue size, so a patient who sees only their own row can say "42nd of 118".
            "total": len(rows),
            "pacientes": [
                r | {"em_reavaliacao": r["solicitacao_id"] in disputed} for r in rows if principal.permits(r)
            ],
        }

    @app.get("/fila/exportacao.csv")
    def export_queue(principal=principal_dependency):
        professional(principal)
        version, rows = store.queue()
        rows = [r for r in rows if principal.permits(r)]
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["solicitacao_id", "posicao", "justificativa"])
        writer.writerows([r["solicitacao_id"], r["posicao"], r.get("justificativa", "")] for r in rows)
        store.log_export(principal.id, version, len(rows))
        return Response(out.getvalue(), media_type="text/csv; charset=utf-8")

    @app.post("/solicitacoes/{sid}/contestacao", status_code=201)
    def contest(sid: str, body: ContestInput, principal=principal_dependency):
        professional(principal)
        row = permit_case(sid, principal)
        try:
            store.open_dispute(sid, row.get("paciente_id"), principal.id, body.motivo)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return {"solicitacao_id": sid, "situacao": "em_reavaliacao"}

    @app.post("/solicitacoes/{sid}/contestacao/conclusao")
    def conclude_contest(sid: str, body: ConclusionInput, principal=principal_dependency):
        professional(principal)
        permit_case(sid, principal)
        try:
            store.conclude_dispute(sid, principal.id, body.justificativa)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return {"solicitacao_id": sid, "situacao": "concluida", "resultado": "posicao_mantida"}

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

    def patient_of(principal):
        if principal.papel != "paciente":
            raise HTTPException(403, "Operacao restrita ao paciente")
        return next(iter(principal.pacientes))

    def audience(principal):
        if principal.papel == "paciente":
            return "paciente", principal.pacientes
        return "profissional", None if principal.sees_all else principal.pacientes

    @app.get("/notificacoes")
    def notifications(principal=principal_dependency):
        rows = store.notifications(*audience(principal), principal.id)
        return {
            "nao_lidas": sum(not r["lida"] for r in rows),
            "notificacoes": [
                {
                    "id": r["id"],
                    "tipo": r["tipo"],
                    "titulo": r["titulo"],
                    "texto": r["texto"],
                    "solicitacao_id": r["sid"],
                    "lida": bool(r["lida"]),
                    "data_hora": r["created_at"],
                }
                for r in rows
            ],
        }

    @app.post("/notificacoes/{nid}/lida")
    def mark_read(nid: int, principal=principal_dependency):
        if not store.mark_read(nid, *audience(principal), principal.id):
            raise HTTPException(404, "Notificacao nao encontrada")
        return {"id": nid, "lida": True}

    @app.get("/preferencias/notificacoes")
    def get_preferences(principal=principal_dependency):
        return store.preferences(patient_of(principal))

    @app.put("/preferencias/notificacoes")
    def put_preferences(body: PreferencesInput, principal=principal_dependency):
        return store.set_preferences(patient_of(principal), body.model_dump(exclude_none=True))

    @app.get("/contatos")
    def contacts(principal=principal_dependency):
        return {
            "contatos": [
                {
                    "contato_id": c["id"],
                    "nome": c["nome"],
                    "parentesco": c["parentesco"],
                    "telefone": masked_phone(c["telefone"]),
                }
                for c in store.contacts(patient_of(principal))
            ]
        }

    @app.post("/contatos", status_code=201)
    def add_contact(body: ContactInput, principal=principal_dependency):
        return {"contato_id": store.add_contact(patient_of(principal), body.model_dump())}

    @app.delete("/contatos/{cid}")
    def delete_contact(cid: int, principal=principal_dependency):
        if not store.delete_contact(patient_of(principal), cid):
            raise HTTPException(404, "Contato nao encontrado")
        return {"contato_id": cid, "removido": True}

    @app.get("/dispositivos")
    def devices(principal=principal_dependency):
        return {
            "dispositivos": [
                {"dispositivo_id": d["id"], "plataforma": d["plataforma"], "data_hora": d["created_at"]}
                for d in store.devices(principal.id)
            ]
        }

    @app.post("/dispositivos", status_code=201)
    def add_device(body: DeviceInput, principal=principal_dependency):
        patient = next(iter(principal.pacientes)) if principal.papel == "paciente" else None
        return {"dispositivo_id": store.add_device(principal.id, patient, body.model_dump())}

    @app.delete("/dispositivos/{did}")
    def delete_device(did: int, principal=principal_dependency):
        if not store.delete_device(principal.id, did):
            raise HTTPException(404, "Dispositivo nao encontrado")
        return {"dispositivo_id": did, "removido": True}

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

    @app.get("/termos/upload")
    def upload_term(principal=principal_dependency):
        return {"versao": extraction.TERM_VERSION, "texto": extraction.TERM_TEXT}

    @app.post("/documentos/arquivo", status_code=201)
    def upload_file(body: FileUpload, principal=principal_dependency):
        permit_case(body.solicitacao_id, principal)
        if not body.aceite_termo or body.termo_versao != extraction.TERM_VERSION:
            raise HTTPException(
                422,
                "Aceite a versao vigente do termo antes de enviar. Sem aceite, o documento pode ser levado a UBS.",
            )
        try:
            data = extraction.decode(body.conteudo_base64)
            pages = extraction.check_file(data, body.tipo_mime)
        except extraction.FileRejected as exc:
            raise HTTPException(422, str(exc)) from None
        document = {
            "solicitacao_id": body.solicitacao_id,
            "sha256": hashlib.sha256(data).hexdigest(),
            "tipo_mime": body.tipo_mime,
            "paginas": pages,
            "tamanho_bytes": len(data),
            "pedido_id": body.pedido_id,
            "origem": "paciente" if principal.papel == "paciente" else "profissional",
        }
        try:
            did = store.register_document(
                document, principal.id, file=(data, body.tipo_mime), term_version=extraction.TERM_VERSION
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        return {"documento_id": did, "situacao": "recebido", "paginas": pages}

    def permitted_document(did, principal):
        try:
            doc = store.document(did)
        except KeyError:
            raise HTTPException(404, "Documento nao encontrado") from None
        permit_case(doc["sid"], principal)
        return doc

    CRITERION_FIELDS = ("limitacao_funcional", "asa", "dor", "comorbidades", "deterioracao")

    def evidence_value(name, value):
        if name == "dor":
            return value["intensidade"]
        if name == "comorbidades":
            return [item["valor"] for item in value]
        return value

    def reevaluate(did, fields):
        """A read document re-scores its patient; a better position becomes a proposal for the doctor.

        The doctor approves the final result, not each evidence: the OCR evidence is registered as approved by
        the system and shown as such in the proposal. Nothing changes the queue before that approval.
        """
        raw = app.state.scoring or store.scoring_model()
        model = raw if isinstance(raw, ScoringModel) else ScoringModel.from_file(raw) if raw else None
        document = store.document(did)
        sid = document["sid"]
        version, rows = store.queue()
        patient = next((r for r in rows if r["solicitacao_id"] == sid), None)
        if model is None or patient is None:
            return
        try:
            result = reassess(rows, sid, fields, model)
        except ValueError:
            return
        if result["criterios"] == patient["criterios"]:
            return store.note(
                sid, "documento_lido", "sistema-ocr", "Documento lido: os critérios não mudaram."
            )
        if result["posicao"] >= patient["posicao"]:
            return store.note(
                sid,
                "documento_lido",
                "sistema-ocr",
                "Documento lido: critérios atualizados, sem mudança de posição.",
            )
        evidences, today = [], store.instant()[:10]
        for name in CRITERION_FIELDS:
            item = fields.get(name) or {}
            if item.get("valor_extraido") is None or item.get("confianca") not in {"alta", "media"}:
                continue
            quote = (item.get("evidencias") or [{}])[0]
            if not quote.get("trecho"):
                continue
            payload = {
                "evidencia": {
                    "evidencia_id": f"OCR-{did[:12]}-{name}",
                    "tipo": "criterio",
                    "resultado": "observado",
                    "data": today,
                },
                "documento_id": did,
                "pagina": quote["pagina"],
                "trecho": quote["trecho"],
                "campo": name,
                "valor": evidence_value(name, item["valor_extraido"]),
                "confianca": item["confianca"],
            }
            eid = store.register_evidence(EvidenceRegistration(**payload).model_dump(), "sistema-ocr")
            store.review_evidence(
                eid,
                "aprovar",
                "sistema-ocr",
                "Lida do documento pelo sistema; o médico confere o resultado final.",
            )
            evidences.append(store.approved_payload(eid, sid))
        body = ProposalInput(
            solicitacao_id=sid,
            posicao_proposta=result["posicao"],
            versao_fila=version,
            ordenacao_incerta=True,
            evidencias=evidences,
            reavaliacao={k: result[k] for k in ("criterios", "swalis", "sem_urgencia", "pontuacao")},
        ).model_dump()
        store.create(body, "sistema-ocr")

    @app.post("/documentos/{did}/extracao")
    async def run_extraction(did: str, principal=principal_dependency):
        permitted_document(did, principal)
        stored = store.document_file(did)
        if stored is None:
            raise HTTPException(409, "Documento sem arquivo para leitura")
        pages = extraction.read_pages(*stored)
        if pages is None:
            result = ("revisao_manual", ["leitura_automatica_indisponivel"], extraction.manual("ilegivel"))
        else:
            masked = extraction.mask(pages)
            if not extraction.masked_safely(masked):
                result = ("revisao_manual", ["mascaramento_nao_assegurado"], extraction.manual("incerto"))
            else:
                try:
                    raw = await app.state.extractor.extract(masked)
                except extraction.ExtractorUnavailable:
                    result = ("pendente", ["servico_indisponivel"], {})
                except Exception:  # noqa: BLE001 -- provider failures must never become simulated data
                    result = ("pendente", ["leitura_falhou"], {})
                else:
                    fields = extraction.normalize(raw, masked)
                    warnings = (
                        ["revisao_necessaria"] if any(f["requer_revisao"] for f in fields.values()) else []
                    )
                    result = ("extraido", warnings, fields)
        store.save_extraction(did, *result)
        if result[0] == "extraido":
            reevaluate(did, result[2])
        return {"documento_id": did, "situacao": result[0], "avisos": result[1]}

    @app.get("/documentos/{did}/extracao")
    def get_extraction(did: str, principal=principal_dependency):
        permitted_document(did, principal)
        return store.extraction(did) or {"situacao": "nao_iniciada", "avisos": [], "campos": {}}

    @app.post("/documentos/{did}/campos/{campo}/revisao")
    def review_field(did: str, campo: str, body: FieldReview, principal=principal_dependency):
        professional(principal)
        permitted_document(did, principal)
        if campo not in extraction.FIELDS:
            raise HTTPException(404, "Campo nao encontrado")
        try:
            store.review_field(did, campo, principal.id, body.acao, body.valor_corrigido, body.justificativa)
        except KeyError:
            raise HTTPException(404, "Extracao nao encontrada") from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return {"documento_id": did, "campo": campo, "acao": body.acao}

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

    ready_only = Query(default=["pronta_para_medico"])

    @app.get("/propostas")
    def list_proposals(situacao: list[ProposalStatus] = ready_only, principal=principal_dependency):
        professional(principal)
        patients = None if principal.sees_all else principal.pacientes
        items = store.list_proposals(sorted(set(situacao)), patients)
        return {"total": len(items), "propostas": items}

    @app.get("/propostas/{pid}")
    def proposal_detail(pid: str, principal=principal_dependency):
        professional(principal)
        try:
            body = store.proposal_detail(pid)
        except KeyError:
            raise HTTPException(404, "Proposta nao encontrada") from None
        permit_case(body["solicitacao_id"], principal)
        return body

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
            pid = store.create(payload, principal.id)
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
            # Criteria re-read from the document take effect only now, with the doctor's approval.
            patient |= p["body"].get("reavaliacao") or {}
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
