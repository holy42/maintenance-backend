"""Notes, salons de discussion, assistant IA commun par problème."""
import re
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.service import ServiceIA
from app.core.exceptions import AccesRefuse, Conflit, DonneesInvalides, NonTrouve
from app.models import (
    Application, ConversationIA, Diagnostic, MembreEquipe, Mention, MessageDiscussion, MessageIA, Note, Probleme,
    Salon, SalonLecture, Solution, SousTache, Tache, Utilisateur,
)
from app.schemas.collaboration import MessageIn, NoteIn
from app.services import notifications as notif
from app.services.contexte_ia import contexte_probleme
from app.services.historique import journaliser

_MENTION = re.compile(r"@([A-Za-z0-9._\-]{3,100})")


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


# ---------- Salons ----------

def creer_salon_probleme(db: Session, p: Probleme) -> Salon:
    s = Salon(application_id=p.application_id, type="probleme", probleme_id=p.id, titre=f"{p.code} · {p.titre}"[:255])
    db.add(s)
    db.flush()
    return s


def message_systeme(db: Session, probleme_id: int, texte: str) -> None:
    """Événement automatique, distinct des messages écrits par les utilisateurs."""
    salon = db.execute(select(Salon).where(Salon.probleme_id == probleme_id)).scalar_one_or_none()
    if salon is not None:
        db.add(MessageDiscussion(salon_id=salon.id, type="systeme", contenu=texte))


def synchroniser_archivage(db: Session, probleme_id: int, archive: bool) -> None:
    salon = db.execute(select(Salon).where(Salon.probleme_id == probleme_id)).scalar_one_or_none()
    if salon is not None:
        salon.archive = archive


def creer_salon_general(db: Session, app: Application, user: Utilisateur, titre: str) -> Salon:
    s = Salon(application_id=app.id, type="general", titre=titre, cree_par=user.id)
    db.add(s)
    db.flush()
    journaliser(db, application_id=app.id, type_element="salon", element_id=s.id, action="salon_cree", auteur_id=user.id)
    return s


def supprimer_salon(db: Session, salon: Salon, user: Utilisateur) -> None:
    """Un salon n'est jamais supprimé, sauf (suppression logique) par le chef de projet : la permission
    `salon.supprimer` est vérifiée par le routeur."""
    salon.supprime_le, salon.supprime_par = _maintenant(), user.id
    journaliser(db, application_id=salon.application_id, type_element="salon", element_id=salon.id,
                action="salon_supprime", auteur_id=user.id)


def lister_salons(db: Session, app: Application, user: Utilisateur) -> list[dict]:
    salons = db.execute(
        select(Salon).where(Salon.application_id == app.id, Salon.supprime_le.is_(None)).order_by(Salon.type, Salon.id)
    ).scalars().all()
    out = []
    for s in salons:
        lecture = db.get(SalonLecture, (s.id, user.id))
        q = select(func.count()).select_from(MessageDiscussion).where(
            MessageDiscussion.salon_id == s.id, MessageDiscussion.supprime_le.is_(None),
            MessageDiscussion.auteur_id.is_distinct_from(user.id),
        )
        if lecture:
            q = q.where(MessageDiscussion.cree_le > lecture.derniere_lecture_le)
        out.append({**{c: getattr(s, c) for c in ("id", "application_id", "type", "probleme_id", "titre", "archive", "cree_le")},
                    "non_lus": db.scalar(q) or 0})
    return out


def publier_message(db: Session, salon: Salon, user: Utilisateur, data: MessageIn) -> MessageDiscussion:
    if salon.supprime_le is not None or salon.archive:
        raise Conflit("Ce salon est archivé : lecture seule.")
    m = MessageDiscussion(salon_id=salon.id, parent_id=data.parent_id, tache_id=data.tache_id,
                          auteur_id=user.id, type="utilisateur", contenu=data.contenu)
    db.add(m)
    db.flush()
    identifiants = set(_MENTION.findall(data.contenu))
    if identifiants:
        mentionnes = db.execute(
            select(Utilisateur.id).join(MembreEquipe, MembreEquipe.utilisateur_id == Utilisateur.id)
            .join(Application, Application.equipe_id == MembreEquipe.equipe_id)
            .where(Application.id == salon.application_id, Utilisateur.identifiant.in_(identifiants))   # accès à l'application
        ).scalars().all()
        for uid in set(mentionnes):
            db.add(Mention(message_id=m.id, utilisateur_id=uid))
        notif.notifier(db, set(mentionnes), type_evenement="mention", message=f"{user.identifiant} vous a mentionné : {salon.titre}",
                       application_id=salon.application_id, type_element="salon", element_id=salon.id, declencheur_id=user.id)
    if data.parent_id:
        parent = db.get(MessageDiscussion, data.parent_id)
        if parent and parent.auteur_id:
            notif.notifier(db, {parent.auteur_id}, type_evenement="reponse_discussion",
                           message=f"{user.identifiant} a répondu à votre message ({salon.titre})",
                           application_id=salon.application_id, type_element="salon", element_id=salon.id,
                           declencheur_id=user.id)
    return m


