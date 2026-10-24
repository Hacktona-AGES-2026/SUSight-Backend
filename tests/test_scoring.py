import json

import numpy as np
import pytest
from conftest import read_lines

from susight.dataset import treat
from susight.scoring.engine import CRITERIA, ROR, Incompatible, Preferences, order_queue, prepare, score_queue


def preferences(rows, **changes):
    comparisons = []
    for i in range(5):
        for j in range(i + 1, 5):
            comparisons.append(
                {
                    "antes": rows[j]["solicitacao_id"],
                    "depois": rows[i]["solicitacao_id"],
                    "fonte": "Monotonicidade de fixture sintetica",
                }
            )
    config = {
        "versao": "test",
        "demonstrativa": True,
        "escalas": {c: {"minimo": 0, "maximo": 10, "fonte": "Fixture sintetica"} for c in CRITERIA},
        "pesos": {c: {"minimo": 0, "maximo": 1, "fonte": "Fixture sintetica"} for c in CRITERIA},
        "comparacoes": comparisons,
        **changes,
    }
    return Preferences.model_validate(config)


def synthetic():
    return [
        {
            "solicitacao_id": str(i),
            "criterios": dict.fromkeys(CRITERIA, i + 1),
            "dias_em_fila": i,
            "oncologico": False,
            "sem_urgencia": False,
        }
        for i in range(5)
    ]


def test_necessary_possible_and_representative():
    rows = synthetic()
    model = ROR(rows, preferences(rows))
    relation = model.relation("4", "0")
    assert relation["a_necessario"] and not relation["incerto"]
    assert model.representative.sum() == pytest.approx(1)
    assert np.all(model.representative >= -1e-8)
    assert all(v @ model.representative <= bound + 1e-7 for _, v, bound in model.constraints)


def test_strict_reversibility_is_not_tie():
    rows = synthetic() + [
        {"solicitacao_id": "A", "criterios": {c: 10 if i < 3 else 0 for i, c in enumerate(CRITERIA)}},
        {"solicitacao_id": "B", "criterios": {c: 0 if i < 3 else 10 for i, c in enumerate(CRITERIA)}},
        {"solicitacao_id": "C", "criterios": dict.fromkeys(CRITERIA, 5)},
        {"solicitacao_id": "D", "criterios": dict.fromkeys(CRITERIA, 5)},
    ]
    model = ROR(rows, preferences(rows))
    assert model.relation("A", "B")["incerto"]
    assert not model.relation("C", "D")["incerto"]
    assert model.relation("C", "D")["empate_necessario"]


def test_conflicting_preferences_name_conflict():
    rows = synthetic()
    prefs = preferences(rows)
    prefs.comparacoes[0].antes, prefs.comparacoes[0].depois = "0", "4"
    with pytest.raises(Incompatible) as info:
        ROR(rows, prefs)
    assert any(x.startswith("par:") for x in info.value.restricoes)


def test_gold_cannot_silently_reverse_necessary_preference():
    rows = synthetic()
    rows[0]["oncologico"] = True
    rows[4]["sem_urgencia"] = True
    model = ROR(rows, preferences(rows))
    with pytest.raises(ValueError, match="necessaria"):
        order_queue(rows, model)


def test_regulation_has_no_score_effect():
    rows = synthetic()
    rows[0]["prioridade_regulacao"] = "alta"
    a = ROR(rows, preferences(rows))
    rows[0]["prioridade_regulacao"] = "baixa"
    b = ROR(rows, preferences(rows))
    assert np.array_equal(a.representative, b.representative)


def test_configuration_requires_scales_sources_and_unique_comparisons():
    rows = synthetic()
    config = preferences(rows).model_dump()
    config["escalas"]["dor"]["maximo"] = 0
    with pytest.raises(ValueError):
        Preferences.model_validate(config)
    config = preferences(rows).model_dump()
    config["comparacoes"][1] = config["comparacoes"][0]
    with pytest.raises(ValueError):
        Preferences.model_validate(config)


