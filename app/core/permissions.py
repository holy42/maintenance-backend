"""Contrôle d'accès CÔTÉ SERVEUR. L'accès se règle par équipe : une personne accède aux
applications des équipes dont elle est membre, avec les permissions de son rôle dans l'équipe.
L'administrateur de la plateforme (est_admin) a tous les droits."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AccesRefuse, Conflit, NonTrouve
from app.models import Application, MembreEquipe, Permission, RolePermission, Utilisateur

TOUS = "*"


def permissions_dans_equipe(db: Session, user: Utilisateur, equipe_id: int) -> set[str]:
    """Codes de permission de l'utilisateur dans l'équipe ({'*'} pour l'administrateur)."""
    if user.est_admin:
        return {TOUS}
    lignes = db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(MembreEquipe, MembreEquipe.role_id == RolePermission.role_id)
        .where(MembreEquipe.utilisateur_id == user.id, MembreEquipe.equipe_id == equipe_id)
    ).scalars()
    return set(lignes)


def est_membre(db: Session, user: Utilisateur, equipe_id: int) -> bool:
    if user.est_admin:
        return True
    return db.execute(
        select(MembreEquipe.equipe_id).where(
            MembreEquipe.utilisateur_id == user.id, MembreEquipe.equipe_id == equipe_id
        )
    ).first() is not None


def equipes_ids(db: Session, user: Utilisateur) -> list[int]:
    return list(db.execute(select(MembreEquipe.equipe_id).where(MembreEquipe.utilisateur_id == user.id)).scalars())


def applications_accessibles_ids(db: Session, user: Utilisateur) -> list[int] | None:
    """None = toutes les applications (administrateur)."""
    if user.est_admin:
        return None
    return list(
        db.execute(select(Application.id).where(Application.equipe_id.in_(equipes_ids(db, user)))).scalars()
    )


def charger_application(db: Session, application_id: int) -> Application:
    app = db.get(Application, application_id)
    if app is None:
        raise NonTrouve("Application introuvable.")
    return app


def verifier_acces(
    db: Session, user: Utilisateur, application: Application, permission: str | None = None, ecriture: bool = False
) -> set[str]:
    """404 si la personne n'a pas accès à l'application (on ne révèle pas son existence),
    403 s'il manque la permission, 409 si l'application est archivée et qu'on veut écrire."""
    if not est_membre(db, user, application.equipe_id):
        raise NonTrouve("Application introuvable.")
    perms = permissions_dans_equipe(db, user, application.equipe_id)
    if permission and TOUS not in perms and permission not in perms:
        raise AccesRefuse(f"Permission requise : {permission}.")
    if ecriture and application.statut == "archivee":
        raise Conflit("Application archivée : lecture seule.")
    return perms


def a_permission(perms: set[str], code: str) -> bool:
    return TOUS in perms or code in perms


def exiger_admin(user: Utilisateur) -> None:
    if not user.est_admin:
        raise AccesRefuse("Réservé à l'administrateur de la plateforme.")
