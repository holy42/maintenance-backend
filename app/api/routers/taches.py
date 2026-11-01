"""Tâches, sous-tâches et critères d'acceptation. Un problème peut avoir plusieurs tâches ; l'IA propose,
l'utilisateur choisit. Une tâche ne se termine que si toutes ses sous-tâches sont terminées."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.schemas import PropositionTaches
from app.ai.service import ServiceIA, get_service_ia
from app.api.deps import utilisateur_courant
from app.api.helpers import application_autorisee, probleme_autorise, tache_autorisee
from app.core.enums import Perm, StatutTache
from app.core.exceptions import AccesRefuse
from app.core.permissions import a_permission, applications_accessibles_ids
from app.database import get_db
from app.models import Probleme, Tache, Utilisateur
from app.schemas.common import Message
from app.schemas.tache import (
    CritereAcceptationIn, CritereAcceptationOut, SousTacheIn, SousTacheOut, StatutSousTacheIn, TacheOut, TachesCreate,
    TacheUpdate,
)
from app.services import taches as svc
from app.services.contexte_ia import contexte_probleme

router = APIRouter(tags=["Tâches"])


def _filtrer(q, statut, responsable_id, en_retard):
    if statut:
        q = q.where(Tache.statut == statut)
    if responsable_id:
        q = q.where(Tache.responsable_id == responsable_id)
    if en_retard:
        q = q.where(Tache.echeance < func.current_date(), Tache.statut.notin_(("terminee", "arretee")))
    return q


@router.get("/taches", response_model=list[TacheOut])
def lister_global(application_id: int | None = None, statut: StatutTache | None = None, responsable_id: int | None = None,
                  mes_taches: bool = False, en_retard: bool = False, limit: int = 100, offset: int = 0,
                  db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    ids = applications_accessibles_ids(db, user)
    q = select(Tache)
    if ids is not None:
        q = q.where(Tache.application_id.in_(ids))
    if application_id:
        q = q.where(Tache.application_id == application_id)
    q = _filtrer(q, statut.value if statut else None, user.id if mes_taches else responsable_id, en_retard)
    return db.execute(q.order_by(Tache.echeance.nulls_last(), Tache.id).limit(min(limit, 300)).offset(offset)).scalars().all()


@router.get("/applications/{application_id}/taches", response_model=list[TacheOut])
def lister(application_id: int, statut: StatutTache | None = None, responsable_id: int | None = None,
           mes_taches: bool = False, en_retard: bool = False, db: Session = Depends(get_db),
           user: Utilisateur = Depends(utilisateur_courant)):
    application_autorisee(db, user, application_id, Perm.PROBLEME_CONSULTER)
    q = _filtrer(select(Tache).where(Tache.application_id == application_id), statut.value if statut else None,
                 user.id if mes_taches else responsable_id, en_retard)
    return db.execute(q.order_by(Tache.echeance.nulls_last(), Tache.id)).scalars().all()


@router.get("/problemes/{probleme_id}/taches", response_model=list[TacheOut])
def taches_du_probleme(probleme_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    p, _ = probleme_autorise(db, user, probleme_id, Perm.PROBLEME_CONSULTER)
    return db.execute(select(Tache).where(Tache.probleme_id == p.id).order_by(Tache.id)).scalars().all()


@router.post("/problemes/{probleme_id}/taches/proposition", response_model=PropositionTaches)
def proposer(probleme_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant),
             ia: ServiceIA = Depends(get_service_ia)):
    """Propositions de l'IA (plusieurs tâches possibles), NON enregistrées : l'utilisateur retient, modifie ou ajoute."""
    p, _ = probleme_autorise(db, user, probleme_id, Perm.TACHE_GERER)
    return ia.proposer_taches(contexte_probleme(db, p))


@router.post("/problemes/{probleme_id}/taches", response_model=list[TacheOut], status_code=201)
def creer(probleme_id: int, data: TachesCreate, db: Session = Depends(get_db),
          user: Utilisateur = Depends(utilisateur_courant)):
    """Création à l'initiative de l'utilisateur : une ou plusieurs tâches, avec sous-tâches et critères d'acceptation."""
    p, app = probleme_autorise(db, user, probleme_id, Perm.TACHE_GERER, ecriture=True)
    return svc.creer_taches(db, app, p, user, data.taches)


