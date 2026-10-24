from test_history import approved_evidence, as_user, current, decide, ready_proposal
from test_tribunal import proposal_reference

from susight.artifacts import TTL

CRITERIA = {"limitacao": 2, "asa": 3, "dor": 7, "comorbidades": 1, "deterioracao": 2, "distancia": 40}


def created_proposal(client):
    as_user(client, "doctor")
    response = client.post("/propostas", json=proposal_reference() | {"versao_fila": current(client)})
    assert response.status_code == 201, response.text
    return response.json()["proposta_id"]


def listing(client, *statuses):
    query = "&".join(f"situacao={s}" for s in statuses)
    return client.get("/propostas" + (f"?{query}" if query else ""))


def detail(client, pid):
    return client.get(f"/propostas/{pid}")


def test_list_shows_only_permitted_cases_oldest_first_with_total(history_api):
    client, clock = history_api
    approved_evidence(client)
    first = ready_proposal(client)
    clock[0] += 60
    second = ready_proposal(client)
    as_user(client, "doctor")
    body = listing(client).json()
    assert body["total"] == 2
    assert [p["proposta_id"] for p in body["propostas"]] == [first, second]
    as_user(client, "admin")
    assert listing(client).json()["total"] == 2
    as_user(client, "other")
    assert listing(client).json()["total"] == 2


def test_list_defaults_to_ready_filters_by_status_and_refuses_unknown(history_api):
    client, _ = history_api
    approved_evidence(client)
    waiting = created_proposal(client)
    ready = ready_proposal(client)
    as_user(client, "doctor")
    assert [p["proposta_id"] for p in listing(client).json()["propostas"]] == [ready]
    both = listing(client, "aguardando_tribunal", "pronta_para_medico").json()["propostas"]
    assert {p["proposta_id"] for p in both} == {waiting, ready}
    assert listing(client, "inexistente").status_code == 422


def test_each_item_has_current_and_proposed_position_and_tribunal_summary(history_api):
    client, _ = history_api
    approved_evidence(client)
    pid = ready_proposal(client)
    as_user(client, "doctor")
    item = listing(client).json()["propostas"][0]
    assert item["proposta_id"] == pid and item["solicitacao_id"] == "20"
    assert item["situacao"] == "pronta_para_medico"
    assert item["posicao_atual"] == 20 and item["posicao_proposta"] == 18
    assert item["recomendacao"] == "aprovar"
    assert item["ordenacao_incerta"] is True and item["evidencias_conflitantes"] is False
    assert item["criada_em"].startswith("2027-")


def test_patient_is_forbidden_and_other_doctor_does_not_see_the_proposal(history_api):
    client, _ = history_api
    approved_evidence(client)
    pid = ready_proposal(client)
    as_user(client, "patient")
    assert listing(client).status_code == 403
    assert detail(client, pid).status_code == 403
    as_user(client, "other")
    assert detail(client, pid).status_code == 200
    as_user(client, "doctor")
    assert detail(client, "inexistente").status_code == 404


def test_detail_has_approved_evidence_full_opinion_and_history(history_api):
    client, _ = history_api
    approved_evidence(client)
    pid = ready_proposal(client)
    as_user(client, "doctor")
    body = detail(client, pid).json()
    assert body["posicao_atual"] == 20 and body["posicao_proposta"] == 18
    evidence = body["evidencias"][0]
    assert (
        evidence["evidencia_id"] == "E1"
        and evidence["tipo"] == "biopsia"
        and evidence["resultado"] == "positivo"
    )
    assert evidence["trecho"] == "Resultado explicitamente descrito no documento sintetico."
    assert evidence["pagina"] == 1 and evidence["revisor"] == "doctor" and evidence["revisado_em"]
    opinion = body["parecer"]
    assert {m["agente"] for m in opinion["manifestacoes"]} == {"evidencias", "contestacao", "equidade"}
    assert opinion["recomendacao"] == "aprovar" and "travas" in opinion and opinion["posicao"]
    assert [e["tipo"] for e in body["historico"]][-1] == "entrada_na_fila"
    assert body["decisao"] is None


def test_detail_after_decision_shows_action_reason_author_and_time(history_api):
    client, _ = history_api
    approved_evidence(client)
    pid = ready_proposal(client)
    decide(client, pid, "rejeitar", "Evidencia insuficiente agora")
    as_user(client, "doctor")
    body = detail(client, pid).json()
    assert body["situacao"] == "rejeitar"
    assert body["decisao"]["acao"] == "rejeitar"
    assert body["decisao"]["motivo"] == "Evidencia insuficiente agora"
    assert body["decisao"]["responsavel"] == "doctor"
    assert body["decisao"]["data_hora"].startswith("2027-")
    assert listing(client, "rejeitar").json()["total"] == 1


def test_expired_proposal_leaves_the_list_and_detail(history_api):
    client, clock = history_api
    approved_evidence(client)
    pid = ready_proposal(client)
    clock[0] += TTL + 1
    as_user(client, "admin")
    assert listing(client).json()["total"] == 0
    assert detail(client, pid).status_code == 404


def test_imported_criteria_swalis_and_priority_reach_the_detail(history_api):
    client, _ = history_api
    as_user(client, "admin")
    rows = client.get("/fila").json()["pacientes"]
    for row in rows:
        row.pop("em_reavaliacao", None)
        # Whole queue in one SWALIS class: a lone class would break the hierarchy check of the SWALIS layer.
        row["swalis"] = "C"
        if row["solicitacao_id"] == "20":
            row |= {"criterios": CRITERIA, "prioridade_regulacao": "Alta"}
    assert (
        client.put("/fila", json={"versao_esperada": current(client), "pacientes": rows}).status_code == 200
    )
    approved_evidence(client)
    pid = ready_proposal(client)
    as_user(client, "doctor")
    body = detail(client, pid).json()
    assert body["criterios"] == CRITERIA
    assert body["swalis"] == "C" and body["prioridade_regulacao"] == "Alta"


def test_missing_criteria_are_null_and_unknown_criterion_is_refused(history_api):
    client, _ = history_api
    approved_evidence(client)
    pid = ready_proposal(client)
    as_user(client, "doctor")
    body = detail(client, pid).json()
    assert body["criterios"] is None and body["swalis"] is None and body["prioridade_regulacao"] is None
    as_user(client, "admin")
    rows = client.get("/fila").json()["pacientes"]
    for row in rows:
        row.pop("em_reavaliacao", None)
    rows[0]["criterios"] = CRITERIA | {"espera": 300}
    assert (
        client.put("/fila", json={"versao_esperada": current(client), "pacientes": rows}).status_code == 422
    )


def test_list_and_detail_never_call_the_ai_provider(history_api):
    client, _ = history_api
    approved_evidence(client)
    pid = ready_proposal(client)
    provider = client.app.state.tribunal.provider
    calls = len(provider.contexts)
    as_user(client, "doctor")
    listing(client)
    detail(client, pid)
    assert len(provider.contexts) == calls
