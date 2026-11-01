import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.exceptions import DonneesInvalides, NonAuthentifie
from app.core.security import (
    creer_jeton_acces, hacher_jeton, hacher_mot_de_passe, nouveau_jeton_reinitialisation, verifier_mot_de_passe,
)
from app.models import ReinitialisationMotDePasse, Utilisateur
from app.services.historique import journaliser

log = logging.getLogger(__name__)


def connecter(db: Session, identifiant: str, mot_de_passe: str) -> str:
    user = db.execute(select(Utilisateur).where(Utilisateur.identifiant == identifiant)).scalar_one_or_none()
    # même message dans tous les cas : on ne révèle pas lequel des deux champs est faux
    if user is None or not user.actif or not verifier_mot_de_passe(mot_de_passe, user.mot_de_passe_hash):
        raise NonAuthentifie("Identifiant ou mot de passe incorrect.")
    return creer_jeton_acces(user.id)


def _envoyer_email(destinataire: str, sujet: str, corps: str) -> None:
    if not settings.smtp_enabled:
        log.warning("SMTP désactivé. E-mail non envoyé à %s : %s", destinataire, corps)   # développement
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.smtp_from, destinataire, sujet
    msg.set_content(corps)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_user:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


def demander_reinitialisation(db: Session, identifiant_ou_email: str) -> None:
    """Répond toujours de la même façon (pas d'énumération des comptes)."""
    user = db.execute(
        select(Utilisateur).where(
            or_(Utilisateur.identifiant == identifiant_ou_email, Utilisateur.email == identifiant_ou_email),
            Utilisateur.actif.is_(True),
        )
    ).scalar_one_or_none()
    if user is None or not user.email:
        return
    jeton, hache = nouveau_jeton_reinitialisation()
    db.add(ReinitialisationMotDePasse(
        utilisateur_id=user.id, jeton_hash=hache,
        expire_le=datetime.now(timezone.utc) + timedelta(minutes=settings.reset_token_minutes),
    ))
    lien = f"{settings.frontend_url}/reinitialiser-mot-de-passe?jeton={jeton}"
    _envoyer_email(user.email, "Réinitialisation de votre mot de passe", f"Pour choisir un nouveau mot de passe : {lien}")


def reinitialiser(db: Session, jeton: str, nouveau: str) -> None:
    r = db.execute(
        select(ReinitialisationMotDePasse).where(ReinitialisationMotDePasse.jeton_hash == hacher_jeton(jeton))
    ).scalar_one_or_none()
    maintenant = datetime.now(timezone.utc)
    if r is None or r.utilise_le is not None or r.expire_le < maintenant:
        raise DonneesInvalides("Lien de réinitialisation invalide ou expiré.")
    user = db.get(Utilisateur, r.utilisateur_id)
    user.mot_de_passe_hash = hacher_mot_de_passe(nouveau)
    r.utilise_le = maintenant
    journaliser(db, application_id=None, type_element="utilisateur", element_id=user.id,
                action="mot_de_passe_reinitialise", auteur_id=user.id)


def changer_mot_de_passe(db: Session, user: Utilisateur, ancien: str, nouveau: str) -> None:
    if not verifier_mot_de_passe(ancien, user.mot_de_passe_hash):
        raise DonneesInvalides("Mot de passe actuel incorrect.")
    user.mot_de_passe_hash = hacher_mot_de_passe(nouveau)
    journaliser(db, application_id=None, type_element="utilisateur", element_id=user.id,
                action="mot_de_passe_modifie", auteur_id=user.id)
