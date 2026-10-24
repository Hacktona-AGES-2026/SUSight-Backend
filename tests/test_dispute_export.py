import csv
import io

from test_history import approved_evidence, as_user, current, history, kinds, ready_proposal
from test_tribunal import proposal_reference

TRICKY = 'Dor forte, piora "documentada"\nem duas consultas'


def contest(client, reason="Exame novo sugere piora", sid="20"):
    return client.post(f"/solicitacoes/{sid}/contestacao", json={"motivo": reason})


def conclude(client, justification="Posicao mantida apos revisao", sid="20"):
    return client.post(f"/solicitacoes/{sid}/contestacao/conclusao", json={"justificativa": justification})


def flags(client):
    as_user(client, "admin")
    return {r["solicitacao_id"]: r["em_reavaliacao"] for r in client.get("/fila").json()["pacientes"]}


def positions(client):
    as_user(client, "admin")
    return [(r["solicitacao_id"], r["posicao"]) for r in client.get("/fila").json()["pacientes"]]


def export(client):
    response = client.get("/fila/exportacao.csv")
    rows = list(csv.reader(io.StringIO(response.text))) if response.status_code == 200 else None
    return response, rows


def test_contest_is_recorded_with_reason_author_and_time_and_keeps_the_queue(history_api):
    client, _ = history_api
    before = positions(client)
    as_user(client, "doctor")
    assert contest(client).status_code == 201
    assert positions(client) == before
    as_user(client, "doctor")
    event = next(e for e in history(client).json()["eventos"] if e["tipo"] == "contestacao")
    assert event["motivo"] == "Exame novo sugere piora"
    assert event["responsavel"] == "doctor" and event["data_hora"].startswith("2027-")


def test_contested_request_is_flagged_and_cannot_be_contested_twice(history_api):
    client, _ = history_api
    as_user(client, "doctor")
    contest(client)
    status = flags(client)
    assert status["20"] is True and status["1"] is False
    as_user(client, "doctor")
    assert contest(client, "Segunda contestacao").status_code == 409


def test_new_proposal_concludes_the_reevaluation(history_api):
    client, _ = history_api
    approved_evidence(client)
    contest(client)
    ready_proposal(client)
    assert flags(client)["20"] is False
    as_user(client, "doctor")
    assert "reavaliacao_concluida" in kinds(client)
    assert contest(client, "Nova contestacao depois da conclusao").status_code == 201


def test_manual_conclusion_requires_justification_and_records_kept_position(history_api):
    client, _ = history_api
    as_user(client, "doctor")
    contest(client)
    assert conclude(client, "").status_code == 422
    assert conclude(client).status_code == 200
    assert flags(client)["20"] is False
    as_user(client, "doctor")
    event = next(e for e in history(client).json()["eventos"] if e["tipo"] == "reavaliacao_concluida")
    assert event["motivo"] == "Posicao mantida apos revisao"
    assert "mantida" in event["texto"].lower()
    assert conclude(client).status_code == 409


def test_contest_and_export_require_authentication_and_permission(history_api):
    client, _ = history_api
    as_user(client, "patient")
    assert contest(client).status_code == 403
    assert export(client)[0].status_code == 403
    del client.headers["Authorization"]
    assert contest(client).status_code == 401
    assert export(client)[0].status_code == 401


def test_admin_export_follows_the_queue_and_is_logged_without_content(history_api):
    client, _ = history_api
    as_user(client, "admin")
    response, rows = export(client)
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    assert rows[0] == ["solicitacao_id", "posicao", "justificativa"]
    assert [(r[0], int(r[1])) for r in rows[1:]] == positions(client)
    with client.app.state.store.db() as db:
        log = [dict(r) for r in db.execute("SELECT * FROM exports")]
    assert len(log) == 1
    assert log[0]["actor"] == "admin" and log[0]["linhas"] == 20 and log[0]["versao_fila"] == current(client)
    assert log[0]["created_at"].startswith("2027-")
    assert set(log[0]) == {"id", "actor", "created_at", "versao_fila", "linhas"}


def test_export_keeps_columns_with_commas_quotes_and_newlines(history_api):
    client, _ = history_api
    as_user(client, "admin")
    rows = client.get("/fila").json()["pacientes"]
    for row in rows:
        row.pop("em_reavaliacao", None)
        row["justificativa"] = TRICKY if row["solicitacao_id"] == "20" else "Criterios principais: dor."
    assert (
        client.put("/fila", json={"versao_esperada": current(client), "pacientes": rows}).status_code == 200
    )
    _, exported = export(client)
    assert all(len(r) == 3 for r in exported)
    assert next(r for r in exported if r[0] == "20")[2] == TRICKY


def test_export_ignores_proposals_not_yet_approved(history_api):
    client, _ = history_api
    approved_evidence(client)
    ready_proposal(client)
    as_user(client, "admin")
    _, rows = export(client)
    assert [(r[0], int(r[1])) for r in rows[1:]] == positions(client)
    assert ("20", 20) in positions(client)


def test_doctor_exports_the_whole_queue(history_api):
    client, _ = history_api
    as_user(client, "doctor")
    response, rows = export(client)
    assert response.status_code == 200
    assert len(rows) - 1 == 20


def test_proposal_reference_still_creates_proposals_without_contest(history_api):
    client, _ = history_api
    approved_evidence(client)
    as_user(client, "doctor")
    response = client.post("/propostas", json=proposal_reference() | {"versao_fila": current(client)})
    assert response.status_code == 201
