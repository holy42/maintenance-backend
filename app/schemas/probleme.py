from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.enums import Categorie, Gravite, Priorite, StatutProbleme, TypeDecision
from app.schemas.common import Sortie
from app.schemas.fiabilite import FiabiliteOut


class ProblemeCreate(BaseModel):
    titre: str = Field(min_length=1, max_length=255)
    categorie: Categorie
    description: str | None = None
    comportement_attendu: str | None = None
    comportement_observe: str | None = None
    gravite: Gravite | None = None
    priorite: Priorite | None = None
    fichier: str | None = None
    ligne_debut: int | None = None
    ligne_fin: int | None = None
    responsable_id: int | None = None
    echeance: date | None = None


class ProblemeUpdate(BaseModel):
    titre: str | None = Field(default=None, max_length=255)
    description: str | None = None
    comportement_attendu: str | None = None
    comportement_observe: str | None = None
    gravite: Gravite | None = None
    priorite: Priorite | None = None
    responsable_id: int | None = None
    echeance: date | None = None


class StatutIn(BaseModel):
    statut: StatutProbleme
    motif: str | None = None


class ProblemeOut(Sortie):
    id: int
    code: str
    application_id: int
    resultat_id: int | None
    verification_id: int | None
    critere_id: int | None
    source: str
    titre: str
    description: str | None
    comportement_attendu: str | None
    comportement_observe: str | None
    categorie: str
    gravite: str | None
    priorite: str | None
    statut: str
    fichier: str | None
    ligne_debut: int | None
    ligne_fin: int | None
    fonction: str | None
    extrait_code: str | None
    niveau_confiance: Decimal | None
    responsable_id: int | None
    echeance: date | None
    cree_le: datetime
    modifie_le: datetime
    fiabilite_preuve: FiabiliteOut | None = None     # étape 3 : fiabilité estimée de la preuve d'origine (si le problème vient d'une analyse)


class SolutionOut(Sortie):
    id: int
    diagnostic_id: int
    description: str
    extrait_code: str | None
    format_code: str | None
    risques: str | None
    tests_suggeres: str | None
    cree_le: datetime
    fiabilite: FiabiliteOut | None = None            # étape 6 : fiabilité estimée de la solution (distincte de la confiance déclarée)


class DiagnosticOut(Sortie):
    id: int
    probleme_id: int
    explication: str
    causes_probables: list | None
    niveau_confiance: Decimal | None
    incertitudes: str | None
    verifications_recommandees: list | None = None   # rédigées par l'IA puis contrôlées (voir app/fiabilite/verifications.py)
    branche_analysee: str | None
    commit_reference: str | None
    modele_ia: str | None
    cree_le: datetime
    solutions: list[SolutionOut] = []


class RetourSolutionIn(BaseModel):
    utilite_percue: str = Field(pattern="^(utile|partiellement_utile|ignoree|autre_appliquee|incorrecte|non_traitee)$")
    commentaire: str | None = None
    commit_associe: str | None = None


class DecisionIn(BaseModel):
    type_decision: TypeDecision
    solution_ids: list[int] = []
    description_alternative: str | None = None
    extrait_code_alternatif: str | None = None
    justification: str | None = None                      # facultative
    motif_non_utilisation: str | None = Field(default=None, pattern="^(pas_utile|fausse|autre_trouvee)$")
    commit_associe: str | None = None
    pull_request: str | None = None


class DecisionOut(Sortie):
    id: int
    probleme_id: int
    developpeur_id: int
    type_decision: str
    description_alternative: str | None
    extrait_code_alternatif: str | None
    justification: str | None
    motif_non_utilisation: str | None
    commit_associe: str | None
    pull_request: str | None
    cree_le: datetime
    solution_ids: list[int] = []
