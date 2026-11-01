from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import Sortie


class DemandeTestIn(BaseModel):
    description: str | None = None            # requise à la première demande (un seul test par problème)


class TestDescriptionIn(BaseModel):
    description: str = Field(min_length=3)


class CritereAcceptationRetour(BaseModel):
    critere_acceptation_id: int
    satisfait: bool
    commentaire: str | None = None


class RetourTesteurIn(BaseModel):
    valide: bool
    commentaire: str | None = None            # obligatoire si non validé
    preuve: str | None = None
    environnement: str | None = None
    commit_teste: str | None = None
    criteres: list[CritereAcceptationRetour] = []


class SessionOut(Sortie):
    id: int
    application_id: int
    test_id: int
    numero: int
    decision_id: int | None
    demande_par: int
    testeur_id: int | None
    branche_testee: str
    commit_teste: str | None
    environnement: str | None
    statut: str
    commentaire: str | None
    preuve: str | None
    demande_le: datetime
    pris_le: datetime | None
    decide_le: datetime | None
    # renseignés par la liste des passages (pour afficher le problème concerné)
    probleme_id: int | None = None
    probleme_code: str | None = None
    probleme_titre: str | None = None
