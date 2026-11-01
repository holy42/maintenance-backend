from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import Sortie


class SousTacheIn(BaseModel):
    titre: str = Field(min_length=1, max_length=255)
    description: str | None = None
    origine: str = Field(default="utilisateur", pattern="^(ia|utilisateur)$")


class CritereAcceptationIn(BaseModel):
    texte: str = Field(min_length=1)
    origine: str = Field(default="utilisateur", pattern="^(ia|utilisateur)$")


class TacheCreate(BaseModel):
    titre: str = Field(min_length=1, max_length=255)
    description: str | None = None
    origine: str = Field(default="utilisateur", pattern="^(ia|utilisateur)$")
    duree_estimee_h: Decimal | None = Field(default=None, ge=0)     # indication modifiable
    responsable_id: int | None = None
    echeance: date | None = None
    solution_ids: list[int] = []
    sous_taches: list[SousTacheIn] = []
    criteres_acceptation: list[CritereAcceptationIn] = []


class TachesCreate(BaseModel):
    """Un problème peut avoir une ou plusieurs tâches."""
    taches: list[TacheCreate] = Field(min_length=1, max_length=10)


class TacheUpdate(BaseModel):
    titre: str | None = Field(default=None, max_length=255)
    description: str | None = None
    duree_estimee_h: Decimal | None = Field(default=None, ge=0)
    responsable_id: int | None = None
    echeance: date | None = None


class SousTacheOut(Sortie):
    id: int
    titre: str
    description: str | None
    statut: str
    ordre: int
    origine: str


class CritereAcceptationOut(Sortie):
    id: int
    texte: str
    ordre: int
    origine: str


class TacheOut(Sortie):
    id: int
    probleme_id: int
    application_id: int
    titre: str
    description: str | None
    origine: str
    duree_estimee_h: Decimal | None
    statut: str
    responsable_id: int | None
    echeance: date | None
    cree_le: datetime
    debut_le: datetime | None
    fin_le: datetime | None
    sous_taches: list[SousTacheOut] = []
    criteres_acceptation: list[CritereAcceptationOut] = []


class StatutSousTacheIn(BaseModel):
    statut: str = Field(pattern="^(a_faire|en_cours|en_pause|arretee|terminee)$")
