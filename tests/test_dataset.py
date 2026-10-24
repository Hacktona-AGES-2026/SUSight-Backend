import hashlib

import pytest
from conftest import read_lines

from susight.dataset import treat
from susight.dataset.core import extract


def test_reproducible_immutable_and_imputation(dataset, tmp_path):
    source = dataset([{}, {"solicitacao_id": "SOL2", "paciente_id": "PAC2", "asa": ""}])
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    for name in ["out1", "out2"]:
        treat(source, tmp_path / name)
    for p in (tmp_path / "out1").iterdir():
        if p.name != "manifesto.json":
            assert p.read_bytes() == (tmp_path / "out2" / p.name).read_bytes()
    assert hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    rows = read_lines(tmp_path / "out1/solicitacoes.jsonl")
    assert rows[1]["medidas_observadas"]["asa"] is None
    assert rows[1]["medidas_pontuacao"]["asa"] == 2
    assert rows[1]["imputacoes"][0]["populacao_ids"] == ["SOL1"]
    assert rows[0]["normalizado"]["cid"] == "K409"
    assert rows[0]["normalizado"]["prioridade_regulacao"] == "media"


def test_alias_keeps_biopsy_and_oldest_id(dataset, tmp_path):
    source = dataset(
        [{}, {"solicitacao_id": "SOL2", "data_entrada_fila": "2026-05-01", "cid_principal": "K409"}],
        [{"solicitacao_id": "SOL2"}],
    )
    quality = treat(source, tmp_path / "out")
    row = read_lines(tmp_path / "out/solicitacoes.jsonl")[0]
    assert row["solicitacao_id"] == "SOL1"
    assert row["aliases"] == ["SOL2"]
    assert row["normalizado"]["biopsia_positiva"] is True
    assert row["normalizado"]["oncologico_por_cid"] is False
    assert quality["cobertura"] == {"ativa": 1, "consolidada": 1}


@pytest.mark.parametrize(
    "change",
    [
        {"justificativa_clinica": "Hernia a direita."},
        {"cid_principal": "K42.9"},
        {"intensidade_dor_eva": "8"},
        {"justificativa_clinica": "Novo episodio de hernia."},
    ],
)
def test_conflicts_not_consolidated(dataset, tmp_path, change):
    source = dataset([{}, {"solicitacao_id": "SOL2", **change}])
    treat(source, tmp_path / "out")
    assert len(read_lines(tmp_path / "out/solicitacoes.jsonl")) == 2


def test_events_orphan_mismatch_history_future_and_duplicate(dataset, tmp_path):
    source = dataset(
        events=[
            {},
            {"evento_id": "EV2"},
            {"evento_id": "EV3", "solicitacao_id": "OUT"},
            {"evento_id": "EV4", "paciente_id": "OTHER"},
            {"evento_id": "EV5", "data_evento": "2025-01-01"},
            {"evento_id": "EV6", "data_evento": "2027-01-01"},
        ]
    )
    quality = treat(source, tmp_path / "out")
    assert quality["eventos_duplicados"] == 1
    ev = read_lines(tmp_path / "out/eventos.jsonl")
    assert {e["situacao"] for e in ev} == {"vinculado", "orfao", "paciente_divergente"}
    assert {e["temporal"] for e in ev} >= {"historico", "futuro"}


@pytest.mark.parametrize(
    "observations,expected",
    [
        ("Paciente desistiu.", "excluida"),
        ("Paciente nao desistiu.", "ativa"),
        ("Talvez desistiu.", "ativa"),
        ("Pretende realizar cirurgia em outro servico.", "ativa"),
        ("Cirurgia realizada em outro servico.", "excluida"),
        ("Paciente desistiu. Paciente retomou a solicitacao.", "ativa"),
    ],
)
def test_exclusion_negation_and_uncertainty(dataset, tmp_path, observations, expected):
    source = dataset([{"observacoes": observations}])
    treat(source, tmp_path / "out")
    assert read_lines(tmp_path / "out/solicitacoes.jsonl")[0]["estado"] == expected


def test_no_global_median_and_no_future_exclusion(dataset, tmp_path):
    source = dataset(
        [{"asa": ""}],
        events=[{"tipo_evento": "contato_telefonico", "resultado": "desistiu", "data_evento": "2027-01-01"}],
    )
    treat(source, tmp_path / "out")
    row = read_lines(tmp_path / "out/solicitacoes.jsonl")[0]
    assert row["estado"] == "pendente"
    assert row["medidas_pontuacao"]["asa"] is None


def test_structural_failure_does_not_publish(dataset, tmp_path):
    source = dataset([{}, {"cid_principal": "C50.9"}])
    with pytest.raises(ValueError, match="conflitante"):
        treat(source, tmp_path / "out")
    assert not (tmp_path / "out").exists()
    with pytest.raises(ValueError, match="sobrepor"):
        treat(source, source / "out")


def test_ordinals_use_upper_median_and_no_cascade(dataset, tmp_path):
    source = dataset(
        [
            {},
            {"solicitacao_id": "SOL2", "paciente_id": "PAC2", "asa": "3"},
            {"solicitacao_id": "SOL3", "paciente_id": "PAC3", "asa": ""},
        ]
    )
    treat(source, tmp_path / "out")
    row = read_lines(tmp_path / "out/solicitacoes.jsonl")[2]
    assert row["medidas_pontuacao"]["asa"] == 3
    assert row["imputacoes"][0]["populacao_ids"] == ["SOL1", "SOL2"]


def test_extract_keeps_source_offsets():
    text = "Paciente com piora, nega diabetes."
    evidence = extract(text, {"arquivo": "teste", "linha": 2, "campo": "observacoes", "solicitacao_id": "S"})
    assert all(e["trecho"] == text[e["inicio"] : e["fim"]] for e in evidence)
    assert next(e for e in evidence if e["conceito"] == "dm")["polaridade"] == "negada"


def test_decomposed_unicode_keeps_original_offsets():
    text = "Situac\u0327a\u0303o: piora cli\u0301nica."
    for entry in extract(
        text, {"arquivo": "teste", "linha": 2, "campo": "observacoes", "solicitacao_id": "S"}
    ):
        assert entry["trecho"] == text[entry["inicio"] : entry["fim"]]


def test_future_text_does_not_override_current_activity(dataset, tmp_path):
    source = dataset(
        events=[
            {
                "tipo_evento": "contato_telefonico",
                "resultado": "desistiu",
                "descricao": "Paciente desistiu.",
                "data_evento": "2027-01-01",
            }
        ]
    )
    treat(source, tmp_path / "out")
    assert read_lines(tmp_path / "out/solicitacoes.jsonl")[0]["estado"] == "ativa"
