"""Notifications d'échéance proche. À lancer par cron (voir README) :
    0 7 * * *  cd /chemin/backend && .venv/bin/python -m app.jobs.echeances
Une seule notification par destinataire, par élément et par jour."""
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Notification, Probleme, Tache
from app.services.notifications import notifier


def _deja_notifie(db: Session, uid: int, type_element: str, element_id: int) -> bool:
    debut = datetime.combine(date.today(), time.min, tzinfo=timezone.utc)
    return db.execute(select(Notification.id).where(
        Notification.destinataire_id == uid, Notification.type_evenement == "echeance_proche",
        Notification.type_element == type_element, Notification.element_id == element_id,
        Notification.cree_le >= debut)).first() is not None


def notifier_echeances(db: Session) -> int:
    limite = date.today() + timedelta(days=settings.echeance_jours_avant)
    n = 0
    taches = db.execute(select(Tache).where(
        Tache.echeance <= limite, Tache.statut.notin_(("terminee", "arretee")), Tache.responsable_id.is_not(None))).scalars()
    for t in taches:
        if not _deja_notifie(db, t.responsable_id, "tache", t.id):
            n += notifier(db, {t.responsable_id}, type_evenement="echeance_proche",
                          message=f"Échéance le {t.echeance:%d/%m} : « {t.titre} »", application_id=t.application_id,
                          type_element="tache", element_id=t.id)
    problemes = db.execute(select(Probleme).where(
        Probleme.echeance <= limite, Probleme.statut.notin_(("faux_positif", "termine", "teste")),
        Probleme.responsable_id.is_not(None))).scalars()
    for p in problemes:
        if not _deja_notifie(db, p.responsable_id, "probleme", p.id):
            n += notifier(db, {p.responsable_id}, type_evenement="echeance_proche",
                          message=f"Échéance le {p.echeance:%d/%m} : {p.code} {p.titre}", application_id=p.application_id,
                          type_element="probleme", element_id=p.id)
    return n


def main() -> None:
    db = SessionLocal()
    try:
        n = notifier_echeances(db)
        db.commit()
        print(f"{n} notification(s) d'échéance créée(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
