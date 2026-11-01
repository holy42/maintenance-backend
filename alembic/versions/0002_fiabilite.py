"""Modèle de fiabilité : tables `modele_fiabilite` et `evaluation_fiabilite`, colonne `diagnostic.verifications_recommandees`.

IDEMPOTENTE : sur une base neuve, le script SQL exécuté par 0001 contient déjà ces objets ; sur une base créée avant l'ajout du
modèle de fiabilité, cette révision les ajoute. Il n'y a rien à faire en plus.

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

SQL = """
ALTER TABLE diagnostic ADD COLUMN IF NOT EXISTS verifications_recommandees JSONB;

CREATE TABLE IF NOT EXISTS modele_fiabilite (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    etape        SMALLINT NOT NULL CHECK (etape IN (3, 6)),
    version      INT NOT NULL,
    algorithme   VARCHAR(20) NOT NULL CHECK (algorithme IN ('logistique','foret')),
    nb_exemples  INT,
    metriques    JSONB,
    parametres   JSONB NOT NULL,
    actif        BOOLEAN NOT NULL DEFAULT FALSE,
    entraine_par BIGINT REFERENCES utilisateur(id),
    entraine_le  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (etape, version)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_modele_fiabilite_actif ON modele_fiabilite(etape) WHERE actif;

CREATE TABLE IF NOT EXISTS evaluation_fiabilite (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    etape          SMALLINT NOT NULL CHECK (etape IN (3, 6)),
    cible_type     VARCHAR(15) NOT NULL CHECK (cible_type IN ('resultat','solution')),
    cible_id       BIGINT NOT NULL,
    application_id BIGINT NOT NULL REFERENCES application(id),
    modele_id      BIGINT REFERENCES modele_fiabilite(id),
    source         VARCHAR(12) NOT NULL CHECK (source IN ('modele','heuristique')),
    score          NUMERIC(4,3) NOT NULL CHECK (score BETWEEN 0 AND 1),
    niveau         VARCHAR(8) NOT NULL CHECK (niveau IN ('faible','moyen','eleve')),
    variables      JSONB NOT NULL,
    explication    JSONB,
    etiquette      BOOLEAN,
    etiquette_le   TIMESTAMPTZ,
    cree_le        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((etape = 3 AND cible_type = 'resultat') OR (etape = 6 AND cible_type = 'solution'))
);
CREATE INDEX IF NOT EXISTS idx_eval_fiab_cible ON evaluation_fiabilite(cible_type, cible_id, cree_le DESC);
CREATE INDEX IF NOT EXISTS idx_eval_fiab_etiquetee ON evaluation_fiabilite(etape) WHERE etiquette IS NOT NULL;
"""


def upgrade() -> None:
    op.get_bind().connection.cursor().execute(SQL)


def downgrade() -> None:
    raise RuntimeError("Pas de retour arrière automatique.")
