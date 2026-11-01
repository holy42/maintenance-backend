from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import utilisateur_courant
from app.database import get_db
from app.core.permissions import equipes_ids
from app.models import MembreEquipe, Utilisateur
from app.schemas.acces import (
    AnnuaireOut, ChangerMotDePasseIn, LoginIn, MotDePasseOublieIn, ReinitialisationIn, TokenOut, UtilisateurOut,
)
from app.schemas.common import Message
from app.services import auth

router = APIRouter(prefix="/auth", tags=["Authentification"])


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    return TokenOut(access_token=auth.connecter(db, data.identifiant, data.mot_de_passe))


@router.get("/me", response_model=UtilisateurOut)
def moi(user: Utilisateur = Depends(utilisateur_courant)):
    return user


@router.post("/mot-de-passe-oublie", response_model=Message, status_code=202)
def mot_de_passe_oublie(data: MotDePasseOublieIn, db: Session = Depends(get_db)):
    auth.demander_reinitialisation(db, data.identifiant_ou_email)
    return Message(message="Si un compte correspond, un e-mail de réinitialisation a été envoyé.")


@router.post("/reinitialiser-mot-de-passe", response_model=Message)
def reinitialiser(data: ReinitialisationIn, db: Session = Depends(get_db)):
    auth.reinitialiser(db, data.jeton, data.nouveau_mot_de_passe)
    return Message(message="Mot de passe modifié.")


@router.post("/changer-mot-de-passe", response_model=Message)
def changer(data: ChangerMotDePasseIn, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    auth.changer_mot_de_passe(db, user, data.ancien_mot_de_passe, data.nouveau_mot_de_passe)
    return Message(message="Mot de passe modifié.")


@router.get("/annuaire", response_model=list[AnnuaireOut])
def annuaire(db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    """Identifiants des personnes qui partagent une équipe avec l'utilisateur (tous pour l'administrateur) :
    sert à afficher des noms plutôt que des numéros."""
    q = select(Utilisateur.id, Utilisateur.identifiant).order_by(Utilisateur.identifiant)
    if not user.est_admin:
        q = q.join(MembreEquipe, MembreEquipe.utilisateur_id == Utilisateur.id).where(
            MembreEquipe.equipe_id.in_(equipes_ids(db, user))).distinct()
    return [AnnuaireOut(id=i, identifiant=n) for i, n in db.execute(q).all()]
