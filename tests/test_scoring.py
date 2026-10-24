import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from conftest import read_lines
from pydantic import ValidationError

from susight.dataset import treat
from susight.policy import POLICY_VERSION
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
        "politica": POLICY_VERSION,
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
    for row in rows:
        row.setdefault("oncologico", False)
        row.setdefault("sem_urgencia", False)
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
    with pytest.raises(Incompatible, match="hierarquia"):
        ROR(rows, preferences(rows))


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
    rows += [
        {
            "solicitacao_id": "ONCO",
            "criterios": dict.fromkeys(CRITERIA, 5),
            "dias_em_fila": 1,
            "oncologico": True,
            "sem_urgencia": False,
        },
        {
            "solicitacao_id": "CALMO",
            "criterios": dict.fromkeys(CRITERIA, 5),
            "dias_em_fila": 999,
            "oncologico": False,
            "sem_urgencia": True,
        },
    ]
    model = ROR(rows, preferences(rows))
    order, _, _ = order_queue(rows, model)
    ids = [r["solicitacao_id"] for r in order]
    assert ids.index("ONCO") < ids.index("CALMO")


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
    model.representative = np.array([1.0] + [0.0] * (2 * len(CRITERIA) - 1))
    assert all(v @ model.representative <= bound + 1e-7 for _, v, bound in model.constraints)
    order, _, _ = order_queue(rows, model)
    ids = [r["solicitacao_id"] for r in order]
    assert ids.index("A") < ids.index("B")


def test_hierarchy_overrides_marginal_dominance_without_falsifying_ror():
    rows = synthetic()
    rows += [
        {
            "solicitacao_id": "ONCO",
            "criterios": dict.fromkeys(CRITERIA, 0),
            "oncologico": True,
            "sem_urgencia": False,
            "dias_em_fila": 1,
        },
        {
            "solicitacao_id": "CALMO",
            "criterios": dict.fromkeys(CRITERIA, 10),
            "oncologico": False,
            "sem_urgencia": True,
            "dias_em_fila": 999,
        },
    ]
    model = ROR(rows, preferences(rows))
    relation = model.relation("ONCO", "CALMO")
    assert relation["origem"] == "hierarquia_regra_de_ouro"
    assert relation["min_diferenca"] is None and relation["a_necessario"]
    order, _, _ = order_queue(rows, model)
    ids = [r["solicitacao_id"] for r in order]
    assert ids.index("ONCO") < ids.index("CALMO")


def swalis_rows():
    rows = synthetic()
    for row in rows:
        row["swalis"] = "B"
    rows += [
        {
            "solicitacao_id": "A2LOW",
            "criterios": dict.fromkeys(CRITERIA, 0),
            "oncologico": True,
            "sem_urgencia": False,
            "dias_em_fila": 1,
            "swalis": "A2",
        },
        {
            "solicitacao_id": "BHIGH",
            "criterios": dict.fromkeys(CRITERIA, 10),
            "oncologico": False,
            "sem_urgencia": False,
            "dias_em_fila": 999,
            "swalis": "B",
        },
    ]
    return rows


def test_swalis_class_precedes_additive_utility():
    rows = swalis_rows()
    model = ROR(rows, preferences(rows))
    relation = model.relation("A2LOW", "BHIGH")
    assert relation["origem"] == "hierarquia_swalis"
    assert relation["a_necessario"] and not relation["b_necessario"] and not relation["incerto"]
    ids = [r["solicitacao_id"] for r in order_queue(rows, model)[0]]
    assert ids.index("A2LOW") < min(ids.index(i) for i in ["0", "1", "2", "3", "4", "BHIGH"])


def test_reference_pair_against_swalis_precedence_is_rejected():
    rows = swalis_rows()
    prefs = preferences(rows)
    prefs.comparacoes[0].antes, prefs.comparacoes[0].depois = "BHIGH", "A2LOW"
    with pytest.raises(Incompatible, match="hierarquia"):
        ROR(rows, prefs)


DOR_MAIOR = [{"maior": "dor", "menor": "limitacao", "fonte": "Fixture sintetica"}]


def shape_rows():
    rows = synthetic()
    zero = dict.fromkeys(CRITERIA, 0)
    rows += [
        {
            "solicitacao_id": "DOR10",
            "criterios": zero | {"dor": 10},
            "oncologico": False,
            "sem_urgencia": False,
            "dias_em_fila": 1,
        },
        {
            "solicitacao_id": "MEIO",
            "criterios": zero | {"dor": 5, "limitacao": 5},
            "oncologico": False,
            "sem_urgencia": False,
            "dias_em_fila": 1,
        },
    ]
    return rows


def test_linear_marginal_equalizes_both_halves_in_every_model():
    rows = synthetic()
    model = ROR(rows, preferences(rows, marginal="linear"))
    assert np.allclose(model.representative[0::2], model.representative[1::2])
    for i in range(len(CRITERIA)):
        v = np.zeros(model.nvars)
        v[2 * i], v[2 * i + 1] = 1, -1
        assert model.solve(v).fun == pytest.approx(0, abs=1e-7)
        assert model.solve(-v).fun == pytest.approx(0, abs=1e-7)


def test_linear_marginal_resolves_shape_only_uncertainty():
    rows = shape_rows()
    free = ROR(rows, preferences(rows, ordem_pesos=DOR_MAIOR))
    assert free.relation("DOR10", "MEIO")["incerto"]
    linear = ROR(rows, preferences(rows, ordem_pesos=DOR_MAIOR, marginal="linear"))
    relation = linear.relation("DOR10", "MEIO")
    assert relation["a_necessario"] and not relation["incerto"]


def test_marginal_defaults_to_free_and_rejects_unknown_shape():
    rows = synthetic()
    assert preferences(rows).marginal == "livre"
    with pytest.raises(ValidationError):
        preferences(rows, marginal="concava")


def test_demonstration_preferences_use_linear_swing_chain_and_ten_percent_bands():
    sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
    from acceptance import SWINGS, demonstration_preferences

    rows = [
        {
            "solicitacao_id": f"{i:02d}",
            "criterios": dict.fromkeys(CRITERIA, i + 1),
            "oncologico": False,
            "sem_urgencia": False,
        }
        for i in range(12)
    ]
    prefs = demonstration_preferences(rows)
    assert prefs.marginal == "linear"
    chain = sorted(SWINGS, key=SWINGS.get, reverse=True)
    assert [(o.maior, o.menor) for o in prefs.ordem_pesos] == list(itertools.pairwise(chain))
    total = sum(SWINGS.values())
    for c in CRITERIA:
        weight = SWINGS[c] / total
        assert prefs.pesos[c].minimo == pytest.approx(0.9 * weight)
        assert prefs.pesos[c].maximo == pytest.approx(1.1 * weight)
    ROR(rows, prefs)


def test_expired_treated_data_is_rejected_before_any_scoring(dataset, tmp_path):
    source = dataset()
    treat(source, tmp_path / "treated")
    path = tmp_path / "treated/manifesto.json"
    manifest = json.loads(path.read_text())
    manifest["criado_epoch"] = 0
    manifest["expira_epoch"] = 1
    path.write_text(json.dumps(manifest))
    # Preferences need not even be opened when source data is expired.
    with pytest.raises(ValueError, match="expirados"):
        score_queue(tmp_path / "treated", tmp_path / "missing.json", tmp_path / "out")
    assert not (tmp_path / "out").exists()