def _message_de(db: Session, message_id: int, user: Utilisateur) -> MessageDiscussion:
    m = db.get(MessageDiscussion, message_id)
    if m is None or m.type != "utilisateur":
        raise NonTrouve("Message introuvable.")
    if m.auteur_id != user.id:
        raise AccesRefuse("Seul l'auteur peut modifier ou supprimer son message.")
    return m


def modifier_message(db: Session, message_id: int, user: Utilisateur, contenu: str) -> MessageDiscussion:
    m = _message_de(db, message_id, user)
    salon = db.get(Salon, m.salon_id)
    journaliser(db, application_id=salon.application_id, type_element="message", element_id=m.id,
                action="message_modifie", auteur_id=user.id, ancienne={"contenu": m.contenu}, nouvelle={"contenu": contenu})
    m.contenu, m.modifie_le = contenu, _maintenant()
    return m


def supprimer_message(db: Session, message_id: int, user: Utilisateur) -> None:
    m = _message_de(db, message_id, user)
    salon = db.get(Salon, m.salon_id)
    # suppression logique : le contenu reste conservé et visible dans l'historique
    journaliser(db, application_id=salon.application_id, type_element="message", element_id=m.id,
                action="message_supprime", auteur_id=user.id, ancienne={"contenu": m.contenu})
    m.supprime_le = _maintenant()


def marquer_salon_lu(db: Session, salon: Salon, user: Utilisateur) -> None:
    lecture = db.get(SalonLecture, (salon.id, user.id))
    if lecture is None:
        db.add(SalonLecture(salon_id=salon.id, utilisateur_id=user.id))
    else:
        lecture.derniere_lecture_le = _maintenant()


# ---------- Notes ----------

def ajouter_note(db: Session, app: Application, user: Utilisateur, data: NoteIn, *, probleme_id: int | None = None,
                 tache_id: int | None = None) -> Note:
    n = Note(application_id=app.id, probleme_id=probleme_id, tache_id=tache_id, auteur_id=user.id,
             type=data.type, contenu=data.contenu)
    db.add(n)
    db.flush()
    journaliser(db, application_id=app.id, type_element="note", element_id=n.id, action="note_ajoutee",
                auteur_id=user.id, nouvelle={"contenu": n.contenu, "type": n.type})
    return n


def _note_de(db: Session, note_id: int, user: Utilisateur) -> Note:
    n = db.get(Note, note_id)
    if n is None or n.supprime_le is not None:
        raise NonTrouve("Note introuvable.")
    if n.auteur_id != user.id:
        raise AccesRefuse("Seul l'auteur peut modifier ou supprimer sa note.")
    return n


def modifier_note(db: Session, note_id: int, user: Utilisateur, contenu: str) -> Note:
    n = _note_de(db, note_id, user)
    journaliser(db, application_id=n.application_id, type_element="note", element_id=n.id, action="note_modifiee",
                auteur_id=user.id, ancienne={"contenu": n.contenu}, nouvelle={"contenu": contenu})
    n.contenu, n.modifie_le = contenu, _maintenant()
    return n


def supprimer_note(db: Session, note_id: int, user: Utilisateur) -> None:
    n = _note_de(db, note_id, user)
    journaliser(db, application_id=n.application_id, type_element="note", element_id=n.id, action="note_supprimee",
                auteur_id=user.id, ancienne={"contenu": n.contenu})        # contenu conservé dans l'historique
    n.supprime_le = _maintenant()


# ---------- Assistant IA : une conversation COMMUNE par problème ----------

