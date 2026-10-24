import asyncio
import json

import pytest
from conftest import approve_in_store, register_http_evidence
from fastapi.testclient import TestClient

from susight.api import create_app
from susight.policy import POLICY_VERSION
from susight.tribunal.guards import guard, validate_queue
from susight.tribunal.models import ProposalInput, Vote
from susight.tribunal.service import Tribunal, consolidate_votes
from susight.tribunal.store import Store

TOKEN = "test-token-susight-123456"


def queue(n=20):
    return [
        {
            "politica": POLICY_VERSION,
            "solicitacao_id": str(i),
            "cid": "K409",
            "dias_em_fila": 100,
            "pontuacao": 0.5,
            "oncologico": False,
            "sem_urgencia": False,
            "posicao": i,
        }
        for i in range(1, n + 1)
    ]


def proposal(version=1):
    return ProposalInput(
        solicitacao_id="20",
        posicao_proposta=18,
        versao_fila=version,
        ordenacao_incerta=True,
        evidencias=[{"evidencia_id": "E1", "tipo": "biopsia", "resultado": "positivo", "data": "2026-10-01"}],
    ).model_dump()


def vote(agent, verdict="a_favor", position=None):
    return Vote(
        agente=agent,
        veredito=verdict,
        posicao_sugerida=position,
        justificativa="As evidencias registradas sustentam este parecer.",
        evidencias_citadas=["E1"],
        sem_comprovacao=False,
    )


class FakeProvider:
    model = "fake-for-tests-only"

    def __init__(self, fail=False, verdicts=None):
        self.fail = fail
        self.verdicts = verdicts or {}
        self.contexts = []
        self.active = 0
        self.maximum = 0

    async def analyze(self, agent, context):
        self.contexts.append(context)
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        try:
            await asyncio.sleep(0.005)
            if self.fail:
                raise RuntimeError("external failure")
            result = vote(agent, self.verdicts.get(agent, "a_favor"))
            result.evidencias_citadas = [e["evidencia_id"] for e in context["evidencias"]]
            return result
        finally:
            self.active -= 1


