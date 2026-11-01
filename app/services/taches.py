"""Tâches, sous-tâches, critères d'acceptation.
Règles (doublées par des déclencheurs SQL) : une tâche ne se termine que si toutes ses sous-tâches sont terminées
(les arrêtées ne bloquent pas) ; un problème peut avoir plusieurs tâches."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import StatutProbleme as SP
from app.core.enums import StatutTache as ST
from app.core.exceptions import Conflit, DonneesInvalides, NonTrouve
from app.models import (
    Application, CritereAcceptation, Diagnostic, MembreEquipe, Probleme, Solution, SousTache, Tache, TacheSolution,
    Utilisateur,
)
from app.schemas.tache import SousTacheIn, TacheCreate, TacheUpdate
from app.services import collaboration as collab
from app.services import notifications as notif
from app.services import problemes as svc_pb
from app.services.historique import enregistrer_statut, journaliser

TRANSITIONS_TACHE: dict[str, set[str]] = {
    ST.A_FAIRE: {ST.EN_COURS},
    ST.EN_PAUSE: {ST.EN_COURS, ST.ARRETEE},
    ST.EN_COURS: {ST.EN_PAUSE, ST.ARRETEE, ST.TERMINEE},
}
STATUTS_PROBLEME_AVEC_TACHES = {SP.CONFIRME, SP.EN_COURS, SP.ROUVERT}


def _membre(db: Session, app: Application, uid: int | None) -> None:
    if uid is not None and db.get(MembreEquipe, (app.equipe_id, uid)) is None:
        raise DonneesInvalides("Le responsable doit être membre de l'équipe de l'application.")


def _solutions_du_probleme(db: Session, p: Probleme, ids: list[int]) -> None:
    if not ids:
        return
    valides = set(db.execute(
        select(Solution.id).join(Diagnostic, Diagnostic.id == Solution.diagnostic_id)
        .where(Diagnostic.probleme_id == p.id, Solution.id.in_(ids))
    ).scalars())
    if valides != set(ids):
        raise DonneesInvalides("Une solution indiquée n'appartient pas à ce problème.")


def creer_taches(db: Session, app: Application, p: Probleme, user: Utilisateur, donnees: list[TacheCreate]) -> list[Tache]:
    """Création à l'initiative de l'utilisateur (même quand l'IA a fait la proposition)."""
    if p.statut not in STATUTS_PROBLEME_AVEC_TACHES:
        raise Conflit(f"Impossible de créer une tâche pour un problème au statut « {p.statut} ».")
    creees = []
    for d in donnees:
        _membre(db, app, d.responsable_id)
        _solutions_du_probleme(db, p, d.solution_ids)
        t = Tache(
            probleme_id=p.id, application_id=app.id, titre=d.titre, description=d.description, origine=d.origine,
            duree_estimee_h=d.duree_estimee_h, responsable_id=d.responsable_id, echeance=d.echeance, cree_par=user.id,
        )
        t.sous_taches = [SousTache(titre=s.titre, description=s.description, origine=s.origine, ordre=i + 1)
                         for i, s in enumerate(d.sous_taches)]
        t.criteres_acceptation = [CritereAcceptation(texte=c.texte, origine=c.origine, ordre=i + 1)
                                  for i, c in enumerate(d.criteres_acceptation)]
        db.add(t)
        db.flush()
        for sid in set(d.solution_ids):
            db.add(TacheSolution(tache_id=t.id, solution_id=sid, ajoute_par=user.id))
        journaliser(db, application_id=app.id, type_element="tache", element_id=t.id, action="tache_creee",
                    auteur_id=user.id, nouvelle={"titre": t.titre, "probleme": p.code})
        enregistrer_statut(db, application_id=app.id, type_element="tache", element_id=t.id, ancien=None,
                           nouveau=ST.A_FAIRE, auteur_id=user.id)
        if t.responsable_id:
            notif.notifier(db, {t.responsable_id}, type_evenement="tache_assignee",
                           message=f"La tâche « {t.titre} » vous est assignée", application_id=app.id,
                           type_element="tache", element_id=t.id, declencheur_id=user.id)
        creees.append(t)
    return creees


def modifier_tache(db: Session, t: Tache, app: Application, user: Utilisateur, data: TacheUpdate) -> Tache:
    champs = data.model_dump(exclude_unset=True)
    _membre(db, app, champs.get("responsable_id"))
    avant = {k: str(getattr(t, k)) for k in champs}
    for k, v in champs.items():
        setattr(t, k, v)
    journaliser(db, application_id=app.id, type_element="tache", element_id=t.id, action="tache_modifiee",
                auteur_id=user.id, ancienne=avant, nouvelle={k: str(v) for k, v in champs.items()})
    return t


def _controler_transition(t: Tache, nouveau: str) -> None:
    if nouveau not in TRANSITIONS_TACHE.get(t.statut, set()):
        raise Conflit(f"Transition de statut de tâche interdite : {t.statut} -> {nouveau}.")
    if nouveau == ST.TERMINEE and any(s.statut not in (ST.TERMINEE, ST.ARRETEE) for s in t.sous_taches):
        raise Conflit("Une tâche ne peut être terminée que si toutes ses sous-tâches sont terminées.")


def changer_statut_tache(db: Session, t: Tache, nouveau: str, user: Utilisateur) -> Tache:
    _controler_transition(t, nouveau)
    ancien = t.statut
    t.statut = str(nouveau)
    db.flush()
    db.refresh(t)                       # le déclencheur SQL a posé debut_le / fin_le
    enregistrer_statut(db, application_id=t.application_id, type_element="tache", element_id=t.id,
                       ancien=ancien, nouveau=nouveau, auteur_id=user.id)
    p = db.get(Probleme, t.probleme_id)
    if nouveau == ST.EN_COURS and p.statut in (SP.CONFIRME, SP.ROUVERT):
        svc_pb.changer_statut(db, p, SP.EN_COURS, user.id, systeme=True, motif="Une tâche a été démarrée")
    if nouveau == ST.TERMINEE:
        _suggerer_test(db, t, p, user)
    return t


def _suggerer_test(db: Session, t: Tache, p: Probleme, user: Utilisateur) -> None:
    """Simple suggestion (pas d'action automatique) quand toutes les tâches sont terminées ou arrêtées."""
    taches = db.execute(select(Tache).where(Tache.probleme_id == p.id)).scalars().all()
    if all(x.statut in (ST.TERMINEE, ST.ARRETEE) for x in taches):
        cibles = {i for i in (p.responsable_id, t.responsable_id) if i}
        notif.notifier(db, cibles, type_evenement="statut_modifie",
                       message=f"Toutes les tâches de {p.code} sont terminées : vous pouvez demander un test.",
                       application_id=p.application_id, type_element="probleme", element_id=p.id,
                       declencheur_id=user.id)


# ---------- Sous-tâches et critères d'acceptation ----------

def _sous_tache(db: Session, sid: int, tache_id: int) -> SousTache:
    s = db.get(SousTache, sid)
    if s is None or s.tache_id != tache_id:
        raise NonTrouve("Sous-tâche introuvable.")
    return s


def ajouter_sous_tache(db: Session, t: Tache, data: SousTacheIn, user: Utilisateur) -> SousTache:
    if t.statut in (ST.TERMINEE, ST.ARRETEE):
        raise Conflit("La tâche est terminée ou arrêtée.")
    ordre = max([s.ordre for s in t.sous_taches], default=0) + 1
    s = SousTache(tache_id=t.id, titre=data.titre, description=data.description, origine=data.origine, ordre=ordre)
    db.add(s)
    db.flush()
    journaliser(db, application_id=t.application_id, type_element="sous_tache", element_id=s.id,
                action="sous_tache_creee", auteur_id=user.id)
    return s


def changer_statut_sous_tache(db: Session, t: Tache, sid: int, nouveau: str, user: Utilisateur) -> SousTache:
    s = _sous_tache(db, sid, t.id)
    if nouveau not in TRANSITIONS_TACHE.get(s.statut, set()):
        raise Conflit(f"Transition interdite : {s.statut} -> {nouveau}.")
    ancien, s.statut = s.statut, nouveau
    enregistrer_statut(db, application_id=t.application_id, type_element="sous_tache", element_id=s.id,
                       ancien=ancien, nouveau=nouveau, auteur_id=user.id)
    return s


def retirer_sous_tache(db: Session, t: Tache, sid: int, user: Utilisateur) -> None:
    s = _sous_tache(db, sid, t.id)
    journaliser(db, application_id=t.application_id, type_element="sous_tache", element_id=s.id,
                action="sous_tache_retiree", auteur_id=user.id, ancienne={"titre": s.titre})
    db.delete(s)


def ajouter_critere_acceptation(db: Session, t: Tache, texte: str, origine: str, user: Utilisateur) -> CritereAcceptation:
    ordre = max([c.ordre for c in t.criteres_acceptation], default=0) + 1
    c = CritereAcceptation(tache_id=t.id, texte=texte, origine=origine, ordre=ordre)
    db.add(c)
    db.flush()
    journaliser(db, application_id=t.application_id, type_element="tache", element_id=t.id,
                action="critere_acceptation_ajoute", auteur_id=user.id, nouvelle={"texte": texte})
    return c
