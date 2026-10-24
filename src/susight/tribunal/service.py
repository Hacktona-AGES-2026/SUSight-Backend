from __future__ import annotations

import asyncio
import hashlib
from collections import Counter
from datetime import UTC, datetime

from susight.dataset.core import normalize

from .guards import guard
from .models import AGENTS, JUDGE, Vote
from .store import EvidenceUnavailable


def pseudonym(sid):
    return hashlib.sha256(sid.encode()).hexdigest()[:16]


def masked_context(proposal, queue, guarded):
    sid = proposal["solicitacao_id"]
    patient = next(r for r in queue if r["solicitacao_id"] == sid)
    lo, hi = sorted([patient["posicao"], guarded["posicao"]])

    def mask(r):
        return {
            "paciente": pseudonym(r["solicitacao_id"]),
            "cid": r["cid"],
            "pontuacao": r["pontuacao"],
            "posicao": r["posicao"],
        }

    return {
        "paciente": mask(patient),
        "posicao_proposta": guarded["posicao"],
        "afetados": [mask(r) for r in queue if lo <= r["posicao"] <= hi and r["solicitacao_id"] != sid],
        "evidencias": [{**e, "evidencia_id": pseudonym(e["evidencia_id"])} for e in proposal["evidencias"]],
        "travas": guarded["travas"],
        "ordenacao_incerta": proposal["ordenacao_incerta"],
        "evidencias_conflitantes": proposal["evidencias_conflitantes"],
    }
        # Reason the doctor gave when sending the proposal back; empty on the first round.
        "devolutiva_medico": proposal.get("devolutiva", ""),


def consolidate_votes(votes, judge=None):
    """The judge's ruling is the opinion; without one (legacy), the majority decides."""
    if judge is not None:
        verdict, dissent = judge.veredito, [v.model_dump() for v in votes if v.veredito != judge.veredito]
        votes = [*votes, judge]
    else:
        counts = Counter(v.veredito for v in votes)
        majority = counts.most_common(1)[0]
        verdict = majority[0] if majority[1] >= 2 else "ajustar"
        dissent = [v.model_dump() for v in votes if majority[1] == 1 or v.veredito != verdict]
    return {
        "recomendacao": {"a_favor": "aprovar", "contra": "negar", "ajustar": "ajustar"}[verdict],
        "divergencias": dissent,
        "manifestacoes": [v.model_dump() for v in votes],
    }


