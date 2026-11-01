"""Problèmes, diagnostics et solutions de l'IA, retours, décision de correction."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.ai.service import ServiceIA, get_service_ia
from app.api.deps import utilisateur_courant
from app.api.helpers import application_autorisee, obtenir, probleme_autorise
from app.core.enums import Categorie, Gravite, Perm, Priorite, StatutProbleme
from app.core.exceptions import DonneesInvalides
from app.core.permissions import applications_accessibles_ids
from app.database import get_db
from app.fiabilite.service import ServiceFiabilite
from app.models import DecisionCorrection, Diagnostic, Probleme, Solution, Utilisateur
from app.schemas.probleme import (
    DecisionIn, DecisionOut, DiagnosticOut, ProblemeCreate, ProblemeOut, ProblemeUpdate, RetourSolutionIn, StatutIn,
)
from app.schemas.common import Message
from app.services import diagnostics as svc_diag
from app.services import problemes as svc
from app.services.historique import journaliser

router = APIRouter(tags=["Problèmes"])


def _filtrer(q, *, categorie, gravite, priorite, statut, responsable_id, recherche):
    for col, val in ((Probleme.categorie, categorie), (Probleme.gravite, gravite), (Probleme.priorite, priorite),
                     (Probleme.statut, statut), (Probleme.responsable_id, responsable_id)):
        if val is not None:
            q = q.where(col == (val.value if hasattr(val, "value") else val))
    if recherche:
        q = q.where(or_(Probleme.code.ilike(f"%{recherche}%"), Probleme.titre.ilike(f"%{recherche}%")))
    return q


@router.get("/problemes", response_model=list[ProblemeOut])
def lister_global(application_id: int | None = None, categorie: Categorie | None = None, gravite: Gravite | None = None,
                  priorite: Priorite | None = None, statut: StatutProbleme | None = None, responsable_id: int | None = None,
                  recherche: str | None = Query(None, description="code ou titre"), limit: int = 50, offset: int = 0,
                  db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    """Vue globale : agrège les applications accessibles, sans perdre l'origine (application_id)."""
    ids = applications_accessibles_ids(db, user)
    q = select(Probleme)
    if ids is not None:
        q = q.where(Probleme.application_id.in_(ids))
    if application_id:
        q = q.where(Probleme.application_id == application_id)
    q = _filtrer(q, categorie=categorie, gravite=gravite, priorite=priorite, statut=statut,
                 responsable_id=responsable_id, recherche=recherche)
    liste = db.execute(q.order_by(Probleme.cree_le.desc()).limit(min(limit, 200)).offset(offset)).scalars().all()
    ServiceFiabilite(db).annoter_problemes(liste)
    return liste


