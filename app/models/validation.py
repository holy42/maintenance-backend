from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, cree_le, pk


class TestCorrection(Base):
    """Un seul test par problème, avec sa description."""
    __tablename__ = "test_correction"
    __test__ = False  # évite la collecte par pytest
    id: Mapped[int] = pk()
    application_id: Mapped[int] = mapped_column(ForeignKey("application.id"))
    probleme_id: Mapped[int] = mapped_column(ForeignKey("probleme.id", ondelete="CASCADE"), unique=True)
    description: Mapped[str] = mapped_column(Text)
    origine: Mapped[str] = mapped_column(String(15), server_default="utilisateur", default="utilisateur")
    redige_par: Mapped[int] = mapped_column(ForeignKey("utilisateur.id"))
    cree_le: Mapped[datetime] = cree_le()
    modifie_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SessionTest(Base):
    """Un passage de test (numéroté). Le testeur est toujours enregistré."""
    __tablename__ = "session_test"
    id: Mapped[int] = pk()
    application_id: Mapped[int] = mapped_column(ForeignKey("application.id"))
    test_id: Mapped[int] = mapped_column(ForeignKey("test_correction.id"))
    numero: Mapped[int] = mapped_column(Integer)
    decision_id: Mapped[int | None] = mapped_column(ForeignKey("decision_correction.id"))
    demande_par: Mapped[int] = mapped_column(ForeignKey("utilisateur.id"))
    testeur_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    branche_testee: Mapped[str] = mapped_column(String(100), server_default="develop", default="develop")
    commit_teste: Mapped[str | None] = mapped_column(String(64))
    environnement: Mapped[str | None] = mapped_column(String(100))
    statut: Mapped[str] = mapped_column(String(15), server_default="a_tester", default="a_tester")
    commentaire: Mapped[str | None] = mapped_column(Text)
    preuve: Mapped[str | None] = mapped_column(Text)
    demande_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    pris_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decide_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResultatCritereAcceptation(Base):
    __tablename__ = "resultat_critere_acceptation"
    session_id: Mapped[int] = mapped_column(ForeignKey("session_test.id", ondelete="CASCADE"), primary_key=True)
    critere_acceptation_id: Mapped[int] = mapped_column(ForeignKey("critere_acceptation.id"), primary_key=True)
    satisfait: Mapped[bool] = mapped_column(Boolean)
    commentaire: Mapped[str | None] = mapped_column(Text)
