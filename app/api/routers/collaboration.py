"""Notes, salons de discussion (un par problème + salons généraux), assistant IA commun par problème."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.service import ServiceIA, get_service_ia
from app.api.deps import utilisateur_courant
from app.api.helpers import application_autorisee, obtenir, probleme_autorise, salon_autorise, tache_autorisee
from app.core.enums import Perm
from app.core.exceptions import NonTrouve
from app.database import get_db
from app.models import MessageDiscussion, Note, Notification, Salon, Utilisateur
from app.schemas.collaboration import (
    ContenuIn, MessageIAOut, MessageIn, MessageOut, NoteIn, NoteOut, QuestionIn, SalonIn, SalonOut,
)
from app.schemas.common import Message
from app.schemas.probleme import SolutionOut
from app.services import collaboration as svc

router = APIRouter(tags=["Collaboration"])


# ---------- Notes ----------

@router.get("/problemes/{probleme_id}/notes", response_model=list[NoteOut])
def notes_probleme(probleme_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    p, _ = probleme_autorise(db, user, probleme_id, Perm.PROBLEME_CONSULTER)
    return db.execute(select(Note).where(Note.probleme_id == p.id).order_by(Note.cree_le)).scalars().all()   # supprimées incluses (trace)


@router.post("/problemes/{probleme_id}/notes", response_model=NoteOut, status_code=201)
def note_probleme(probleme_id: int, data: NoteIn, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    p, app = probleme_autorise(db, user, probleme_id, Perm.DISCUSSION_PARTICIPER, ecriture=True)
    return svc.ajouter_note(db, app, user, data, probleme_id=p.id)


@router.get("/taches/{tache_id}/notes", response_model=list[NoteOut])
def notes_tache(tache_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    t, _, _ = tache_autorisee(db, user, tache_id, Perm.PROBLEME_CONSULTER)
    return db.execute(select(Note).where(Note.tache_id == t.id).order_by(Note.cree_le)).scalars().all()


@router.post("/taches/{tache_id}/notes", response_model=NoteOut, status_code=201)
def note_tache(tache_id: int, data: NoteIn, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    t, app, _ = tache_autorisee(db, user, tache_id, Perm.DISCUSSION_PARTICIPER, ecriture=True)
    return svc.ajouter_note(db, app, user, data, tache_id=t.id)


@router.patch("/notes/{note_id}", response_model=NoteOut)
def modifier_note(note_id: int, data: ContenuIn, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    """Seul l'auteur peut modifier sa note."""
    n = obtenir(db.get(Note, note_id), "Note introuvable.")
    application_autorisee(db, user, n.application_id, Perm.DISCUSSION_PARTICIPER, ecriture=True)
    return svc.modifier_note(db, note_id, user, data.contenu)


