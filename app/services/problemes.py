"""Problèmes : création, statuts, confirmation des résultats d'analyse."""
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy.orm import Session

from app.core.enums import StatutProbleme as SP
from app.core.exceptions import Conflit
from app.fiabilite.service import ServiceFiabilite
from app.models import Application, Probleme, ResultatAnalyse, Utilisateur, Verification
from app.schemas.probleme import ProblemeCreate
from app.services import collaboration as collab
from app.services import notifications as notif
from app.services.historique import enregistrer_statut, journaliser

# PROPOSITION, à valider (les transitions des statuts du problème ne sont pas encore tranchées).
# Transitions autorisées « à la main » par un utilisateur autorisé.
# Réservées au système : en_cours -> a_tester (demande de test), a_tester -> teste / rouvert (retour du testeur),
# confirme / rouvert -> en_cours (démarrage d'une tâche).
TRANSITIONS_MANUELLES: dict[str, set[str]] = {
    SP.NOUVEAU: {SP.A_ANALYSER, SP.CONFIRME, SP.FAUX_POSITIF},
    SP.A_ANALYSER: {SP.CONFIRME, SP.FAUX_POSITIF},
    SP.CONFIRME: {SP.EN_COURS, SP.FAUX_POSITIF},
    SP.FAUX_POSITIF: {SP.A_ANALYSER},
    SP.ROUVERT: {SP.EN_COURS},
    SP.TESTE: {SP.TERMINE},
    SP.TERMINE: {SP.ROUVERT},
}


def changer_statut(db: Session, p: Probleme, nouveau: str, auteur_id: int | None, *, motif: str | None = None,
                   systeme: bool = False) -> None:
    ancien = p.statut
    if ancien == nouveau:
        return
    if not systeme and nouveau not in TRANSITIONS_MANUELLES.get(ancien, set()):
        raise Conflit(f"Transition de statut interdite : {ancien} -> {nouveau}.")
    p.statut = str(nouveau)
    enregistrer_statut(db, application_id=p.application_id, type_element="probleme", element_id=p.id,
                       ancien=ancien, nouveau=nouveau, auteur_id=auteur_id, motif=motif)
    collab.message_systeme(db, p.id, f"Statut modifié : {ancien} → {nouveau}")
    if nouveau in (SP.TERMINE, SP.FAUX_POSITIF):
        collab.synchroniser_archivage(db, p.id, True)            # salon archivé (lecture seule)
    elif nouveau == SP.ROUVERT:
        collab.synchroniser_archivage(db, p.id, False)           # salon rouvert avec le problème
        app = db.get(Application, p.application_id)
        cibles = {i for i in (p.responsable_id, auteur_id) if i}
        notif.notifier(db, cibles, type_evenement="probleme_rouvert", message=f"Problème rouvert : {p.code} {p.titre}",
                       application_id=p.application_id, type_element="probleme", element_id=p.id,
                       declencheur_id=auteur_id)
        if p.gravite == "critique":
            notif.notifier_probleme_critique(db, app, p.id, p.titre, auteur_id)


def _valeurs(data: ProblemeCreate) -> dict:
    """Valeurs à insérer (les énumérations deviennent de simples chaînes)."""
    return {k: (v.value if isinstance(v, Enum) else v) for k, v in data.model_dump(exclude_none=True).items()}


def creer_probleme(db: Session, app: Application, user: Utilisateur, data: ProblemeCreate, *, source: str = "humain",
                   statut: str = SP.NOUVEAU, resultat: ResultatAnalyse | None = None,
                   verification: Verification | None = None, critere_id: int | None = None) -> Probleme:
    p = Probleme(
        application_id=app.id, source=source, statut=str(statut), resultat_id=resultat.id if resultat else None,
        verification_id=verification.id if verification else None, critere_id=critere_id, cree_par=user.id,
        **_valeurs(data),
    )
    db.add(p)
    db.flush()
    db.refresh(p)                                               # charge le code PB-xxxx calculé par la base
    collab.creer_salon_probleme(db, p)                          # un salon par problème, créé automatiquement
    journaliser(db, application_id=app.id, type_element="probleme", element_id=p.id, action="probleme_cree",
                auteur_id=user.id, nouvelle={"code": p.code, "titre": p.titre, "source": source})
    enregistrer_statut(db, application_id=app.id, type_element="probleme", element_id=p.id, ancien=None,
                       nouveau=statut, auteur_id=user.id)
    if p.responsable_id:
        notif.notifier(db, {p.responsable_id}, type_evenement="probleme_assigne", message=f"{p.code} vous est assigné : {p.titre}",
                       application_id=app.id, type_element="probleme", element_id=p.id, declencheur_id=user.id)
    if p.gravite == "critique":
        notif.notifier_probleme_critique(db, app, p.id, p.titre, user.id)
    return p


def confirmer_resultat(db: Session, app: Application, user: Utilisateur, resultat: ResultatAnalyse,
                       verification: Verification, titre: str | None, motif: str | None) -> Probleme:
    if resultat.statut_validation != "non_valide":
        raise Conflit("Ce résultat a déjà fait l'objet d'une décision.")
    resultat.statut_validation = "confirme"
    ServiceFiabilite(db).etiqueter_resultat(resultat.id, True)          # vérité terrain : l'anomalie est réelle
    resultat.decide_par, resultat.motif_decision = user.id, motif
    resultat.decide_le = datetime.now(timezone.utc)
    from app.core.enums import Categorie, Gravite
    data = ProblemeCreate(
        titre=(titre or resultat.message)[:255], categorie=Categorie(resultat.categorie), description=resultat.message,
        gravite=Gravite(resultat.gravite) if resultat.gravite else None, fichier=resultat.fichier,
        ligne_debut=resultat.ligne_debut, ligne_fin=resultat.ligne_fin,
    )
    p = creer_probleme(db, app, user, data, source=resultat.source, statut=SP.CONFIRME, resultat=resultat,
                       verification=verification, critere_id=resultat.critere_id)
    p.fonction, p.extrait_code = resultat.fonction, resultat.extrait_code
    journaliser(db, application_id=app.id, type_element="resultat", element_id=resultat.id,
                action="resultat_confirme", auteur_id=user.id, nouvelle={"probleme": p.code}, commentaire=motif)
    return p


def ecarter_resultat(db: Session, app: Application, user: Utilisateur, resultat: ResultatAnalyse, motif: str | None) -> None:
    if resultat.statut_validation != "non_valide":
        raise Conflit("Ce résultat a déjà fait l'objet d'une décision.")
    resultat.statut_validation, resultat.decide_par, resultat.motif_decision = "ecarte", user.id, motif
    ServiceFiabilite(db).etiqueter_resultat(resultat.id, False)         # vérité terrain : faux positif
    resultat.decide_le = datetime.now(timezone.utc)
    journaliser(db, application_id=app.id, type_element="resultat", element_id=resultat.id,
                action="resultat_ecarte", auteur_id=user.id, commentaire=motif)
