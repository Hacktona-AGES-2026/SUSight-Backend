import hashlib
import json
import sqlite3

import pytest
from conftest import approve_in_store
from fastapi.testclient import TestClient
from test_tribunal import FakeProvider, proposal, proposal_reference, queue

from susight.access import Access
from susight.api import create_app
from susight.artifacts import TTL, protect, purge_artifacts, retention
from susight.tribunal.service import Tribunal
from susight.tribunal.store import Store


@pytest.fixture
def clock():
    return [1800000000.0]


@pytest.fixture
def api(tmp_path, clock):
    principals = [
        {
            "id": name,
            "papel": role,
            "pacientes": scope,
            "token_sha256": hashlib.sha256(name.encode()).hexdigest(),
        }
        for name, role, scope in [
            ("admin", "admin", []),
            ("doctor", "medico", ["PAC20"]),
            ("patient", "paciente", ["PAC20"]),
            ("other", "medico", ["PAC1"]),
            ("other_patient", "paciente", ["PAC1"]),
        ]
    ]
    app = create_app(
        tmp_path / "db.sqlite",
        FakeProvider(),
        access=Access(entries=principals),
        clock=lambda: clock[0],
        start_worker=False,
    )
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer admin"
        rows = queue()
        for row in rows:
            row["paciente_id"] = "PAC" + row["solicitacao_id"]
        assert client.put("/fila", json={"versao_esperada": 0, "pacientes": rows}).status_code == 200
        yield client, app


def document(client, sid="20"):
    return client.post(
        "/documentos",
        json={
            "solicitacao_id": sid,
            "sha256": "a" * 64,
            "tipo_mime": "application/pdf",
            "paginas": 1,
            "tamanho_bytes": 100,
        },
    )


def evidence(client, did, eid="E1", value="Condicao registrada", confidence="alta"):
    return client.post(
        "/evidencias",
        json={
            "evidencia": {
                "evidencia_id": eid,
                "tipo": "biopsia",
                "resultado": "positivo",
                "data": "2026-10-01",
            },
            "documento_id": did,
            "pagina": 1,
            "trecho": "Resultado explicitamente descrito no documento sintetico.",
            "campo": "comorbidades",
            "valor": value,
            "confianca": confidence,
        },
    )


def test_patient_and_professional_scopes_and_no_self_approval(api):
    client, app = api
    client.headers["Authorization"] = "Bearer patient"
    own = client.get("/fila").json()["pacientes"]
    assert len(own) == 1 and own[0]["solicitacao_id"] == "20"
    assert document(client, "1").status_code == 404
    did = document(client).json()["documento_id"]
    assert evidence(client, did).status_code == 201
    assert (
        client.post("/evidencias/E1/revisao", json={"acao": "aprovar", "justificativa": "Teste"}).status_code
        == 403
    )
    assert client.post("/propostas", json=proposal_reference()).status_code == 403
    assert client.put("/fila", json={"versao_esperada": 1, "pacientes": queue()}).status_code == 403
    client.headers["Authorization"] = "Bearer other"
    # One shared queue: every doctor sees every case.
    assert client.get("/documentos/" + did).status_code == 200
    assert client.get("/evidencias/E1").status_code == 200
    client.headers["Authorization"] = "Bearer doctor"
    assert client.post("/propostas", json=proposal_reference()).status_code == 422
    approved = client.post(
        "/evidencias/E1/revisao", json={"acao": "aprovar", "justificativa": "Conferido no documento"}
    )
    assert approved.status_code == 200
    record = client.get("/evidencias/E1").json()
    assert record["revisor"] == "doctor" and record["revisado_em"]
    pid = client.post("/propostas", json=proposal_reference()).json()["proposta_id"]
    client.headers["Authorization"] = "Bearer patient"
    assert client.get(f"/propostas/{pid}/parecer").status_code == 403
    client.headers["Authorization"] = "Bearer other"
    assert client.get(f"/propostas/{pid}/parecer").status_code == 200
    client.headers["Authorization"] = "Bearer doctor"
    client.post(f"/propostas/{pid}/tribunal")
    decision = client.post(
        f"/propostas/{pid}/decisao", json={"medico": "Nome informado pelo cliente", "acao": "aprovar"}
    )
    assert decision.status_code == 200
    with app.state.store.db() as db:
        assert db.execute("SELECT actor FROM decisions").fetchone()[0] == "doctor"


