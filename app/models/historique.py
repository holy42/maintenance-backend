from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, cree_le, pk


class EvenementHistorique(Base):
    """Journal de toutes les activités (ajout seul : protégé par un déclencheur SQL)."""
    __tablename__ = "evenement_historique"
    id: Mapped[int] = pk()
    application_id: Mapped[int | None] = mapped_column(ForeignKey("application.id"))
    type_element: Mapped[str] = mapped_column(String(30))
    element_id: Mapped[int] = mapped_column()
    auteur_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    action: Mapped[str] = mapped_column(String(50))
    ancienne_valeur: Mapped[dict | None] = mapped_column(JSONB)
    nouvelle_valeur: Mapped[dict | None] = mapped_column(JSONB)
    commentaire: Mapped[str | None] = mapped_column(Text)
    cree_le: Mapped[datetime] = cree_le()


class HistoriqueStatut(Base):
    __tablename__ = "historique_statut"
    id: Mapped[int] = pk()
    application_id: Mapped[int] = mapped_column(ForeignKey("application.id"))
    type_element: Mapped[str] = mapped_column(String(20))
    element_id: Mapped[int] = mapped_column()
    ancien_statut: Mapped[str | None] = mapped_column(String(20))
    nouveau_statut: Mapped[str] = mapped_column(String(20))
    auteur_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    motif: Mapped[str | None] = mapped_column(Text)
    cree_le: Mapped[datetime] = cree_le()


class Rapport(Base):
    __tablename__ = "rapport"
    id: Mapped[int] = pk()
    application_id: Mapped[int | None] = mapped_column(ForeignKey("application.id"))
    equipe_id: Mapped[int | None] = mapped_column(ForeignKey("equipe.id"))
    type: Mapped[str] = mapped_column(String(40))
    parametres: Mapped[dict | None] = mapped_column(JSONB)
    contenu: Mapped[dict] = mapped_column(JSONB)
    genere_par: Mapped[int] = mapped_column(ForeignKey("utilisateur.id"))
    genere_le: Mapped[datetime] = cree_le()
