"""Chargement d'objets + contrôle d'accès (côté serveur, à chaque requête)."""
from sqlalchemy.orm import Session

from app.core.exceptions import NonTrouve
from app.core.permissions import verifier_acces
from app.models import (
    Application, Critere, Probleme, ResultatAnalyse, Salon, SessionTest, Tache, TestCorrection, Utilisateur, Verification,
)


def obtenir(objet, message: str):
    """Retourne l'objet ou lève NonTrouve (404)."""
    if objet is None:
        raise NonTrouve(message)
    return objet


def _app(db: Session, application_id: int) -> Application:
    app = db.get(Application, application_id)
    if app is None:
        raise NonTrouve("Application introuvable.")
    return app


def application_autorisee(db: Session, user: Utilisateur, application_id: int, permission: str | None = None,
                          ecriture: bool = False) -> Application:
    app = _app(db, application_id)
    verifier_acces(db, user, app, permission, ecriture)
    return app


def probleme_autorise(db: Session, user: Utilisateur, probleme_id: int, permission: str | None = None,
                      ecriture: bool = False) -> tuple[Probleme, Application]:
    p = db.get(Probleme, probleme_id)
    if p is None:
        raise NonTrouve("Problème introuvable.")
    return p, application_autorisee(db, user, p.application_id, permission, ecriture)


def tache_autorisee(db: Session, user: Utilisateur, tache_id: int, permission: str | None = None,
                    ecriture: bool = False) -> tuple[Tache, Application, set[str]]:
    t = db.get(Tache, tache_id)
    if t is None:
        raise NonTrouve("Tâche introuvable.")
    app = _app(db, t.application_id)
    return t, app, verifier_acces(db, user, app, permission, ecriture)


def verification_autorisee(db: Session, user: Utilisateur, vid: int, permission: str | None = None
                           ) -> tuple[Verification, Application]:
    v = db.get(Verification, vid)
    if v is None:
        raise NonTrouve("Vérification introuvable.")
    return v, application_autorisee(db, user, v.application_id, permission)


def resultat_autorise(db: Session, user: Utilisateur, rid: int, permission: str | None = None, ecriture: bool = False
                      ) -> tuple[ResultatAnalyse, Verification, Application]:
    r = db.get(ResultatAnalyse, rid)
    if r is None:
        raise NonTrouve("Résultat introuvable.")
    v = db.get(Verification, r.verification_id)
    return r, v, application_autorisee(db, user, v.application_id, permission, ecriture)


def critere_autorise(db: Session, user: Utilisateur, cid: int, permission: str | None = None
                     ) -> tuple[Critere, Application | None]:
    c = db.get(Critere, cid)
    if c is None:
        raise NonTrouve("Critère introuvable.")
    if c.application_id is None:                       # critère standard : visible de tous
        return c, None
    return c, application_autorisee(db, user, c.application_id, permission, ecriture=permission is not None)


def salon_autorise(db: Session, user: Utilisateur, salon_id: int, permission: str | None = None) -> tuple[Salon, Application]:
    s = db.get(Salon, salon_id)
    if s is None or s.supprime_le is not None:
        raise NonTrouve("Salon introuvable.")
    return s, application_autorisee(db, user, s.application_id, permission)


def session_autorisee(db: Session, user: Utilisateur, sid: int, permission: str | None = None
                      ) -> tuple[SessionTest, TestCorrection, Application]:
    s = db.get(SessionTest, sid)
    if s is None:
        raise NonTrouve("Passage de test introuvable.")
    test = db.get(TestCorrection, s.test_id)
    return s, test, application_autorisee(db, user, s.application_id, permission)
