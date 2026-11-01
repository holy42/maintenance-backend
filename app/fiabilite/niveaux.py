"""Du pourcentage au niveau (faible / moyen / élevé). Seuils par défaut à confirmer sur les données de validation."""
SEUILS_PAR_DEFAUT = (0.40, 0.70)
LIBELLES = {"faible": "Faible", "moyen": "Moyenne", "eleve": "Élevée"}


def niveau(score: float, seuils: tuple[float, float] = SEUILS_PAR_DEFAUT) -> str:
    if score >= seuils[1]:
        return "eleve"
    if score >= seuils[0]:
        return "moyen"
    return "faible"
