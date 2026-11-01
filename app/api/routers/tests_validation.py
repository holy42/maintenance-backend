"""Tests : un seul test par problème (avec description), passages numérotés. File ouverte à tous les testeurs,
le testeur qui prend un test est enregistré. Retour « validé » ou « non validé » (commentaire obligatoire si refus)."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.service import ServiceIA, get_service_ia
from app.api.deps import utilisateur_courant
from app.api.helpers import application_autorisee, probleme_autorise, session_autorisee
from app.core.enums import Perm
from app.database import get_db
from app.models import CritereAcceptation, Probleme, SessionTest, Tache, TestCorrection, Utilisateur
from app.schemas.tache import CritereAcceptationOut
from app.schemas.validation import DemandeTestIn, RetourTesteurIn, SessionOut, TestDescriptionIn
from app.services import tests_validation as svc

router = APIRouter(tags=["Tests"])


@router.get("/applications/{application_id}/tests/sessions", response_model=list[SessionOut])
def lister(application_id: int, statut: str | None = None, mes_tests: bool = False, db: Session = Depends(get_db),
           user: Utilisateur = Depends(utilisateur_courant)):
    application_autorisee(db, user, application_id, Perm.PROBLEME_CONSULTER)
    q = (select(SessionTest, Probleme.id, Probleme.code, Probleme.titre)
         .join(TestCorrection, TestCorrection.id == SessionTest.test_id)
         .join(Probleme, Probleme.id == TestCorrection.probleme_id)
         .where(SessionTest.application_id == application_id))
    if statut:
        q = q.where(SessionTest.statut == statut)
    if mes_tests:
        q = q.where(SessionTest.testeur_id == user.id)
    lignes = db.execute(q.order_by(SessionTest.demande_le.desc())).all()
    return [SessionOut.model_validate(s).model_copy(update={"probleme_id": pid, "probleme_code": code, "probleme_titre": titre})
            for s, pid, code, titre in lignes]


@router.get("/problemes/{probleme_id}/test")
def lire_test(probleme_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    p, _ = probleme_autorise(db, user, probleme_id, Perm.PROBLEME_CONSULTER)
    t = db.execute(select(TestCorrection).where(TestCorrection.probleme_id == p.id)).scalar_one_or_none()
    if t is None:
        return {"test": None, "sessions": []}
    sessions = db.execute(select(SessionTest).where(SessionTest.test_id == t.id).order_by(SessionTest.numero)).scalars().all()
    return {"test": {"id": t.id, "description": t.description, "origine": t.origine, "cree_le": t.cree_le},
            "sessions": [SessionOut.model_validate(s) for s in sessions]}


@router.put("/problemes/{probleme_id}/test")
def definir_description(probleme_id: int, data: TestDescriptionIn, db: Session = Depends(get_db),
                        user: Utilisateur = Depends(utilisateur_courant)):
    p, app = probleme_autorise(db, user, probleme_id, Perm.PROBLEME_MODIFIER, ecriture=True)
    t = svc.definir_description_test(db, app, p, user, data.description)
    return {"id": t.id, "description": t.description}


@router.post("/problemes/{probleme_id}/test/description-proposee")
def description_proposee(probleme_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant),
                        ia: ServiceIA = Depends(get_service_ia)):
    """Proposition de l'IA (non enregistrée) pour rédiger la description du test."""
    p, _ = probleme_autorise(db, user, probleme_id, Perm.PROBLEME_MODIFIER)
    return {"description": svc.proposer_description(db, p, ia)}


@router.post("/problemes/{probleme_id}/test/demander", response_model=SessionOut, status_code=201)
def demander(probleme_id: int, data: DemandeTestIn, db: Session = Depends(get_db),
             user: Utilisateur = Depends(utilisateur_courant)):
    """Possible seulement si toutes les tâches du problème sont terminées (les arrêtées ne bloquent pas)."""
    p, app = probleme_autorise(db, user, probleme_id, Perm.PROBLEME_MODIFIER, ecriture=True)
    return svc.demander_test(db, app, p, user, data.description)


@router.get("/tests/sessions/{session_id}")
def detail(session_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    """Ce qu'il faut tester : description du test, critères d'acceptation des tâches, branche à tester."""
    s, test, _ = session_autorisee(db, user, session_id, Perm.PROBLEME_CONSULTER)
    criteres = db.execute(select(CritereAcceptation).join(Tache, Tache.id == CritereAcceptation.tache_id)
                          .where(Tache.probleme_id == test.probleme_id).order_by(CritereAcceptation.id)).scalars().all()
    return {"session": SessionOut.model_validate(s), "probleme_id": test.probleme_id, "description_test": test.description,
            "criteres_acceptation": [CritereAcceptationOut.model_validate(c) for c in criteres]}


@router.post("/tests/sessions/{session_id}/prendre", response_model=SessionOut)
def prendre(session_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    s, _, _ = session_autorisee(db, user, session_id, Perm.TEST_VALIDER)
    return svc.prendre_en_charge(db, s, user)


@router.post("/tests/sessions/{session_id}/retour", response_model=SessionOut)
def retour(session_id: int, data: RetourTesteurIn, db: Session = Depends(get_db),
           user: Utilisateur = Depends(utilisateur_courant)):
    """validé -> problème « testé » ; non validé -> problème « rouvert »."""
    s, _, _ = session_autorisee(db, user, session_id, Perm.TEST_VALIDER)
    return svc.rendre_retour(db, s, user, data)
