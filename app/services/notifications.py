"""Notifications internes. Un événement crée une notification par destinataire autorisé,
en respectant les préférences. Chef de projet : seulement ce qui le concerne + problèmes critiques."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Application, MembreEquipe, Notification, PreferenceNotification, Role


def _desactive(db: Session, utilisateur_id: int, type_evenement: str) -> bool:
    pref = db.get(PreferenceNotification, (utilisateur_id, type_evenement))
    return pref is not None and not pref.active


def notifier(
    db: Session, destinataires: set[int] | list[int], *, type_evenement: str, message: str,
    application_id: int | None = None, type_element: str | None = None, element_id: int | None = None,
    declencheur_id: int | None = None,
) -> int:
    """Crée les notifications. Retourne le nombre créé. L'auteur de l'action n'est pas notifié."""
    n = 0
    for uid in set(destinataires):
        if uid == declencheur_id or _desactive(db, uid, type_evenement):
            continue
        db.add(Notification(
            destinataire_id=uid, application_id=application_id, type_evenement=type_evenement,
            message=message[:500], type_element=type_element, element_id=element_id,
            declencheur_id=declencheur_id,
        ))
        n += 1
    return n


def membres_avec_role(db: Session, application: Application, *noms_roles: str) -> set[int]:
    q = select(MembreEquipe.utilisateur_id).join(Role, Role.id == MembreEquipe.role_id).where(
        MembreEquipe.equipe_id == application.equipe_id
    )
    if noms_roles:
        q = q.where(Role.nom.in_(noms_roles))
    return set(db.execute(q).scalars())


def notifier_probleme_critique(db: Session, application: Application, probleme_id: int, titre: str,
                               declencheur_id: int | None = None) -> None:
    """Le chef de projet reçoit les problèmes critiques même s'ils ne le concernent pas."""
    notifier(
        db, membres_avec_role(db, application, "chef_projet"), type_evenement="probleme_critique",
        message=f"Problème critique : {titre}", application_id=application.id, type_element="probleme",
        element_id=probleme_id, declencheur_id=declencheur_id,
    )
