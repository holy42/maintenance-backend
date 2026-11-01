from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, cree_le, pk


class ModeleFiabiliteVersion(Base):
    """Une version entraînée du modèle de fiabilité pour une étape (3 ou 6). Inactive tant qu'un administrateur ne l'active pas."""
    __tablename__ = "modele_fiabilite"
    id: Mapped[int] = pk()
    etape: Mapped[int] = mapped_column(SmallInteger)
    version: Mapped[int] = mapped_column(Integer)
    algorithme: Mapped[str] = mapped_column(String(20))
    nb_exemples: Mapped[int | None] = mapped_column(Integer)
    metriques: Mapped[dict | None] = mapped_column(JSONB)
    parametres: Mapped[dict] = mapped_column(JSONB)
    actif: Mapped[bool] = mapped_column(Boolean, server_default="false", default=False)
    entraine_par: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("utilisateur.id"))
    entraine_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvaluationFiabilite(Base):
    """Score de fiabilité d'un résultat d'analyse (étape 3) ou d'une solution de Gemini (étape 6), avec la vérité terrain
    quand elle est connue (`etiquette`)."""
    __tablename__ = "evaluation_fiabilite"
    id: Mapped[int] = pk()
    etape: Mapped[int] = mapped_column(SmallInteger)
    cible_type: Mapped[str] = mapped_column(String(15))
    cible_id: Mapped[int] = mapped_column(BigInteger)
    application_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("application.id"))
    modele_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("modele_fiabilite.id"))
    source: Mapped[str] = mapped_column(String(12))
    score: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    niveau: Mapped[str] = mapped_column(String(8))
    variables: Mapped[dict] = mapped_column(JSONB)
    explication: Mapped[list | None] = mapped_column(JSONB)
    etiquette: Mapped[bool | None] = mapped_column(Boolean)
    etiquette_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cree_le: Mapped[datetime] = cree_le()
