"""Chiffrement du jeton d'accès au dépôt Git (Fernet). Le jeton n'est jamais réaffiché."""
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings
from app.core.exceptions import ErreurMetier


def _fernet() -> Fernet:
    if not settings.encryption_key:
        raise ErreurMetier("ENCRYPTION_KEY n'est pas configurée.")
    return Fernet(settings.encryption_key.encode())


def chiffrer(valeur: str) -> str:
    return _fernet().encrypt(valeur.encode()).decode()


def dechiffrer(valeur: str) -> str:
    try:
        return _fernet().decrypt(valeur.encode()).decode()
    except InvalidToken as exc:
        raise ErreurMetier("Jeton chiffré illisible : clé de chiffrement modifiée ?") from exc
