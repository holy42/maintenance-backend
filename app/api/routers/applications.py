"""Applications, dépôt Git (un seul par application, lecture seule), membres (lecture seule), vue d'ensemble."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import utilisateur_courant
from app.api.helpers import application_autorisee
from app.core.crypto import chiffrer, dechiffrer
from app.core.enums import Perm
from app.core.permissions import applications_accessibles_ids, charger_application, verifier_acces
from app.database import get_db
from app.models import Application, DepotGit, MembreEquipe, Role, Utilisateur
from app.schemas.acces import MembreOut
from app.schemas.application import ApplicationCreate, ApplicationOut, ApplicationUpdate, DepotIn, DepotOut
from app.schemas.common import Message
from app.services import applications as svc
from app.services import git_service
from app.services.historique import journaliser

router = APIRouter(tags=["Applications"])


def _sorties(db: Session, apps: list[Application]) -> list[ApplicationOut]:
    technos = svc.technologies_par_application(db, [a.id for a in apps])
    return [ApplicationOut.model_validate(a).model_copy(update={"technologies": technos.get(a.id, [])}) for a in apps]


@router.get("/applications", response_model=list[ApplicationOut])
def lister(statut: str | None = None, q: str | None = None, equipe_id: int | None = None,
           db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    """Uniquement les applications des équipes de l'utilisateur."""
    ids = applications_accessibles_ids(db, user)
    req = select(Application).order_by(Application.nom)
    if ids is not None:
        req = req.where(Application.id.in_(ids))
    if statut:
        req = req.where(Application.statut == statut)
    if equipe_id:
        req = req.where(Application.equipe_id == equipe_id)
    if q:
        req = req.where(Application.nom.ilike(f"%{q}%"))
    return _sorties(db, list(db.execute(req).scalars().all()))


@router.post("/applications", response_model=ApplicationOut, status_code=201)
def creer(data: ApplicationCreate, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    return _sorties(db, [svc.creer_application(db, user, data)])[0]


@router.get("/applications/{application_id}", response_model=ApplicationOut)
def detail(application_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    return _sorties(db, [application_autorisee(db, user, application_id)])[0]


@router.patch("/applications/{application_id}", response_model=ApplicationOut)
def modifier(application_id: int, data: ApplicationUpdate, db: Session = Depends(get_db),
             user: Utilisateur = Depends(utilisateur_courant)):
    app = application_autorisee(db, user, application_id, Perm.APPLICATION_CONFIGURER, ecriture=True)
    return _sorties(db, [svc.modifier_application(db, app, user, data)])[0]


@router.post("/applications/{application_id}/archiver", response_model=ApplicationOut)
def archiver(application_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    app = application_autorisee(db, user, application_id, Perm.APPLICATION_CONFIGURER, ecriture=True)
    return _sorties(db, [svc.definir_statut(db, app, user, "archivee")])[0]


@router.post("/applications/{application_id}/restaurer", response_model=ApplicationOut)
def restaurer(application_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    app = application_autorisee(db, user, application_id, Perm.APPLICATION_CONFIGURER)
    return _sorties(db, [svc.definir_statut(db, app, user, "active")])[0]


@router.get("/applications/{application_id}/membres", response_model=list[MembreOut])
def membres(application_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    """Lecture seule : l'accès se règle par équipe (les rôles se modifient dans l'administration)."""
    app = application_autorisee(db, user, application_id)
    lignes = db.execute(
        select(MembreEquipe, Utilisateur.identifiant, Role.nom).join(Utilisateur, Utilisateur.id == MembreEquipe.utilisateur_id)
        .join(Role, Role.id == MembreEquipe.role_id).where(MembreEquipe.equipe_id == app.equipe_id)
        .order_by(Utilisateur.identifiant)).all()
    return [MembreOut(utilisateur_id=m.utilisateur_id, identifiant=i, role_id=m.role_id, role=r) for m, i, r in lignes]


@router.get("/applications/{application_id}/mes-permissions")
def mes_permissions(application_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    """Permissions de l'utilisateur dans l'équipe de l'application ("*" = administrateur). L'interface s'en sert
    pour masquer des boutons ; la vraie protection reste le contrôle côté serveur."""
    app = charger_application(db, application_id)
    perms = verifier_acces(db, user, app)
    return {"permissions": sorted(perms), "est_admin": user.est_admin, "archivee": app.statut == "archivee"}


@router.get("/applications/{application_id}/vue-ensemble")
def vue_ensemble(application_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    return svc.vue_ensemble(db, application_autorisee(db, user, application_id))


# ---------- Dépôt Git ----------

def _depot_out(d: DepotGit) -> DepotOut:
    return DepotOut(id=d.id, application_id=d.application_id, url=d.url, branche_defaut=d.branche_defaut,
                    derniere_synchro_le=d.derniere_synchro_le, jeton_configure=bool(d.jeton_acces_chiffre))


def _depot(db: Session, application_id: int) -> DepotGit | None:
    return db.execute(select(DepotGit).where(DepotGit.application_id == application_id)).scalar_one_or_none()


@router.get("/applications/{application_id}/depot", response_model=DepotOut | None)
def lire_depot(application_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    application_autorisee(db, user, application_id)
    d = _depot(db, application_id)
    return _depot_out(d) if d else None


@router.put("/applications/{application_id}/depot", response_model=DepotOut)
def definir_depot(application_id: int, data: DepotIn, db: Session = Depends(get_db),
                  user: Utilisateur = Depends(utilisateur_courant)):
    app = application_autorisee(db, user, application_id, Perm.APPLICATION_CONFIGURER, ecriture=True)
    url, branche = git_service.valider_url(data.url), git_service.valider_branche(data.branche_defaut)
    d = _depot(db, app.id)
    if d is None:
        d = DepotGit(application_id=app.id, url=url, branche_defaut=branche)
        db.add(d)
    d.url, d.branche_defaut = url, branche
    if data.jeton:                                        # le jeton est chiffré et n'est jamais renvoyé
        d.jeton_acces_chiffre = chiffrer(data.jeton)
    db.flush()
    journaliser(db, application_id=app.id, type_element="depot", element_id=d.id, action="depot_configure", auteur_id=user.id)
    return _depot_out(d)


@router.post("/applications/{application_id}/depot/tester")
def tester_depot(application_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    app = application_autorisee(db, user, application_id, Perm.APPLICATION_CONFIGURER)
    d = _depot(db, app.id)
    if d is None:
        return Message(message="Aucun dépôt configuré.")
    jeton = dechiffrer(d.jeton_acces_chiffre) if d.jeton_acces_chiffre else None
    return {"connecte": True, "branches": git_service.tester_connexion(d.url, jeton)}


@router.get("/applications/{application_id}/depot/commits")
def commits(application_id: int, branche: str = Query("develop"), db: Session = Depends(get_db),
            user: Utilisateur = Depends(utilisateur_courant)):
    application_autorisee(db, user, application_id)
    return git_service.commits_recents(application_id, branche)
