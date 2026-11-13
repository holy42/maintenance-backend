"""Préférences personnelles des canaux de notification.

Revision ID: 0003
Revises: 0002
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().connection.cursor().execute("""
        CREATE TABLE IF NOT EXISTS preference_canal_notification (
            utilisateur_id BIGINT PRIMARY KEY REFERENCES utilisateur(id) ON DELETE CASCADE,
            son_active BOOLEAN NOT NULL DEFAULT TRUE,
            navigateur_actif BOOLEAN NOT NULL DEFAULT TRUE
        )
    """)


def downgrade() -> None:
    raise RuntimeError("Pas de retour arrière automatique : recréez la base (DROP SCHEMA public CASCADE).")
