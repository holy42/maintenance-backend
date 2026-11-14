"""Environnement Alembic. La base est créée par la migration 0001 (script SQL complet) ; les migrations
suivantes se rédigent à la main : l'autogénération ne voit ni les vues, ni les déclencheurs, ni les
contraintes composées du script SQL."""
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine

# Les exécutables de console placent le dossier `.venv\Scripts` sur sys.path,
# pas nécessairement le dossier du projet.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.models import Base  # noqa: F401  (importe tous les modèles)

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=settings.database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(settings.database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
