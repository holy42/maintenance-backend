from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import Sortie


class LoginIn(BaseModel):
    identifiant: str
    mot_de_passe: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UtilisateurOut(Sortie):
    id: int
    identifiant: str
    email: str | None
    est_admin: bool
    actif: bool
    cree_le: datetime


class UtilisateurCreate(BaseModel):
    identifiant: str = Field(min_length=3, max_length=100)
    email: str | None = None
    mot_de_passe: str = Field(min_length=10)
    est_admin: bool = False


class UtilisateurUpdate(BaseModel):
    email: str | None = None
    est_admin: bool | None = None


class MotDePasseOublieIn(BaseModel):
    identifiant_ou_email: str


class ReinitialisationIn(BaseModel):
    jeton: str
    nouveau_mot_de_passe: str = Field(min_length=10)


class ChangerMotDePasseIn(BaseModel):
    ancien_mot_de_passe: str
    nouveau_mot_de_passe: str = Field(min_length=10)


class EquipeIn(BaseModel):
    nom: str = Field(min_length=1, max_length=150)
    description: str | None = None


class EquipeOut(Sortie):
    id: int
    nom: str
    description: str | None


class MembreIn(BaseModel):
    utilisateur_id: int
    role_id: int


class MembreOut(BaseModel):
    utilisateur_id: int
    identifiant: str
    role_id: int
    role: str


class RoleOut(Sortie):
    id: int
    nom: str
    description: str | None


class PermissionOut(Sortie):
    id: int
    code: str
    description: str | None


class RolePermissionsIn(BaseModel):
    permission_ids: list[int]


class AnnuaireOut(BaseModel):
    id: int
    identifiant: str
