"""Registre des analyseurs disponibles. Ajouter une technologie = écrire un adaptateur et l'enregistrer ici."""
from app.analysis.base import AnalyseurCode
from app.analysis.php_treesitter import AnalyseurPHPTreeSitter

_ANALYSEURS: list[AnalyseurCode] = [AnalyseurPHPTreeSitter()]


def analyseurs_pour(technologies: set[str], regles_actives: set[str]) -> list[AnalyseurCode]:
    techs = {t.lower() for t in technologies}
    return [a for a in _ANALYSEURS if (a.technologies & techs) and (a.regles & regles_actives)]


def regles_connues() -> set[str]:
    return {r for a in _ANALYSEURS for r in a.regles}
