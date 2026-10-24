import base64
import copy
import json
import re

import pytest
from pdfs import JPEG_STUB, PNG_1X1, make_pdf
from test_history import as_user

from susight.artifacts import TTL

REPORT = [
    "LAUDO DE AVALIAÇÃO PRÉ-ANESTÉSICA",
    "Nome: Joana Sintetica da Silva",
    "CNS: 898 0012 3456 7890",
    "Data do exame: 12/09/2026",
    "Classificação ASA: III",
    "Dor: 6 na escala EVA 0-10",
    "Limitação funcional: moderada",
    "Comorbidades: hipertensão arterial; nega diabetes",
    "Joana Sintetica da Silva - CNS 898001234567890",
]


def field(value, quote, confidence="alta", status="presente"):
    return {
        "valor": value,
        "situacao": status,
        "confianca": confidence,
        "evidencias": [{"trecho": quote, "pagina": 1}],
    }


GOOD = {
    "tipo_documento": field("avaliacao_pre_anestesica", "AVALIAÇÃO PRÉ-ANESTÉSICA"),
    "data_documento": field("2026-09-12", "Data do exame: 12/09/2026"),
    "asa": field("III", "Classificação ASA: III"),
    "dor": field({"intensidade": 6, "escala": "EVA 0-10", "descricao": None}, "Dor: 6 na escala EVA 0-10"),
    "limitacao_funcional": field("moderada", "Limitação funcional: moderada"),
    "cid": field("K40.9", "Diagnóstico (CID-10): K40.9"),
    "deterioracao": field("moderada", "Piora moderada durante a espera"),
    "porte": field("medio", "Porte cirúrgico: médio"),
    "comorbidades": field(
        [
            {
                "valor": "hipertensão arterial",
                "confianca": "alta",
                "evidencias": [{"trecho": "hipertensão arterial", "pagina": 1}],
            }
        ],
        "hipertensão arterial",
    ),
}
FIELDS = {
    "cid",
    "deterioracao",
    "porte",
    "limitacao_funcional",
    "asa",
    "dor",
    "socioeconomico",
    "comorbidades",
    "tipo_documento",
    "data_documento",
}


class FakeExtractor:
    def __init__(self, result=None):
        self.result = copy.deepcopy(GOOD if result is None else result)
        self.sent = []

    async def extract(self, pages):
        self.sent.append(pages)
        return copy.deepcopy(self.result)


def b64(data):
    return base64.b64encode(data).decode()


def upload(client, data, mime="application/pdf", **extra):
    term = client.get("/termos/upload").json()["versao"]
    body = {
        "solicitacao_id": "20",
        "tipo_mime": mime,
        "conteudo_base64": b64(data),
        "termo_versao": term,
        "aceite_termo": True,
    }
    return client.post("/documentos/arquivo", json=body | extra)


def extract(client, extractor, pages=None, mime="application/pdf", data=None):
    client.app.state.extractor = extractor
    as_user(client, "patient")
    response = upload(client, data if data is not None else make_pdf(pages or [REPORT]), mime)
    assert response.status_code == 201, response.text
    did = response.json()["documento_id"]
    assert client.post(f"/documentos/{did}/extracao").status_code == 200
    return did, client.get(f"/documentos/{did}/extracao").json()


def count(client, table):
    with client.app.state.store.db() as db:
        return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_term_is_served_and_upload_requires_explicit_acceptance(history_api):
    client, _ = history_api
    as_user(client, "patient")
    term = client.get("/termos/upload").json()
    assert term["versao"] and "finalidade" in term["texto"].lower()
    assert upload(client, make_pdf([REPORT]), aceite_termo=False).status_code == 422
    assert upload(client, make_pdf([REPORT]), termo_versao="versao-antiga").status_code == 422
    assert count(client, "documents") == 0
    assert upload(client, make_pdf([REPORT])).status_code == 201
    with client.app.state.store.db() as db:
        consent = dict(db.execute("SELECT * FROM consents").fetchone())
    assert (
        consent["actor"] == "patient" and consent["termo_versao"] == term["versao"] and consent["accepted_at"]
    )


def test_pdf_and_image_uploads_by_patient_and_doctor_are_linked_to_the_request(history_api):
    client, _ = history_api
    as_user(client, "patient")
    assert upload(client, make_pdf([REPORT])).status_code == 201
    as_user(client, "doctor")
    assert upload(client, PNG_1X1, "image/png").status_code == 201
    assert upload(client, JPEG_STUB, "image/jpeg").status_code == 201
    kinds = [e["tipo"] for e in client.get("/solicitacoes/20/historico").json()["eventos"]]
    assert kinds.count("documento_recebido") == 3


