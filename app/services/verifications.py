"""Vérifications à la demande. Version analysée = dernier commit de la branche choisie (develop par défaut,
ou la branche du problème rouvert, nommée d'après son code). Pas de comparaison entre versions.
L'exécution se fait en arrière-plan (BackgroundTasks de FastAPI) : si le serveur redémarre pendant une
vérification, elle est marquée « échouée » au démarrage suivant (voir marquer_verifications_interrompues)."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.analysis import registry
from app.analysis.secrets_filter import preparer_extrait
from app.ai.service import ServiceIA
from app.core.crypto import dechiffrer
from app.fiabilite.service import ServiceFiabilite
from app.core.exceptions import DonneesInvalides, ErreurMetier, IAIndisponible
from app.database import SessionLocal
from app.models import (
    Application, ApplicationTechnologie, Critere, DepotGit, ResultatAnalyse, Technologie, Utilisateur, Verification,
    VerificationCritere,
)
from app.schemas.verification import VerificationCreate
from app.services import git_service
from app.services import notifications as notif
from app.services.historique import enregistrer_statut, journaliser

log = logging.getLogger(__name__)


def creer_verification(db: Session, app: Application, user: Utilisateur, data: VerificationCreate) -> Verification:
    branche = git_service.valider_branche(data.branche)
    criteres = db.execute(select(Critere).where(Critere.id.in_(data.critere_ids))).scalars().all()
    if len(criteres) != len(set(data.critere_ids)):
        raise DonneesInvalides("Un critère sélectionné n'existe pas.")
    for c in criteres:
        if c.application_id not in (None, app.id):
            raise DonneesInvalides("Un critère appartient à une autre application.")
        if c.statut != "actif":
            raise DonneesInvalides(f"Le critère « {c.nom} » n'est pas actif.")
    depot = db.execute(select(DepotGit).where(DepotGit.application_id == app.id)).scalar_one_or_none()
    if depot is None:
        raise DonneesInvalides("Aucun dépôt Git n'est configuré pour cette application.")
    v = Verification(
        application_id=app.id, depot_id=depot.id, branche=branche, declenchee_par=user.id,
        perimetre=json.dumps({"dossiers": data.dossiers, "exclusions": data.exclusions}),
        avec_interpretation_ia=data.avec_interpretation_ia,
    )
    db.add(v)
    db.flush()
    for c in criteres:
        db.add(VerificationCritere(verification_id=v.id, critere_id=c.id))
    journaliser(db, application_id=app.id, type_element="verification", element_id=v.id, action="verification_lancee",
                auteur_id=user.id, nouvelle={"branche": branche, "criteres": [c.id for c in criteres]})
    enregistrer_statut(db, application_id=app.id, type_element="verification", element_id=v.id, ancien=None,
                       nouveau="en_attente", auteur_id=user.id)
    return v


def criteres_a_verifier_manuellement(db: Session, v: Verification) -> list[Critere]:
    """Critères sélectionnés qui ne sont pas exécutés automatiquement (validation humaine)."""
    return list(db.execute(
        select(Critere).join(VerificationCritere, VerificationCritere.critere_id == Critere.id)
        .where(VerificationCritere.verification_id == v.id,
               or_(Critere.mode_verification == "manuelle", Critere.mode_verification.is_(None)))
        .order_by(Critere.id)
    ).scalars())


# ---------- exécution en arrière-plan ----------

def executer_verification(verification_id: int, ia: ServiceIA | None = None) -> None:
    """Point d'entrée des tâches d'arrière-plan : ouvre sa propre session."""
    db = SessionLocal()
    try:
        _executer(db, verification_id, ia)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        if not isinstance(exc, ErreurMetier):
            log.exception("Échec de la vérification %s", verification_id)
        _marquer_echec(verification_id, exc.message if isinstance(exc, ErreurMetier)
                       else f"Erreur interne lors de la vérification ({type(exc).__name__}) : voir le journal du serveur.")
    finally:
        db.close()


def _marquer_echec(verification_id: int, motif: str) -> None:
    db = SessionLocal()
    try:
        v = db.get(Verification, verification_id)
        if v is not None and v.statut in ("en_attente", "en_cours"):
            ancien = v.statut
            v.statut, v.motif_echec, v.fin_le = "echouee", motif, datetime.now(timezone.utc)
            enregistrer_statut(db, application_id=v.application_id, type_element="verification", element_id=v.id,
                               ancien=ancien, nouveau="echouee", motif=motif)
            notif.notifier(db, {v.declenchee_par}, type_evenement="verification_terminee",
                           message=f"Vérification n°{v.id} échouée : {motif}", application_id=v.application_id,
                           type_element="verification", element_id=v.id)
        db.commit()
    finally:
        db.close()


def marquer_verifications_interrompues() -> int:
    """À appeler au démarrage : les vérifications restées « en cours » ont été interrompues."""
    db = SessionLocal()
    try:
        res = db.execute(update(Verification).where(Verification.statut.in_(("en_attente", "en_cours"))).values(
            statut="echouee", motif_echec="Interrompue par un redémarrage du serveur.", fin_le=datetime.now(timezone.utc)))
        db.commit()
        return res.rowcount or 0
    finally:
        db.close()


def _regles_par_critere(criteres: list[Critere]) -> dict[str, int]:
    """Règle d'analyse -> critère. Convention : critere.formulation_structuree = {"regle": "php.syntaxe"}."""
    connues = registry.regles_connues()
    out: dict[str, int] = {}
    for c in criteres:
        regle = (c.formulation_structuree or {}).get("regle")
        if c.mode_verification == "regle_statique" and regle in connues:
            out[regle] = c.id
    return out