@router.get("/applications/{application_id}/problemes", response_model=list[ProblemeOut])
def lister(application_id: int, categorie: Categorie | None = None, gravite: Gravite | None = None,
           priorite: Priorite | None = None, statut: StatutProbleme | None = None, responsable_id: int | None = None,
           recherche: str | None = None, limit: int = 50, offset: int = 0,
           db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    application_autorisee(db, user, application_id, Perm.PROBLEME_CONSULTER)
    q = _filtrer(select(Probleme).where(Probleme.application_id == application_id), categorie=categorie,
                 gravite=gravite, priorite=priorite, statut=statut, responsable_id=responsable_id, recherche=recherche)
    liste = db.execute(q.order_by(Probleme.cree_le.desc()).limit(min(limit, 200)).offset(offset)).scalars().all()
    ServiceFiabilite(db).annoter_problemes(liste)
    return liste


@router.post("/applications/{application_id}/problemes", response_model=ProblemeOut, status_code=201)
def creer(application_id: int, data: ProblemeCreate, db: Session = Depends(get_db),
          user: Utilisateur = Depends(utilisateur_courant)):
    """Création manuelle : le problème a la source « humain » et aucun résultat d'origine."""
    app = application_autorisee(db, user, application_id, Perm.PROBLEME_MODIFIER, ecriture=True)
    return svc.creer_probleme(db, app, user, data)


@router.get("/problemes/{probleme_id}", response_model=ProblemeOut)
def detail(probleme_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    p = probleme_autorise(db, user, probleme_id, Perm.PROBLEME_CONSULTER)[0]
    ServiceFiabilite(db).annoter_problemes([p])
    return p


@router.patch("/problemes/{probleme_id}", response_model=ProblemeOut)
def modifier(probleme_id: int, data: ProblemeUpdate, db: Session = Depends(get_db),
             user: Utilisateur = Depends(utilisateur_courant)):
    """Le code et la date de création ne sont pas modifiables ; chaque changement est tracé."""
    p, app = probleme_autorise(db, user, probleme_id, Perm.PROBLEME_MODIFIER, ecriture=True)
    champs = data.model_dump(exclude_unset=True)
    champs = {k: (v.value if hasattr(v, "value") else v) for k, v in champs.items()}
    avant = {k: str(getattr(p, k)) for k in champs}
    for k, v in champs.items():
        setattr(p, k, v)
    journaliser(db, application_id=app.id, type_element="probleme", element_id=p.id, action="probleme_modifie",
                auteur_id=user.id, ancienne=avant, nouvelle={k: str(v) for k, v in champs.items()})
    return p


@router.post("/problemes/{probleme_id}/statut", response_model=ProblemeOut)
def changer_statut(probleme_id: int, data: StatutIn, db: Session = Depends(get_db),
                   user: Utilisateur = Depends(utilisateur_courant)):
    """Seules les transitions manuelles autorisées sont acceptées. « à tester », « testé » et « rouvert »
    (après test) passent par la demande de test et le retour du testeur."""
    p, _ = probleme_autorise(db, user, probleme_id, Perm.PROBLEME_MODIFIER, ecriture=True)
    svc.changer_statut(db, p, data.statut.value, user.id, motif=data.motif)
    return p


# ---------- Diagnostics et solutions (l'IA propose, elle ne modifie jamais le code) ----------

@router.post("/problemes/{probleme_id}/diagnostics", response_model=DiagnosticOut, status_code=201)
def demander_diagnostic(probleme_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant),
                        ia: ServiceIA = Depends(get_service_ia)):
    """Crée un NOUVEAU diagnostic (les précédents sont conservés). 503 si le service d'IA est indisponible."""
    p, _ = probleme_autorise(db, user, probleme_id, Perm.PROBLEME_MODIFIER, ecriture=True)
    d = svc_diag.generer_diagnostic(db, p, user, ia)
    ServiceFiabilite(db).annoter_diagnostics([d])
    return d


@router.get("/problemes/{probleme_id}/diagnostics", response_model=list[DiagnosticOut])
def diagnostics(probleme_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    p, _ = probleme_autorise(db, user, probleme_id, Perm.PROBLEME_CONSULTER)
    liste = db.execute(select(Diagnostic).where(Diagnostic.probleme_id == p.id).order_by(Diagnostic.cree_le.desc())).scalars().all()
    ServiceFiabilite(db).annoter_diagnostics(liste)
    return liste


@router.post("/solutions/{solution_id}/retour", response_model=Message, status_code=201)
def retour_solution(solution_id: int, data: RetourSolutionIn, db: Session = Depends(get_db),
                    user: Utilisateur = Depends(utilisateur_courant)):
    """Évaluation de l'utilité PERÇUE d'une solution (la réussite vient du testeur)."""
    s = obtenir(db.get(Solution, solution_id), "Solution introuvable.")
    d = db.get(Diagnostic, s.diagnostic_id)
    p, _ = probleme_autorise(db, user, d.probleme_id, Perm.SOLUTION_DECIDER, ecriture=True)
    svc_diag.enregistrer_retour(db, s, p, user, data)
    return Message(message="Retour enregistré.")


# ---------- Décision de correction ----------

def _decision_out(db: Session, d: DecisionCorrection) -> DecisionOut:
    out = DecisionOut.model_validate(d)
    out.solution_ids = svc_diag.solutions_de_la_decision(db, d)
    return out


@router.post("/problemes/{probleme_id}/decisions", response_model=DecisionOut, status_code=201)
def decider(probleme_id: int, data: DecisionIn, db: Session = Depends(get_db),
            user: Utilisateur = Depends(utilisateur_courant)):
    """Le développeur retient, adapte ou ignore les solutions de l'IA, ou prend sa propre voie. La justification
    est facultative ; l'IA n'applique rien au dépôt."""
    p, app = probleme_autorise(db, user, probleme_id, Perm.SOLUTION_DECIDER, ecriture=True)
    return _decision_out(db, svc_diag.enregistrer_decision(db, app, p, user, data))


@router.get("/problemes/{probleme_id}/decisions", response_model=list[DecisionOut])
def decisions(probleme_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    p, _ = probleme_autorise(db, user, probleme_id, Perm.PROBLEME_CONSULTER)
    ds = db.execute(select(DecisionCorrection).where(DecisionCorrection.probleme_id == p.id)
                    .order_by(DecisionCorrection.cree_le.desc())).scalars().all()
    return [_decision_out(db, d) for d in ds]
