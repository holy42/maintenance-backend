"""Contexte envoyé à l'IA : limité au nécessaire, secrets masqués, taille bornée.
Le contexte d'un problème n'inclut jamais les données d'un autre problème."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.secrets_filter import preparer_extrait
from app.config import settings
from app.fiabilite.libelles import libelle
from app.fiabilite.service import ServiceFiabilite
from app.models import Note, Probleme, SousTache, Tache


def contexte_probleme(db: Session, p: Probleme, *, avec_solutions: bool = True, tache: Tache | None = None,
                      sous_tache: SousTache | None = None) -> dict:
    limite = settings.ai_max_context_chars
    ctx: dict = {
        "code": p.code, "titre": p.titre, "categorie": p.categorie, "gravite": p.gravite,
        "description": p.description, "comportement_attendu": p.comportement_attendu,
        "comportement_observe": p.comportement_observe, "fichier": p.fichier,
        "lignes": [p.ligne_debut, p.ligne_fin], "fonction": p.fonction,
        "extrait_code": preparer_extrait(p.extrait_code, limite // 2),
    }
    preuve = ServiceFiabilite(db).preuve_du_probleme(p)
    if preuve is not None:     # étape 4 : on transmet la fiabilité de la preuve et ses points faibles
        facteurs = [{"facteur": libelle(f["variable"]), "sens": f["sens"]} for f in (preuve.explication or [])]
        ctx["fiabilite_preuve"] = {"score_pct": round(float(preuve.score) * 100), "niveau": preuve.niveau,
                                   "appris": preuve.source == "modele", "facteurs": facteurs}
        ctx["incertitudes_identifiees"] = [f"{libelle(f['variable'])} : {f['sens']} la fiabilité de la preuve"
                                           for f in (preuve.explication or []) if f.get("effet", 0) < 0]
    if avec_solutions:
        ctx["diagnostics_precedents"] = [
            {
                "id": d.id, "explication": d.explication, "incertitudes": d.incertitudes,
                "solutions": [
                    {"id": s.id, "description": s.description, "extrait_code": preparer_extrait(s.extrait_code, 1500)}
                    for s in d.solutions
                ],
            }
            for d in p.diagnostics[:2]
        ]
    notes = db.execute(
        select(Note.contenu).where(Note.probleme_id == p.id, Note.supprime_le.is_(None))
        .order_by(Note.cree_le.desc()).limit(5)
    ).scalars().all()
    ctx["notes"] = [preparer_extrait(n, 500) for n in notes]
    if tache is not None:
        ctx["tache"] = {"titre": tache.titre, "statut": tache.statut}
    if sous_tache is not None:
        ctx["sous_tache"] = {"titre": sous_tache.titre, "statut": sous_tache.statut}
    return ctx
