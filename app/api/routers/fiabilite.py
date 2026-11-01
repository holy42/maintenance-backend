"""Gestion du modèle de fiabilité (administrateur) : jeu de données étiqueté, entraînement, versions, activation."""
import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import utilisateur_courant
from app.core.exceptions import Conflit, NonTrouve
from app.core.permissions import exiger_admin
from app.database import get_db
from app.fiabilite.service import ServiceFiabilite
from app.models import ModeleFiabiliteVersion, Utilisateur
from app.schemas.fiabilite import EntrainementIn, ModeleVersionOut
from app.services.historique import journaliser

router = APIRouter(prefix="/fiabilite", tags=["Modèle de fiabilité"])


def _admin(user: Utilisateur = Depends(utilisateur_courant)) -> Utilisateur:
    exiger_admin(user)
    return user


@router.get("/apercu")
def apercu(db: Session = Depends(get_db), _: Utilisateur = Depends(_admin)):
    """Nombre d'exemples étiquetés par étape (3 : preuves de l'analyse ; 6 : solutions de Gemini) et version active."""
    svc = ServiceFiabilite(db)
    actives = {v.etape: v.version for v in db.execute(select(ModeleFiabiliteVersion).where(ModeleFiabiliteVersion.actif.is_(True))).scalars()}
    return [{**svc.apercu(e), "version_active": actives.get(e)} for e in (3, 6)]


@router.get("/modeles", response_model=list[ModeleVersionOut])
def modeles(db: Session = Depends(get_db), _: Utilisateur = Depends(_admin)):
    return db.execute(select(ModeleFiabiliteVersion).order_by(ModeleFiabiliteVersion.etape, ModeleFiabiliteVersion.version.desc())).scalars().all()


@router.post("/modeles/entrainer", response_model=ModeleVersionOut, status_code=201)
def entrainer(data: EntrainementIn, db: Session = Depends(get_db), admin: Utilisateur = Depends(_admin)):
    """Entraîne une nouvelle version (inactive) sur les exemples étiquetés. 409 si le jeu est insuffisant ou si les variables
    n'apportent rien par rapport à une prédiction constante."""
    if data.etape not in (3, 6) or data.algorithme not in ("auto", "logistique", "foret"):
        raise Conflit("Étape (3 ou 6) ou algorithme (auto, logistique, foret) invalide.")
    try:
        v = ServiceFiabilite(db).entrainer(data.etape, admin.id, data.algorithme)
    except ValueError as exc:
        raise Conflit(str(exc)) from exc
    journaliser(db, application_id=None, type_element="modele_fiabilite", element_id=v.id, action="modele_entraine", auteur_id=admin.id,
                nouvelle={"etape": v.etape, "version": v.version, "algorithme": v.algorithme, "n": v.nb_exemples})
    return v


@router.post("/modeles/{version_id}/activer", response_model=ModeleVersionOut)
def activer(version_id: int, db: Session = Depends(get_db), admin: Utilisateur = Depends(_admin)):
    try:
        v = ServiceFiabilite(db).activer(version_id)
    except LookupError as exc:
        raise NonTrouve(str(exc)) from exc
    journaliser(db, application_id=None, type_element="modele_fiabilite", element_id=v.id, action="modele_active", auteur_id=admin.id,
                nouvelle={"etape": v.etape, "version": v.version})
    return v


@router.get("/jeu-donnees")
def jeu_donnees(etape: int = Query(3), db: Session = Depends(get_db), _: Utilisateur = Depends(_admin)):
    """Exemples étiquetés au format CSV (utilisable avec `python -m app.fiabilite.cli comparer`)."""
    if etape not in (3, 6):
        raise Conflit("Étape invalide (3 ou 6).")
    noms, X, y = ServiceFiabilite(db).jeu_de_donnees(etape)
    sortie = io.StringIO()
    w = csv.writer(sortie)
    w.writerow([*noms, "etiquette"])
    for x, yi in zip(X, y):
        w.writerow([*x, yi])
    return Response(sortie.getvalue(), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=fiabilite_etape{etape}.csv"})
