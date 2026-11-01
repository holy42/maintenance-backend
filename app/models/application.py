from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, cree_le, pk


class Application(Base):
    __tablename__ = "application"
    id: Mapped[int] = pk()
    equipe_id: Mapped[int] = mapped_column(ForeignKey("equipe.id"))
    nom: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    statut: Mapped[str] = mapped_column(String(20), server_default="active", default="active")
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    cree_le: Mapped[datetime] = cree_le()
    __table_args__ = (UniqueConstraint("equipe_id", "nom"),)


class Technologie(Base):
    __tablename__ = "technologie"
    id: Mapped[int] = pk()
    nom: Mapped[str] = mapped_column(String(80))
    framework: Mapped[str | None] = mapped_column(String(80))


class ApplicationTechnologie(Base):
    __tablename__ = "application_technologie"
    application_id: Mapped[int] = mapped_column(ForeignKey("application.id", ondelete="CASCADE"), primary_key=True)
    technologie_id: Mapped[int] = mapped_column(ForeignKey("technologie.id"), primary_key=True)


class DepotGit(Base):
    __tablename__ = "depot_git"
    id: Mapped[int] = pk()
    application_id: Mapped[int] = mapped_column(ForeignKey("application.id", ondelete="CASCADE"), unique=True)
    url: Mapped[str] = mapped_column(String(500))
    branche_defaut: Mapped[str] = mapped_column(String(100), server_default="develop", default="develop")
    jeton_acces_chiffre: Mapped[str | None] = mapped_column(Text)
    derniere_synchro_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
