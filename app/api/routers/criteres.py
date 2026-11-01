from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.schemas import PropositionCritere
from app.ai.service import ServiceIA, get_service_ia
from app.api.deps import utilisateur_courant
from app.api.helpers import application_autorisee, critere_autorise
from app.core.enums import Perm
from app.core.permissions import exiger_admin
from app.database import get_db
from app.models import Utilisateur
from app.schemas.verification import CritereCreate, CritereOut, CritereUpdate, StructurerIn
from app.services import criteres as svc

router = APIRouter(tags=["Critères de vérification"])


@router.get("/applications/{application_id}/criteres", response_model=list[CritereOut])
def lister(application_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    return svc.lister(db, application_autorisee(db, user, application_id, Perm.PROBLEME_CONSULTER))


@router.post("/applications/{application_id}/criteres/structurer", response_model=PropositionCritere)
def structurer(application_id: int, data: StructurerIn, db: Session = Depends(get_db),
               user: Utilisateur = Depends(utilisateur_courant), ia: ServiceIA = Depends(get_service_ia)):
    """Proposition de l'IA (non enregistrée) : l'utilisateur la relit, l'ajuste puis la valide."""
    application_autorisee(db, user, application_id, Perm.CRITERE_GERER)
    return svc.proposer(ia, data.description)


@router.post("/applications/{application_id}/criteres", response_model=CritereOut, status_code=201)
def creer(application_id: int, data: CritereCreate, db: Session = Depends(get_db),
          user: Utilisateur = Depends(utilisateur_courant)):
    app = application_autorisee(db, user, application_id, Perm.CRITERE_GERER, ecriture=True)
    return svc.creer(db, app, user, data)


@router.patch("/criteres/{critere_id}", response_model=CritereOut)
def modifier(critere_id: int, data: CritereUpdate, db: Session = Depends(get_db),
             user: Utilisateur = Depends(utilisateur_courant)):
    c, _ = critere_autorise(db, user, critere_id, Perm.CRITERE_GERER)
    return svc.modifier(db, c, user, data)


@router.post("/criteres/{critere_id}/valider", response_model=CritereOut)
def valider(critere_id: int, activer: bool = False, db: Session = Depends(get_db),
            user: Utilisateur = Depends(utilisateur_courant)):
    c, _ = critere_autorise(db, user, critere_id, Perm.CRITERE_GERER)
    return svc.valider(db, c, user, activer)


@router.post("/criteres/{critere_id}/activer", response_model=CritereOut)
def activer(critere_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    c, app = critere_autorise(db, user, critere_id, Perm.CRITERE_GERER)
    if app is None:
        exiger_admin(user)                  # un critère standard est commun à toutes les applications
    return svc.activer(db, c, user)


@router.post("/criteres/{critere_id}/desactiver", response_model=CritereOut)
def desactiver(critere_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    c, app = critere_autorise(db, user, critere_id, Perm.CRITERE_GERER)
    if app is None:
        exiger_admin(user)
    return svc.desactiver(db, c, user)