class Tribunal:
    def __init__(self, store, provider, timeout=30.0, concurrency=1):
        self.store, self.provider, self.timeout = store, provider, timeout
        self.semaphore = asyncio.Semaphore(concurrency)

    async def process(self, pid):
        async with self.semaphore:
            try:
                if not self.store.claim(pid):
                    return self.store.get(pid)
                p = self.store.get(pid)
            except KeyError:
                return {"id": pid, "status": "expirada", "attempts": 0, "opinion": None}
            try:
                self.store.live_evidence(p["body"])
                version, queue = self.store.queue()
                body = p["body"]
                if version != body["versao_fila"]:
                    self.store.finish(pid, "desatualizada", error="Fila mudou: nova proposta necessaria")
                    return self.store.get(pid)
                checked = guard(queue, body["solicitacao_id"], body["posicao_proposta"])
                if not checked["liberada"]:
                    self.store.finish(
                        pid,
                        "barrada",
                        opinion={
                            "recomendacao": "negar",
                            "manifestacoes": [],
                            "travas": checked["travas"],
                            "posicao": checked["posicao"],
                        },
                    )
                    return self.store.get(pid)
                context = masked_context(body, queue, checked)
                votes = await asyncio.gather(
                    *(
                        asyncio.wait_for(self.provider.analyze(a, context), timeout=self.timeout)
                        for a in AGENTS
                    ),
                    return_exceptions=True,
                )
                if any(isinstance(v, BaseException) for v in votes):
                    raise ValueError("Falha ou tempo limite em agente")
                original_ids = {pseudonym(e["evidencia_id"]): e["evidencia_id"] for e in body["evidencias"]}
                known = set(original_ids)
                proof = any(
                    e["tipo"]
                    in {"biopsia", "exame_imagem", "pronto_socorro", "internacao", "consulta_reavaliacao"}
                    for e in body["evidencias"]
                )

                def check(role, raw):
                    vote = Vote.model_validate(raw)
                    if vote.agente != role or not set(vote.evidencias_citadas).issubset(known):
                        raise ValueError("Agente ou referencia de evidencia invalida")
                    if vote.posicao_sugerida is not None and vote.posicao_sugerida > len(queue):
                        raise ValueError("Posicao sugerida fora da fila")
                    # This is a lexical guard, not a claim of semantic medical verification.
                    if any(
                        term in normalize(vote.justificativa)
                        for term in ["diagnostico confirmado", "voce tem cancer", "risco iminente de morte"]
                    ):
                        raise ValueError("Linguagem nao permitida")
                    if not proof:
                        vote.sem_comprovacao = True
                        if role in {"evidencias", JUDGE} and vote.veredito == "a_favor":
                            vote.veredito = "contra"
                            vote.justificativa = (
                                "Nao ha exame ou evento clinico documentado que comprove a mudanca."
                            )
                    if vote.veredito in {"a_favor", "ajustar"} and not vote.evidencias_citadas:
                        raise ValueError("Voto favoravel ou ajuste sem referencia de evidencia")
                    vote.evidencias_citadas = [original_ids[e] for e in vote.evidencias_citadas]
                    return vote

                normalized = [check(role, raw) for role, raw in zip(AGENTS, votes)]
                # The judge reads the three arguments and decides; the doctor still has the last word.
                heard = [
                    {
                        "agente": v.agente,
                        "veredito": v.veredito,
                        "posicao_sugerida": v.posicao_sugerida,
                        "justificativa": v.justificativa,
                    }
                    for v in normalized
                ]
                ruling = await asyncio.wait_for(
                    self.provider.analyze(JUDGE, context | {"votos": heard}), timeout=self.timeout
                )
                judge = check(JUDGE, ruling)
                opinion = consolidate_votes(normalized, judge)
                target = checked["posicao"]
                if opinion["recomendacao"] == "ajustar":
                    target = judge.posicao_sugerida or target
                result = guard(queue, body["solicitacao_id"], target)
                if not result["liberada"]:
                    opinion["recomendacao"] = "negar"
                opinion.update(
                    {
                        "posicao": result["posicao"],
                        "travas": sorted(set(checked["travas"] + result["travas"])),
                        "modelo": getattr(self.provider, "model", "cliente_de_teste"),
                        "criado_em": datetime.now(UTC).isoformat(),
                        "tentativas": p["attempts"] + 1,
                        "sem_comprovacao": not proof,
                        "versao_fila": version,
                    }
                )
                self.store.live_evidence(body)
                if self.store.queue()[0] != version:
                    self.store.finish(pid, "desatualizada", error="Fila mudou durante analise")
                else:
                    self.store.finish(pid, "pronta_para_medico", opinion=opinion)
            except (KeyError, EvidenceUnavailable):
                self.store.finish(pid, "invalidada", error="Referencia expirada ou sem aprovacao valida")
            except Exception:  # noqa: BLE001 -- provider failures must remain durable and retriable
                attempts = p["attempts"] + 1
                self.store.finish(
                    pid,
                    "tribunal_indisponivel" if attempts >= 3 else "aguardando_tribunal",
                    error="Nao foi possivel concluir o parecer. Nova tentativa agendada.",
                    delay=min(300, 5 * 2 ** min(attempts - 1, 6)),
                )
            except BaseException:
                self.store.finish(pid, "aguardando_tribunal", error="Processamento interrompido", delay=5)
                raise
            try:
                return self.store.get(pid)
            except KeyError:
                return {"id": pid, "status": "expirada", "attempts": p["attempts"], "opinion": None}

    async def worker(self):
        while True:
            for pid in self.store.due():
                await self.process(pid)
            await asyncio.sleep(1)
