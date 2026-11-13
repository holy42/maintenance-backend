"""Notifications internes, historique de toutes les activités (lecture seule) et rapports."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import utilisateur_courant
from app.api.helpers import application_autorisee, obtenir, probleme_autorise
from app.core.enums import Perm
from app.core.permissions import applications_accessibles_ids
from app.database import get_db
from app.models import EvenementHistorique, Notification, PreferenceCanalNotification, PreferenceNotification, Rapport, Tache, Utilisateur
from app.schemas.collaboration import NotificationOut, PreferenceCanalNotificationIn, PreferenceIn
from app.schemas.common import Message
from app.services import rapports as svc_rapports

router = APIRouter(tags=["Suivi"])


# ---------- Notifications ----------

@router.get("/notifications", response_model=list[NotificationOut])
def notifications(non_lues: bool = False, type_evenement: str | None = None, application_id: int | None = None,
                  apres_id: int | None = None, limit: int = 100, db: Session = Depends(get_db),
                  user: Utilisateur = Depends(utilisateur_courant)):
    q = select(Notification).where(Notification.destinataire_id == user.id)
    if non_lues:
        q = q.where(Notification.lu.is_(False))
    if type_evenement:
        q = q.where(Notification.type_evenement == type_evenement)
    if application_id:
        q = q.where(Notification.application_id == application_id)
    if apres_id is not None:
        q = q.where(Notification.id > apres_id).order_by(Notification.id.asc())
    else:
        q = q.order_by(Notification.cree_le.desc())
    return db.execute(q.limit(min(limit, 300))).scalars().all()


@router.get("/notifications/compteur")
def compteur(db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    from sqlalchemy import func
    non_lues, dernier_id = db.execute(select(
        func.count().filter(Notification.lu.is_(False)), func.max(Notification.id)
    ).where(Notification.destinataire_id == user.id)).one()
    return {"non_lues": non_lues or 0, "dernier_id": dernier_id}


@router.post("/notifications/tout-lire", response_model=Message)
def tout_lire(db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    maintenant = datetime.now(timezone.utc)
    for n in db.execute(select(Notification).where(Notification.destinataire_id == user.id, Notification.lu.is_(False))).scalars():
        n.lu, n.lu_le = True, maintenant
    return Message(message="Toutes les notifications sont marquées comme lues.")


def _ma_notification(db: Session, user: Utilisateur, nid: int) -> Notification:
    n = obtenir(db.get(Notification, nid), "Notification introuvable.")
    if n.destinataire_id != user.id:
        obtenir(None, "Notification introuvable.")
    return n


@router.post("/notifications/{notification_id}/lue", response_model=NotificationOut)
def marquer_lue(notification_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    n = _ma_notification(db, user, notification_id)
    n.lu, n.lu_le = True, datetime.now(timezone.utc)
    return n


@router.post("/notifications/{notification_id}/non-lue", response_model=NotificationOut)
def marquer_non_lue(notification_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    n = _ma_notification(db, user, notification_id)
    n.lu, n.lu_le = False, None
    return n


@router.get("/notifications/preferences", response_model=list[PreferenceIn])
def preferences(db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    return [PreferenceIn(type_evenement=p.type_evenement, active=p.active)
            for p in db.execute(select(PreferenceNotification).where(PreferenceNotification.utilisateur_id == user.id)).scalars()]


@router.put("/notifications/preferences", response_model=Message)
def definir_preferences(data: list[PreferenceIn], db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    for d in data:
        p = db.get(PreferenceNotification, (user.id, d.type_evenement))
        if p is None:
            db.add(PreferenceNotification(utilisateur_id=user.id, type_evenement=d.type_evenement, active=d.active))
        else:
            p.active = d.active
    return Message(message="Préférences enregistrées.")


@router.get("/notifications/preferences-canaux", response_model=PreferenceCanalNotificationIn)
def preferences_canaux(db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    pref = db.get(PreferenceCanalNotification, user.id)
    if pref is None:
        return PreferenceCanalNotificationIn()
    return PreferenceCanalNotificationIn(son=pref.son_active, navigateur=pref.navigateur_actif)


@router.put("/notifications/preferences-canaux", response_model=Message)
def definir_preferences_canaux(data: PreferenceCanalNotificationIn, db: Session = Depends(get_db),
                               user: Utilisateur = Depends(utilisateur_courant)):
    pref = db.get(PreferenceCanalNotification, user.id)
    if pref is None:
        db.add(PreferenceCanalNotification(
            utilisateur_id=user.id, son_active=data.son, navigateur_actif=data.navigateur,
        ))
    else:
        pref.son_active = data.son
        pref.navigateur_actif = data.navigateur
    return Message(message="Préférences de notification enregistrées.")


# ---------- Historique (toutes les activités, quel que soit l'auteur ; lecture seule) ----------

class EvenementOut(BaseModel):
    id: int
    application_id: int | None
    type_element: str
    element_id: int
    auteur_id: int | None
    action: str
    ancienne_valeur: dict | None
    nouvelle_valeur: dict | None
    commentaire: str | None
    cree_le: datetime

    model_config = {"from_attributes": True}


def _requete_historique(db, user, application_id, type_element, auteur_id, action, jours):
    q = select(EvenementHistorique)
    if application_id:
        application_autorisee(db, user, application_id, Perm.HISTORIQUE_CONSULTER)
        q = q.where(EvenementHistorique.application_id == application_id)
    else:
        ids = applications_accessibles_ids(db, user)
        if ids is not None:
            q = q.where(EvenementHistorique.application_id.in_(ids))
    for col, val in ((EvenementHistorique.type_element, type_element), (EvenementHistorique.auteur_id, auteur_id),
                     (EvenementHistorique.action, action)):
        if val is not None:
            q = q.where(col == val)
    if jours:
        q = q.where(EvenementHistorique.cree_le >= datetime.now(timezone.utc) - timedelta(days=jours))
    return q


@router.get("/historique", response_model=list[EvenementOut])
def historique(application_id: int | None = None, type_element: str | None = None, auteur_id: int | None = None,
               action: str | None = None, jours: int | None = 30, limit: int = 200, offset: int = 0,
               db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    q = _requete_historique(db, user, application_id, type_element, auteur_id, action, jours)
    return db.execute(q.order_by(EvenementHistorique.cree_le.desc()).limit(min(limit, 500)).offset(offset)).scalars().all()


@router.get("/problemes/{probleme_id}/historique", response_model=list[EvenementOut])
def historique_probleme(probleme_id: int, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    p, _ = probleme_autorise(db, user, probleme_id, Perm.HISTORIQUE_CONSULTER)
    ids_taches = list(db.execute(select(Tache.id).where(Tache.probleme_id == p.id)).scalars())
    E = EvenementHistorique
    q = select(E).where(((E.type_element == "probleme") & (E.element_id == p.id))
                        | ((E.type_element == "tache") & (E.element_id.in_(ids_taches or [0]))))
    return db.execute(q.order_by(E.cree_le.desc())).scalars().all()


# ---------- Rapports ----------

def _ids(db, user, application_id):
    if application_id:
        application_autorisee(db, user, application_id, Perm.RAPPORT_CONSULTER)
        return [application_id]
    return applications_accessibles_ids(db, user)


@router.get("/rapports/problemes-taches")
def rapport_problemes_taches(application_id: int | None = None, jours: int = 30, db: Session = Depends(get_db),
                             user: Utilisateur = Depends(utilisateur_courant)):
    return svc_rapports.rapport_problemes_taches(db, _ids(db, user, application_id), jours)


@router.get("/rapports/ia-tests")
def rapport_ia_tests(application_id: int | None = None, db: Session = Depends(get_db),
                     user: Utilisateur = Depends(utilisateur_courant)):
    return svc_rapports.rapport_ia_tests(db, _ids(db, user, application_id))


class RapportEnregistrerIn(BaseModel):
    type: str                    # problemes_taches | ia_tests
    application_id: int | None = None
    jours: int = 30


@router.post("/rapports", status_code=201)
def enregistrer_rapport(data: RapportEnregistrerIn, db: Session = Depends(get_db), user: Utilisateur = Depends(utilisateur_courant)):
    """Garde une photographie datée du rapport (pour comparer plus tard ou l'exporter)."""
    ids = _ids(db, user, data.application_id)
    contenu = (svc_rapports.rapport_problemes_taches(db, ids, data.jours) if data.type == "problemes_taches"
               else svc_rapports.rapport_ia_tests(db, ids))
    r = svc_rapports.enregistrer_rapport(db, user, data.type, data.application_id, None,
                                         {"jours": data.jours}, jsonable_encoder(contenu))
    return {"id": r.id, "genere_le": r.genere_le}


@router.get("/rapports")
def rapports_enregistres(application_id: int | None = None, db: Session = Depends(get_db),
                         user: Utilisateur = Depends(utilisateur_courant)):
    ids = _ids(db, user, application_id)
    q = select(Rapport)
    if ids is not None:
        q = q.where(Rapport.application_id.in_(ids))
    return [{"id": r.id, "type": r.type, "application_id": r.application_id, "genere_le": r.genere_le, "contenu": r.contenu}
            for r in db.execute(q.order_by(Rapport.genere_le.desc()).limit(50)).scalars()]
