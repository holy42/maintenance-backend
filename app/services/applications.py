from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import AccesRefuse, Conflit, DonneesInvalides
from app.core.permissions import TOUS, permissions_dans_equipe
from app.models import (
    Application, ApplicationTechnologie, Equipe, Probleme, SessionTest, Tache, Technologie, Utilisateur, Verification,
)
from app.schemas.application import ApplicationCreate, ApplicationUpdate
from app.services.historique import journaliser


def _technologies(db: Session, app: Application, noms: list[str]) -> None:
    db.query(ApplicationTechnologie).filter(ApplicationTechnologie.application_id == app.id).delete()
    for nom in {n.strip().lower() for n in noms if n.strip()}:
        t = db.execute(select(Technologie).where(func.lower(Technologie.nom) == nom, Technologie.framework.is_(None))
                       ).scalar_one_or_none()
        if t is None:
            t = Technologie(nom=nom)
            db.add(t)
            db.flush()
        db.add(ApplicationTechnologie(application_id=app.id, technologie_id=t.id))


def creer_application(db: Session, user: Utilisateur, data: ApplicationCreate) -> Application:
    if db.get(Equipe, data.equipe_id) is None:
        raise DonneesInvalides("Équipe introuvable.")
    perms = permissions_dans_equipe(db, user, data.equipe_id)
    if TOUS not in perms and "application.configurer" not in perms:
        raise AccesRefuse("Permission requise : application.configurer.")
    app = Application(equipe_id=data.equipe_id, nom=data.nom, description=data.description,
                      responsable_id=data.responsable_id)
    db.add(app)
    db.flush()
    _technologies(db, app, data.technologies)
    journaliser(db, application_id=app.id, type_element="application", element_id=app.id, action="application_creee",
                auteur_id=user.id, nouvelle={"nom": app.nom})
    return app


def modifier_application(db: Session, app: Application, user: Utilisateur, data: ApplicationUpdate) -> Application:
    champs = data.model_dump(exclude_unset=True)
    technos = champs.pop("technologies", None)
    for k, v in champs.items():
        setattr(app, k, v)
    if technos is not None:
        _technologies(db, app, technos)
    journaliser(db, application_id=app.id, type_element="application", element_id=app.id, action="application_modifiee",
                auteur_id=user.id, nouvelle=champs | ({"technologies": technos} if technos is not None else {}))
    return app


def definir_statut(db: Session, app: Application, user: Utilisateur, statut: str) -> Application:
    if app.statut == statut:
        raise Conflit(f"L'application est déjà « {statut} ».")
    ancien, app.statut = app.statut, statut
    journaliser(db, application_id=app.id, type_element="application", element_id=app.id, action="application_statut",
                auteur_id=user.id, ancienne={"statut": ancien}, nouvelle={"statut": statut})
    return app


def vue_ensemble(db: Session, app: Application) -> dict:
    def n(q):
        return db.scalar(q) or 0
    ouverts = Probleme.statut.notin_(("faux_positif", "termine"))
    derniere = db.execute(select(Verification).where(Verification.application_id == app.id)
                          .order_by(Verification.debut_le.desc())).scalars().first()
    return {
        "problemes_ouverts": n(select(func.count()).select_from(Probleme).where(Probleme.application_id == app.id, ouverts)),
        "problemes_critiques": n(select(func.count()).select_from(Probleme).where(
            Probleme.application_id == app.id, ouverts, Probleme.gravite == "critique")),
        "taches_en_cours": n(select(func.count()).select_from(Tache).where(Tache.application_id == app.id, Tache.statut == "en_cours")),
        "taches_en_retard": n(select(func.count()).select_from(Tache).where(
            Tache.application_id == app.id, Tache.echeance < func.current_date(), Tache.statut.notin_(("terminee", "arretee")))),
        "tests_en_attente": n(select(func.count()).select_from(SessionTest).where(
            SessionTest.application_id == app.id, SessionTest.statut.in_(("a_tester", "en_cours")))),
        "corrections_en_attente_de_test": n(select(func.count()).select_from(Probleme).where(
            Probleme.application_id == app.id, Probleme.statut == "a_tester")),
        "derniere_verification": None if derniere is None else {
            "id": derniere.id, "branche": derniere.branche, "commit": derniere.commit_analyse, "statut": derniere.statut,
            "resultat_global": derniere.resultat_global, "debut_le": derniere.debut_le},
    }


def technologies_par_application(db: Session, ids: list[int]) -> dict[int, list[str]]:
    """{application_id: ["php", "javascript", ...]} pour l'affichage."""
    if not ids:
        return {}
    out: dict[int, list[str]] = {}
    lignes = db.execute(
        select(ApplicationTechnologie.application_id, Technologie.nom)
        .join(Technologie, Technologie.id == ApplicationTechnologie.technologie_id)
        .where(ApplicationTechnologie.application_id.in_(ids)).order_by(Technologie.nom)
    ).all()
    for app_id, nom in lignes:
        out.setdefault(app_id, []).append(nom)
    return out
