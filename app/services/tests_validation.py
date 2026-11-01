"""Test d'un problème : un seul test par problème (avec sa description), plusieurs passages numérotés.
La file est ouverte à tous les testeurs ; le testeur qui prend un test est toujours enregistré.
Un retour « non validé » fait passer le problème à « rouvert »."""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.service import ServiceIA
from app.core.enums import StatutProbleme as SP
from app.core.enums import StatutSession as SS
from app.core.enums import StatutTache as ST
from app.core.exceptions import AccesRefuse, Conflit, DonneesInvalides
from app.fiabilite.service import ServiceFiabilite
from app.models import (
    Application, CritereAcceptation, DecisionCorrection, DepotGit, HistoriqueStatut, Probleme, ResultatCritereAcceptation,
    SessionTest, Tache, TestCorrection, Utilisateur,
)
from app.schemas.validation import RetourTesteurIn
from app.services import collaboration as collab
from app.services import notifications as notif
from app.services import problemes as svc_pb
from app.services.contexte_ia import contexte_probleme
from app.services.historique import enregistrer_statut, journaliser


def branche_du_probleme(db: Session, p: Probleme) -> str:
    """develop (ou la branche par défaut du dépôt) ; après « rouvert », la branche porte le code du problème."""
    rouvert = db.scalar(select(func.count()).select_from(HistoriqueStatut).where(
        HistoriqueStatut.type_element == "probleme", HistoriqueStatut.element_id == p.id,
        HistoriqueStatut.nouveau_statut == SP.ROUVERT))
    if rouvert:
        return p.code
    depot = db.execute(select(DepotGit).where(DepotGit.application_id == p.application_id)).scalar_one_or_none()
    return depot.branche_defaut if depot else "develop"


def _controler_enchainement(db: Session, p: Probleme) -> None:
    taches = db.execute(select(Tache).where(Tache.probleme_id == p.id)).scalars().all()
    if any(t.statut not in (ST.TERMINEE, ST.ARRETEE) for t in taches):
        raise Conflit("Test impossible : toutes les tâches du problème doivent être terminées.")
    derniere = db.scalar(select(func.max(HistoriqueStatut.cree_le)).where(
        HistoriqueStatut.type_element == "probleme", HistoriqueStatut.element_id == p.id,
        HistoriqueStatut.nouveau_statut == SP.ROUVERT))
    if not any(t.statut == ST.TERMINEE and (derniere is None or (t.fin_le and t.fin_le > derniere)) for t in taches):
        raise Conflit("Test impossible : aucune tâche terminée (depuis la dernière réouverture du problème).")


def definir_description_test(db: Session, app: Application, p: Probleme, user: Utilisateur, description: str,
                             origine: str = "utilisateur") -> TestCorrection:
    t = db.execute(select(TestCorrection).where(TestCorrection.probleme_id == p.id)).scalar_one_or_none()
    if t is None:
        t = TestCorrection(application_id=app.id, probleme_id=p.id, description=description,
                           origine=origine, redige_par=user.id)
        db.add(t)
    else:
        t.description, t.modifie_le = description, datetime.now(timezone.utc)
    db.flush()
    journaliser(db, application_id=app.id, type_element="test", element_id=t.id, action="test_decrit",
                auteur_id=user.id, nouvelle={"description": description})
    return t


def proposer_description(db: Session, p: Probleme, ia: ServiceIA) -> str:
    return ia.proposer_description_test(contexte_probleme(db, p)).description


def demander_test(db: Session, app: Application, p: Probleme, user: Utilisateur, description: str | None) -> SessionTest:
    if p.statut != SP.EN_COURS:
        raise Conflit(f"Le test ne peut être demandé que pour un problème « en cours » (statut actuel : {p.statut}).")
    _controler_enchainement(db, p)
    decision = db.execute(select(DecisionCorrection).where(DecisionCorrection.probleme_id == p.id)
                          .order_by(DecisionCorrection.cree_le.desc())).scalars().first()
    if decision is None:
        raise Conflit("Enregistrez d'abord la décision de correction.")
    test = db.execute(select(TestCorrection).where(TestCorrection.probleme_id == p.id)).scalar_one_or_none()
    if description:
        test = definir_description_test(db, app, p, user, description)
    if test is None:
        raise DonneesInvalides("Une description du test est requise (un seul test par problème).")
    numero = (db.scalar(select(func.max(SessionTest.numero)).where(SessionTest.test_id == test.id)) or 0) + 1
    s = SessionTest(application_id=app.id, test_id=test.id, numero=numero, decision_id=decision.id,
                    demande_par=user.id, branche_testee=branche_du_probleme(db, p))
    db.add(s)
    db.flush()
    enregistrer_statut(db, application_id=app.id, type_element="session_test", element_id=s.id, ancien=None,
                       nouveau=SS.A_TESTER, auteur_id=user.id)
    svc_pb.changer_statut(db, p, SP.A_TESTER, user.id, systeme=True, motif=f"Test demandé (passage n°{numero})")
    notif.notifier(db, notif.membres_avec_role(db, app, "testeur"), type_evenement="test_demande",
                   message=f"Test à faire : {p.code} {p.titre}", application_id=app.id, type_element="session_test",
                   element_id=s.id, declencheur_id=user.id)
    return s


