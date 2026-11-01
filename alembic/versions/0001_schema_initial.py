"""Schéma initial : exécute le script SQL complet (tables, vues, déclencheurs, rôles et permissions).

Revision ID: 0001
Revises:
"""
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCRIPT = Path(__file__).resolve().parents[2] / "sql" / "schema_base_de_donnees.sql"


def upgrade() -> None:
    # curseur brut du pilote : le script contient des « % » et des blocs $$ qu'il ne faut pas interpréter
    curseur = op.get_bind().connection.cursor()
    curseur.execute(SCRIPT.read_text(encoding="utf-8"))


def downgrade() -> None:
    raise RuntimeError("Pas de retour arrière automatique : recréez la base (DROP SCHEMA public CASCADE).")
