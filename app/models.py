import uuid

from sqlalchemy import Column, Float, ForeignKey, String
from sqlalchemy.orm import relationship

from .database import Base


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class UserModel(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_new_id)
    phone = Column(String, unique=True, nullable=False)
    role = Column(String, nullable=False)  # "agriculteur" | "agent_cooperative"
    token = Column(String, nullable=True)
    name = Column(String, nullable=True)

    fields = relationship("FieldModel", back_populates="owner", cascade="all, delete-orphan")


class FieldModel(Base):
    __tablename__ = "fields"

    id = Column(String, primary_key=True, default=_new_id)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    crop = Column(String, nullable=False)  # "mais" | "tomate" | "coton"
    size_hectares = Column(Float, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    planting_date = Column(String, nullable=False)

    owner = relationship("UserModel", back_populates="fields")
