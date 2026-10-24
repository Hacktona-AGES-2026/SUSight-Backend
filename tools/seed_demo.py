"""Seed a local demo database so the web and app can be tried against the real API.

Synthetic data only. The tribunal opinions come from a deterministic stand-in provider
defined below, never from a real model: this tool is for local testing, not production.

    uv run --no-sync python tools/seed_demo.py --database data/demo.sqlite3
    SUSIGHT_DATABASE=data/demo.sqlite3 SUSIGHT_API_TOKEN=<16+ chars> \
        uv run --no-sync uvicorn susight.api:create_app --factory --port 8000 --workers 1
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from susight.policy import POLICY_VERSION
from susight.tribunal.guards import validate_queue
from susight.tribunal.models import (
    DocumentInput,
    EvidenceRegistration,
    ProposalInput,
    Vote,
)
from susight.tribunal.service import Tribunal
from susight.tribunal.store import Store

# (solicitacao, paciente, cid, dias em fila, prioridade regulacao): 20 casos, para a trava de 10% permitir subir
CIDS = ["K409", "H259", "K802", "M170"]
PRIORITIES = ["Alta"] * 6 + ["Moderada"] * 8 + ["Baixa"] * 6
PATIENTS = [
    (f"SOL-{1000 + n}", f"PAC-{1000 + n}", CIDS[n % 4], 460 - n * 17, PRIORITIES[n - 1]) for n in range(1, 21)
]
CRITERIA = {"limitacao": 2, "asa": 2, "dor": 6, "comorbidades": 1, "deterioracao": 2, "distancia": 25}

# solicitacao -> (posicao proposta, evidencia (tipo, resultado, trecho), veredito do agente de contestacao)
PROPOSALS = {
    "SOL-1014": (12, ("exame_imagem", "piora", "Raio-X do joelho mostra piora articular."), "contra"),
    "SOL-1016": (14, ("consulta_reavaliacao", "piora", "Consulta registra novas crises de dor."), "a_favor"),
    "SOL-1008": (6, ("consulta_reavaliacao", "piora", "Reavaliacao registra piora do quadro."), "a_favor"),
    "SOL-1010": (
        8,
        ("internacao", "atendimento", "Atendimento de urgencia registrado no periodo."),
        "a_favor",
    ),
}


# Paciente de demonstração do app Pulse: entra com este CPF e este código de 6 dígitos.
APP_PATIENT = ("52998224725", "123456", "PAC-1008", "SOL-1008")


class DemoProvider:
    """Deterministic stand-in for the tribunal agents (local demonstration only)."""

    model = "demo-seed-not-a-real-model"

    async def analyze(self, agent, context):
        text = {
            "evidencias": "As evidencias aprovadas sustentam a piora e apoiam subir a posicao.",
            "contestacao": "O documento mais recente e antigo e o relato isolado nao comprova a mudanca.",
            "equidade": "A mudanca respeita o limite por reavaliacao e a hierarquia da fila.",
        }[agent]
        verdict = "contra" if agent == "contestacao" and context["_demo_contra"] else "a_favor"
        return Vote(
            agente=agent,
            veredito=verdict,
            justificativa=text,
            evidencias_citadas=[e["evidencia_id"] for e in context["evidencias"]],
            sem_comprovacao=verdict == "contra",
        )


def seed(database, password):
    store = Store(database)
    rows = []
    for position, (sid, pid, cid, days, priority) in enumerate(PATIENTS, 1):
        rows.append(
            {
                "politica": POLICY_VERSION,
                "solicitacao_id": sid,
                "paciente_id": pid,
                "cid": cid,
                "dias_em_fila": days,
                "pontuacao": round(1 - position * 0.04, 2),
                "oncologico": False,
                "sem_urgencia": False,
                "posicao": position,
                "justificativa": f"Posicao definida pela pontuacao clinica e pela classe de risco ({priority}).",
                "criterios": CRITERIA,
                "swalis": "C",
                "prioridade_regulacao": priority,
            }
        )
    store.import_queue(validate_queue(rows), 0, "seed-demo")

    store.provision_account("medico-demo", "medico", [p[1] for p in PATIENTS], password)
    store.provision_account("admin-demo", "admin", [], password)

    version, _ = store.queue()
    created = []
    for index, (sid, (target, (kind, result, excerpt), _)) in enumerate(PROPOSALS.items(), 1):
        doc = DocumentInput(
            solicitacao_id=sid,
            sha256=f"{index:064x}",
            tipo_mime="application/pdf",
            paginas=1,
            tamanho_bytes=1000,
            sintetico=True,
        )
        did = store.register_document(doc.model_dump(), "seed-demo")
        evidence_id = f"EVT-{index}"
        registration = EvidenceRegistration(
            evidencia={"evidencia_id": evidence_id, "tipo": kind, "resultado": result, "data": "2026-10-20"},
            documento_id=did,
            pagina=1,
            trecho=excerpt,
            campo="comorbidades",
            valor="Condicao explicitamente documentada",
            confianca="alta",
        )
        eid = store.register_evidence(registration.model_dump(), "seed-demo")
        store.review_evidence(eid, "aprovar", "medico-demo", "Conferido com documento sintetico")
        body = ProposalInput(
            solicitacao_id=sid,
            posicao_proposta=target,
            versao_fila=version,
            ordenacao_incerta=True,
            evidencias=[store.approved_payload(eid, sid)],
        ).model_dump()
        created.append((store.create(body, "medico-demo"), sid))

    demo_contra = {sid for sid, (_, _, v) in PROPOSALS.items() if v == "contra"}
    provider = DemoProvider()
    tribunal = Tribunal(store, provider)

    async def run():
        for pid, sid in created:
            original = provider.analyze

            async def analyze(agent, context, _sid=sid, _original=original):
                return await _original(agent, context | {"_demo_contra": _sid in demo_contra})

            provider.analyze = analyze
            await tribunal.process(pid)
            provider.analyze = original

    asyncio.run(run())

    # O paciente do app: um pedido de exame em aberto e a conta com CPF e codigo de 6 digitos.
    cpf, code, patient_id, sid = APP_PATIENT
    store.provision_account(cpf, "paciente", [patient_id], code)
    pid = next(p for p, s_ in created if s_ == sid)
    exams = [
        {"exame": "Risco cirurgico", "explicacao": "Envie o exame de risco cirurgico recente."},
        {"exame": "Eletrocardiograma", "explicacao": "Exame pre-operatorio."},
    ]
    store.decide(pid, "medico-demo", "pedir_informacoes", "Faltam exames para avaliar a piora.", None, exams)
    return len(rows), len(created)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database", required=True)
    parser.add_argument("--password", default="demo1234")
    args = parser.parse_args()
    path = Path(args.database)
    if path.exists():
        parser.exit(1, f"Erro: {path} ja existe; apague-o para semear de novo\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    patients, proposals = seed(path, args.password)
    print(f"Fila com {patients} pacientes e {proposals} propostas prontas em {path}")
    print("Contas: medico-demo e admin-demo, senha:", args.password)
    print(f"App do paciente: CPF {APP_PATIENT[0]}, codigo {APP_PATIENT[1]}")
