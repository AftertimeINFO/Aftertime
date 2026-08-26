import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def new_id() -> str:
    return str(uuid.uuid4())


class SyncStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class Entity(Base):
    __tablename__ = "entities"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(50), index=True)
    level: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(240), index=True)
    symbol: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    jurisdiction: Mapped[str | None] = mapped_column(String(50))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Relation(Base):
    __tablename__ = "relations"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=new_id)
    subject_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"))
    predicate: Mapped[str] = mapped_column(String(80))
    object_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"))
    coefficient: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(80))
    confidence: Mapped[float] = mapped_column(Float, default=1)
    source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id"))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("ix_relations_subject_predicate", "subject_id", "predicate"),
        Index("ix_relations_object", "object_id"),
    )


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(240))
    url: Mapped[str] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(String(120))
    adapter: Mapped[str] = mapped_column(String(80))
    enabled: Mapped[bool] = mapped_column(default=True)
    configuration: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Observation(Base):
    __tablename__ = "observations"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=new_id)
    subject_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"))
    property: Mapped[str] = mapped_column(String(120), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(80))
    actuality: Mapped[str] = mapped_column(String(30))
    epistemic_status: Mapped[str] = mapped_column(String(30))
    valid_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    recorded_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    uncertainty_low: Mapped[float | None] = mapped_column(Float)
    uncertainty_high: Mapped[float | None] = mapped_column(Float)
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)


class ProcessModel(Base):
    __tablename__ = "process_models"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(240))
    version: Mapped[str] = mapped_column(String(60))
    owner_entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id"))
    duration_hours: Mapped[float] = mapped_column(Float)
    yield_factor: Mapped[float] = mapped_column(Float)
    specification: Mapped[dict] = mapped_column(JSONB)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))


class Route(Base):
    __tablename__ = "routes"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    origin_id: Mapped[str] = mapped_column(ForeignKey("entities.id"))
    destination_id: Mapped[str] = mapped_column(ForeignKey("entities.id"))
    mode: Mapped[str] = mapped_column(String(40))
    distance_km: Mapped[float] = mapped_column(Float)
    capacity_per_day: Mapped[float] = mapped_column(Float)
    duration_hours: Mapped[float] = mapped_column(Float)
    availability: Mapped[float] = mapped_column(Float)
    loss_factor: Mapped[float] = mapped_column(Float)
    recovery_hours: Mapped[float] = mapped_column(Float)


class Scenario(Base):
    __tablename__ = "scenarios"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    probability: Mapped[float] = mapped_column(Float)
    assumptions: Mapped[dict] = mapped_column(JSONB)
    model_version: Mapped[str] = mapped_column(String(60))


class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=new_id)
    scenario_id: Mapped[str | None] = mapped_column(ForeignKey("scenarios.id"))
    model_version: Mapped[str] = mapped_column(String(60))
    request: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SyncJob(Base):
    __tablename__ = "sync_jobs"
    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    status: Mapped[SyncStatus] = mapped_column(Enum(SyncStatus), default=SyncStatus.queued)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    records_seen: Mapped[int] = mapped_column(default=0)
    records_written: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