@router.get("/taches/{tache_id}", response_model=TacheOut)
def detail(tache_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    return tache_autorisee(db, user, tache_id, Perm.PROBLEME_CONSULTER)[0]


@router.patch("/taches/{tache_id}", response_model=TacheOut)
def modifier(tache_id: int, data: TacheUpdate, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    t, app, _ = tache_autorisee(db, user, tache_id, Perm.TACHE_GERER, ecriture=True)
    return svc.modifier_tache(db, t, app, user, data)


def _agir(db: Session, user: Utilisateur, tache_id: int, nouveau: str) -> Tache:
    t, _, perms = tache_autorisee(db, user, tache_id, ecriture=True)
    if not (a_permission(perms, Perm.TACHE_GERER) or t.responsable_id == user.id):
        raise AccesRefuse("Réservé au responsable de la tâche ou à une personne pouvant gérer les tâches.")
    return svc.changer_statut_tache(db, t, nouveau, user)


@router.post("/taches/{tache_id}/demarrer", response_model=TacheOut)
def demarrer(tache_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    return _agir(db, user, tache_id, StatutTache.EN_COURS)


@router.post("/taches/{tache_id}/pause", response_model=TacheOut)
def pause(tache_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    return _agir(db, user, tache_id, StatutTache.EN_PAUSE)


@router.post("/taches/{tache_id}/arreter", response_model=TacheOut)
def arreter(tache_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    return _agir(db, user, tache_id, StatutTache.ARRETEE)


@router.post("/taches/{tache_id}/terminer", response_model=TacheOut)
def terminer(tache_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    return _agir(db, user, tache_id, StatutTache.TERMINEE)


@router.post("/taches/{tache_id}/sous-taches", response_model=SousTacheOut, status_code=201)
def ajouter_sous_tache(tache_id: int, data: SousTacheIn, db: Session = Depends(get_db),
                       user: Utilisateur = Depends(utilisateur_courant)):
    t, _, _ = tache_autorisee(db, user, tache_id, Perm.TACHE_GERER, ecriture=True)
    return svc.ajouter_sous_tache(db, t, data, user)


@router.patch("/taches/{tache_id}/sous-taches/{sous_tache_id}/statut", response_model=SousTacheOut)
def statut_sous_tache(tache_id: int, sous_tache_id: int, data: StatutSousTacheIn, db: Session = Depends(get_db),
                      user: Utilisateur = Depends(utilisateur_courant)):
    t, _, perms = tache_autorisee(db, user, tache_id, ecriture=True)
    if not (a_permission(perms, Perm.TACHE_GERER) or t.responsable_id == user.id):
        raise AccesRefuse("Réservé au responsable de la tâche ou à une personne pouvant gérer les tâches.")
    return svc.changer_statut_sous_tache(db, t, sous_tache_id, data.statut, user)


@router.delete("/taches/{tache_id}/sous-taches/{sous_tache_id}", response_model=Message)
def retirer_sous_tache(tache_id: int, sous_tache_id: int, db: Session = Depends(get_db),
                       user: Utilisateur = Depends(utilisateur_courant)):
    t, _, _ = tache_autorisee(db, user, tache_id, Perm.TACHE_GERER, ecriture=True)
    svc.retirer_sous_tache(db, t, sous_tache_id, user)
    return Message(message="Sous-tâche retirée.")


@router.post("/taches/{tache_id}/criteres-acceptation", response_model=CritereAcceptationOut, status_code=201)
def ajouter_critere(tache_id: int, data: CritereAcceptationIn, db: Session = Depends(get_db),
                    user: Utilisateur = Depends(utilisateur_courant)):
    t, _, _ = tache_autorisee(db, user, tache_id, Perm.TACHE_GERER, ecriture=True)
    return svc.ajouter_critere_acceptation(db, t, data.texte, data.origine, user)
