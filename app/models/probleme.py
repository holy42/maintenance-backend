from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Computed, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, cree_le, pk


class Probleme(Base):
    __tablename__ = "probleme"
    id: Mapped[int] = pk()
    code: Mapped[str] = mapped_column(String(20), Computed("'PB-' || id::text", persisted=True), unique=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("application.id"))
    resultat_id: Mapped[int | None] = mapped_column(ForeignKey("resultat_analyse.id"))
    verification_id: Mapped[int | None] = mapped_column(ForeignKey("verification.id"))
    critere_id: Mapped[int | None] = mapped_column(ForeignKey("critere.id"))
    source: Mapped[str] = mapped_column(String(10))
    titre: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    comportement_attendu: Mapped[str | None] = mapped_column(Text)
    comportement_observe: Mapped[str | None] = mapped_column(Text)
    categorie: Mapped[str] = mapped_column(String(30))
    gravite: Mapped[str | None] = mapped_column(String(10))
    priorite: Mapped[str | None] = mapped_column(String(10))
    statut: Mapped[str] = mapped_column(String(20), server_default="nouveau", default="nouveau")
    fichier: Mapped[str | None] = mapped_column(String(500))
    ligne_debut: Mapped[int | None] = mapped_column(Integer)
    ligne_fin: Mapped[int | None] = mapped_column(Integer)
    fonction: Mapped[str | None] = mapped_column(String(200))
    extrait_code: Mapped[str | None] = mapped_column(Text)
    niveau_confiance: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    cree_par: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    echeance: Mapped[date | None] = mapped_column(Date)
    cree_le: Mapped[datetime] = cree_le()
    modifie_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    diagnostics: Mapped[list["Diagnostic"]] = relationship(order_by="Diagnostic.cree_le.desc()")


class Diagnostic(Base):
    __tablename__ = "diagnostic"
    id: Mapped[int] = pk()
    probleme_id: Mapped[int] = mapped_column(ForeignKey("probleme.id", ondelete="CASCADE"))
    explication: Mapped[str] = mapped_column(Text)
    causes_probables: Mapped[list | None] = mapped_column(JSONB)
    niveau_confiance: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    incertitudes: Mapped[str | None] = mapped_column(Text)
    verifications_recommandees: Mapped[list | None] = mapped_column(JSONB)
    branche_analysee: Mapped[str | None] = mapped_column(String(100))
    commit_reference: Mapped[str | None] = mapped_column(String(64))
    modele_ia: Mapped[str | None] = mapped_column(String(80))
    version_prompt: Mapped[str | None] = mapped_column(String(40))
    cree_le: Mapped[datetime] = cree_le()
    solutions: Mapped[list["Solution"]] = relationship(order_by="Solution.id")


class Solution(Base):
    __tablename__ = "solution"
    id: Mapped[int] = pk()
    diagnostic_id: Mapped[int] = mapped_column(ForeignKey("diagnostic.id", ondelete="CASCADE"))
    description: Mapped[str] = mapped_column(Text)
    extrait_code: Mapped[str | None] = mapped_column(Text)
    format_code: Mapped[str | None] = mapped_column(String(20), server_default="extrait")
    risques: Mapped[str | None] = mapped_column(Text)
    tests_suggeres: Mapped[str | None] = mapped_column(Text)
    commit_reference: Mapped[str | None] = mapped_column(String(64))
    cree_le: Mapped[datetime] = cree_le()


class RetourSolution(Base):
    __tablename__ = "retour_solution"
    id: Mapped[int] = pk()
    solution_id: Mapped[int] = mapped_column(ForeignKey("solution.id", ondelete="CASCADE"))
    utilisateur_id: Mapped[int] = mapped_column(ForeignKey("utilisateur.id"))
    utilite_percue: Mapped[str] = mapped_column(String(20))
    commentaire: Mapped[str | None] = mapped_column(Text)
    commit_associe: Mapped[str | None] = mapped_column(String(64))
    cree_le: Mapped[datetime] = cree_le()


class DecisionCorrection(Base):
    __tablename__ = "decision_correction"
    id: Mapped[int] = pk()
    probleme_id: Mapped[int] = mapped_column(ForeignKey("probleme.id", ondelete="CASCADE"))
    developpeur_id: Mapped[int] = mapped_column(ForeignKey("utilisateur.id"))
    type_decision: Mapped[str] = mapped_column(String(20))
    description_alternative: Mapped[str | None] = mapped_column(Text)
    extrait_code_alternatif: Mapped[str | None] = mapped_column(Text)
    justification: Mapped[str | None] = mapped_column(Text)
    motif_non_utilisation: Mapped[str | None] = mapped_column(String(20))
    commit_associe: Mapped[str | None] = mapped_column(String(64))
    pull_request: Mapped[str | None] = mapped_column(String(255))
    cree_le: Mapped[datetime] = cree_le()


class DecisionSolution(Base):
    __tablename__ = "decision_solution"
    decision_id: Mapped[int] = mapped_column(ForeignKey("decision_correction.id", ondelete="CASCADE"), primary_key=True)
    solution_id: Mapped[int] = mapped_column(ForeignKey("solution.id"), primary_key=True)
