from test_access_retention import document, evidence
from test_history import approved_evidence, as_user, decide, kinds, ready_proposal

EXAMS = [{"exame": "Raio X do joelho", "explicacao": "Comparar com o exame anterior"}, {"exame": "Hemograma"}]


def requests(client, sid="20"):
    return client.get(f"/solicitacoes/{sid}/exames-pedidos")


def ask(client):
    approved_evidence(client)
    decide(client, ready_proposal(client), "pedir_informacoes", "Faltam exames recentes", EXAMS)
    as_user(client, "patient")
    return requests(client).json()


def linked_document(client, pedido_id, sid="20"):
    return client.post(
        "/documentos",
        json={
            "solicitacao_id": sid,
            "sha256": "b" * 64,
            "tipo_mime": "application/pdf",
            "paginas": 1,
            "tamanho_bytes": 100,
            "pedido_id": pedido_id,
        },
    )


def test_asking_for_information_creates_pending_requests_with_author_and_time(history_api):
    client, _ = history_api
    body = ask(client)
    assert body["pendentes"] == 2
    by_name = {p["exame"]: p for p in body["pedidos"]}
    assert set(by_name) == {"Raio X do joelho", "Hemograma"}
    assert by_name["Raio X do joelho"]["explicacao"] == "Comparar com o exame anterior"
    for item in body["pedidos"]:
        assert item["situacao"] == "pendente"
        assert item["responsavel"] == "doctor"
        assert item["data_hora"].startswith("2027-")
        assert item["pedido_id"]


def test_asking_for_information_does_not_change_the_queue(history_api):
    client, _ = history_api
    as_user(client, "admin")
    before = [(r["solicitacao_id"], r["posicao"]) for r in client.get("/fila").json()["pacientes"]]
    ask(client)
    as_user(client, "admin")
    assert [(r["solicitacao_id"], r["posicao"]) for r in client.get("/fila").json()["pacientes"]] == before


def test_requested_exam_goes_received_then_in_analysis_then_answered(history_api):
    client, _ = history_api
    pedido = ask(client)["pedidos"][0]["pedido_id"]
    as_user(client, "patient")
    did = linked_document(client, pedido).json()["documento_id"]
    situation = {p["pedido_id"]: p["situacao"] for p in requests(client).json()["pedidos"]}
    assert situation[pedido] == "recebido"
    assert requests(client).json()["pendentes"] == 1
    assert "exame_recebido" in kinds(client)
    assert evidence(client, did, eid="E2").status_code == 201
    situation = {p["pedido_id"]: p["situacao"] for p in requests(client).json()["pedidos"]}
    assert situation[pedido] == "em_analise"
    as_user(client, "doctor")
    review = client.post("/evidencias/E2/revisao", json={"acao": "aprovar", "justificativa": "Conferido"})
    assert review.status_code == 200
    situation = {p["pedido_id"]: p["situacao"] for p in requests(client).json()["pedidos"]}
    assert situation[pedido] == "atendido"


def test_requests_are_visible_only_to_the_patient_and_authorized_professional(history_api):
    client, _ = history_api
    ask(client)
    for name in ["other_patient", "other"]:
        as_user(client, name)
        assert requests(client).status_code == 404
    as_user(client, "doctor")
    assert requests(client).json()["pendentes"] == 2


def test_document_cannot_link_to_another_case_or_an_answered_request(history_api):
    client, _ = history_api
    pedido = ask(client)["pedidos"][0]["pedido_id"]
    as_user(client, "admin")
    assert linked_document(client, pedido, sid="1").status_code == 422
    as_user(client, "patient")
    assert linked_document(client, "inexistente").status_code == 422
    assert linked_document(client, pedido).status_code == 201
    assert linked_document(client, pedido).status_code == 422


def test_asking_requires_exams_and_other_decisions_refuse_them(history_api):
    client, _ = history_api
    approved_evidence(client)
    pid = ready_proposal(client)
    as_user(client, "doctor")
    no_exam = {"medico": "Dra Teste", "acao": "pedir_informacoes", "motivo": "Faltam dados", "exames": []}
    assert client.post(f"/propostas/{pid}/decisao", json=no_exam).status_code == 422
    with_exam = {"medico": "Dra Teste", "acao": "rejeitar", "motivo": "Nao sobe", "exames": EXAMS}
    assert client.post(f"/propostas/{pid}/decisao", json=with_exam).status_code == 422


def test_requests_have_no_route_to_be_changed_by_hand(history_api):
    client, _ = history_api
    ask(client)
    as_user(client, "doctor")
    assert client.patch("/solicitacoes/20/exames-pedidos", json={"situacao": "atendido"}).status_code == 405
    assert requests(client).json()["pendentes"] == 2


def test_document_without_request_keeps_working(history_api):
    client, _ = history_api
    as_user(client, "patient")
    assert document(client).status_code == 201