def _executer(db: Session, verification_id: int, ia: ServiceIA | None) -> None:
    v = db.get(Verification, verification_id)
    if v is None or v.statut != "en_attente":
        return
    app = db.get(Application, v.application_id)
    v.statut = "en_cours"
    enregistrer_statut(db, application_id=app.id, type_element="verification", element_id=v.id,
                       ancien="en_attente", nouveau="en_cours")
    db.commit()                                         # visible par l'interface (suivi de l'état)

    depot = db.get(DepotGit, v.depot_id)
    jeton = dechiffrer(depot.jeton_acces_chiffre) if depot.jeton_acces_chiffre else None
    racine, commit = git_service.synchroniser(app.id, depot.url, jeton, v.branche)
    v.commit_analyse, depot.derniere_synchro_le = commit, datetime.now(timezone.utc)

    criteres = list(db.execute(
        select(Critere).join(VerificationCritere, VerificationCritere.critere_id == Critere.id)
        .where(VerificationCritere.verification_id == v.id)).scalars())
    regles = _regles_par_critere(criteres)
    techs = {t.lower() for t in db.execute(
        select(Technologie.nom).join(ApplicationTechnologie, ApplicationTechnologie.technologie_id == Technologie.id)
        .where(ApplicationTechnologie.application_id == app.id)).scalars()}
    perimetre = json.loads(v.perimetre or "{}")

    constats = []
    for analyseur in registry.analyseurs_pour(techs, set(regles)):
        constats += analyseur.analyser(Path(racine), perimetre.get("dossiers", []), perimetre.get("exclusions", []),
                                       set(regles) & set(analyseur.regles))
    paires = []
    for c in constats:
        r = ResultatAnalyse(
            verification_id=v.id, critere_id=regles.get(c.regle), source="outil", outil=c.outil, categorie=c.categorie,
            gravite=c.gravite, fichier=c.fichier, ligne_debut=c.ligne_debut, ligne_fin=c.ligne_fin, fonction=c.fonction,
            extrait_code=c.extrait_code, message=c.message, elements_preuve=c.elements_preuve, donnees_brutes=c.donnees_brutes,
        )
        db.add(r)
        paires.append((r, c))
    db.flush()                                          # attribue les identifiants ; une erreur ici est réelle et arrête la vérification
    try:                                                # étape 3 : fiabilité de chaque preuve de l'outil d'analyse
        with db.begin_nested():                         # un échec du calcul de fiabilité n'annule ni ne bloque la vérification
            ServiceFiabilite(db).evaluer_resultats(v, paires)
    except Exception:
        log.exception("Calcul de fiabilité (étape 3) impossible pour la vérification %s", v.id)
    n_ia = 0
    if v.avec_interpretation_ia and constats:
        n_ia = _interpreter(db, v, constats, ia or ServiceIA())
    v.statut, v.fin_le = "terminee", datetime.now(timezone.utc)
    v.resultat_global = f"{len(constats)} résultat(s), {n_ia} IA"[:30]      # colonne VARCHAR(30) du script SQL
    enregistrer_statut(db, application_id=app.id, type_element="verification", element_id=v.id,
                       ancien="en_cours", nouveau="terminee")
    notif.notifier(db, {v.declenchee_par}, type_evenement="verification_terminee",
                   message=f"Vérification n°{v.id} terminée : {v.resultat_global}", application_id=app.id,
                   type_element="verification", element_id=v.id)


def _interpreter(db: Session, v: Verification, constats, ia: ServiceIA) -> int:
    """Hypothèses de l'IA : jamais présentées comme des faits (source = « ia », non validées)."""
    contexte = {"constats_outils": [
        {"fichier": c.fichier, "ligne": c.ligne_debut, "message": c.message, "extrait": preparer_extrait(c.extrait_code, 800)}
        for c in constats[:30]
    ]}
    try:
        hyp = ia.interpreter(contexte)
    except IAIndisponible:
        log.warning("IA indisponible : la vérification continue sans interprétation.")
        return 0
    for h in hyp.hypotheses:
        db.add(ResultatAnalyse(verification_id=v.id, source="ia", outil=f"ia:{ia.modele}", categorie=h.categorie,
                               gravite=h.gravite, fichier=h.fichier, ligne_debut=h.ligne, message=h.message,
                               elements_preuve=h.elements_preuve or "Hypothèse de l'IA, non vérifiée."))
    return len(hyp.hypotheses)
