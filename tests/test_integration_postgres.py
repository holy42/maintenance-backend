"""Teste les déclencheurs SQL sur une VRAIE base PostgreSQL vide (non exécuté par l'auteur du squelette).
Lancer :  TEST_DATABASE_URL=postgresql+psycopg2://... pytest tests/test_integration_postgres.py"""
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL non défini")


@pytest.fixture()
def conn():
    engine = create_engine(URL)
    with engine.begin() as c:
        c.exec_driver_sql("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        c.connection.cursor().execute((Path(__file__).parents[1] / "sql" / "schema_base_de_donnees.sql").read_text(encoding="utf-8"))
    with engine.connect() as c:
        yield c


def _jeu(c):
    c.execute(text("INSERT INTO utilisateur (identifiant, mot_de_passe_hash) VALUES ('dev','x')"))
    c.execute(text("INSERT INTO equipe (nom) VALUES ('Alpha')"))
    c.execute(text("INSERT INTO application (equipe_id, nom) VALUES (1,'App')"))
    c.execute(text("INSERT INTO probleme (application_id, source, titre, categorie, statut) VALUES (1,'humain','P','fonctionnel','en_cours')"))
    c.execute(text("INSERT INTO tache (probleme_id, application_id, titre, cree_par, statut) VALUES (1,1,'T',1,'en_cours')"))
    c.execute(text("INSERT INTO sous_tache (tache_id, titre, ordre, origine) VALUES (1,'S',1,'utilisateur')"))


def test_tache_non_terminable_avec_sous_tache_ouverte(conn):
    _jeu(conn)
    with pytest.raises(DBAPIError):
        conn.execute(text("UPDATE tache SET statut='terminee' WHERE id=1"))


def test_historique_en_ajout_seul(conn):
    conn.execute(text("INSERT INTO evenement_historique (type_element, element_id, action) VALUES ('x',1,'a')"))
    with pytest.raises(DBAPIError):
        conn.execute(text("DELETE FROM evenement_historique"))
