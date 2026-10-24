import logging
import stat

import pytest
from test_history import approved_evidence, ready_proposal

from susight.tribunal.store import Store

PASSWORD = "senha-teste-sintetica-1"


def provision(client):
    store = client.app.state.store
    store.provision_account("PAC20", "paciente", ["PAC20"], PASSWORD)
    store.provision_account("medico.demo", "medico", ["PAC20"], PASSWORD)
    store.provision_account("medico.outro", "medico", ["PAC1"], PASSWORD)


def login(client, identifier, password=PASSWORD):
    client.headers.pop("Authorization", None)
    return client.post("/sessoes", json={"identificador": identifier, "senha": password})


def use(client, token):
    client.headers["Authorization"] = "Bearer " + token


def session(client, identifier):
    response = login(client, identifier)
    assert response.status_code == 200, response.text
    use(client, response.json()["token"])
    return response.json()["token"]


def test_valid_login_for_patient_and_doctor_returns_a_working_session(history_api):
    client, _ = history_api
    provision(client)
    response = login(client, "PAC20")
    assert response.json()["papel"] == "paciente" and response.json()["inatividade_segundos"] == 1800
    use(client, response.json()["token"])
    assert [r["solicitacao_id"] for r in client.get("/fila").json()["pacientes"]] == ["20"]
    session(client, "medico.demo")
    assert [r["solicitacao_id"] for r in client.get("/fila").json()["pacientes"]] == ["20"]


def test_invalid_credentials_do_not_reveal_which_field_is_wrong(history_api):
    client, _ = history_api
    provision(client)
    wrong_password = login(client, "PAC20", "senha-errada-123")
    unknown = login(client, "PAC999")
    assert wrong_password.status_code == unknown.status_code == 401
    assert wrong_password.json() == unknown.json()
    assert "PAC" not in wrong_password.text and "senha-errada" not in wrong_password.text


def test_there_is_no_route_to_create_accounts(history_api):
    client, _ = history_api
    assert client.post("/contas", json={"identificador": "PAC5", "senha": PASSWORD}).status_code in {404, 405}
    assert not [p for p in client.get("/openapi.json").json()["paths"] if p.startswith("/contas")]
    assert login(client, "PAC5").status_code == 401


def test_password_and_session_token_are_stored_only_as_hashes(history_api):
    client, _ = history_api
    provision(client)
    token = login(client, "PAC20").json()["token"]
    with client.app.state.store.db() as db:
        dump = "\n".join(db.iterdump())
        account = dict(db.execute("SELECT * FROM accounts WHERE id='PAC20'").fetchone())
    assert PASSWORD not in dump and token not in dump
    assert account["senha_hash"] and account["sal"] and account["senha_hash"] != PASSWORD


def test_session_expires_after_inactivity_and_each_use_renews_it(history_api):
    client, clock = history_api
    provision(client)
    session(client, "PAC20")
    for _ in range(2):
        clock[0] += 1000
        assert client.get("/fila").status_code == 200
    clock[0] += 1801
    assert client.get("/fila").status_code == 401


def test_logout_ends_the_session_and_removes_devices(history_api):
    client, _ = history_api
    provision(client)
    session(client, "PAC20")
    assert (
        client.post("/dispositivos", json={"plataforma": "ios", "token": "token-sintetico-123"}).status_code
        == 201
    )
    assert client.delete("/sessoes").status_code == 200
    assert client.get("/fila").status_code == 401
    assert client.app.state.store.devices("PAC20") == []


def test_repeated_wrong_passwords_lock_the_account_for_a_while(history_api):
    client, clock = history_api
    provision(client)
    for _ in range(5):
        assert login(client, "PAC20", "senha-errada-123").status_code == 401
    assert login(client, "PAC20").status_code == 429
    clock[0] += 901
    assert login(client, "PAC20").status_code == 200


def test_session_scope_limits_patients_and_professionals(history_api):
    client, _ = history_api
    provision(client)
    approved_evidence(client)
    session(client, "PAC20")
    assert client.get("/solicitacoes/1/historico").status_code == 404
    assert client.get("/solicitacoes/20/historico").status_code == 200
    session(client, "medico.outro")
    assert client.get("/solicitacoes/20/historico").status_code == 404
    assert (
        client.post("/evidencias/E1/revisao", json={"acao": "rejeitar", "justificativa": "Teste"}).status_code
        == 404
    )


def test_decision_through_a_session_records_the_authenticated_doctor(history_api):
    client, _ = history_api
    provision(client)
    approved_evidence(client)
    pid = ready_proposal(client)
    session(client, "medico.demo")
    decision = client.post(f"/propostas/{pid}/decisao", json={"medico": "Nome digitado", "acao": "aprovar"})
    assert decision.status_code == 200, decision.text
    events = client.get("/solicitacoes/20/historico").json()["eventos"]
    change = next(e for e in events if e["tipo"] == "posicao_alterada")
    assert change["responsavel"] == "medico.demo"


def test_identifier_and_password_never_reach_the_logs(history_api, caplog):
    client, _ = history_api
    provision(client)
    caplog.set_level(logging.DEBUG)
    login(client, "PAC20")
    login(client, "PAC20", "senha-errada-123")
    assert (
        PASSWORD not in caplog.text and "senha-errada-123" not in caplog.text and "PAC20" not in caplog.text
    )


def test_command_line_creates_account_with_password_only_in_a_private_file(tmp_path):
    from susight import accounts

    database = tmp_path / "db.sqlite"
    secret = tmp_path / "PAC7.senha"
    accounts.create(database, "PAC7", "paciente", ["PAC7"], secret)
    assert stat.S_IMODE(secret.stat().st_mode) == 0o600
    password = secret.read_text().strip()
    assert len(password) >= 16
    assert Store(database).login("PAC7", password)["papel"] == "paciente"
    with pytest.raises(ValueError):
        accounts.create(database, "PAC7", "paciente", ["PAC7"], tmp_path / "outro.senha")
    with pytest.raises((ValueError, FileExistsError)):
        accounts.create(database, "PAC8", "paciente", ["PAC8"], secret)
