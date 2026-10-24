from __future__ import annotations

import asyncio
import contextlib
import hmac
import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import Field, field_validator

from .tribunal.guards import guard, validate_queue
from .tribunal.models import ProposalInput, QueuePatient, Strict
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

    @field_validator("medico")
    @classmethod
    def named_actor(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Nome do medico obrigatorio")
        return value


class ReferenceVersion(Strict):
    versao_fila: int = Field(ge=1)


def create_app(database=None, provider=None, token=None, start_worker=True):
    # Refuse an unauthenticated clinical API. Config is evaluated at lifespan time.
    configured_token = token if token is not None else os.environ.get("SUSIGHT_API_TOKEN", "")
    store = Store(database or os.environ.get("SUSIGHT_DATABASE", "data/susight.sqlite3"))
    tribunal = Tribunal(store, provider or GeminiProvider())

    @asynccontextmanager
    async def lifespan(app):
        if not configured_token or len(configured_token) < 16:
            raise RuntimeError("Configure SUSIGHT_API_TOKEN com pelo menos 16 caracteres")
        task = asyncio.create_task(tribunal.worker()) if start_worker else None
        yield
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="SUSight Backend", version="0.1.0", lifespan=lifespan)
    app.state.store, app.state.tribunal = store, tribunal

    def authenticate(authorization: str | None = Header(default=None)):
        expected = "Bearer " + configured_token
        if not configured_token or not hmac.compare_digest(authorization or "", expected):
            raise HTTPException(401, "Autenticacao necessaria")

    def get_proposal(pid):
        try:
            return store.get(pid)
        except KeyError:
            raise HTTPException(404, "Proposta nao encontrada") from None

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/fila", dependencies=[Depends(authenticate)])
    def current_queue():
        version, rows = store.queue()
        return {"versao": version, "pacientes": rows}

    @app.put("/fila", dependencies=[Depends(authenticate)])
    def import_queue(payload: QueueImport):
        try:
            rows = validate_queue([r.model_dump() for r in payload.pacientes])
            version = store.import_queue(rows, payload.versao_esperada)
            return {"versao": version, "solicitacoes": len(rows)}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None

    @app.post("/propostas", status_code=201, dependencies=[Depends(authenticate)])
    def create_proposal(body: ProposalInput):
        version, queue = store.queue()
        if version != body.versao_fila:
            raise HTTPException(409, "Versao da fila desatualizada")
        if not any(r["solicitacao_id"] == body.solicitacao_id for r in queue):
            raise HTTPException(404, "Solicitacao nao encontrada")
        if body.posicao_proposta > len(queue):
            raise HTTPException(422, "Posicao fora da fila")
        try:
            pid = store.create(body.model_dump())
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return {"proposta_id": pid, "situacao": "aguardando_tribunal"}

    @app.post("/propostas/{pid}/tribunal", dependencies=[Depends(authenticate)])
    async def invoke(pid: str):
        get_proposal(pid)
        p = await tribunal.process(pid)
        return {"proposta_id": pid, "situacao": p["status"], "tentativas": p["attempts"]}

    @app.get("/propostas/{pid}/parecer", dependencies=[Depends(authenticate)])
    def opinion(pid: str):
        p = get_proposal(pid)
        return {
            "proposta_id": pid,
            "situacao": p["status"],
            "parecer": p["opinion"],
            "tentativas": p["attempts"],
            "aviso": p["error"],
        }

    @app.post("/propostas/{pid}/decisao", dependencies=[Depends(authenticate)])
    def decide(pid: str, payload: Decision):
        p = get_proposal(pid)
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
            version = store.decide(pid, payload.medico.strip(), payload.acao, payload.motivo.strip(), changed)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return {"proposta_id": pid, "situacao": payload.acao, "versao_fila": version}

    return app
