import json

from test_access_retention import document, evidence
from test_dispute_export import conclude, contest
from test_exam_requests import EXAMS, linked_document
from test_history import approved_evidence, as_user, decide, ready_proposal

TITLES = {
    "documento_recebido": "Documento recebido",
    "analise_concluida": "Análise do documento concluída",
    "exame_pedido": "Falta um exame",
    "posicao_alterada": "Sua posição mudou",
    "reavaliacao_concluida": "Reavaliação concluída",
    "fila_atualizada": "Fila aprovada e atualizada",
    "paciente_respondeu": "Paciente respondeu ao pedido",
    "proposta_para_revisao": "Nova proposta para revisão",
}
CONTACT = {"nome": "Maria Sintetica", "parentesco": "filha", "telefone": "51999991234"}


def inbox(client):
    return client.get("/notificacoes")


def kinds(client):
    return [n["tipo"] for n in inbox(client).json()["notificacoes"]]


def preferences(client, **values):
    return client.put("/preferencias/notificacoes", json=values)


def test_patient_is_notified_of_each_fact_and_others_are_not(history_api):
    client, _ = history_api
    approved_evidence(client)
    decide(client, ready_proposal(client), "pedir_informacoes", "Faltam exames", EXAMS)
    decide(client, ready_proposal(client), "aprovar")
    contest(client)
    conclude(client)
    as_user(client, "patient")
    got = kinds(client)
    for kind in [
        "documento_recebido",
        "analise_concluida",
        "exame_pedido",
        "posicao_alterada",
        "reavaliacao_concluida",
    ]:
        assert kind in got, kind
    stamps = [n["data_hora"] for n in inbox(client).json()["notificacoes"]]
    assert stamps == sorted(stamps, reverse=True)
    as_user(client, "other_patient")
    assert kinds(client) == []


def test_read_notification_stops_being_new(history_api):
    client, _ = history_api
    as_user(client, "patient")
    document(client)
    body = inbox(client).json()
    assert body["nao_lidas"] == 1 and body["notificacoes"][0]["lida"] is False
    nid = body["notificacoes"][0]["id"]
    assert client.post(f"/notificacoes/{nid}/lida").status_code == 200
    body = inbox(client).json()
    assert body["nao_lidas"] == 0 and body["notificacoes"][0]["lida"] is True


def test_requested_exam_notice_ignores_preferences_but_others_respect_them(history_api):
    client, _ = history_api
    as_user(client, "patient")
    assert (
        preferences(
            client, documento_recebido=False, analise_concluida=False, prioridade_validada=False
        ).status_code
        == 200
    )
    assert client.get("/preferencias/notificacoes").json()["documento_recebido"] is False
    approved_evidence(client)
    decide(client, ready_proposal(client), "pedir_informacoes", "Faltam exames", EXAMS)
    as_user(client, "patient")
    got = kinds(client)
    assert "exame_pedido" in got
    assert "documento_recebido" not in got and "analise_concluida" not in got


def test_requested_exam_notice_cannot_be_turned_off(history_api):
    client, _ = history_api
    as_user(client, "patient")
    assert preferences(client, exame_pedido=False).status_code == 422


def test_contact_phone_is_masked_on_read(history_api):
    client, _ = history_api
    as_user(client, "patient")
    assert client.post("/contatos", json=CONTACT).status_code == 201
    contacts = client.get("/contatos").json()["contatos"]
    assert contacts[0]["nome"] == "Maria Sintetica" and contacts[0]["parentesco"] == "filha"
    assert contacts[0]["telefone"].endswith("1234") and "99999" not in contacts[0]["telefone"]
    assert "51999991234" not in json.dumps(contacts)


def test_patient_cannot_reach_other_patients_notifications_contacts_or_devices(history_api):
    client, _ = history_api
    as_user(client, "patient")
    document(client)
    nid = inbox(client).json()["notificacoes"][0]["id"]
    cid = client.post("/contatos", json=CONTACT).json()["contato_id"]
    did = client.post("/dispositivos", json={"plataforma": "ios", "token": "token-sintetico-123"}).json()[
        "dispositivo_id"
    ]
    as_user(client, "other_patient")
    assert client.post(f"/notificacoes/{nid}/lida").status_code == 404
    assert client.get("/contatos").json()["contatos"] == []
    assert client.delete(f"/contatos/{cid}").status_code == 404
    assert client.get("/dispositivos").json()["dispositivos"] == []
    assert client.delete(f"/dispositivos/{did}").status_code == 404
    as_user(client, "patient")
    assert len(client.get("/contatos").json()["contatos"]) == 1


def test_notifications_carry_only_fixed_texts_without_document_content_or_identifiers(history_api):
    client, _ = history_api
    approved_evidence(client)
    decide(client, ready_proposal(client), "aprovar")
    for name in ["patient", "doctor"]:
        as_user(client, name)
        items = inbox(client).json()["notificacoes"]
        assert items
        text = json.dumps(items, ensure_ascii=False)
        assert (
            "PAC20" not in text and "a" * 64 not in text and "Resultado explicitamente descrito" not in text
        )
        for item in items:
            assert item["titulo"] == TITLES[item["tipo"]]
            assert "diagn" not in item["texto"].lower()


def test_removed_device_is_no_longer_registered(history_api):
    client, _ = history_api
    as_user(client, "patient")
    did = client.post("/dispositivos", json={"plataforma": "ios", "token": "token-sintetico-123"}).json()[
        "dispositivo_id"
    ]
    devices = client.get("/dispositivos").json()["dispositivos"]
    assert [d["dispositivo_id"] for d in devices] == [did]
    assert "token-sintetico-123" not in json.dumps(devices)
    assert client.delete(f"/dispositivos/{did}").status_code == 200
    assert client.get("/dispositivos").json()["dispositivos"] == []


def test_doctor_is_notified_for_own_cases_only(history_api):
    client, _ = history_api
    approved_evidence(client)
    decide(client, ready_proposal(client), "pedir_informacoes", "Faltam exames", EXAMS)
    as_user(client, "patient")
    pedido = client.get("/solicitacoes/20/exames-pedidos").json()["pedidos"][0]["pedido_id"]
    did = linked_document(client, pedido).json()["documento_id"]
    assert evidence(client, did, eid="E2").status_code == 201
    decide(client, ready_proposal(client), "aprovar")
    as_user(client, "doctor")
    got = kinds(client)
    for kind in ["proposta_para_revisao", "paciente_respondeu", "fila_atualizada"]:
        assert kind in got, kind
    assert "documento_recebido" not in got
    as_user(client, "other")
    assert kinds(client) == got


def test_preferences_contacts_and_devices_belong_to_patients(history_api):
    client, _ = history_api
    as_user(client, "doctor")
    assert client.post("/contatos", json=CONTACT).status_code == 403
    assert preferences(client, documento_recebido=False).status_code == 403
