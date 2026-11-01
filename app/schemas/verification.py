from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import Categorie
from app.schemas.common import Sortie
from app.schemas.fiabilite import FiabiliteOut


class CritereCreate(BaseModel):
    nom: str = Field(min_length=1, max_length=150)
    description: str
    categorie: Categorie
    automatisabilite: str = Field(default="a_determiner", pattern="^(automatisable|partielle|humaine|a_determiner)$")
    mode_verification: str | None = Field(default=None, pattern="^(test_auto|regle_statique|assistee_ia|manuelle)$")
    formulation_structuree: dict | None = None


class CritereUpdate(BaseModel):
    nom: str | None = None
    description: str | None = None
    categorie: Categorie | None = None
    automatisabilite: str | None = None
    mode_verification: str | None = None
    formulation_structuree: dict | None = None


class StructurerIn(BaseModel):
    description: str = Field(min_length=5)


class CritereOut(Sortie):
    id: int
    application_id: int | None
    createur_id: int | None
    nom: str
    description: str
    formulation_structuree: dict | None
    origine: str
    categorie: str
    automatisabilite: str
    mode_verification: str | None
    statut: str
    valide_par: int | None
    cree_le: datetime


class VerificationCreate(BaseModel):
    branche: str = "develop"                    # develop, ou branche du problème rouvert (ex. PB-1029)
    dossiers: list[str] = []                    # périmètre ; vide = dossiers par défaut de l'application
    exclusions: list[str] = ["vendor", "node_modules", "writable"]
    critere_ids: list[int] = Field(min_length=1)
    avec_interpretation_ia: bool = True


class VerificationOut(Sortie):
    id: int
    application_id: int
    branche: str
    commit_analyse: str | None
    perimetre: str | None
    declenchee_par: int
    statut: str
    motif_echec: str | None
    avec_interpretation_ia: bool
    resultat_global: str | None
    debut_le: datetime
    fin_le: datetime | None


class ResultatOut(Sortie):
    id: int
    verification_id: int
    critere_id: int | None
    source: str
    outil: str | None
    categorie: str
    gravite: str | None
    fichier: str | None
    ligne_debut: int | None
    ligne_fin: int | None
    fonction: str | None
    extrait_code: str | None
    message: str
    elements_preuve: str | None
    statut_validation: str
    motif_decision: str | None
    decide_le: datetime | None
    fiabilite: FiabiliteOut | None = None      # étape 3 : fiabilité estimée de la preuve (outil d'analyse)


class DecisionResultatIn(BaseModel):
    motif: str | None = None
    titre: str | None = None                    # pour la confirmation : titre du problème créé