def conversation_du_probleme(db: Session, p: Probleme, user: Utilisateur) -> ConversationIA:
    c = db.execute(select(ConversationIA).where(ConversationIA.probleme_id == p.id)).scalar_one_or_none()
    if c is None:
        c = ConversationIA(probleme_id=p.id, application_id=p.application_id, cree_par=user.id)
        db.add(c)
        db.flush()
    return c


def messages_ia(db: Session, p: Probleme) -> list[MessageIA]:
    return list(db.execute(
        select(MessageIA).join(ConversationIA, ConversationIA.id == MessageIA.conversation_id)
        .where(ConversationIA.probleme_id == p.id).order_by(MessageIA.id)
    ).scalars())


def poser_question(db: Session, p: Probleme, user: Utilisateur, question: str, ia: ServiceIA,
                   tache_id: int | None = None, sous_tache_id: int | None = None) -> MessageIA:
    tache = db.get(Tache, tache_id) if tache_id else None
    sous = db.get(SousTache, sous_tache_id) if sous_tache_id else None
    if (tache and tache.probleme_id != p.id) or (sous and (tache is None or sous.tache_id != tache.id)):
        raise DonneesInvalides("La tâche ou la sous-tâche n'appartient pas à ce problème.")
    conv = conversation_du_probleme(db, p, user)
    historique = [
        {"emetteur": m.emetteur, "contenu": m.contenu} for m in messages_ia(db, p)[-10:]
    ]
    ctx = contexte_probleme(db, p, tache=tache, sous_tache=sous)
    reponse = ia.repondre(ctx, historique, question)          # IAIndisponible (503) si le service est en panne
    db.add(MessageIA(conversation_id=conv.id, emetteur="utilisateur", auteur_id=user.id, contenu=question,
                     tache_id=tache_id, sous_tache_id=sous_tache_id))
    refs = {"contexte": sorted(k for k, v in ctx.items() if v), "diagnostics": [d.id for d in p.diagnostics[:2]]}
    if reponse.solution:
        refs["solution_proposee"] = reponse.solution.model_dump()
    m = MessageIA(conversation_id=conv.id, emetteur="assistant", contenu=reponse.contenu,
                  informations_manquantes=reponse.informations_manquantes, niveau_confiance=reponse.niveau_confiance,
                  contexte_utilise=refs, tache_id=tache_id, sous_tache_id=sous_tache_id,
                  modele_ia=ia.modele, version_prompt=ia.version_prompt)
    db.add(m)
    db.flush()
    journaliser(db, application_id=p.application_id, type_element="probleme", element_id=p.id,
                action="question_assistant", auteur_id=user.id)
    return m


def proposer_comme_solution(db: Session, p: Probleme, message_id: int, user: Utilisateur) -> Solution:
    m = db.get(MessageIA, message_id)
    prop = (m.contexte_utilise or {}).get("solution_proposee") if m else None
    if m is None or not prop:
        raise NonTrouve("Aucune solution proposée dans ce message.")
    if m.solution_id:
        raise Conflit("Ce message est déjà devenu une solution.")
    d = Diagnostic(probleme_id=p.id, explication=f"Proposition issue de l'assistant IA (message n°{m.id}).",
                   modele_ia=m.modele_ia, version_prompt=m.version_prompt)
    db.add(d)
    db.flush()
    s = Solution(diagnostic_id=d.id, description=prop["description"], extrait_code=prop.get("extrait_code"),
                 format_code=prop.get("format_code", "extrait"), risques=prop.get("risques"),
                 tests_suggeres=prop.get("tests_suggeres"))
    db.add(s)
    db.flush()
    m.solution_id = s.id
    journaliser(db, application_id=p.application_id, type_element="solution", element_id=s.id,
                action="solution_depuis_assistant", auteur_id=user.id)
    return s


def partager_dans_salon(db: Session, p: Probleme, message_id: int, user: Utilisateur) -> MessageDiscussion:
    m = db.get(MessageIA, message_id)
    salon = db.execute(select(Salon).where(Salon.probleme_id == p.id)).scalar_one_or_none()
    if m is None or m.emetteur != "assistant" or salon is None:
        raise NonTrouve("Message ou salon introuvable.")
    msg = MessageDiscussion(salon_id=salon.id, auteur_id=user.id, type="utilisateur",
                            contenu=f"[Partagé depuis l'assistant IA · hypothèse non vérifiée]\n{m.contenu}")
    db.add(msg)
    db.flush()
    return msg
