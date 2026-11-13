"""Tables of the ODbL grid layer (schema ``odbl``).

Rows here are derived from OpenStreetMap and therefore carry ODbL. Nothing in the core
schema copies them; scenarios and runs refer to assets by id only.
"""

from datetime import date, datetime

from sqlalchemy import (
    DDL,
    BigInteger,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import UserDefinedType

from app.db import Base
from app.grid import ODBL_SCHEMA


class RawGeometry(UserDefinedType):
    """PostGIS geometry handled in SQL (WKB/WKT); no GeoJSON conversion in the ORM."""

    cache_ok = True

    def __init__(self, srid: int = 4326):
        self.srid = srid

    def get_col_spec(self, **kw) -> str:
        return f"geometry(Geometry, {self.srid})"


SCHEMA = {"schema": ODBL_SCHEMA}

# Every create_all (bootstrap of a new layer, tests, early migrations) needs the schema first.
event.listen(Base.metadata, "before_create", DDL(f"CREATE SCHEMA IF NOT EXISTS {ODBL_SCHEMA}"))


class GridImportBatch(Base):
    __tablename__ = "grid_import_batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region: Mapped[str] = mapped_column(String(40), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checksum: Mapped[str | None] = mapped_column(String(80))
    licence: Mapped[str] = mapped_column(String(40), default="ODbL-1.0")
    attribution: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="running")
    counts: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = SCHEMA


class GridAsset(Base):
    """One OSM power object: line, cable, substation, plant, generator or converter."""

    __tablename__ = "grid_assets"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    osm_type: Mapped[str] = mapped_column(String(1))
    osm_id: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    subkind: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="active")
    name: Mapped[str | None] = mapped_column(Text)
    name_en: Mapped[str | None] = mapped_column(Text)
    operator: Mapped[str | None] = mapped_column(Text)
    ref: Mapped[str | None] = mapped_column(Text)
    voltages_kv: Mapped[list[float]] = mapped_column(ARRAY(Float), default=list)
    max_voltage_kv: Mapped[float | None] = mapped_column(Float, index=True)
    frequency_hz: Mapped[float | None] = mapped_column(Float)
    circuits: Mapped[int | None] = mapped_column(Integer)
    cables: Mapped[int | None] = mapped_column(Integer)
    capacity_mw: Mapped[float | None] = mapped_column(Float)
    capacity_source: Mapped[str | None] = mapped_column(String(40))
    fuel: Mapped[str | None] = mapped_column(String(20))
    start_date: Mapped[str | None] = mapped_column(String(40))
    country: Mapped[str | None] = mapped_column(String(8), index=True)
    length_km: Mapped[float | None] = mapped_column(Float)
    tags: Mapped[dict] = mapped_column(JSONB, default=dict)
    quality: Mapped[list] = mapped_column(JSONB, default=list)
    geom = mapped_column(RawGeometry(4326))
    geom_3857 = mapped_column(
        RawGeometry(3857), Computed("ST_Transform(geom, 3857)", persisted=True)
    )
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey(f"{ODBL_SCHEMA}.grid_import_batches.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (
        UniqueConstraint("osm_type", "osm_id", name="uq_grid_assets_osm"),
        Index("ix_grid_assets_geom", "geom", postgresql_using="gist"),
        Index("ix_grid_assets_geom_3857", "geom_3857", postgresql_using="gist"),
        Index("ix_grid_assets_kind_voltage", "kind", "max_voltage_kv"),
        SCHEMA,
    )


class GridOverride(Base):
    """Dated, sourced correction of an asset: status, capacity, control, repair."""

    __tablename__ = "grid_overrides"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey(f"{ODBL_SCHEMA}.grid_assets.id", ondelete="CASCADE"), index=True
    )
    field: Mapped[str] = mapped_column(String(40))
    value: Mapped[dict] = mapped_column(JSONB)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = SCHEMA


class GridControlArea(Base):
    """Territory outside the control of the system operator from a date (e.g. occupation).

    A snapshot records which areas each bus lies in; while an area is in force during a run
    its buses, plants and loads leave the national system and the country's demand is
    spread over the territory still controlled.
    """

    __tablename__ = "grid_control_areas"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    country: Mapped[str] = mapped_column(String(8))
    controlled_by: Mapped[str] = mapped_column(String(16))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    geom = mapped_column(RawGeometry(4326))
    source_url: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (Index("ix_grid_control_areas_geom", "geom", postgresql_using="gist"), SCHEMA)


