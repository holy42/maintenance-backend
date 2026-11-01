"""Contrats de l'API du modèle de fiabilité.
`FiabiliteOut` est volontairement distinct de la « confiance déclarée » par Gemini : l'interface montre les deux, nettement séparés."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Sortie


class FacteurOut(BaseModel):
    variable: str
    libelle: str
    effet: float                      # écart de score (en points de probabilité) dû à cette variable
    sens: str                         # « augmente » | « diminue »


class FiabiliteOut(BaseModel):
    etape: int
    score: float                      # probabilité estimée, entre 0 et 1
    pourcentage: int
    niveau: Literal["faible", "moyen", "eleve"]
    libelle_niveau: str
    source: Literal["modele", "heuristique"]      # « heuristique » = règles fixées à la main, NON apprises
    appris: bool
    modele_id: int | None = None
    facteurs: list[FacteurOut] = []
    etiquette: bool | None = None     # vérité terrain, quand elle est connue


class EntrainementIn(BaseModel):
    etape: int = Field(description="3 : preuves de l'analyse ; 6 : solutions de Gemini")
    algorithme: str = "auto"          # auto | logistique | foret


class ModeleVersionOut(Sortie):
    id: int
    etape: int
    version: int
    algorithme: str
    nb_exemples: int | None
    metriques: dict | None
    actif: bool
    entraine_par: int | None
    entraine_le: datetime
