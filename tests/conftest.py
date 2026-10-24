import csv
import json
from pathlib import Path

import pytest


@pytest.fixture
def dataset(tmp_path):
    source = tmp_path / "raw"
    source.mkdir()

    def write(requests=None, events=None):
        row = {
            "solicitacao_id": "SOL1",
            "paciente_id": "PAC1",
            "procedimento_id": "PROC1",
            "cid_principal": "K40.9",
            "data_entrada_fila": "2026-01-01",
            "asa": "2",
            "intensidade_dor_eva": "4",
            "limitacao_funcional": "leve",
            "distancia_hospital_km": "20",
            "justificativa_clinica": "Hernia sintomatica redutivel.",
            "observacoes": "",
            "dias_em_fila": "295",
            "especialidade": "Geral",
            "procedimento": "Hernia",
            "comorbidades": "HAS",
            "prioridade_regulacao": "Média",
            "flag_oncologico": "nao",
        }
        rows = [{**row, **r} for r in (requests if requests is not None else [{}])]
        evfields = [
            "evento_id",
            "solicitacao_id",
            "paciente_id",
            "data_evento",
            "tipo_evento",
            "resultado",
            "valor_numerico",
            "descricao",
            "origem",
        ]
        defaults = dict.fromkeys(evfields, "") | {
            "evento_id": "EV1",
            "solicitacao_id": "SOL1",
            "paciente_id": "PAC1",
            "data_evento": "2026-10-01",
            "tipo_evento": "biopsia",
            "resultado": "positivo",
            "origem": "laboratorio",
        }
        tables = {
            "fila_cirurgica.csv": (list(row), rows),
            "eventos_clinicos.csv": (evfields, [{**defaults, **e} for e in events or []]),
            "procedimentos.csv": (
                ["procedimento_id", "procedimento", "especialidade"],
                [{"procedimento_id": "PROC1", "procedimento": "Hernia", "especialidade": "Geral"}],
            ),
        }
        for name, (fields, data) in tables.items():
            with (source / name).open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields)
                w.writeheader()
                w.writerows(data)
        for name in ["README.md", "dicionario_dados.md"]:
            (source / name).write_text("Dados sinteticos de teste.")
        return source

    return write


@pytest.fixture
def history_api(tmp_path):
    """API with a 20-patient queue (PAC1..PAC20) and scoped demo identities."""
    import hashlib

    from fastapi.testclient import TestClient
    from test_tribunal import FakeProvider, queue

    from susight.access import Access
    from susight.api import create_app

    clock = [1800000000.0]
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
        yield client, clock


def read_lines(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def approve_in_store(store, evidence=None, sid="20"):
    from susight.tribunal.models import DocumentInput, EvidenceRegistration

    evidence = evidence or {
        "evidencia_id": "E1",
        "tipo": "biopsia",
        "resultado": "positivo",
        "data": "2026-10-01",
    }
    doc = DocumentInput(
        solicitacao_id=sid,
        sha256="a" * 64,
        tipo_mime="application/pdf",
        paginas=1,
        tamanho_bytes=100,
        sintetico=True,
    )
    did = store.register_document(doc.model_dump(), "uploader-test")
    body = EvidenceRegistration(
        evidencia=evidence,
        documento_id=did,
        pagina=1,
        trecho="Biopsia com resultado positivo registrado no documento sintetico.",
        campo="comorbidades",
        valor="Condicao explicitamente documentada",
        confianca="alta",
    )
    eid = store.register_evidence(body.model_dump(), "uploader-test")
    store.review_evidence(eid, "aprovar", "medico-test", "Conferido com documento sintetico de teste")
    return eid, did


def register_http_evidence(client):
    doc = client.post(
        "/documentos",
        json={
            "solicitacao_id": "20",
            "sha256": "a" * 64,
            "tipo_mime": "application/pdf",
            "paginas": 1,
            "tamanho_bytes": 100,
            "sintetico": True,
        },
    )
    assert doc.status_code == 201, doc.text
    body = {
        "evidencia": {"evidencia_id": "E1", "tipo": "biopsia", "resultado": "positivo", "data": "2026-10-01"},
        "documento_id": doc.json()["documento_id"],
        "pagina": 1,
        "trecho": "Biopsia documentada no caso sintetico.",
        "campo": "comorbidades",
        "valor": "Condicao registrada",
        "confianca": "alta",
    }
    assert client.post("/evidencias", json=body).status_code == 201
    response = client.post(
        "/evidencias/E1/revisao", json={"acao": "aprovar", "justificativa": "Conferido com fonte sintetica"}
    )
    assert response.status_code == 200, response.text
