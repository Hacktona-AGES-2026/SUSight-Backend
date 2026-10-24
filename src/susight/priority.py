"""Hard eligibility precedence is separate from additive utility."""


def priority_group(patient):
    if patient["oncologico"]:
        return 0
    return int(patient["sem_urgencia"] or patient.get("sem_urgencia_verificador", False))
