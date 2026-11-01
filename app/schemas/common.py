from pydantic import BaseModel, ConfigDict


class Sortie(BaseModel):
    """Base des schémas de sortie (lecture depuis les objets SQLAlchemy)."""
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    message: str
