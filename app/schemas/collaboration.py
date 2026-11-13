from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import Sortie


class NoteIn(BaseModel):
    contenu: str = Field(min_length=1)
    type: str = Field(default="note_interne", pattern="^(note_interne|commentaire_correction)$")


class NoteOut(Sortie):
    id: int
    probleme_id: int | None
    tache_id: int | None
    auteur_id: int
    type: str
    contenu: str
    cree_le: datetime
    modifie_le: datetime | None
    supprime_le: datetime | None


class SalonIn(BaseModel):
    titre: str = Field(min_length=1, max_length=255)


class SalonOut(Sortie):
    id: int
    application_id: int
    type: str
    probleme_id: int | None
    titre: str
    archive: bool
    cree_le: datetime
    non_lus: int = 0


class MessageIn(BaseModel):
    contenu: str = Field(min_length=1)
    parent_id: int | None = None
    tache_id: int | None = None


class MessageOut(Sortie):
    id: int
    salon_id: int
    parent_id: int | None
    tache_id: int | None
    auteur_id: int | None
    type: str
    contenu: str
    cree_le: datetime
    modifie_le: datetime | None
    supprime_le: datetime | None


class QuestionIn(BaseModel):
    question: str = Field(min_length=1)
    tache_id: int | None = None               # question issue de « Demander de l'aide »
    sous_tache_id: int | None = None


class MessageIAOut(Sortie):
    id: int
    conversation_id: int
    emetteur: str
    auteur_id: int | None
    contenu: str
    contexte_utilise: dict | None
    informations_manquantes: str | None
    niveau_confiance: Decimal | None
    solution_id: int | None
    tache_id: int | None
    sous_tache_id: int | None
    cree_le: datetime


class NotificationOut(Sortie):
    id: int
    application_id: int | None
    type_evenement: str
    message: str
    type_element: str | None
    element_id: int | None
    lu: bool
    cree_le: datetime


class PreferenceIn(BaseModel):
    type_evenement: str
    active: bool


class PreferenceCanalNotificationIn(BaseModel):
    son: bool = True
    navigateur: bool = True


class ContenuIn(BaseModel):
    contenu: str = Field(min_length=1)
