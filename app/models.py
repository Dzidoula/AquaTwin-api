import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String
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

    # Soil state carried across daily engine calls — main.m originally keeps
    # this in memory across an infinite real-time loop; we persist it per
    # field instead so each call can pick up where the last one left off.
    engine_psi_state = Column(JSON, nullable=True)
    engine_theta_infiltre = Column(Float, nullable=False, default=0.0)
    engine_last_julian_day = Column(Integer, nullable=True)

    owner = relationship("UserModel", back_populates="fields")
    jobs = relationship("RecommendationJobModel", back_populates="field", cascade="all, delete-orphan")


class RecommendationJobModel(Base):
    __tablename__ = "recommendation_jobs"

    id = Column(String, primary_key=True, default=_new_id)
    field_id = Column(String, ForeignKey("fields.id"), nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending|running|done|failed
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime, nullable=True)
    result = Column(JSON, nullable=True)
    error = Column(String, nullable=True)

    field = relationship("FieldModel", back_populates="jobs")