@pytest.mark.parametrize(
    "data, mime",
    [
        (b"", "application/pdf"),
        (PNG_1X1, "application/pdf"),
        (b"%PDF-1.4\n" + b"\0" * (10 * 1024 * 1024), "application/pdf"),
        (make_pdf([["Pagina"]] * 11), "application/pdf"),
        (make_pdf([REPORT], encrypted=True), "application/pdf"),
        (b"%PDF-1.4\nconteudo quebrado", "application/pdf"),
        (b"\0\0\0\x18ftypheic", "image/heic"),
    ],
    ids=[
        "vazio",
        "formato-falso",
        "acima-de-10-mib",
        "mais-de-10-paginas",
        "protegido",
        "corrompido",
        "heic",
    ],
)
def test_invalid_files_are_rejected_with_guidance_and_nothing_is_stored(history_api, data, mime):
    client, _ = history_api
    as_user(client, "patient")
    response = upload(client, data, mime)
    assert response.status_code == 422
    assert response.json()["detail"]
    assert count(client, "documents") == 0 and count(client, "document_files") == 0


def test_extraction_always_returns_the_ten_fields_and_absent_is_null(history_api):
    client, _ = history_api
    _, result = extract(client, FakeExtractor())
    assert result["situacao"] == "extraido"
    assert set(result["campos"]) == FIELDS
    absent = result["campos"]["socioeconomico"]
    assert absent["valor_extraido"] is None and absent["situacao"] == "ausente"
    assert absent["confianca"] is None and absent["evidencias"] == []
    assert result["campos"]["asa"]["valor_extraido"] == "III"
    assert result["campos"]["data_documento"]["valor_extraido"] == "2026-09-12"


def test_value_without_evidence_found_in_the_document_becomes_null_for_review(history_api):
    client, _ = history_api
    bad = copy.deepcopy(GOOD) | {"asa": field("II", "ASA II registrada no prontuario")}
    _, result = extract(client, FakeExtractor(bad))
    asa = result["campos"]["asa"]
    assert asa["valor_extraido"] is None and asa["requer_revisao"] is True


def test_low_confidence_and_non_present_status_become_null_for_review(history_api):
    client, _ = history_api
    bad = copy.deepcopy(GOOD)
    bad["dor"]["confianca"] = "baixa"
    bad["limitacao_funcional"]["situacao"] = "conflitante"
    _, result = extract(client, FakeExtractor(bad))
    for name in ["dor", "limitacao_funcional"]:
        assert result["campos"][name]["valor_extraido"] is None
        assert result["campos"][name]["requer_revisao"] is True
    assert result["campos"]["limitacao_funcional"]["evidencias"]
    for item in result["campos"].values():
        assert item["confianca"] in {"alta", "media", "baixa", None}


def test_clinical_domains_are_enforced_without_silent_conversion(history_api):
    client, _ = history_api
    bad = copy.deepcopy(GOOD)
    bad["asa"]["valor"] = "VII"
    bad["data_documento"]["valor"] = "03/04"
    bad["tipo_documento"]["valor"] = "receita"
    bad["cid"]["valor"] = "hernia"
    bad["porte"]["valor"] = "enorme"
    bad["deterioracao"]["valor"] = "muito"
    _, result = extract(client, FakeExtractor(bad))
    for name in ["asa", "data_documento", "tipo_documento", "cid", "porte", "deterioracao"]:
        assert result["campos"][name]["valor_extraido"] is None, name
        assert result["campos"][name]["requer_revisao"] is True
    assert result["campos"]["dor"]["valor_extraido"] == {
        "intensidade": 6,
        "escala": "EVA 0-10",
        "descricao": None,
    }


def test_only_masked_text_reaches_the_extractor(history_api):
    client, _ = history_api
    fake = FakeExtractor()
    extract(
        client,
        fake,
        pages=[REPORT, ["Paciente: Joana Sintetica da Silva", "Exame complementar sem alteracoes"]],
    )
    sent = json.dumps(fake.sent, ensure_ascii=False)
    assert "Joana" not in sent and "Sintetica" not in sent
    assert not re.search(r"\d{11,}", re.sub(r"[\s.-]", "", sent))
    assert "898" not in sent


