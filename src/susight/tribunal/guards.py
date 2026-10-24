from __future__ import annotations

from susight.priority import priority_group

from .models import QueuePatient


def validate_queue(queue):
    rows = [QueuePatient.model_validate(r).model_dump() for r in queue]
    if not rows or len({r["solicitacao_id"] for r in rows}) != len(rows):
        raise ValueError("Fila vazia ou IDs repetidos")
    if sorted(r["posicao"] for r in rows) != list(range(1, len(rows) + 1)):
        raise ValueError("Posicoes devem ser consecutivas")
    rows.sort(key=lambda r: r["posicao"])
    if any(
        (a["sem_urgencia"] or a.get("sem_urgencia_verificador", False)) and b["oncologico"]
        for i, a in enumerate(rows)
        for b in rows[i + 1 :]
    ):
        raise ValueError("Fila de entrada viola regra de ouro")
    if any(priority_group(a) > priority_group(b) for i, a in enumerate(rows) for b in rows[i + 1 :]):
        raise ValueError("Fila de entrada viola hierarquia de prioridade")
    return rows


def guard(queue, sid, target):
    rows = sorted(queue, key=lambda r: r["posicao"])
    patient = next((r for r in rows if r["solicitacao_id"] == sid), None)
    if patient is None:
        raise ValueError("Solicitacao nao pertence a fila")
    if not 1 <= target <= len(rows):
        raise ValueError("Posicao fora da fila")
    old = patient["posicao"]
    reasons = []
    # A single-patient move cannot repair preexisting violations elsewhere.
    # CID flags are validated at queue import; all resulting pairs are checked below.
    required = old
    if patient["oncologico"]:
        calm = [
            r["posicao"]
            for r in rows
            if (r["sem_urgencia"] or r.get("sem_urgencia_verificador", False)) and r["posicao"] < old
        ]
        if calm:
            required = min(calm)
    limit = max(1, old - len(rows) // 10)
    if target < limit and required >= limit:
        target = limit
        reasons.append("limite_elevacao_10_porcento")
    if required < limit:
        target = min(target, required)
        reasons.append("regra_de_ouro_prevalece")
    rest = [r for r in rows if r["solicitacao_id"] != sid]
    candidate = rest[: target - 1] + [patient] + rest[target - 1 :]
    if any(
        (a["sem_urgencia"] or a.get("sem_urgencia_verificador", False)) and b["oncologico"]
        for i, a in enumerate(candidate)
        for b in candidate[i + 1 :]
    ):
        return {"liberada": False, "posicao": old, "travas": reasons + ["regra_de_ouro"]}
    if any(
        priority_group(a) > priority_group(b) for i, a in enumerate(candidate) for b in candidate[i + 1 :]
    ):
        return {"liberada": False, "posicao": old, "travas": reasons + ["hierarquia_regra_de_ouro"]}
    if target < old:
        crossed = [r for r in rest if target <= r["posicao"] < old]
        if any(
            priority_group(r) == priority_group(patient)
            and r["pontuacao"] > patient["pontuacao"] + 1e-7
            and r["dias_em_fila"] > patient["dias_em_fila"]
            for r in crossed
        ):
            return {"liberada": False, "posicao": old, "travas": reasons + ["prioridade_maior_e_mais_espera"]}
    return {"liberada": True, "posicao": target, "travas": reasons}