@router.delete("/notes/{note_id}", response_model=Message)
def supprimer_note(note_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    """Seul l'auteur peut supprimer sa note (suppression logique : le contenu reste dans l'historique)."""
    n = obtenir(db.get(Note, note_id), "Note introuvable.")
    application_autorisee(db, user, n.application_id, Perm.DISCUSSION_PARTICIPER, ecriture=True)
    svc.supprimer_note(db, note_id, user)
    return Message(message="Note supprimée.")


# ---------- Salons ----------

@router.get("/applications/{application_id}/salons", response_model=list[SalonOut])
def salons(application_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    app = application_autorisee(db, user, application_id, Perm.DISCUSSION_PARTICIPER)
    return svc.lister_salons(db, app, user)


@router.post("/applications/{application_id}/salons", response_model=SalonOut, status_code=201)
def creer_salon(application_id: int, data: SalonIn, db: Session = Depends(get_db),
                user: Utilisateur = Depends(utilisateur_courant)):
    app = application_autorisee(db, user, application_id, Perm.DISCUSSION_PARTICIPER, ecriture=True)
    return svc.creer_salon_general(db, app, user, data.titre)


@router.delete("/salons/{salon_id}", response_model=Message)
def supprimer_salon(salon_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    """Jamais supprimé, sauf par le chef de projet (permission salon.supprimer) ; suppression logique tracée."""
    s, _ = salon_autorise(db, user, salon_id, Perm.SALON_SUPPRIMER)
    svc.supprimer_salon(db, s, user)
    return Message(message="Salon supprimé.")


@router.get("/salons/{salon_id}/messages", response_model=list[MessageOut])
def messages(salon_id: int, limit: int = 200, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    s, _ = salon_autorise(db, user, salon_id, Perm.DISCUSSION_PARTICIPER)
    return db.execute(select(MessageDiscussion).where(MessageDiscussion.salon_id == s.id)
                      .order_by(MessageDiscussion.cree_le).limit(min(limit, 500))).scalars().all()


@router.post("/salons/{salon_id}/messages", response_model=MessageOut, status_code=201)
def publier(salon_id: int, data: MessageIn, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    s, _ = salon_autorise(db, user, salon_id, Perm.DISCUSSION_PARTICIPER)
    return svc.publier_message(db, s, user, data)


@router.patch("/messages/{message_id}", response_model=MessageOut)
def modifier_message(message_id: int, data: ContenuIn, db: Session = Depends(get_db),
                     user: Utilisateur = Depends(utilisateur_courant)):
    """Seul l'auteur peut modifier son message."""
    m = obtenir(db.get(MessageDiscussion, message_id), "Message introuvable.")
    salon_autorise(db, user, m.salon_id, Perm.DISCUSSION_PARTICIPER)
    return svc.modifier_message(db, message_id, user, data.contenu)


@router.delete("/messages/{message_id}", response_model=Message)
def supprimer_message(message_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    m = obtenir(db.get(MessageDiscussion, message_id), "Message introuvable.")
    salon_autorise(db, user, m.salon_id, Perm.DISCUSSION_PARTICIPER)
    svc.supprimer_message(db, message_id, user)
    return Message(message="Message supprimé.")


@router.post("/salons/{salon_id}/lu", response_model=Message)
def marquer_lu(salon_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    s, _ = salon_autorise(db, user, salon_id, Perm.DISCUSSION_PARTICIPER)
    svc.marquer_salon_lu(db, s, user)
    return Message(message="Salon marqué comme lu.")


# ---------- Assistant IA : UNE conversation COMMUNE par problème ----------

@router.get("/problemes/{probleme_id}/assistant/messages", response_model=list[MessageIAOut])
def historique_assistant(probleme_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    p, _ = probleme_autorise(db, user, probleme_id, Perm.ASSISTANT_UTILISER)
    return svc.messages_ia(db, p)


@router.post("/problemes/{probleme_id}/assistant/messages", response_model=MessageIAOut, status_code=201)
def poser_question(probleme_id: int, data: QuestionIn, db: Session = Depends(get_db),
                   user: Utilisateur = Depends(utilisateur_courant), ia: ServiceIA = Depends(get_service_ia)):
    """Pose une question (ou « Demander de l'aide » sur une tâche / sous-tâche). Retourne la réponse de l'assistant,
    qui signale les informations manquantes plutôt que d'inventer. 503 si le service d'IA est indisponible."""
    p, _ = probleme_autorise(db, user, probleme_id, Perm.ASSISTANT_UTILISER, ecriture=True)
    return svc.poser_question(db, p, user, data.question, ia, data.tache_id, data.sous_tache_id)


@router.post("/problemes/{probleme_id}/assistant/messages/{message_id}/proposer-solution", response_model=SolutionOut, status_code=201)
def proposer_solution(probleme_id: int, message_id: int, db: Session = Depends(get_db),
                      user: Utilisateur = Depends(utilisateur_courant)):
    p, _ = probleme_autorise(db, user, probleme_id, Perm.PROBLEME_MODIFIER, ecriture=True)
    return svc.proposer_comme_solution(db, p, message_id, user)


@router.post("/problemes/{probleme_id}/assistant/messages/{message_id}/partager-salon", response_model=MessageOut, status_code=201)
def partager(probleme_id: int, message_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    p, _ = probleme_autorise(db, user, probleme_id, Perm.DISCUSSION_PARTICIPER, ecriture=True)
    return svc.partager_dans_salon(db, p, message_id, user)
