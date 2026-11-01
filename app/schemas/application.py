from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import Sortie


class ApplicationCreate(BaseModel):
    equipe_id: int
    nom: str = Field(min_length=1, max_length=150)
    description: str | None = None
    responsable_id: int | None = None
    technologies: list[str] = []            # ex. ["php", "javascript"]


class ApplicationUpdate(BaseModel):
    nom: str | None = Field(default=None, max_length=150)
    description: str | None = None
    statut: str | None = Field(default=None, pattern="^(active|en_maintenance|archivee)$")
    responsable_id: int | None = None
    technologies: list[str] | None = None


class ApplicationOut(Sortie):
    id: int
    equipe_id: int
    nom: str
    description: str | None
    statut: str
    responsable_id: int | None
    cree_le: datetime
    technologies: list[str] = []


class DepotIn(BaseModel):
    url: str
    branche_defaut: str = "develop"
    jeton: str | None = None                 # chiffré côté serveur, jamais renvoyé


class DepotOut(Sortie):
    id: int
    application_id: int
    url: str
    branche_defaut: str
    derniere_synchro_le: datetime | None
    jeton_configure: bool = False
