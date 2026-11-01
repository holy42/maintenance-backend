"""Historique de TOUTES les activités, quel que soit l'auteur (NULL = système).
Le journal est en ajout seul (déclencheurs SQL)."""
from sqlalchemy.orm import Session

from app.models import EvenementHistorique, HistoriqueStatut


def journaliser(
    db: Session, *, application_id: int | None, type_element: str, element_id: int, action: str,
    auteur_id: int | None = None, ancienne: dict | None = None, nouvelle: dict | None = None,
    commentaire: str | None = None,
) -> EvenementHistorique:
    ev = EvenementHistorique(
        application_id=application_id, type_element=type_element, element_id=element_id, auteur_id=auteur_id,
        action=action, ancienne_valeur=ancienne, nouvelle_valeur=nouvelle, commentaire=commentaire,
    )
    db.add(ev)
    return ev


def enregistrer_statut(
    db: Session, *, application_id: int, type_element: str, element_id: int, ancien: str | None,
    nouveau: str, auteur_id: int | None = None, motif: str | None = None,
) -> None:
    """Écrit la transition dans historique_statut (base du calcul des temps de résolution et
    de la règle « tâche terminée depuis la dernière réouverture »)."""
    db.add(HistoriqueStatut(
        application_id=application_id, type_element=type_element, element_id=element_id,
        ancien_statut=str(ancien) if ancien else None, nouveau_statut=str(nouveau), auteur_id=auteur_id, motif=motif,
    ))
    journaliser(
        db, application_id=application_id, type_element=type_element, element_id=element_id,
        action="statut_modifie", auteur_id=auteur_id, ancienne={"statut": str(ancien) if ancien else None}, nouvelle={"statut": str(nouveau)},
        commentaire=motif,
    )