class GridSnapshot(Base):
    """Bus-branch network built from the assets as they stood on ``as_of``."""

    __tablename__ = "grid_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)
    countries: Mapped[list[str]] = mapped_column(ARRAY(String(8)))
    min_voltage_kv: Mapped[float] = mapped_column(Float, default=110)
    status: Mapped[str] = mapped_column(String(20), default="building")
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    fingerprint: Mapped[str] = mapped_column(String(80), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = SCHEMA


class GridBus(Base):
    __tablename__ = "grid_buses"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey(f"{ODBL_SCHEMA}.grid_snapshots.id", ondelete="CASCADE"), index=True
    )
    asset_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    voltage_kv: Mapped[float] = mapped_column(Float)
    country: Mapped[str | None] = mapped_column(String(8))
    synthetic: Mapped[bool] = mapped_column(default=False)
    # substation | plant | junction | end: what the bus stands for in the network.
    role: Mapped[str] = mapped_column(String(20), default="substation")
    lon: Mapped[float] = mapped_column(Float)
    lat: Mapped[float] = mapped_column(Float)
    # Control areas (of any date) the bus lies in; a run decides by date which are in force.
    areas: Mapped[list[int] | None] = mapped_column(ARRAY(Integer))
    __table_args__ = SCHEMA


class GridBranch(Base):
    __tablename__ = "grid_branches"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey(f"{ODBL_SCHEMA}.grid_snapshots.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(20))
    asset_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    # Every OSM way of the branch (a line between two substations is usually many ways).
    asset_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger), default=list)
    from_bus: Mapped[int] = mapped_column(BigInteger)
    to_bus: Mapped[int] = mapped_column(BigInteger)
    voltage_kv: Mapped[float] = mapped_column(Float)
    circuits: Mapped[int] = mapped_column(Integer, default=1)
    length_km: Mapped[float] = mapped_column(Float, default=0)
    x_pu: Mapped[float] = mapped_column(Float)
    s_nom_mva: Mapped[float] = mapped_column(Float)
    estimated: Mapped[list] = mapped_column(JSONB, default=list)
    __table_args__ = SCHEMA


class GridGenerator(Base):
    __tablename__ = "grid_generators"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey(f"{ODBL_SCHEMA}.grid_snapshots.id", ondelete="CASCADE"), index=True
    )
    bus_id: Mapped[int] = mapped_column(BigInteger)
    asset_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    fuel: Mapped[str | None] = mapped_column(String(20))
    p_max_mw: Mapped[float] = mapped_column(Float)
    availability: Mapped[float] = mapped_column(Float, default=1.0)
    estimated: Mapped[list] = mapped_column(JSONB, default=list)
    __table_args__ = SCHEMA


class GridLoad(Base):
    __tablename__ = "grid_loads"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey(f"{ODBL_SCHEMA}.grid_snapshots.id", ondelete="CASCADE"), index=True
    )
    bus_id: Mapped[int] = mapped_column(BigInteger)
    country: Mapped[str | None] = mapped_column(String(8))
    share: Mapped[float] = mapped_column(Float)
    population: Mapped[float | None] = mapped_column(Float)
    geom = mapped_column(RawGeometry(4326))
    __table_args__ = SCHEMA


class GridScenario(Base):
    """A historical replay or a what-if: timed events against real assets."""

    __tablename__ = "grid_scenarios"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(20))
    description: Mapped[str] = mapped_column(Text, default="")
    countries: Mapped[list[str]] = mapped_column(ARRAY(String(8)))
    as_of: Mapped[date] = mapped_column(Date)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    events: Mapped[list] = mapped_column(JSONB, default=list)
    uncertainty: Mapped[dict] = mapped_column(JSONB, default=dict)
    expected: Mapped[dict] = mapped_column(JSONB, default=dict)
    sources: Mapped[list] = mapped_column(JSONB, default=list)
    author: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = SCHEMA


class GridRun(Base):
    __tablename__ = "grid_runs"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(
        ForeignKey(f"{ODBL_SCHEMA}.grid_scenarios.id", ondelete="CASCADE"), index=True
    )
    snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey(f"{ODBL_SCHEMA}.grid_snapshots.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(20), default="single")
    members: Mapped[int] = mapped_column(Integer, default=1)
    seed: Mapped[int] = mapped_column(Integer, default=42)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0)
    summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = SCHEMA


class GridRunFrame(Base):
    """State of the network after one step: metrics plus compact branch and bus states."""

    __tablename__ = "grid_run_frames"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey(f"{ODBL_SCHEMA}.grid_runs.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    state: Mapped[dict] = mapped_column(JSONB, default=dict)
    events: Mapped[list] = mapped_column(JSONB, default=list)
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_grid_run_frames_sequence"),
        SCHEMA,
    )
