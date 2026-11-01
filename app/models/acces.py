from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, cree_le, pk


class Utilisateur(Base):
    __tablename__ = "utilisateur"
    id: Mapped[int] = pk()
    identifiant: Mapped[str] = mapped_column(String(100), unique=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    mot_de_passe_hash: Mapped[str] = mapped_column(String(255))
    est_admin: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), default=False)
    actif: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), default=True)
    cree_le: Mapped[datetime] = cree_le()


class ReinitialisationMotDePasse(Base):
    __tablename__ = "reinitialisation_mot_de_passe"
    id: Mapped[int] = pk()
    utilisateur_id: Mapped[int] = mapped_column(ForeignKey("utilisateur.id", ondelete="CASCADE"))
    jeton_hash: Mapped[str] = mapped_column(String(255), unique=True)
    expire_le: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    utilise_le: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cree_le: Mapped[datetime] = cree_le()


class Equipe(Base):
    __tablename__ = "equipe"
    id: Mapped[int] = pk()
    nom: Mapped[str] = mapped_column(String(150), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    cree_le: Mapped[datetime] = cree_le()


class Permission(Base):
    __tablename__ = "permission"
    id: Mapped[int] = pk()
    code: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str | None] = mapped_column(Text)


class Role(Base):
    __tablename__ = "role"
    id: Mapped[int] = pk()
    nom: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str | None] = mapped_column(Text)


class RolePermission(Base):
    __tablename__ = "role_permission"
    role_id: Mapped[int] = mapped_column(ForeignKey("role.id", ondelete="CASCADE"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permission.id", ondelete="CASCADE"), primary_key=True)


class MembreEquipe(Base):
    __tablename__ = "membre_equipe"
    equipe_id: Mapped[int] = mapped_column(ForeignKey("equipe.id", ondelete="CASCADE"), primary_key=True)
    utilisateur_id: Mapped[int] = mapped_column(ForeignKey("utilisateur.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("role.id"))
    attribue_par: Mapped[int | None] = mapped_column(ForeignKey("utilisateur.id"))
    attribue_le: Mapped[datetime] = cree_le()
