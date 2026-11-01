"""Schémas STRICTS des réponses de l'IA. Toute réponse non conforme est rejetée (IAIndisponible)."""
from typing import Literal

from pydantic import BaseModel, Field

CATEGORIES = Literal[
    "erreur_technique", "fonctionnel", "nouvelle_fonctionnalite", "regression", "securite", "propre_application"
]


class DiagnosticIA(BaseModel):
    explication: str
    causes_probables: list[str] = Field(default_factory=list, max_length=6)
    niveau_confiance: float = Field(ge=0, le=1)
    incertitudes: str | None = None          # « ce que l'IA ne sait pas »
    verifications_recommandees: list[str] = Field(default_factory=list, max_length=8)   # à effectuer par un humain


class SolutionIA(BaseModel):
    description: str
    extrait_code: str | None = None          # proposition séparée : jamais appliquée au dépôt
    format_code: Literal["extrait", "diff"] = "extrait"
    risques: str | None = None
    tests_suggeres: str | None = None


class ReponseDiagnostic(BaseModel):
    diagnostic: DiagnosticIA
    solutions: list[SolutionIA] = Field(min_length=1, max_length=4)


class SousTacheIA(BaseModel):
    titre: str
    description: str | None = None


class TacheIA(BaseModel):
    titre: str
    description: str | None = None
    duree_estimee_h: float | None = Field(default=None, ge=0, le=500)   # simple indication
    sous_taches: list[SousTacheIA] = Field(default_factory=list, max_length=8)
    criteres_acceptation: list[str] = Field(default_factory=list, max_length=6)


class PropositionTaches(BaseModel):
    taches: list[TacheIA] = Field(min_length=1, max_length=5)


class FormulationStructuree(BaseModel):
    condition: str
    attendu: str
    portee: str | None = None


class PropositionCritere(BaseModel):
    nom: str
    formulation: FormulationStructuree
    categorie: CATEGORIES
    automatisabilite: Literal["automatisable", "partielle", "humaine"]
    mode_verification: Literal["test_auto", "regle_statique", "assistee_ia", "manuelle"] | None = None
    incertitudes: list[str] = Field(default_factory=list, max_length=5)


class ReponseAssistant(BaseModel):
    contenu: str
    informations_manquantes: str | None = None
    niveau_confiance: float | None = Field(default=None, ge=0, le=1)
    solution: SolutionIA | None = None


class DescriptionTestIA(BaseModel):
    description: str


class HypotheseIA(BaseModel):
    fichier: str | None = None
    ligne: int | None = None
    message: str
    categorie: CATEGORIES
    gravite: Literal["critique", "elevee", "moyenne", "faible"] | None = None
    elements_preuve: str | None = None


class HypothesesIA(BaseModel):
    hypotheses: list[HypotheseIA] = Field(default_factory=list, max_length=20)
