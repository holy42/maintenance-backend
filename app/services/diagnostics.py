"""Diagnostics et solutions de l'IA, évaluation par le développeur, décision de correction.
L'IA propose ; elle ne modifie jamais le code. Rien n'est écrasé : chaque demande crée un nouveau diagnostic."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.service import ServiceIA
from app.core.enums import StatutProbleme as SP
from app.core.enums import TypeDecision
from app.core.exceptions import Conflit, DonneesInvalides
from app.fiabilite import controles
from app.fiabilite.service import ServiceFiabilite
from app.fiabilite.verifications import controler_verifications
from app.models import (
    Application, DecisionCorrection, DecisionSolution, Diagnostic, Probleme, RetourSolution, Solution, Utilisateur,
    Verification,
)
from app.schemas.probleme import DecisionIn, RetourSolutionIn
from app.services import collaboration as collab
from app.services import git_service
from app.services import notifications as notif
from app.services.contexte_ia import contexte_probleme
from app.services.historique import journaliser
from app.services.tests_validation import branche_du_probleme


def generer_diagnostic(db: Session, p: Probleme, user: Utilisateur, ia: ServiceIA) -> Diagnostic:
    if p.statut in (SP.FAUX_POSITIF, SP.TERMINE):
        raise Conflit(f"Pas de diagnostic pour un problème « {p.statut} ».")
    reponse = ia.diagnostiquer(contexte_probleme(db, p))        # IAIndisponible (503) si le service est en panne
    commit = db.get(Verification, p.verification_id).commit_analyse if p.verification_id else None
    d = Diagnostic(
        probleme_id=p.id, explication=reponse.diagnostic.explication, causes_probables=reponse.diagnostic.causes_probables,
        niveau_confiance=reponse.diagnostic.niveau_confiance, incertitudes=reponse.diagnostic.incertitudes,
        branche_analysee=branche_du_probleme(db, p), commit_reference=commit,
        modele_ia=ia.modele, version_prompt=ia.version_prompt,
    )
    d.solutions = [Solution(description=s.description, extrait_code=s.extrait_code, format_code=s.format_code,
                            risques=s.risques, tests_suggeres=s.tests_suggeres, commit_reference=commit)
                   for s in reponse.solutions]
    db.add(d)
    db.flush()
    fiab = ServiceFiabilite(db)
    preuve = fiab.preuve_du_probleme(p)
    d.verifications_recommandees = controler_verifications(          # rédigées par l'IA, puis contrôlées
        reponse.diagnostic.verifications_recommandees, {p.fichier} if p.fichier else None, p.categorie)
    depot = git_service.dossier_depot(p.application_id)               # copie locale du dépôt, si une vérification l'a déjà clonée
    for s, brute in zip(d.solutions, reponse.solutions):               # étape 6 : fiabilité de chaque solution de Gemini
        fiab.evaluer_solution(
            s, d, p, reponse.diagnostic, preuve,
            reference_valide=controles.reference_valide(s.extrait_code, depot),
            syntaxe_valide=controles.syntaxe_php_valide(s.extrait_code, brute.format_code),
        )
    journaliser(db, application_id=p.application_id, type_element="probleme", element_id=p.id,
                action="diagnostic_ia_cree", auteur_id=user.id, nouvelle={"diagnostic": d.id})
    if p.responsable_id:
        notif.notifier(db, {p.responsable_id}, type_evenement="nouvelle_recommandation_ia",
                       message=f"Nouveau diagnostic de l'IA sur {p.code}", application_id=p.application_id,
                       type_element="probleme", element_id=p.id, declencheur_id=user.id)
    return d


def enregistrer_retour(db: Session, s: Solution, p: Probleme, user: Utilisateur, data: RetourSolutionIn) -> RetourSolution:
    """Utilité PERÇUE par le développeur. La réussite de la correction vient du testeur."""
    r = RetourSolution(solution_id=s.id, utilisateur_id=user.id, **data.model_dump())
    db.add(r)
    db.flush()
    journaliser(db, application_id=p.application_id, type_element="solution", element_id=s.id, action="retour_solution",
                auteur_id=user.id, nouvelle={"utilite": data.utilite_percue})
    return r


def enregistrer_decision(db: Session, app: Application, p: Probleme, user: Utilisateur, data: DecisionIn) -> DecisionCorrection:
    if p.statut not in (SP.CONFIRME, SP.EN_COURS, SP.ROUVERT):
        raise Conflit(f"Décision impossible pour un problème « {p.statut} ».")
    ids = set(data.solution_ids)
    if data.type_decision in (TypeDecision.IA_RETENUE, TypeDecision.IA_ADAPTEE):
        if not ids:
            raise DonneesInvalides("Indiquez au moins une solution de l'IA retenue.")
        valides = set(db.execute(select(Solution.id).join(Diagnostic, Diagnostic.id == Solution.diagnostic_id)
                                 .where(Diagnostic.probleme_id == p.id, Solution.id.in_(ids))).scalars())
        if valides != ids:
            raise DonneesInvalides("Une solution indiquée n'appartient pas à ce problème.")
    else:
        if not (data.description_alternative or "").strip():
            raise DonneesInvalides("Décrivez votre solution.")
    if data.motif_non_utilisation and data.type_decision not in (TypeDecision.AUTRE_SOLUTION, TypeDecision.SANS_IA):
        raise DonneesInvalides("Le motif ne s'applique qu'aux choix « autre solution » et « sans l'IA ».")
    d = DecisionCorrection(
        probleme_id=p.id, developpeur_id=user.id, type_decision=data.type_decision.value,
        description_alternative=data.description_alternative, extrait_code_alternatif=data.extrait_code_alternatif,
        justification=data.justification, motif_non_utilisation=data.motif_non_utilisation,
        commit_associe=data.commit_associe, pull_request=data.pull_request,
    )
    db.add(d)
    db.flush()
    for sid in ids if data.type_decision in (TypeDecision.IA_RETENUE, TypeDecision.IA_ADAPTEE) else set():
        db.add(DecisionSolution(decision_id=d.id, solution_id=sid))
    journaliser(db, application_id=app.id, type_element="probleme", element_id=p.id, action="decision_enregistree",
                auteur_id=user.id, nouvelle={"type": d.type_decision, "solutions": sorted(ids)})
    collab.message_systeme(db, p.id, f"Décision enregistrée : {d.type_decision}")
    if p.responsable_id:
        notif.notifier(db, {p.responsable_id}, type_evenement="decision_enregistree",
                       message=f"Décision de correction enregistrée sur {p.code}", application_id=app.id,
                       type_element="probleme", element_id=p.id, declencheur_id=user.id)
    return d


def solutions_de_la_decision(db: Session, d: DecisionCorrection) -> list[int]:
    return list(db.execute(select(DecisionSolution.solution_id).where(DecisionSolution.decision_id == d.id)).scalars())
