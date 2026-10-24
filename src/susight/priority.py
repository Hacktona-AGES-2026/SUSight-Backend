"""Hard eligibility precedence is separate from additive utility."""

SWALIS_ORDER = ("A1", "A2", "B", "C", "D")
NO_URGENCY = len(SWALIS_ORDER)


def priority_group(patient):
    """0..4: protected group by SWALIS class; 5: no clinical urgency.

    The class is clinical-only (see scoring.prepare); waiting time never enters.
    """
    if not patient["oncologico"] and (
        patient["sem_urgencia"] or patient.get("sem_urgencia_verificador", False)
    ):
        return NO_URGENCY
    swalis = patient.get("swalis")
    return SWALIS_ORDER.index(swalis) if swalis in SWALIS_ORDER else 0


def hierarchy_origin(group_a, group_b):
    """Name the rule that fixes the order between two different groups."""
    return "hierarquia_regra_de_ouro" if NO_URGENCY in (group_a, group_b) else "hierarquia_swalis"
