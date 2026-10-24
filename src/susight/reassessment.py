"""Re-score one patient from the criteria the OCR read, without recomputing the whole ranking.

The representative value function that ranked the queue (`funcao_representativa.json`) is applied to the
one patient, who is then placed among the others by the same hierarchy: protected class first, then score.
This approximates the full ROR run; the tribunal and the doctor still decide before the queue changes.
"""

from __future__ import annotations

from susight.priority import priority_group

CRITERIA = ["limitacao", "asa", "dor", "comorbidades", "deterioracao", "distancia"]
LIMITATIONS = ["nenhuma", "leve", "moderada", "grave"]
ASA = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6}
# Demonstration approximations, like the severity weights used when the queue was scored.
DETERIORATION = {"nenhuma": 0, "leve": 1, "moderada": 3, "grave": 6}
COMORBIDITY_SEVERITY = (("cardiopatia", 2), ("insuficiencia cardiaca", 2), ("dpoc", 2))


class ScoringModel:
    """The value function that ordered the queue: piecewise-linear marginals over explicit scales."""

    def __init__(self, escalas, incrementos):
        self.escalas, self.incrementos = escalas, list(incrementos)

    @classmethod
    def from_file(cls, body):
        return cls(body["preferencias"]["escalas"], body["incrementos"])

    def score(self, criteria):
        total = 0.0
        for i, name in enumerate(CRITERIA):
            scale = self.escalas[name]
            span = scale["maximo"] - scale["minimo"]
            x = min(1.0, max(0.0, (float(criteria[name]) - scale["minimo"]) / span))
            total += (
                min(2 * x, 1.0) * self.incrementos[2 * i] + max(0.0, 2 * x - 1) * self.incrementos[2 * i + 1]
            )
        return total


def _usable(field):
    return (
        field
        and field.get("valor_extraido") is not None
        and field.get("situacao") == "presente"
        and field.get("confianca") in {"alta", "media"}
    )


def _comorbidity_points(items):
    points = 0
    for item in items:
        text = (item.get("valor", "") if isinstance(item, dict) else str(item)).lower()
        points += next((p for key, p in COMORBIDITY_SEVERITY if key in text), 1)
    return points


def criteria_from_fields(fields, old):
    """Criteria the document states, over the patient's previous ones (what it does not say stays)."""
    criteria = dict(old)
    read = {name: f["valor_extraido"] for name, f in fields.items() if _usable(f)}
    if read.get("limitacao_funcional") in LIMITATIONS:
        criteria["limitacao"] = LIMITATIONS.index(read["limitacao_funcional"])
    if str(read.get("asa", "")).rstrip("E") in ASA:
        criteria["asa"] = ASA[str(read["asa"]).rstrip("E")]
    if isinstance(read.get("dor"), dict) and read["dor"].get("intensidade") is not None:
        criteria["dor"] = read["dor"]["intensidade"]
    if isinstance(read.get("comorbidades"), list):
        criteria["comorbidades"] = _comorbidity_points(read["comorbidades"])
    if read.get("deterioracao") in DETERIORATION:
        criteria["deterioracao"] = DETERIORATION[read["deterioracao"]]
    return criteria


def _raised_class(old, criteria):
    """Classes only go up with documented worsening (same thresholds as the dataset scoring)."""
    if old in {"A1", "A2"}:
        return old
    if criteria["dor"] >= 7 or criteria["limitacao"] >= 3 or criteria["deterioracao"] > 0:
        new = "B"
    elif criteria["dor"] >= 4 or criteria["limitacao"] >= 2:
        new = "C"
    else:
        new = "D"
    order = ["B", "C", "D"]
    return old if old in order and order.index(old) < order.index(new) else new


def reassess(queue, sid, fields, model):
    """New criteria, class, score and position for `sid`; raises ValueError when rows are not scored."""
    rows = sorted(queue, key=lambda r: r["posicao"])
    patient = next(r for r in rows if r["solicitacao_id"] == sid)
    if any(not r.get("criterios") for r in rows):
        raise ValueError("Fila sem criterios de pontuacao")
    criteria = criteria_from_fields(fields, patient["criterios"])
    swalis = _raised_class(patient.get("swalis"), criteria)
    worse = criteria != patient["criterios"] and (
        criteria["dor"] > 3 or criteria["limitacao"] >= 2 or criteria["deterioracao"] > 0
    )
    quiet = patient["sem_urgencia"] and not worse
    updated = patient | {
        "criterios": criteria,
        "swalis": swalis,
        "sem_urgencia": quiet,
        "sem_urgencia_verificador": patient.get("sem_urgencia_verificador", False) and quiet,
        "pontuacao": model.score(criteria),
    }
    key = (priority_group(updated), -updated["pontuacao"], sid)
    ahead = sum(
        1
        for r in rows
        if r["solicitacao_id"] != sid and (priority_group(r), -r["pontuacao"], r["solicitacao_id"]) < key
    )
    # Never ranks below where it already is for a document that did not worsen anything.
    position = min(ahead + 1, patient["posicao"])
    return {
        "criterios": criteria,
        "swalis": swalis,
        "sem_urgencia": quiet,
        "pontuacao": updated["pontuacao"],
        "posicao": position,
    }