def test_identifier_that_cannot_be_masked_blocks_any_external_send(history_api):
    client, _ = history_api
    fake = FakeExtractor()
    _, result = extract(client, fake, pages=[REPORT + ["Registro interno 12345678901234567"]])
    assert fake.sent == []
    assert result["situacao"] == "revisao_manual"
    assert "mascaramento_nao_assegurado" in result["avisos"]
    assert all(c["valor_extraido"] is None and c["requer_revisao"] for c in result["campos"].values())


def test_scanned_pdf_and_images_go_to_manual_review_without_calling_the_extractor(history_api):
    client, _ = history_api
    fake = FakeExtractor()
    for data, mime in [(make_pdf([[]]), "application/pdf"), (PNG_1X1, "image/png")]:
        _, result = extract(client, fake, data=data, mime=mime)
        assert result["situacao"] == "revisao_manual"
        assert "leitura_automatica_indisponivel" in result["avisos"]
        assert set(result["campos"]) == FIELDS
    assert fake.sent == []


def test_missing_provider_keeps_extraction_pending_without_inventing_fields(history_api, monkeypatch):
    client, _ = history_api
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    from susight.extraction import GeminiExtractor

    _, result = extract(client, GeminiExtractor())
    assert result["situacao"] == "pendente"
    assert "servico_indisponivel" in result["avisos"]
    assert result["campos"] == {}


def test_extraction_and_field_review_do_not_change_the_queue(history_api):
    client, _ = history_api
    as_user(client, "admin")
    before = [(r["solicitacao_id"], r["posicao"]) for r in client.get("/fila").json()["pacientes"]]
    did, _ = extract(client, FakeExtractor())
    as_user(client, "doctor")
    review = {"acao": "aprovar", "justificativa": "Conferido com o documento"}
    assert client.post(f"/documentos/{did}/campos/asa/revisao", json=review).status_code == 200
    as_user(client, "admin")
    assert [(r["solicitacao_id"], r["posicao"]) for r in client.get("/fila").json()["pacientes"]] == before


def test_professional_correction_keeps_the_extracted_value(history_api):
    client, _ = history_api
    did, _ = extract(client, FakeExtractor())
    review = {
        "acao": "corrigir",
        "valor_corrigido": "II",
        "justificativa": "Documento cita ASA II na pagina 2",
    }
    assert client.post(f"/documentos/{did}/campos/asa/revisao", json=review).status_code == 403
    as_user(client, "doctor")
    assert client.post(f"/documentos/{did}/campos/asa/revisao", json=review).status_code == 200
    asa = client.get(f"/documentos/{did}/extracao").json()["campos"]["asa"]
    assert asa["valor_extraido"] == "III"
    assert asa["revisao"]["acao"] == "corrigir" and asa["revisao"]["valor_corrigido"] == "II"
    assert asa["revisao"]["revisor"] == "doctor" and asa["revisao"]["data_hora"].startswith("2027-")
    approve_null = {"acao": "aprovar", "justificativa": "Conferido"}
    assert (
        client.post(f"/documentos/{did}/campos/socioeconomico/revisao", json=approve_null).status_code == 409
    )
    no_value = {"acao": "corrigir", "justificativa": "Sem valor"}
    assert client.post(f"/documentos/{did}/campos/dor/revisao", json=no_value).status_code == 422


def test_other_patient_cannot_read_the_extraction(history_api):
    client, _ = history_api
    did, _ = extract(client, FakeExtractor())
    as_user(client, "other_patient")
    assert client.get(f"/documentos/{did}/extracao").status_code == 404
    assert client.post(f"/documentos/{did}/extracao").status_code == 404


def test_file_fields_reviews_and_consent_expire_with_the_document(history_api):
    client, clock = history_api
    did, _ = extract(client, FakeExtractor())
    as_user(client, "doctor")
    review = {"acao": "aprovar", "justificativa": "Conferido com o documento"}
    client.post(f"/documentos/{did}/campos/asa/revisao", json=review)
    clock[0] += TTL + 1
    client.app.state.store.purge_expired()
    for table in [
        "documents",
        "document_files",
        "consents",
        "extractions",
        "extraction_fields",
        "field_reviews",
    ]:
        assert count(client, table) == 0, table


def test_extra_fields_such_as_waiting_time_are_ignored(history_api):
    client, _ = history_api
    extra = copy.deepcopy(GOOD) | {"tempo_espera": field("300 dias", "Data do exame: 12/09/2026")}
    _, result = extract(client, FakeExtractor(extra))
    assert set(result["campos"]) == FIELDS
