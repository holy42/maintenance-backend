"""Rapports : lecture des vues d'indicateurs du script SQL.
Limites assumées : la période ne filtre que les comptages directs ; les vues d'indicateurs IA et tests
sont cumulées sur toute la durée. L'utilité perçue n'est pas la réussite (c'est le test qui l'établit)."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import Rapport, Utilisateur


def _filtre(ids: list[int] | None, alias: str = "") -> tuple[str, dict]:
    col = f"{alias}application_id"
    return ("" if ids is None else f" WHERE {col} = ANY(:ids)"), ({} if ids is None else {"ids": ids})


def _lignes(db: Session, sql: str, params: dict) -> list[dict]:
    return [dict(r) for r in db.execute(text(sql), params).mappings().all()]


def rapport_problemes_taches(db: Session, ids: list[int] | None, jours: int = 30) -> dict:
    where, p = _filtre(ids)
    depuis = datetime.now(timezone.utc) - timedelta(days=jours)
    cond_ids = "" if ids is None else " AND application_id = ANY(:ids)"
    base = {**p, "depuis": depuis}
    crees = db.execute(text(f"SELECT count(*) FROM probleme WHERE cree_le >= :depuis{cond_ids}"), base).scalar()
    termines = db.execute(text(
        f"SELECT count(DISTINCT element_id) FROM historique_statut WHERE type_element='probleme' "
        f"AND nouveau_statut='termine' AND cree_le >= :depuis{cond_ids}"), base).scalar()
    return {
        "periode_jours": jours, "problemes_crees": crees, "problemes_termines": termines,
        "par_gravite": _lignes(db, f"SELECT gravite, sum(nb)::int AS nb FROM v_problemes_par_gravite{where} GROUP BY gravite", p),
        "par_categorie": _lignes(db, f"SELECT categorie, sum(nb)::int AS nb FROM v_problemes_par_gravite{where} GROUP BY categorie", p),
        "par_application": _lignes(db, f"SELECT application_id, sum(nb)::int AS nb FROM v_problemes_par_gravite{where} GROUP BY application_id", p),
        "evolution": _lignes(db, f"SELECT mois, sum(nb_crees)::int AS nb FROM v_evolution_problemes{where} GROUP BY mois ORDER BY mois", p),
        "temps_moyen_resolution": _lignes(db, f"SELECT gravite, sum(nb_resolus)::int AS nb_resolus, avg(duree_moyenne) AS duree_moyenne "
                                              f"FROM v_temps_moyen_resolution{where} GROUP BY gravite", p),
        "taches": _lignes(db, f"SELECT statut, sum(nb)::int AS nb, sum(nb_en_retard)::int AS nb_en_retard FROM v_taches_stats{where} GROUP BY statut", p),
    }


def rapport_ia_tests(db: Session, ids: list[int] | None) -> dict:
    where, p = _filtre(ids)
    return {
        "decisions_correction": _lignes(db, f"SELECT type_decision, sum(nb)::int AS nb FROM v_decisions_correction{where} GROUP BY type_decision", p),
        "utilite_solutions_ia": _lignes(db, f"SELECT utilite_percue, sum(nb)::int AS nb FROM v_utilite_solutions_ia{where} GROUP BY utilite_percue", p),
        "faux_positifs": _lignes(db, f"SELECT * FROM v_faux_positifs{where}", p),
        "validation_tests": _lignes(db, f"SELECT * FROM v_validation_tests{where}", p),
        "problemes_rouverts": _lignes(db, f"SELECT * FROM v_problemes_rouverts{where}", p),
        "validation_par_decision": _lignes(db, f"SELECT * FROM v_validation_par_decision{where}", p),
        "avertissement": "Indicateurs cumulés. L'utilité perçue est l'avis du développeur, pas une preuve ; une solution "
                         "retenue n'est pas forcément correcte (le test l'établit) ; les faux positifs reposent sur des "
                         "décisions humaines, sans vérité de référence. Avec peu de données, aucune généralisation.",
    }


def enregistrer_rapport(db: Session, user: Utilisateur, type_: str, application_id: int | None, equipe_id: int | None,
                        parametres: dict, contenu: dict) -> Rapport:
    r = Rapport(type=type_, application_id=application_id, equipe_id=equipe_id, parametres=parametres,
                contenu=contenu, genere_par=user.id)
    db.add(r)
    db.flush()
    return r