def test_registry_refuses_unapproved_changed_and_other_case_evidence(api):
    client, app = api
    eid, _did = approve_in_store(app.state.store)
    body = proposal()
    body["evidencias"][0]["resultado"] = "negativo"
    with pytest.raises(ValueError, match="difere"):
        app.state.store.create(body)
    assert client.post("/propostas", json=body).status_code == 422  # inline claims forbidden
    body = proposal_reference()
    body["solicitacao_id"] = "1"
    assert client.post("/propostas", json=body).status_code == 422
    with pytest.raises(ValueError, match="ja registrado"):
        doc = app.state.store.evidence(eid)["body"]
        app.state.store.register_evidence(doc, "uploader")
    assert (
        client.post(
            "/evidencias/E1/revisao", json={"acao": "rejeitar", "justificativa": "Nova decisao"}
        ).status_code
        == 409
    )


def test_low_confidence_and_absent_not_promoted_by_review(api):
    client, _ = api
    did = document(client).json()["documento_id"]
    assert evidence(client, did, value=None, confidence="baixa").status_code == 201
    assert (
        client.post("/evidencias/E1/revisao", json={"acao": "aprovar", "justificativa": "Teste"}).status_code
        == 409
    )
    assert client.post("/propostas", json=proposal_reference()).status_code == 422


def test_expiry_removes_content_dependencies_and_stops_retries(api, clock):
    client, app = api
    approve_in_store(app.state.store)
    pid = client.post("/propostas", json=proposal_reference()).json()["proposta_id"]
    client.post(f"/propostas/{pid}/tribunal")
    clock[0] += TTL + 1
    assert client.get(f"/propostas/{pid}/parecer").status_code == 404
    assert app.state.store.due() == []
    assert client.get("/evidencias/E1").status_code == 404
    assert client.get("/fila").json()["pacientes"] == []
    with app.state.store.db() as db:
        for table in ["evidence", "documents", "proposals", "decisions", "queues"]:
            assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert client.put("/fila", json={"versao_esperada": 0, "pacientes": queue()}).status_code == 409


async def test_expiry_during_agent_call_cannot_publish_or_restart(tmp_path, clock):
    store = Store(tmp_path / "expiry.sqlite", clock=lambda: clock[0])
    store.import_queue(queue(), 0)
    approve_in_store(store)
    pid = store.create(proposal())

    class Expiring(FakeProvider):
        async def analyze(self, agent, context):
            vote = await super().analyze(agent, context)
            clock[0] += TTL + 1
            return vote

    result = await Tribunal(store, Expiring()).process(pid)
    assert result["status"] == "expirada"
    assert store.due() == []
    with pytest.raises(KeyError):
        store.get(pid)


def test_artifact_cleanup_preserves_sources_unmarked_dirs_and_symlink_targets(tmp_path):
    root = tmp_path / "outputs"
    root.mkdir()
    old = root / "old"
    old.mkdir()
    (old / "manifesto.json").write_text(json.dumps(retention(now=100)))
    (old / "dados.json").write_text("dados sinteticos")
    protect(old)
    fresh = root / "fresh"
    fresh.mkdir()
    (fresh / "manifesto.json").write_text(json.dumps(retention(now=100 + TTL)))
    source = root / "source"
    source.mkdir()
    (source / "manifesto.json").write_text(json.dumps(retention(now=100)))
    (source / "fila_cirurgica.csv").write_text("original")
    external = tmp_path / "external"
    external.mkdir()
    (root / "link").symlink_to(external, target_is_directory=True)
    plain = root / "plain"
    plain.mkdir()
    assert purge_artifacts(root, now=100 + TTL + 1) == ["old"]
    assert source.exists() and fresh.exists() and plain.exists() and external.exists()


def test_legacy_schema_expires_unverifiable_content(tmp_path, clock):
    path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE queues(version INTEGER PRIMARY KEY,body TEXT NOT NULL)")
        db.execute("INSERT INTO queues VALUES (?,?)", (4, json.dumps(queue())))
    store = Store(path, clock=lambda: clock[0])
    assert store.queue() == (4, [])
    assert store.import_queue(queue(), 4) == 5


