"""Base déclarative. Les modèles décrivent des tables DÉJÀ créées par sql/schema_base_de_donnees.sql
(contraintes, déclencheurs et vues y sont définis) : on n'utilise pas create_all()."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Identity, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def pk() -> Mapped[int]:
    return mapped_column(BigInteger, Identity(always=True), primary_key=True)


def cree_le() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def horodatage(nullable: bool = True) -> Mapped[datetime | None]:
    return mapped_column(DateTime(timezone=True), nullable=nullable)