@pytest.fixture
def setup(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    store.import_queue(validate_queue(queue()), 0)
    approve_in_store(store)
    return store


def test_guards_limit_no_wait_dominance_and_gold():
    rows = queue()
    assert guard(rows, "20", 1)["posicao"] == 18
    rows[18]["pontuacao"] = 0.8
    rows[18]["dias_em_fila"] = 200
    assert guard(rows, "20", 18)["liberada"]
    rows = queue()
    for row in rows[:-1]:
        row["sem_urgencia"] = True
    rows[-1]["oncologico"] = True
    rows[-1]["cid"] = "C509"
    result = guard(rows, "20", 1)
    assert result["liberada"] and result["posicao"] == 1
    assert "regra_de_ouro_prevalece" in result["travas"]
    rows = queue()
    rows[0]["oncologico"] = True
    rows[0]["cid"] = "C509"
    rows[-1]["sem_urgencia"] = True
    assert not guard(rows, "1", 20)["liberada"]


def test_small_queue_floor_limit_and_invalid_flags():
    assert guard(queue(5), "5", 1)["posicao"] == 5
    rows = queue()
    rows[0]["oncologico"] = True
    with pytest.raises(ValueError):
        validate_queue(rows)


def test_majority_and_three_different_votes():
    result = consolidate_votes([vote("evidencias"), vote("contestacao", "contra"), vote("equidade")])
    assert result["recomendacao"] == "aprovar" and len(result["divergencias"]) == 1
    result = consolidate_votes(
        [vote("evidencias"), vote("contestacao", "contra"), vote("equidade", "ajustar", 19)]
    )
    assert result["recomendacao"] == "ajustar" and len(result["divergencias"]) == 3


async def test_parallel_votes_and_no_automatic_application(setup):
    pid = setup.create(proposal())
    provider = FakeProvider()
    result = await Tribunal(setup, provider).process(pid)
    assert result["status"] == "pronta_para_medico"
    assert provider.maximum == 3
    assert setup.queue()[0] == 1
    context = json.dumps(provider.contexts)
    assert "SOLICITACAO" not in context
    assert "nome_paciente" not in context and "municipio" not in context
    assert result["opinion"]["posicao"] == 18
    again = await Tribunal(setup, provider).process(pid)
    assert again["attempts"] == 1


async def test_failures_persist_warn_and_recover(setup):
    pid = setup.create(proposal())
    service = Tribunal(setup, FakeProvider(fail=True))
    for _ in range(3):
        await service.process(pid)
    assert setup.get(pid)["status"] == "tribunal_indisponivel"
    reopened = Store(setup.path)
    assert reopened.get(pid)["attempts"] == 3
    await Tribunal(reopened, FakeProvider()).process(pid)
    assert reopened.get(pid)["status"] == "pronta_para_medico"
    assert reopened.get(pid)["attempts"] == 4


async def test_report_only_cannot_get_evidence_support(setup):
    body = proposal()
    body["evidencias"] = [
        {"evidencia_id": "E2", "tipo": "relato", "resultado": "relatado", "data": "2026-10-01"}
    ]
    approve_in_store(setup, body["evidencias"][0])
    pid = setup.create(body)
    result = await Tribunal(setup, FakeProvider()).process(pid)
    votes = result["opinion"]["manifestacoes"]
    assert votes[0]["veredito"] == "contra"
    assert all(v["sem_comprovacao"] for v in votes)


async def test_timeout_invalid_role_citation_and_stale_queue(setup):
    class Invalid(FakeProvider):
        async def analyze(self, agent, context):
            v = vote(agent)
            v.evidencias_citadas = ["made-up"]
            return v

    pid = setup.create(proposal())
    assert (await Tribunal(setup, Invalid()).process(pid))["status"] == "aguardando_tribunal"
    setup.import_queue(queue(), 1)
    assert (await Tribunal(setup, FakeProvider()).process(pid))["status"] == "desatualizada"
    pid = setup.create(proposal(2))
    assert (await Tribunal(setup, FakeProvider(), timeout=0.00001).process(pid))[
        "status"
    ] == "aguardando_tribunal"


def test_http_decision_auth_version_and_audit(tmp_path):
    app = create_app(tmp_path / "api.sqlite", FakeProvider(), TOKEN, start_worker=False)
    with TestClient(app) as client:
        assert client.get("/fila").status_code == 401
        client.headers["Authorization"] = "Bearer " + TOKEN
        assert client.get("/propostas/missing/parecer").status_code == 404
        assert client.put("/fila", json={"versao_esperada": 0, "pacientes": queue()}).status_code == 200
        register_http_evidence(client)
        response = client.post("/propostas", json=proposal_reference())
        assert response.status_code == 201
        pid = response.json()["proposta_id"]
        assert (
            client.post(
                f"/propostas/{pid}/decisao", json={"medico": "Medico teste", "acao": "aprovar"}
            ).status_code
            == 409
        )
        assert client.post(f"/propostas/{pid}/tribunal").json()["situacao"] == "pronta_para_medico"
        assert (
            client.post(
                f"/propostas/{pid}/decisao", json={"medico": "Medico teste", "acao": "rejeitar"}
            ).status_code
            == 422
        )
        approved = client.post(
            f"/propostas/{pid}/decisao", json={"medico": "Medico teste", "acao": "aprovar"}
        )
        assert approved.status_code == 200
        assert approved.json()["versao_fila"] == 2
        current = client.get("/fila").json()
        assert current["pacientes"][17]["solicitacao_id"] == "20"
        assert (
            client.post(
                f"/propostas/{pid}/decisao", json={"medico": "Medico teste", "acao": "aprovar"}
            ).status_code
            == 409
        )
        with app.state.store.db() as db:
            decision = dict(db.execute("SELECT * FROM decisions").fetchone())
        assert decision["actor"] == "admin-demo" and decision["created_at"]
        assert client.post("/propostas", json=proposal_reference()).status_code == 409


def test_no_unconfigured_authenticated_api(tmp_path):
    app = create_app(tmp_path / "no.sqlite", FakeProvider(), token="", start_worker=False)
    with pytest.raises(RuntimeError, match="SUSIGHT_API_TOKEN"), TestClient(app):
        pass


async def test_invalid_adjustment_is_guarded_again(setup):
    class Adjust(FakeProvider):
        async def analyze(self, agent, context):
            result = vote(agent, "ajustar", 1)
            result.evidencias_citadas = [e["evidencia_id"] for e in context["evidencias"]]
            return result

    pid = setup.create(proposal())
    result = await Tribunal(setup, Adjust()).process(pid)
    assert result["opinion"]["posicao"] == 18
    assert "limite_elevacao_10_porcento" in result["opinion"]["travas"]


async def test_restart_recovers_interrupted_claim(setup):
    pid = setup.create(proposal())
    assert setup.claim(pid)
    reopened = Store(setup.path)
    assert reopened.get(pid)["status"] == "aguardando_tribunal"
    assert (await Tribunal(reopened, FakeProvider()).process(pid))["status"] == "pronta_para_medico"


def test_doctor_can_disagree_with_consultative_opinion(tmp_path):
    provider = FakeProvider(verdicts={a: "contra" for a in ["evidencias", "contestacao", "equidade"]})
    app = create_app(tmp_path / "override.sqlite", provider, TOKEN, start_worker=False)
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + TOKEN
        client.put("/fila", json={"versao_esperada": 0, "pacientes": queue()})
        register_http_evidence(client)
        pid = client.post("/propostas", json=proposal_reference()).json()["proposta_id"]
        client.post(f"/propostas/{pid}/tribunal")
        path = f"/propostas/{pid}/decisao"
        assert client.post(path, json={"medico": "Medico teste", "acao": "aprovar"}).status_code == 422
        response = client.post(
            path,
            json={
                "medico": "Medico teste",
                "acao": "aprovar",
                "motivo": "Revisao medica independente das evidencias.",
            },
        )
        assert response.status_code == 200


def test_masking_is_allowlisted_and_hashes_identifiers():
    from susight.tribunal.service import masked_context

    body = proposal()
    body["nome_paciente"] = "Nome que nao pode sair"
    body["municipio"] = "Municipio que nao pode sair"
    body["evidencias"][0]["evidencia_id"] = "Nome identificador sensivel"
    context = masked_context(body, queue(), {"posicao": 18, "travas": []})
    text = json.dumps(context)
    assert "Nome" not in text and "Municipio" not in text
    assert context["paciente"]["paciente"] != "20"


def test_blank_medical_name_rejected():
    from susight.api import Decision

    with pytest.raises(ValueError):
        Decision(medico="   ", acao="aprovar")


def proposal_reference():
    body = proposal()
    body["evidencias_ids"] = [e["evidencia_id"] for e in body.pop("evidencias")]
    return body
