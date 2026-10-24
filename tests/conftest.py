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


def read_lines(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]
