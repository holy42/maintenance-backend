"""Critères de vérification : langage naturel -> proposition de l'IA -> validation humaine -> activation."""
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.ai.schemas import PropositionCritere
from app.ai.service import ServiceIA
from app.core.exceptions import Conflit
from app.models import Application, Critere, Utilisateur
from app.schemas.verification import CritereCreate, CritereUpdate
from app.services.historique import enregistrer_statut, journaliser


def lister(db: Session, app: Application) -> list[Critere]:
    """Critères standards (communs) + critères de l'application."""
    return list(db.execute(select(Critere).where(or_(Critere.application_id == app.id, Critere.application_id.is_(None)))
                           .order_by(Critere.categorie, Critere.id)).scalars())


def proposer(ia: ServiceIA, description: str) -> PropositionCritere:
    """L'IA reformule et classe. Elle ne vérifie rien et n'active rien."""
    return ia.formuler_critere(description)


def creer(db: Session, app: Application, user: Utilisateur, data: CritereCreate) -> Critere:
    c = Critere(application_id=app.id, createur_id=user.id, origine="personnalisee", statut="brouillon",
                nom=data.nom, description=data.description, categorie=data.categorie.value,
                automatisabilite=data.automatisabilite, mode_verification=data.mode_verification,
                formulation_structuree=data.formulation_structuree)
    db.add(c)
    db.flush()
    journaliser(db, application_id=app.id, type_element="critere", element_id=c.id, action="critere_cree",
                auteur_id=user.id, nouvelle={"nom": c.nom})
    enregistrer_statut(db, application_id=app.id, type_element="critere", element_id=c.id, ancien=None,
                       nouveau="brouillon", auteur_id=user.id)
    return c


def _modifiable(c: Critere) -> None:
    if c.origine == "standard":
        raise Conflit("Un critère standard n'est pas modifiable.")


def modifier(db: Session, c: Critere, user: Utilisateur, data: CritereUpdate) -> Critere:
    _modifiable(c)
    champs = data.model_dump(exclude_unset=True)
    if "categorie" in champs and champs["categorie"] is not None:
        champs["categorie"] = champs["categorie"].value
    for k, v in champs.items():
        setattr(c, k, v)
    if c.statut in ("valide", "actif"):                 # un critère modifié doit être revalidé
        ancien, c.statut, c.valide_par = c.statut, "brouillon", None
        enregistrer_statut(db, application_id=c.application_id, type_element="critere", element_id=c.id,
                           ancien=ancien, nouveau="brouillon", auteur_id=user.id, motif="Critère modifié : à revalider")
    journaliser(db, application_id=c.application_id, type_element="critere", element_id=c.id, action="critere_modifie",
                auteur_id=user.id)
    return c


def valider(db: Session, c: Critere, user: Utilisateur, activer: bool) -> Critere:
    _modifiable(c)
    if c.statut not in ("brouillon", "inactif"):
        raise Conflit(f"Un critère « {c.statut} » ne peut pas être validé.")
    ancien = c.statut
    c.valide_par, c.statut = user.id, "actif" if activer else "valide"
    enregistrer_statut(db, application_id=c.application_id, type_element="critere", element_id=c.id,
                       ancien=ancien, nouveau=c.statut, auteur_id=user.id)
    return c


def activer(db: Session, c: Critere, user: Utilisateur) -> Critere:
    if c.statut == "actif":
        return c
    if c.origine != "standard" and (c.valide_par is None or c.statut not in ("valide", "inactif")):
        raise Conflit("Un critère personnalisé doit être validé avant d'être activé.")
    ancien, c.statut = c.statut, "actif"
    if c.application_id:
        enregistrer_statut(db, application_id=c.application_id, type_element="critere", element_id=c.id,
                           ancien=ancien, nouveau="actif", auteur_id=user.id)
    return c


def desactiver(db: Session, c: Critere, user: Utilisateur) -> Critere:
    if c.statut != "actif":
        raise Conflit("Ce critère n'est pas actif.")
    c.statut = "inactif"
    if c.application_id:
        enregistrer_statut(db, application_id=c.application_id, type_element="critere", element_id=c.id,
                           ancien="actif", nouveau="inactif", auteur_id=user.id)
    return c
