"""Mots de passe hachés, jetons JWT, jetons de réinitialisation."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings
from app.core.exceptions import NonAuthentifie

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hacher_mot_de_passe(mot_de_passe: str) -> str:
    return _pwd.hash(mot_de_passe)


def verifier_mot_de_passe(mot_de_passe: str, hache: str) -> bool:
    return _pwd.verify(mot_de_passe, hache)


def creer_jeton_acces(utilisateur_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    return jwt.encode({"sub": str(utilisateur_id), "exp": expire}, settings.secret_key, algorithm=settings.algorithm)


def lire_jeton_acces(jeton: str) -> int:
    try:
        payload = jwt.decode(jeton, settings.secret_key, algorithms=[settings.algorithm])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError) as exc:
        raise NonAuthentifie("Jeton invalide ou expiré.") from exc


def hacher_jeton(jeton: str) -> str:
    return hashlib.sha256(jeton.encode()).hexdigest()


def nouveau_jeton_reinitialisation() -> tuple[str, str]:
    """Retourne (jeton à envoyer par e-mail, hachage à stocker)."""
    jeton = secrets.token_urlsafe(32)
    return jeton, hacher_jeton(jeton)
