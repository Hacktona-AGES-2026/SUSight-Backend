import csv
import json

import pytest

from susight.dataset import treat
from susight.scoring.analysis import analyze


def test_analysis_uses_observed_asa_and_reports_duplicates_and_catalog_conflict(dataset, tmp_path):
    source = dataset(
        [
            {"solicitacao_id": "A", "paciente_id": "SAME", "especialidade": "Outra", "asa": ""},
            {"solicitacao_id": "B", "paciente_id": "SAME", "cid_principal": "K42.9"},
            {"solicitacao_id": "C", "paciente_id": "OTHER", "asa": "4"},
        ]
    )
    with (source / "procedimentos.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["procedimento_id", "procedimento", "especialidade", "porte"])
        w.writeheader()
        w.writerow(
            {
                "procedimento_id": "PROC1",
                "procedimento": "Hernia",
                "especialidade": "Geral",
                "porte": "especial",
            }
        )
    treat(source, tmp_path / "treated")
    report = analyze(source, tmp_path / "treated", tmp_path / "analysis")
    principal = report["principal"]
    assert principal["solicitacoes"] == 3
    assert all(c["porte"] == "especial" for c in principal["asa_porte"])
    assert principal["qualidade"]["asa_imputado_na_pontuacao_nao_usado_na_tabela"] == 1
    assert principal["qualidade"]["especialidade_divergente"] == 1
    assert any(c["asa_observado"] == "ausente" for c in principal["asa_porte"])
    assert sum(c["quantidade"] for c in principal["asa_porte"]) == 3
    assert sum(c["proporcao"] for c in principal["asa_porte"]) == pytest.approx(1)
    assert report["sensibilidade_sem_grupos_suspeitos"]["solicitacoes"] == 1
    assert report["suspeitas_retiradas_apenas_da_sensibilidade"] == 2
    assert report["fila_alterada"] is False
    assert "SAME" not in json.dumps(report)
    assert (tmp_path / "analysis/analise.json").stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="existente"):
        analyze(source, tmp_path / "treated", tmp_path / "analysis")
    with pytest.raises(ValueError, match="sobreposta"):
        analyze(source, tmp_path / "treated", source / "out")


def test_analysis_rejects_mismatched_and_expired_sources(dataset, tmp_path):
    source = dataset()
    treat(source, tmp_path / "treated")
    manifest_path = tmp_path / "treated/manifesto.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["expira_epoch"] = 1
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="expirado"):
        analyze(source, tmp_path / "treated", tmp_path / "analysis")
    assert not (tmp_path / "analysis").exists()
