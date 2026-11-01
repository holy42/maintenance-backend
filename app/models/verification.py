from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, cree_le, pk


class Critere(Base):
    __tablename__ = "critere"
    id: Mapped[int] = pk()
    application_id: Mapped[int | None] = mapped_column(ForeignKey("application.id", ondelete="CASCADE"))
    createur_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    nom: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(Text)
    formulation_structuree: Mapped[dict | None] = mapped_column(JSONB)
    origine: Mapped[str] = mapped_column(String(20))
    categorie: Mapped[str] = mapped_column(String(30))
    automatisabilite: Mapped[str] = mapped_column(String(20), server_default="a_determiner", default="a_determiner")
    mode_verification: Mapped[str | None] = mapped_column(String(30))
    statut: Mapped[str] = mapped_column(String(20), server_default="brouillon", default="brouillon")
    valide_par: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    cree_le: Mapped[datetime] = cree_le()


class Verification(Base):
    __tablename__ = "verification"
    id: Mapped[int] = pk()
    application_id: Mapped[int] = mapped_column(ForeignKey("application.id"))
    depot_id: Mapped[int | None] = mapped_column(ForeignKey("depot_git.id"))
    branche: Mapped[str] = mapped_column(String(100), server_default="develop", default="develop")
    commit_analyse: Mapped[str | None] = mapped_column(String(64))
    perimetre: Mapped[str | None] = mapped_column(Text)
    declenchee_par: Mapped[int] = mapped_column(ForeignKey("utilisateur.id"))
    type: Mapped[str] = mapped_column(String(20), server_default="a_la_demande", default="a_la_demande")
    statut: Mapped[str] = mapped_column(String(20), server_default="en_attente", default="en_attente")
    motif_echec: Mapped[str | None] = mapped_column(Text)
    avec_interpretation_ia: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), default=True)
    resultat_global: Mapped[str | None] = mapped_column(String(30))
    debut_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    fin_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resultats: Mapped[list["ResultatAnalyse"]] = relationship(back_populates="verification")


class VerificationCritere(Base):
    __tablename__ = "verification_critere"
    verification_id: Mapped[int] = mapped_column(ForeignKey("verification.id", ondelete="CASCADE"), primary_key=True)
    critere_id: Mapped[int] = mapped_column(ForeignKey("critere.id"), primary_key=True)


class ResultatAnalyse(Base):
    __tablename__ = "resultat_analyse"
    id: Mapped[int] = pk()
    verification_id: Mapped[int] = mapped_column(ForeignKey("verification.id", ondelete="CASCADE"))
    critere_id: Mapped[int | None] = mapped_column(ForeignKey("critere.id"))
    source: Mapped[str] = mapped_column(String(10))
    outil: Mapped[str | None] = mapped_column(String(80))
    categorie: Mapped[str] = mapped_column(String(30))
    gravite: Mapped[str | None] = mapped_column(String(10))
    fichier: Mapped[str | None] = mapped_column(String(500))
    ligne_debut: Mapped[int | None] = mapped_column(Integer)
    ligne_fin: Mapped[int | None] = mapped_column(Integer)
    fonction: Mapped[str | None] = mapped_column(String(200))
    extrait_code: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    elements_preuve: Mapped[str | None] = mapped_column(Text)
    donnees_brutes: Mapped[dict | None] = mapped_column(JSONB)
    statut_validation: Mapped[str] = mapped_column(String(20), server_default="non_valide", default="non_valide")
    decide_par: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    motif_decision: Mapped[str | None] = mapped_column(Text)
    decide_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cree_le: Mapped[datetime] = cree_le()
    verification: Mapped["Verification"] = relationship(back_populates="resultats")