def test_export_and_coverage(dataset, tmp_path):
    source = dataset(
        [
            {
                "solicitacao_id": str(i),
                "paciente_id": str(i),
                "intensidade_dor_eva": str(4 + i),
                "data_entrada_fila": f"2026-01-0{5 - i}",
            }
            for i in range(5)
        ]
    )
    treated = tmp_path / "treated"
    treat(source, treated)
    rows = [prepare(r) for r in read_lines(treated / "solicitacoes.jsonl")]
    prefs = preferences(rows)
    # Use only monotonic pain as swing for this synthetic export test.
    for c in CRITERIA:
        prefs.pesos[c].minimo = prefs.pesos[c].maximo = 1 if c == "dor" else 0
    path = tmp_path / "prefs.json"
    path.write_text(prefs.model_dump_json())
    a = score_queue(treated, path, tmp_path / "out1")
    b = score_queue(treated, path, tmp_path / "out2")
    assert a == b and a["solicitacoes"] == 5
    assert (tmp_path / "out1/fila_priorizada.csv").read_bytes() == (
        tmp_path / "out2/fila_priorizada.csv"
    ).read_bytes()
    ordered = json.loads((tmp_path / "out1/fila.json").read_text())
    assert ordered[0]["solicitacao_id"] == "4"


def test_necessary_tie_can_be_reordered_by_gold():
    rows = synthetic()
    # The last two patients have identical features: both weak relations are necessary.
    rows[3]["criterios"] = rows[4]["criterios"].copy()
    rows[3]["oncologico"] = True
    rows[4]["sem_urgencia"] = True
    prefs = preferences(synthetic())
    prefs.comparacoes = [p for p in prefs.comparacoes if (p.antes, p.depois) != ("4", "3")]
    # One extra strict reference to keep 10 comparisons while avoiding a forced tie reversal.
    extra = {
        "solicitacao_id": "X",
        "criterios": dict.fromkeys(CRITERIA, 9),
        "dias_em_fila": 9,
        "oncologico": False,
        "sem_urgencia": False,
    }
    from susight.scoring.engine import Pair

    prefs.comparacoes.append(Pair(antes="X", depois="4", fonte="Fixture sintetica"))
    model = ROR(rows + [extra], prefs)
    order, _, _ = order_queue(rows + [extra], model)
    assert [r["solicitacao_id"] for r in order].index("3") < [r["solicitacao_id"] for r in order].index("4")


def test_official_verifier_synthetic_end_to_end(dataset, tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    source = dataset(
        [
            {
                "solicitacao_id": str(i),
                "paciente_id": str(i),
                "intensidade_dor_eva": str(i * 2),
                "cid_principal": "C50.9" if i == 4 else "K40.9",
                "data_entrada_fila": f"2026-01-0{5 - i}",
            }
            for i in range(5)
        ]
    )
    treat(source, tmp_path / "treated")
    rows = [prepare(r) for r in read_lines(tmp_path / "treated/solicitacoes.jsonl")]
    prefs = preferences(rows)
    for c in CRITERIA:
        prefs.pesos[c].minimo = prefs.pesos[c].maximo = 1 if c == "dor" else 0
    config = tmp_path / "preferences.json"
    config.write_text(prefs.model_dump_json())
    score_queue(tmp_path / "treated", config, tmp_path / "scored")
    checker = Path(__file__).resolve().parents[1] / "tools/verificar_fila_priorizada.py"
    result = subprocess.run(
        [
            sys.executable,
            str(checker),
            str(tmp_path / "scored/fila_priorizada.csv"),
            "--dataset",
            str(source),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "RESULTADO: OK" in result.stdout


def test_representative_tie_does_not_reverse_one_way_necessity():
    rows = synthetic() + [
        {
            "solicitacao_id": "A",
            "criterios": dict.fromkeys(CRITERIA, 8),
            "dias_em_fila": 0,
            "oncologico": False,
            "sem_urgencia": False,
        },
        {
            "solicitacao_id": "B",
            "criterios": dict.fromkeys(CRITERIA, 5),
            "dias_em_fila": 999,
            "oncologico": False,
            "sem_urgencia": False,
        },
    ]
    model = ROR(rows, preferences(rows))
    # Feasible endpoint: first marginal increment = 1, all remaining increments = 0.
    model.representative = np.array([1.0] + [0.0] * 13)
    assert all(v @ model.representative <= bound + 1e-7 for _, v, bound in model.constraints)
    order, _, _ = order_queue(rows, model)
    ids = [r["solicitacao_id"] for r in order]
    assert ids.index("A") < ids.index("B")
