"""Vérifications à la demande et résultats d'analyse (outil, hypothèse de l'IA, ou décision humaine)."""
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import utilisateur_courant
from app.api.helpers import application_autorisee, resultat_autorise, verification_autorisee
from app.core.enums import Perm
from app.database import get_db
from app.fiabilite.service import ServiceFiabilite
from app.models import ResultatAnalyse, Utilisateur, Verification
from app.schemas.probleme import ProblemeOut
from app.schemas.verification import (
    CritereOut, DecisionResultatIn, ResultatOut, VerificationCreate, VerificationOut,
)
from app.services import problemes as svc_pb
from app.services import verifications as svc

router = APIRouter(tags=["Vérifications"])


@router.get("/applications/{application_id}/verifications", response_model=list[VerificationOut])
def lister(application_id: int, statut: str | None = None, branche: str | None = None, limit: int = 50, offset: int = 0,
           db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    application_autorisee(db, user, application_id, Perm.PROBLEME_CONSULTER)
    q = select(Verification).where(Verification.application_id == application_id)
    if statut:
        q = q.where(Verification.statut == statut)
    if branche:
        q = q.where(Verification.branche == branche)
    return db.execute(q.order_by(Verification.debut_le.desc()).limit(min(limit, 200)).offset(offset)).scalars().all()


@router.post("/applications/{application_id}/verifications", response_model=VerificationOut, status_code=202)
def lancer(application_id: int, data: VerificationCreate, taches: BackgroundTasks, db: Session = Depends(get_db),
           user: Utilisateur = Depends(utilisateur_courant)):
    """Crée la vérification puis l'exécute EN ARRIÈRE-PLAN. L'interface suit son état par interrogation
    (GET /verifications/{id}) : en_attente -> en_cours -> terminee | echouee."""
    app = application_autorisee(db, user, application_id, Perm.VERIFICATION_LANCER, ecriture=True)
    v = svc.creer_verification(db, app, user, data)
    db.commit()                                   # la tâche d'arrière-plan doit retrouver la vérification
    taches.add_task(svc.executer_verification, v.id)
    return v


@router.get("/verifications/{verification_id}", response_model=VerificationOut)
def detail(verification_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    return verification_autorisee(db, user, verification_id, Perm.PROBLEME_CONSULTER)[0]


@router.get("/verifications/{verification_id}/resultats", response_model=list[ResultatOut])
def resultats(verification_id: int, categorie: str | None = None, source: str | None = None,
              statut_validation: str | None = None, db: Session = Depends(get_db),
              user: Utilisateur = Depends(utilisateur_courant)):
    v, _ = verification_autorisee(db, user, verification_id, Perm.PROBLEME_CONSULTER)
    q = select(ResultatAnalyse).where(ResultatAnalyse.verification_id == v.id)
    for col, val in ((ResultatAnalyse.categorie, categorie), (ResultatAnalyse.source, source),
                     (ResultatAnalyse.statut_validation, statut_validation)):
        if val:
            q = q.where(col == val)
    liste = db.execute(q.order_by(ResultatAnalyse.id)).scalars().all()
    ServiceFiabilite(db).annoter_resultats(liste)
    return liste


@router.get("/verifications/{verification_id}/criteres-manuels", response_model=list[CritereOut])
def criteres_manuels(verification_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    """Critères à validation humaine : non exécutés automatiquement, à vérifier à la main."""
    v, _ = verification_autorisee(db, user, verification_id, Perm.PROBLEME_CONSULTER)
    return svc.criteres_a_verifier_manuellement(db, v)


@router.get("/resultats/{resultat_id}", response_model=ResultatOut)
def resultat(resultat_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    r = resultat_autorise(db, user, resultat_id, Perm.PROBLEME_CONSULTER)[0]
    ServiceFiabilite(db).annoter_resultats([r])
    return r


@router.post("/resultats/{resultat_id}/confirmer", response_model=ProblemeOut, status_code=201)
def confirmer(resultat_id: int, data: DecisionResultatIn, db: Session = Depends(get_db),
              user: Utilisateur = Depends(utilisateur_courant)):
    """Décision humaine : confirme le résultat et crée le problème (un résultat à la fois)."""
    r, v, app = resultat_autorise(db, user, resultat_id, Perm.PROBLEME_MODIFIER, ecriture=True)
    return svc_pb.confirmer_resultat(db, app, user, r, v, data.titre, data.motif)


@router.post("/resultats/{resultat_id}/ecarter", response_model=ResultatOut)
def ecarter(resultat_id: int, data: DecisionResultatIn, db: Session = Depends(get_db),
            user: Utilisateur = Depends(utilisateur_courant)):
    r, _, app = resultat_autorise(db, user, resultat_id, Perm.PROBLEME_MODIFIER, ecriture=True)
    svc_pb.ecarter_resultat(db, app, user, r, data.motif)
    ServiceFiabilite(db).annoter_resultats([r])
    return r
