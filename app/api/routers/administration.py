"""Administration : utilisateurs, équipes, rôles et permissions (administrateur de la plateforme)."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import utilisateur_courant
from app.api.helpers import obtenir
from app.core.exceptions import Conflit, DonneesInvalides, NonTrouve
from app.core.permissions import equipes_ids, exiger_admin
from app.core.security import hacher_mot_de_passe
from app.database import get_db
from app.models import Equipe, MembreEquipe, Permission, Role, RolePermission, Utilisateur
from app.schemas.acces import (
    EquipeIn, EquipeOut, MembreIn, MembreOut, PermissionOut, RoleOut, RolePermissionsIn, UtilisateurCreate,
    UtilisateurOut, UtilisateurUpdate,
)
from app.schemas.common import Message
from app.services import auth
from app.services.historique import journaliser

router = APIRouter(tags=["Administration"])


def _admin(user: Utilisateur = Depends(utilisateur_courant)) -> Utilisateur:
    exiger_admin(user)
    return user


# ---------- Utilisateurs ----------

@router.get("/utilisateurs", response_model=list[UtilisateurOut])
def lister_utilisateurs(db: Session = Depends(get_db), _: Utilisateur = Depends(_admin)):
    return db.execute(select(Utilisateur).order_by(Utilisateur.identifiant)).scalars().all()


@router.post("/utilisateurs", response_model=UtilisateurOut, status_code=201)
def creer_utilisateur(data: UtilisateurCreate, db: Session = Depends(get_db), admin: Utilisateur = Depends(_admin)):
    if db.execute(select(Utilisateur.id).where(Utilisateur.identifiant == data.identifiant)).first():
        raise Conflit("Cet identifiant existe déjà.")
    u = Utilisateur(identifiant=data.identifiant, email=data.email, est_admin=data.est_admin,
                    mot_de_passe_hash=hacher_mot_de_passe(data.mot_de_passe))
    db.add(u)
    db.flush()
    journaliser(db, application_id=None, type_element="utilisateur", element_id=u.id, action="utilisateur_cree", auteur_id=admin.id)
    return u


@router.patch("/utilisateurs/{uid}", response_model=UtilisateurOut)
def modifier_utilisateur(uid: int, data: UtilisateurUpdate, db: Session = Depends(get_db), admin: Utilisateur = Depends(_admin)):
    u = obtenir(db.get(Utilisateur, uid), "Utilisateur introuvable.")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(u, k, v)
    journaliser(db, application_id=None, type_element="utilisateur", element_id=u.id, action="utilisateur_modifie", auteur_id=admin.id)
    return u


@router.post("/utilisateurs/{uid}/desactiver", response_model=UtilisateurOut)
def desactiver(uid: int, db: Session = Depends(get_db), admin: Utilisateur = Depends(_admin)):
    """On désactive, on ne supprime jamais (l'historique référence les auteurs)."""
    u = obtenir(db.get(Utilisateur, uid), "Utilisateur introuvable.")
    if u.id == admin.id:
        raise Conflit("Vous ne pouvez pas désactiver votre propre compte.")
    u.actif = False
    journaliser(db, application_id=None, type_element="utilisateur", element_id=u.id, action="utilisateur_desactive", auteur_id=admin.id)
    return u


@router.post("/utilisateurs/{uid}/reactiver", response_model=UtilisateurOut)
def reactiver(uid: int, db: Session = Depends(get_db), admin: Utilisateur = Depends(_admin)):
    u = obtenir(db.get(Utilisateur, uid), "Utilisateur introuvable.")
    u.actif = True
    journaliser(db, application_id=None, type_element="utilisateur", element_id=u.id, action="utilisateur_reactive", auteur_id=admin.id)
    return u


@router.post("/utilisateurs/{uid}/reinitialiser-mot-de-passe", response_model=Message)
def reinitialiser_mot_de_passe(uid: int, db: Session = Depends(get_db), admin: Utilisateur = Depends(_admin)):
    u = obtenir(db.get(Utilisateur, uid), "Utilisateur introuvable.")
    auth.demander_reinitialisation(db, u.identifiant)
    return Message(message="Un lien de réinitialisation a été envoyé à l'utilisateur (s'il a une adresse e-mail).")


# ---------- Équipes ----------

@router.get("/equipes", response_model=list[EquipeOut])
def lister_equipes(db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    q = select(Equipe).order_by(Equipe.nom)
    if not user.est_admin:
        q = q.where(Equipe.id.in_(equipes_ids(db, user)))
    return db.execute(q).scalars().all()


@router.post("/equipes", response_model=EquipeOut, status_code=201)
def creer_equipe(data: EquipeIn, db: Session = Depends(get_db), admin: Utilisateur = Depends(_admin)):
    e = Equipe(**data.model_dump())
    db.add(e)
    db.flush()
    journaliser(db, application_id=None, type_element="equipe", element_id=e.id, action="equipe_creee", auteur_id=admin.id)
    return e


@router.patch("/equipes/{eid}", response_model=EquipeOut)
def modifier_equipe(eid: int, data: EquipeIn, db: Session = Depends(get_db), admin: Utilisateur = Depends(_admin)):
    e = obtenir(db.get(Equipe, eid), "Équipe introuvable.")
    e.nom, e.description = data.nom, data.description
    return e


@router.get("/equipes/{eid}/membres", response_model=list[MembreOut])
def membres(eid: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    if not user.est_admin and eid not in equipes_ids(db, user):
        raise NonTrouve("Équipe introuvable.")
    lignes = db.execute(
        select(MembreEquipe, Utilisateur.identifiant, Role.nom).join(Utilisateur, Utilisateur.id == MembreEquipe.utilisateur_id)
        .join(Role, Role.id == MembreEquipe.role_id).where(MembreEquipe.equipe_id == eid).order_by(Utilisateur.identifiant)).all()
    return [MembreOut(utilisateur_id=m.utilisateur_id, identifiant=i, role_id=m.role_id, role=r) for m, i, r in lignes]


@router.post("/equipes/{eid}/membres", response_model=Message, status_code=201)
def attribuer_role(eid: int, data: MembreIn, db: Session = Depends(get_db), admin: Utilisateur = Depends(_admin)):
    """Ajoute un membre ou change son rôle dans l'équipe (l'administrateur attribue les rôles)."""
    if db.get(Equipe, eid) is None or db.get(Utilisateur, data.utilisateur_id) is None or db.get(Role, data.role_id) is None:
        raise DonneesInvalides("Équipe, utilisateur ou rôle introuvable.")
    m = db.get(MembreEquipe, (eid, data.utilisateur_id))
    if m is None:
        db.add(MembreEquipe(equipe_id=eid, utilisateur_id=data.utilisateur_id, role_id=data.role_id, attribue_par=admin.id))
    else:
        m.role_id, m.attribue_par = data.role_id, admin.id
    journaliser(db, application_id=None, type_element="equipe", element_id=eid, action="role_attribue",
                auteur_id=admin.id, nouvelle={"utilisateur": data.utilisateur_id, "role": data.role_id})
    return Message(message="Rôle attribué.")


@router.delete("/equipes/{eid}/membres/{uid}", response_model=Message)
def retirer_membre(eid: int, uid: int, db: Session = Depends(get_db), admin: Utilisateur = Depends(_admin)):
    m = obtenir(db.get(MembreEquipe, (eid, uid)), "Membre introuvable.")
    db.delete(m)          # ses notes, décisions et tests passés restent dans l'historique
    journaliser(db, application_id=None, type_element="equipe", element_id=eid, action="membre_retire",
                auteur_id=admin.id, nouvelle={"utilisateur": uid})
    return Message(message="Membre retiré de l'équipe.")


# ---------- Rôles et permissions ----------

@router.get("/roles", response_model=list[RoleOut])
def roles(db: Session = Depends(get_db), _: Utilisateur = Depends(utilisateur_courant)):
    return db.execute(select(Role).order_by(Role.nom)).scalars().all()


@router.get("/permissions", response_model=list[PermissionOut])
def permissions(db: Session = Depends(get_db), _: Utilisateur = Depends(utilisateur_courant)):
    return db.execute(select(Permission).order_by(Permission.code)).scalars().all()


@router.get("/roles/{rid}/permissions", response_model=list[PermissionOut])
def permissions_du_role(rid: int, db: Session = Depends(get_db), _: Utilisateur = Depends(_admin)):
    return db.execute(select(Permission).join(RolePermission, RolePermission.permission_id == Permission.id)
                      .where(RolePermission.role_id == rid).order_by(Permission.code)).scalars().all()


@router.put("/roles/{rid}/permissions", response_model=Message)
def definir_permissions(rid: int, data: RolePermissionsIn, db: Session = Depends(get_db), admin: Utilisateur = Depends(_admin)):
    if db.get(Role, rid) is None:
        raise NonTrouve("Rôle introuvable.")
    existantes = set(db.execute(select(Permission.id).where(Permission.id.in_(data.permission_ids))).scalars())
    if existantes != set(data.permission_ids):
        raise DonneesInvalides("Une permission n'existe pas.")
    db.query(RolePermission).filter(RolePermission.role_id == rid).delete()
    for pid in existantes:
        db.add(RolePermission(role_id=rid, permission_id=pid))
    journaliser(db, application_id=None, type_element="role", element_id=rid, action="permissions_modifiees",
                auteur_id=admin.id, nouvelle={"permissions": sorted(existantes)})
    return Message(message="Permissions enregistrées.")
