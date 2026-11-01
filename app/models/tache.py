from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, cree_le, pk


class Tache(Base):
    __tablename__ = "tache"
    id: Mapped[int] = pk()
    probleme_id: Mapped[int] = mapped_column(ForeignKey("probleme.id"))
    application_id: Mapped[int] = mapped_column(ForeignKey("application.id"))
    titre: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    origine: Mapped[str] = mapped_column(String(15), server_default="utilisateur", default="utilisateur")
    duree_estimee_h: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    statut: Mapped[str] = mapped_column(String(20), server_default="a_faire", default="a_faire")
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    cree_par: Mapped[int] = mapped_column(ForeignKey("utilisateur.id"))
    echeance: Mapped[date | None] = mapped_column(Date)
    cree_le: Mapped[datetime] = cree_le()
    debut_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fin_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sous_taches: Mapped[list["SousTache"]] = relationship(order_by="SousTache.ordre", cascade="all, delete-orphan")
    criteres_acceptation: Mapped[list["CritereAcceptation"]] = relationship(
        order_by="CritereAcceptation.ordre", cascade="all, delete-orphan"
    )


class SousTache(Base):
    __tablename__ = "sous_tache"
    id: Mapped[int] = pk()
    tache_id: Mapped[int] = mapped_column(ForeignKey("tache.id", ondelete="CASCADE"))
    titre: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    statut: Mapped[str] = mapped_column(String(20), server_default="a_faire", default="a_faire")
    ordre: Mapped[int] = mapped_column(Integer)
    origine: Mapped[str] = mapped_column(String(15))


class CritereAcceptation(Base):
    __tablename__ = "critere_acceptation"
    id: Mapped[int] = pk()
    tache_id: Mapped[int] = mapped_column(ForeignKey("tache.id", ondelete="CASCADE"))
    texte: Mapped[str] = mapped_column(Text)
    ordre: Mapped[int] = mapped_column(Integer)
    origine: Mapped[str] = mapped_column(String(15))


class TacheSolution(Base):
    __tablename__ = "tache_solution"
    tache_id: Mapped[int] = mapped_column(ForeignKey("tache.id", ondelete="CASCADE"), primary_key=True)
    solution_id: Mapped[int] = mapped_column(ForeignKey("solution.id"), primary_key=True)
    ajoute_par: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    ajoute_le: Mapped[datetime] = cree_le()