def prendre_en_charge(db: Session, s: SessionTest, user: Utilisateur) -> SessionTest:
    if s.statut != SS.A_TESTER:
        raise Conflit("Ce test est déjà pris en charge ou terminé.")
    s.testeur_id, s.statut, s.pris_le = user.id, str(SS.EN_COURS), datetime.now(timezone.utc)
    db.flush()         # le déclencheur SQL refuse un testeur auteur de la correction
    enregistrer_statut(db, application_id=s.application_id, type_element="session_test", element_id=s.id,
                       ancien=SS.A_TESTER, nouveau=SS.EN_COURS, auteur_id=user.id, motif=f"Pris par {user.identifiant}")
    return s


def rendre_retour(db: Session, s: SessionTest, user: Utilisateur, data: RetourTesteurIn) -> SessionTest:
    if s.statut != SS.EN_COURS:
        raise Conflit("Ce test n'est pas en cours.")
    if s.testeur_id != user.id:
        raise AccesRefuse("Seul le testeur qui a pris ce test peut rendre le retour.")
    if not data.valide and not (data.commentaire or "").strip():
        raise DonneesInvalides("Un commentaire est obligatoire pour un retour non validé.")
    test = db.get(TestCorrection, s.test_id)
    p = db.get(Probleme, test.probleme_id)
    ids_valides = set(db.execute(
        select(CritereAcceptation.id).join(Tache, Tache.id == CritereAcceptation.tache_id).where(Tache.probleme_id == p.id)
    ).scalars())
    for c in data.criteres:
        if c.critere_acceptation_id not in ids_valides:
            raise DonneesInvalides("Un critère d'acceptation n'appartient pas à ce problème.")
        db.add(ResultatCritereAcceptation(session_id=s.id, critere_acceptation_id=c.critere_acceptation_id,
                                          satisfait=c.satisfait, commentaire=c.commentaire))
    ancien = s.statut
    s.statut = str(SS.VALIDE if data.valide else SS.NON_VALIDE)
    s.commentaire, s.preuve, s.environnement, s.commit_teste = data.commentaire, data.preuve, data.environnement, data.commit_teste
    s.decide_le = datetime.now(timezone.utc)
    db.flush()
    enregistrer_statut(db, application_id=s.application_id, type_element="session_test", element_id=s.id,
                       ancien=ancien, nouveau=s.statut, auteur_id=user.id, motif=data.commentaire)
    app = db.get(Application, s.application_id)
    decision = db.get(DecisionCorrection, s.decision_id) if s.decision_id else None
    if decision is not None:
        ServiceFiabilite(db).etiqueter_solutions(decision, data.valide)   # vérité terrain de l'étape 6
    cibles = {i for i in (p.responsable_id, decision.developpeur_id if decision else None, s.demande_par) if i}
    if data.valide:
        svc_pb.changer_statut(db, p, SP.TESTE, user.id, systeme=True, motif=f"Test validé par {user.identifiant}")
        notif.notifier(db, cibles, type_evenement="test_valide", message=f"Test validé : {p.code} {p.titre}",
                       application_id=app.id, type_element="probleme", element_id=p.id, declencheur_id=user.id)
    else:
        svc_pb.changer_statut(db, p, SP.ROUVERT, user.id, systeme=True, motif=f"Test non validé par {user.identifiant}")
        notif.notifier(db, cibles, type_evenement="test_non_valide", message=f"Test non validé : {p.code} {p.titre}",
                       application_id=app.id, type_element="probleme", element_id=p.id, declencheur_id=user.id)
    collab.message_systeme(db, p.id, f"Test {'validé' if data.valide else 'non validé'} par {user.identifiant} (passage n°{s.numero})")
    return s
