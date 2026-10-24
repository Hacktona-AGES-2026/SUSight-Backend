import pytest

from susight.policy import POLICY_VERSION
from susight.reassessment import ScoringModel, criteria_from_fields, reassess

CRITERIA = ["limitacao", "asa", "dor", "comorbidades", "deterioracao", "distancia"]
SCALES = {
    "limitacao": (0, 3),
    "asa": (1, 4),
    "dor": (0, 10),
    "comorbidades": (0, 7),
    "deterioracao": (0, 20),
    "distancia": (0, 800),
}


def model():
    return ScoringModel(
        escalas={c: {"minimo": lo, "maximo": hi} for c, (lo, hi) in SCALES.items()},
        incrementos=[1 / 12] * 12,
    )


def field(value, confidence="alta"):
    return {"valor_extraido": value, "situacao": "presente", "confianca": confidence, "requer_revisao": False}


def row(n, swalis="C", dor=2, limitacao=1, **extra):
    criteria = {
        "limitacao": limitacao,
        "asa": 2,
        "dor": dor,
        "comorbidades": 0,
        "deterioracao": 0,
        "distancia": 10,
    }
    base = {
        "politica": POLICY_VERSION,
        "solicitacao_id": f"S{n}",
        "paciente_id": f"P{n}",
        "cid": "K409",
        "dias_em_fila": 100,
        "oncologico": False,
        "sem_urgencia": False,
        "swalis": swalis,
        "criterios": criteria,
        "posicao": n,
    }
    base["pontuacao"] = model().score(criteria)
    return base | extra


WORSE = {
    "limitacao_funcional": field("grave"),
    "asa": field("III"),
    "dor": field({"intensidade": 8, "escala": "EVA", "descricao": None}),
    "comorbidades": field([{"valor": "hipertensão arterial"}, {"valor": "diabetes mellitus tipo 2"}]),
    "deterioracao": field("moderada"),
}


def test_ocr_fields_become_scoring_criteria_and_keep_what_the_document_does_not_say():
    got = criteria_from_fields(WORSE, {"distancia": 17, "dor": 0})
    assert got == {"limitacao": 3, "asa": 3, "dor": 8, "comorbidades": 2, "deterioracao": 3, "distancia": 17}


def test_missing_low_confidence_or_unreadable_fields_are_ignored():
    fields = {
        "dor": field({"intensidade": 9}, "baixa"),
        "asa": {"valor_extraido": None, "situacao": "ausente", "confianca": None, "requer_revisao": False},
        "limitacao_funcional": field("moderada"),
    }
    assert criteria_from_fields(fields, {"dor": 1, "asa": 2}) == {"dor": 1, "asa": 2, "limitacao": 2}


def test_a_worse_documented_case_moves_up_inside_its_group_and_class_is_raised():
    rows = [row(n, swalis="B" if n < 3 else "C") for n in range(1, 11)]
    result = reassess(rows, "S10", WORSE, model())
    assert result["swalis"] == "B"  # dor 8 and grave limitation
    assert result["sem_urgencia"] is False
    assert result["posicao"] == 1  # now class B, and its documented criteria outscore the other B rows
    assert result["criterios"]["dor"] == 8


def test_never_jumps_ahead_of_a_more_urgent_class():
    rows = [row(1, swalis="A1")] + [row(n) for n in range(2, 8)]
    result = reassess(rows, "S7", WORSE, model())
    assert result["posicao"] >= 2


def test_a_document_that_changes_nothing_keeps_the_position():
    rows = [row(n) for n in range(1, 6)]
    same = {"dor": field({"intensidade": 2}), "limitacao_funcional": field("leve")}
    assert reassess(rows, "S3", same, model())["posicao"] == 3


def test_reassess_needs_scored_rows():
    rows = [row(n) for n in range(1, 4)]
    rows[2]["criterios"] = None
    with pytest.raises(ValueError):
        reassess(rows, "S3", WORSE, model())


# --- end to end: the upload reads the document, re-scores the patient and the proposal reaches the doctor ---

import hashlib

from fastapi.testclient import TestClient
from pdfs import make_pdf
from test_extraction import GOOD, REPORT, FakeExtractor, upload
from test_history import as_user
from test_tribunal import FakeProvider, queue

from susight.access import Access
from susight.api import create_app


@pytest.fixture
def pipeline(tmp_path):
    principals = [
        {"id": n, "papel": r, "pacientes": s, "token_sha256": hashlib.sha256(n.encode()).hexdigest()}
        for n, r, s in [("admin", "admin", []), ("doctor", "medico", []), ("patient", "paciente", ["PAC20"])]
    ]
    app = create_app(
        tmp_path / "pipeline.sqlite",
        FakeProvider(),
        access=Access(entries=principals),
        start_worker=False,
        extractor=FakeExtractor(),
        scoring=model(),
    )
    with TestClient(app) as client:
        as_user(client, "admin")
        rows = [r | {"paciente_id": "PAC" + r["solicitacao_id"], "swalis": "C"} for r in queue()]
        for r in rows:
            r["criterios"] = {
                "limitacao": 1,
                "asa": 2,
                "dor": 2,
                "comorbidades": 0,
                "deterioracao": 0,
                "distancia": 10,
            }
            r["pontuacao"] = model().score(r["criterios"]) - r["posicao"] * 1e-4
        assert client.put("/fila", json={"versao_esperada": 0, "pacientes": rows}).status_code == 200
        yield client


def send_report(client):
    as_user(client, "patient")
    did = upload(client, make_pdf([REPORT])).json()["documento_id"]
    assert client.post(f"/documentos/{did}/extracao").status_code == 200
    as_user(client, "doctor")
    return did


def test_reading_a_worse_document_creates_a_proposal_for_the_doctor_with_evidence_taken_from_the_ocr(
    pipeline,
):
    did = send_report(pipeline)
    proposals = pipeline.get("/propostas", params={"situacao": "aguardando_tribunal"}).json()["propostas"]
    assert len(proposals) == 1 and proposals[0]["solicitacao_id"] == "20"
    detail = pipeline.get(f"/propostas/{proposals[0]['proposta_id']}").json()
    assert detail["posicao_proposta"] < 20
    assert {e["revisor"] for e in detail["evidencias"]} == {"sistema-ocr"}
    assert {e["trecho"] for e in detail["evidencias"]} >= {"Classificação ASA: III"}
    assert pipeline.get(f"/documentos/{did}").status_code == 200


def test_the_tribunal_and_the_doctors_approval_update_the_patient_and_the_queue(pipeline):
    send_report(pipeline)
    pid = pipeline.get("/propostas", params={"situacao": "aguardando_tribunal"}).json()["propostas"][0][
        "proposta_id"
    ]
    assert pipeline.post(f"/propostas/{pid}/tribunal").status_code == 200
    answer = pipeline.post(f"/propostas/{pid}/decisao", json={"acao": "aprovar", "medico": "Medico teste"})
    assert answer.status_code == 200, answer.text
    row = next(r for r in pipeline.get("/fila").json()["pacientes"] if r["solicitacao_id"] == "20")
    assert row["posicao"] < 20
    assert row["criterios"]["asa"] == 3 and row["criterios"]["dor"] == 6


def test_a_document_that_changes_nothing_creates_no_proposal(pipeline):
    pipeline.app.state.extractor = FakeExtractor(
        {k: v for k, v in GOOD.items() if k in {"tipo_documento", "data_documento"}}
    )
    send_report(pipeline)
    assert pipeline.get("/propostas", params={"situacao": "aguardando_tribunal"}).json()["total"] == 0
