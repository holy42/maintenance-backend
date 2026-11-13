from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, cree_le, pk


class Note(Base):
    __tablename__ = "note"
    id: Mapped[int] = pk()
    application_id: Mapped[int] = mapped_column(ForeignKey("application.id"))
    probleme_id: Mapped[int | None] = mapped_column(ForeignKey("probleme.id", ondelete="CASCADE"))
    tache_id: Mapped[int | None] = mapped_column(ForeignKey("tache.id", ondelete="CASCADE"))
    auteur_id: Mapped[int] = mapped_column(ForeignKey("utilisateur.id"))
    type: Mapped[str] = mapped_column(String(25), server_default="note_interne", default="note_interne")
    contenu: Mapped[str] = mapped_column(Text)
    cree_le: Mapped[datetime] = cree_le()
    modifie_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supprime_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Salon(Base):
    __tablename__ = "salon"
    id: Mapped[int] = pk()
    application_id: Mapped[int] = mapped_column(ForeignKey("application.id"))
    type: Mapped[str] = mapped_column(String(10))
    probleme_id: Mapped[int | None] = mapped_column(ForeignKey("probleme.id", ondelete="CASCADE"), unique=True)
    titre: Mapped[str] = mapped_column(String(255))
    cree_par: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    archive: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), default=False)
    cree_le: Mapped[datetime] = cree_le()
    supprime_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supprime_par: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))


class MessageDiscussion(Base):
    __tablename__ = "message_discussion"
    id: Mapped[int] = pk()
    salon_id: Mapped[int] = mapped_column(ForeignKey("salon.id", ondelete="CASCADE"))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("message_discussion.id"))
    tache_id: Mapped[int | None] = mapped_column(ForeignKey("tache.id"))
    auteur_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    type: Mapped[str] = mapped_column(String(12), server_default="utilisateur", default="utilisateur")
    contenu: Mapped[str] = mapped_column(Text)
    cree_le: Mapped[datetime] = cree_le()
    modifie_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supprime_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SalonLecture(Base):
    __tablename__ = "salon_lecture"
    salon_id: Mapped[int] = mapped_column(ForeignKey("salon.id", ondelete="CASCADE"), primary_key=True)
    utilisateur_id: Mapped[int] = mapped_column(ForeignKey("utilisateur.id", ondelete="CASCADE"), primary_key=True)
    derniere_lecture_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class Mention(Base):
    __tablename__ = "mention"
    message_id: Mapped[int] = mapped_column(ForeignKey("message_discussion.id", ondelete="CASCADE"), primary_key=True)
    utilisateur_id: Mapped[int] = mapped_column(ForeignKey("utilisateur.id"), primary_key=True)


class ConversationIA(Base):
    __tablename__ = "conversation_ia"
    id: Mapped[int] = pk()
    probleme_id: Mapped[int] = mapped_column(ForeignKey("probleme.id", ondelete="CASCADE"), unique=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("application.id"))
    cree_par: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    cree_le: Mapped[datetime] = cree_le()


class MessageIA(Base):
    __tablename__ = "message_ia"
    id: Mapped[int] = pk()
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversation_ia.id", ondelete="CASCADE"))
    emetteur: Mapped[str] = mapped_column(String(12))
    auteur_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    contenu: Mapped[str] = mapped_column(Text)
    contexte_utilise: Mapped[dict | None] = mapped_column(JSONB)
    informations_manquantes: Mapped[str | None] = mapped_column(Text)
    niveau_confiance: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    solution_id: Mapped[int | None] = mapped_column(ForeignKey("solution.id"))
    tache_id: Mapped[int | None] = mapped_column(ForeignKey("tache.id"))
    sous_tache_id: Mapped[int | None] = mapped_column(ForeignKey("sous_tache.id"))
    modele_ia: Mapped[str | None] = mapped_column(String(80))
    version_prompt: Mapped[str | None] = mapped_column(String(40))
    cree_le: Mapped[datetime] = cree_le()


class Notification(Base):
    __tablename__ = "notification"
    id: Mapped[int] = pk()
    destinataire_id: Mapped[int] = mapped_column(ForeignKey("utilisateur.id", ondelete="CASCADE"))
    application_id: Mapped[int | None] = mapped_column(ForeignKey("application.id", ondelete="CASCADE"))
    type_evenement: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(String(500))
    type_element: Mapped[str | None] = mapped_column(String(30))
    element_id: Mapped[int | None] = mapped_column()
    declencheur_id: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    lu: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), default=False)
    lu_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cree_le: Mapped[datetime] = cree_le()


class PreferenceNotification(Base):
    __tablename__ = "preference_notification"
    utilisateur_id: Mapped[int] = mapped_column(ForeignKey("utilisateur.id", ondelete="CASCADE"), primary_key=True)
    type_evenement: Mapped[str] = mapped_column(String(40), primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), default=True)


class PreferenceCanalNotification(Base):
    __tablename__ = "preference_canal_notification"
    utilisateur_id: Mapped[int] = mapped_column(ForeignKey("utilisateur.id", ondelete="CASCADE"), primary_key=True)
    son_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), default=True)
    navigateur_actif: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), default=True)
