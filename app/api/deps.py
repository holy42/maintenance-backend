"""Dépendances FastAPI : session, utilisateur courant."""
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import NonAuthentifie
from app.core.security import lire_jeton_acces
from app.database import get_db
from app.models import Utilisateur

_bearer = HTTPBearer(auto_error=False)


def utilisateur_courant(
    identifiants: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)
) -> Utilisateur:
    if identifiants is None:
        raise NonAuthentifie("Authentification requise.")
    user = db.get(Utilisateur, lire_jeton_acces(identifiants.credentials))
    if user is None or not user.actif:
        raise NonAuthentifie("Compte inconnu ou désactivé.")
    return user
