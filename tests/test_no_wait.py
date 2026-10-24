import copy
import json

import numpy as np
import pytest
from conftest import approve_in_store, read_lines
from test_scoring import preferences, synthetic
from test_tribunal import FakeProvider, proposal, queue

from susight.dataset import treat
from susight.policy import POLICY_VERSION
from susight.scoring.engine import ROR, Preferences, order_queue, prepare
from susight.tribunal.guards import guard
from susight.tribunal.service import Tribunal, masked_context
from susight.tribunal.store import Store


def test_preparation_and_ror_ignore_administrative_wait(dataset, tmp_path):
    treat(dataset(), tmp_path / "treated")
    record = read_lines(tmp_path / "treated/solicitacoes.jsonl")[0]
    a = prepare(record)
    record["normalizado"].update(dias_em_fila=9000, data_entrada_fila="2001-01-01")
    b = prepare(record)
    assert a["criterios"] == b["criterios"] and "espera" not in a["criterios"]
    rows = synthetic() + [a | {"solicitacao_id": "A"}, b | {"solicitacao_id": "B"}]
    config = preferences(rows)
    model = ROR(rows, config)
    first = order_queue(rows, model)
    relations = [model.relation("A", r["solicitacao_id"]) for r in rows[:-2]]
    for row in rows:
        row["dias_em_fila"] = 10000 - row["dias_em_fila"]
        row["data_entrada_fila"] = "2000-01-01"
    changed = ROR(list(reversed(rows)), config)
    second = order_queue(list(reversed(rows)), changed)
    assert [r["solicitacao_id"] for r in first[0]] == [r["solicitacao_id"] for r in second[0]]
    assert first[1:] == second[1:]
    assert np.array_equal(model.representative, changed.representative)
    assert relations == [changed.relation("A", r["solicitacao_id"]) for r in rows[:-2]]
    assert model.nvars == 12


def test_config_rejects_legacy_wait_including_hidden_swings():
    config = preferences(synthetic()).model_dump()
    for alteration in [
        {"politica": "legado"},
        {"escalas": config["escalas"] | {"espera": config["escalas"]["dor"]}},
        {"swings_demonstrativos": {"espera": 100}},
    ]:
        with pytest.raises(ValueError):
            Preferences.model_validate(config | alteration)
    config.pop("politica")
    with pytest.raises(ValueError):
        Preferences.model_validate(config)


def test_guards_and_external_context_ignore_wait():
    rows = queue()
    rows[18]["pontuacao"] = 0.9
    before = guard(rows, "20", 18)
    context = masked_context(proposal(), rows, before)
    rows[18]["dias_em_fila"] = 10000
    rows[-1]["dias_em_fila"] = 0
    assert before == guard(rows, "20", 18) and before["liberada"]
    assert masked_context(proposal(), rows, before) == context
    assert "dias_em_fila" not in json.dumps(context)


def test_policy_migration_preserves_audit_but_requires_reimport(tmp_path):
    store = Store(tmp_path / "legacy.sqlite")
    store.import_queue(queue(), 0)
    approve_in_store(store)
    pid = store.create(proposal())
    with store.db() as db:
        db.execute("UPDATE queues SET policy='legado'")
    migrated = Store(store.path)
    assert migrated.queue() == (1, [])
    assert migrated.get(pid)["status"] == "desatualizada"
    with migrated.db() as db:
        assert db.execute("SELECT COUNT(*) FROM queue_imports").fetchone()[0] == 1
    legacy = copy.deepcopy(queue())
    for row in legacy:
        del row["politica"]
    with pytest.raises(ValueError):
        migrated.import_queue(legacy, 1)
    assert migrated.import_queue(queue(), 1) == 2
    assert migrated.queue()[1][0]["politica"] == POLICY_VERSION
    with pytest.raises(ValueError):
        migrated.create(proposal())


async def test_reimport_during_provider_call_invalidates_result_and_old_decision(tmp_path):
    store = Store(tmp_path / "race.sqlite")
    store.import_queue(queue(), 0)
    approve_in_store(store)
    pid = store.create(proposal())

    class Reimporting(FakeProvider):
        async def analyze(self, agent, context):
            result = await super().analyze(agent, context)
            if agent == "evidencias":
                store.import_queue(queue(), 1)
            return result

    result = await Tribunal(store, Reimporting()).process(pid)
    assert result["status"] == "desatualizada" and result["opinion"] is None
    with pytest.raises(ValueError):
        store.decide(pid, "doctor", "aprovar", "Teste", queue())


async def test_reimport_preserves_old_opinion_for_audit_but_forbids_applying_it(tmp_path):
    store = Store(tmp_path / "audit.sqlite")
    store.import_queue(queue(), 0)
    approve_in_store(store)
    pid = store.create(proposal())
    before = await Tribunal(store, FakeProvider()).process(pid)
    assert before["status"] == "pronta_para_medico"
    store.import_queue(queue(), 1)
    after = store.get(pid)
    assert after["status"] == "desatualizada"
    assert after["opinion"] == before["opinion"]
    with pytest.raises(ValueError):
        store.decide(pid, "doctor", "aprovar", "Teste", queue())
