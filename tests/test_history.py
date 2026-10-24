import json

from test_access_retention import document, evidence
from test_tribunal import proposal_reference

from susight.artifacts import TTL


def as_user(client, name):
    client.headers["Authorization"] = "Bearer " + name


def history(client, sid="20"):
    return client.get(f"/solicitacoes/{sid}/historico")


def approved_evidence(client):
    as_user(client, "doctor")
    did = document(client).json()["documento_id"]
    assert evidence(client, did).status_code == 201
    review = client.post("/evidencias/E1/revisao", json={"acao": "aprovar", "justificativa": "Conferido"})
    assert review.status_code == 200
    return did


def ready_proposal(client):
    as_user(client, "doctor")
    pid = client.post("/propostas", json=proposal_reference() | {"versao_fila": current(client)}).json()[
        "proposta_id"
    ]
    assert client.post(f"/propostas/{pid}/tribunal").json()["situacao"] == "pronta_para_medico"
    return pid


def current(client):
    return client.get("/fila").json()["versao"]


def decide(client, pid, action, reason="", exams=None):
    body = {"medico": "Dra Teste", "acao": action, "motivo": reason}
    if action == "pedir_informacoes":
        body["exames"] = exams or [{"exame": "Exame de imagem recente"}]
    response = client.post(f"/propostas/{pid}/decisao", json=body)
    assert response.status_code == 200, response.text
    return response


def kinds(client, sid="20"):
    return [e["tipo"] for e in history(client, sid).json()["eventos"]]


def test_queue_entry_is_recorded_once_even_after_reimport(history_api):
    client, _ = history_api
    as_user(client, "admin")
    rows = client.get("/fila").json()["pacientes"]
    assert client.put("/fila", json={"versao_esperada": 1, "pacientes": rows}).status_code == 200
    as_user(client, "patient")
    assert kinds(client) == ["entrada_na_fila"]


def test_document_received_event_survives_document_expiry_without_content(history_api):
    client, clock = history_api
    did = approved_evidence(client)
    clock[0] += TTL + 1
    assert client.get("/documentos/" + did).status_code == 404
    as_user(client, "patient")
    response = history(client)
    assert response.status_code == 200
    assert "documento_recebido" in kinds(client)
    text = json.dumps(response.json(), ensure_ascii=False)
    assert "a" * 64 not in text and "Resultado explicitamente descrito" not in text and did not in text


def test_every_decision_is_recorded_with_type_reason_actor_and_time(history_api):
    client, _ = history_api
    approved_evidence(client)
    decide(client, ready_proposal(client), "rejeitar", "Evidencia insuficiente para subir agora")
    decide(client, ready_proposal(client), "pedir_informacoes", "Enviar exame de imagem recente")
    as_user(client, "doctor")
    pid = client.post("/propostas", json=proposal_reference() | {"versao_fila": current(client)}).json()[
        "proposta_id"
    ]
    cancel = client.post(f"/propostas/{pid}/cancelar", json={"justificativa": "Proposta duplicada"})
    assert cancel.status_code == 200
    decide(client, ready_proposal(client), "aprovar")
    events = {e["tipo"]: e for e in history(client).json()["eventos"]}
    assert events["proposta_rejeitada"]["motivo"] == "Evidencia insuficiente para subir agora"
    assert events["informacao_solicitada"]["motivo"] == "Enviar exame de imagem recente"
    assert events["proposta_cancelada"]["motivo"] == "Proposta duplicada"
    assert "posicao_alterada" in events
    for kind in ["proposta_rejeitada", "informacao_solicitada", "proposta_cancelada", "posicao_alterada"]:
        assert events[kind]["responsavel"] == "doctor"
        assert events[kind]["data_hora"].startswith("2027-")
        assert events[kind]["texto"]


def test_approved_change_records_previous_and_new_position(history_api):
    client, _ = history_api
    approved_evidence(client)
    decide(client, ready_proposal(client), "aprovar")
    new = next(r["posicao"] for r in client.get("/fila").json()["pacientes"] if r["solicitacao_id"] == "20")
    change = next(e for e in history(client).json()["eventos"] if e["tipo"] == "posicao_alterada")
    assert new < 20
    assert change["texto"] == f"Posição alterada de 20ª para {new}ª após aprovação médica."


def test_proposal_still_in_analysis_does_not_create_position_change(history_api):
    client, _ = history_api
    approved_evidence(client)
    ready_proposal(client)
    assert "posicao_alterada" not in kinds(client)


def test_history_is_newest_first(history_api):
    client, _ = history_api
    approved_evidence(client)
    events = history(client).json()["eventos"]
    assert [e["tipo"] for e in events] == ["documento_recebido", "entrada_na_fila"]
    assert events[0]["data_hora"] >= events[1]["data_hora"]


def test_history_is_scoped_to_patient_and_authorized_professional(history_api):
    client, _ = history_api
    approved_evidence(client)
    as_user(client, "other_patient")
    assert history(client).status_code == 404
    as_user(client, "other")
    assert history(client).status_code == 200
    as_user(client, "patient")
    assert history(client, "1").status_code == 404
    assert history(client).status_code == 200
    as_user(client, "doctor")
    assert history(client).status_code == 200


def test_history_stays_readable_after_imported_queue_expires(history_api):
    client, clock = history_api
    approved_evidence(client)
    clock[0] += TTL + 1
    as_user(client, "patient")
    assert client.get("/fila").json()["pacientes"] == []
    assert kinds(client) == ["documento_recebido", "entrada_na_fila"]
    as_user(client, "doctor")
    assert history(client).status_code == 200