async def test_cancellation_while_agents_run_does_not_resurrect_proposal(tmp_path, clock):
    store = Store(tmp_path / "cancel.sqlite", clock=lambda: clock[0])
    store.import_queue(queue(), 0)
    approve_in_store(store)
    pid = store.create(proposal())

    class Cancelling(FakeProvider):
        async def analyze(self, agent, context):
            result = await super().analyze(agent, context)
            if agent == "evidencias":
                store.cancel(pid, "doctor", "Analise encerrada pelo responsavel")
            return result

    result = await Tribunal(store, Cancelling()).process(pid)
    assert result["status"] == "cancelada" and result["opinion"] is None
    assert store.due() == []


def test_all_report_files_are_owner_only(dataset, tmp_path):
    from susight.dataset import treat

    source = dataset()
    dest = tmp_path / "out"
    treat(source, dest)
    assert dest.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in dest.iterdir())


def test_identity_configuration_rejects_invalid_role_and_multiple_patient_scope():
    digest = hashlib.sha256(b"test").hexdigest()
    with pytest.raises(ValueError):
        Access(entries=[{"id": "u", "papel": "paciente", "pacientes": ["A", "B"], "token_sha256": digest}])
    with pytest.raises(ValueError):
        Access(entries=[{"id": "u", "papel": "superuser", "pacientes": [], "token_sha256": digest}])


def test_cancel_endpoint_authorizes_case_and_stops_pending_work(api):
    client, app = api
    approve_in_store(app.state.store)
    pid = client.post("/propostas", json=proposal_reference()).json()["proposta_id"]
    client.headers["Authorization"] = "Bearer patient"
    assert (
        client.post(
            f"/propostas/{pid}/cancelar", json={"justificativa": "Solicitado cancelamento"}
        ).status_code
        == 403
    )
    client.headers["Authorization"] = "Bearer doctor"
    assert (
        client.post(
            f"/propostas/{pid}/cancelar", json={"justificativa": "Caso encerrado pelo responsavel"}
        ).status_code
        == 200
    )
    assert app.state.store.due() == []
    assert client.post(f"/propostas/{pid}/tribunal").json()["situacao"] == "cancelada"


async def test_vote_without_evidence_reference_is_not_published(tmp_path):
    store = Store(tmp_path / "no-citation.sqlite")
    store.import_queue(queue(), 0)
    approve_in_store(store)
    pid = store.create(proposal())

    class NoCitation(FakeProvider):
        async def analyze(self, agent, context):
            result = await super().analyze(agent, context)
            result.evidencias_citadas = []
            return result

    result = await Tribunal(store, NoCitation()).process(pid)
    assert result["status"] == "aguardando_tribunal" and result["opinion"] is None


def test_individual_token_provisioning_has_scopes_permissions_and_no_overwrite(tmp_path):
    from susight.provision import provision

    directory = tmp_path / "identities"
    path = provision(directory, "PAC20")
    config = json.loads(path.read_text())
    access = Access(entries=config["identidades"])
    for uid in ["admin-demo", "medico-demo", "paciente-demo"]:
        token_file = directory / (uid + ".token")
        token = token_file.read_text().strip()
        assert token_file.stat().st_mode & 0o777 == 0o600
        assert token not in path.read_text()
        assert access.resolve("Bearer " + token).id == uid
    assert access.resolve("Bearer invalid") is None
    with pytest.raises(ValueError, match="existente"):
        provision(directory, "PAC2")


def test_document_registration_enforces_input_limits(api):
    client, _ = api
    base = {
        "solicitacao_id": "20",
        "sha256": "a" * 64,
        "tipo_mime": "application/pdf",
        "paginas": 1,
        "tamanho_bytes": 100,
    }
    for change in [
        {"paginas": 11},
        {"tamanho_bytes": 10 * 1024 * 1024 + 1},
        {"tipo_mime": "image/png", "paginas": 2},
    ]:
        assert client.post("/documentos", json=base | change).status_code == 422
