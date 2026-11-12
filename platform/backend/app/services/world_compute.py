"""Computation of the world ledger up to a horizon, and the coverage it gives the balance.

The world model is computed, not kept up to date by itself: a computation writes the
ledger events from the start of history (``world_pilot.HISTORY``) to a chosen horizon.
Years with published figures are history; the years after them are a forecast that
extends the last historical year with a yearly growth rate.

The latest successful computation is the coverage of the layer: the material balance
can be reported only for periods inside ``[data_from, horizon]``. Without any
computation, coverage falls back to the span of the pilot events already in the ledger
(databases seeded before computations existed).
"""

import time
from collections import Counter
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import Source, WorldComputation, WorldEvent
from app.world_pilot import (
    HISTORY_FROM,
    HISTORY_TO,
    LEGACY_RUN_IDS,
    MAX_HORIZON,
    PARAMETERS,
    RUN_ID,
    SOURCE_ID,
    flows_by_year,
    generate_pilot_events,
    seed_pilot_world,
)

LOCK_KEY = 815_202_611  # pg advisory lock: one computation per database at a time
MAX_GROWTH_PCT = 50.0


class ComputeError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def _last_day(bound: datetime) -> str:
    """Exclusive upper bound (midnight) → inclusive calendar date."""
    return (bound - timedelta(days=1)).date().isoformat()


def coverage(db: Session) -> dict | None:
    """Dates the balance can be reported for in this layer, or None when nothing is computed."""
    latest = db.scalar(
        select(WorldComputation)
        .where(WorldComputation.status == "done")
        .order_by(WorldComputation.created_at.desc())
        .limit(1)
    )
    if latest is not None:
        return {
            "source": "computation",
            "computation_id": latest.id,
            "from": latest.data_from.date().isoformat(),
            "to": _last_day(latest.horizon),
            "history_to": _last_day(min(latest.history_to, latest.horizon)),
            "forecast": latest.horizon > latest.history_to,
            "computed_at": _iso(latest.created_at),
            "parameters": latest.parameters,
        }
    first, last = db.execute(
        select(func.min(WorldEvent.occurred_at), func.max(WorldEvent.occurred_at)).where(
            WorldEvent.run_id.in_((RUN_ID, *LEGACY_RUN_IDS))
        )
    ).one()
    if first is None:
        return None
    return {
        "source": "events",
        "computation_id": None,
        "from": first.date().isoformat(),
        "to": last.date().isoformat(),
        "history_to": last.date().isoformat(),
        "forecast": False,
        "computed_at": None,
        "parameters": {},
    }


def check_period(db: Session, start: datetime, end: datetime) -> None:
    """Refuse a balance period outside the computed coverage of the layer."""
    covered = coverage(db)
    if covered is None:
        return
    lo = datetime.fromisoformat(covered["from"]).replace(tzinfo=UTC)
    hi = datetime.fromisoformat(covered["to"]).replace(tzinfo=UTC) + timedelta(days=1)
    if start < lo or end > hi:
        raise ComputeError(
            422,
            f"Немає розрахунку на цей період: світ розраховано з {covered['from']} "
            f"по {covered['to']}. Розширте горизонт у розділі «Розрахунок».",
        )


def computable(db: Session) -> bool:
    return db.get(Source, SOURCE_ID) is not None


def history(db: Session, limit: int = 20) -> list[dict]:
    rows = db.scalars(
        select(WorldComputation).order_by(WorldComputation.created_at.desc()).limit(limit)
    )
    return [
        {
            "id": row.id,
            "status": row.status,
            "from": row.data_from.date().isoformat(),
            "to": _last_day(row.horizon),
            "history_to": _last_day(min(row.history_to, row.horizon)),
            "parameters": row.parameters,
            "summary": row.summary,
            "note": row.note,
            "duration_ms": row.duration_ms,
            "created_at": _iso(row.created_at),
        }
        for row in rows
    ]


def overview(db: Session) -> dict:
    covered = coverage(db)
    growth = float((covered or {}).get("parameters", {}).get("growth_pct", 0.0))
    horizon = (
        datetime.fromisoformat(covered["to"]).replace(tzinfo=UTC) + timedelta(days=1)
        if covered
        else HISTORY_TO
    )
    return {
        "computable": computable(db),
        "coverage": covered,
        "limits": {
            "min_horizon": _last_day(HISTORY_FROM + timedelta(days=60)),
            "max_horizon": _last_day(MAX_HORIZON),
            "history_from": HISTORY_FROM.date().isoformat(),
            "history_to": _last_day(HISTORY_TO),
            "max_growth_pct": MAX_GROWTH_PCT,
        },
        "flows": flows_by_year(max(horizon, HISTORY_TO), growth),
        "computations": history(db),
    }


def compute(db: Session, horizon: date, growth_pct: float = 0.0, note: str = "") -> dict:
    """Recompute the pilot ledger from the start of history up to ``horizon`` (inclusive)."""
    if not computable(db):
        raise ComputeError(
            409,
            "У цьому шарі немає моделі світу для розрахунку: спочатку завантажте сутності й "
            "джерела (пілот Saudi Arabia → India є лише в DEV).",
        )
    bound = datetime(horizon.year, horizon.month, horizon.day, tzinfo=UTC) + timedelta(days=1)
    if bound < HISTORY_FROM + timedelta(days=61):
        raise ComputeError(422, f"Горизонт має бути не раніше {_last_day(HISTORY_FROM + timedelta(days=61))}")
    if bound > MAX_HORIZON:
        raise ComputeError(422, f"Горизонт не може бути пізніше {_last_day(MAX_HORIZON)}")
    if not -MAX_GROWTH_PCT <= growth_pct <= MAX_GROWTH_PCT:
        raise ComputeError(422, f"Зміна потоку має бути в межах ±{MAX_GROWTH_PCT:g}% на рік")
    if not db.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": LOCK_KEY}).scalar():
        raise ComputeError(409, "Розрахунок у цьому шарі вже виконується")

    started = time.perf_counter()
    seed_pilot_world(db)
    count = generate_pilot_events(db, force=True, until=bound, growth_pct=growth_pct)
    provenance = Counter(
        dict(
            db.execute(
                select(WorldEvent.provenance, func.count())
                .where(WorldEvent.run_id == RUN_ID)
                .group_by(WorldEvent.provenance)
            ).all()
        )
    )
    cargoes = db.scalar(
        select(func.count())
        .select_from(WorldEvent)
        .where(WorldEvent.run_id == RUN_ID, WorldEvent.event_type_id == "type:transform")
    )
    duration = round((time.perf_counter() - started) * 1000)
    parameters = {
        "horizon": horizon.isoformat(),
        "growth_pct": growth_pct,
        "cargo_bbl": PARAMETERS["cargo_bbl"],
        "method": "Останній історичний рік, змінений на growth_pct щороку",
    }
    record = WorldComputation(
        run_id=RUN_ID,
        status="done",
        data_from=HISTORY_FROM,
        history_to=HISTORY_TO,
        horizon=bound,
        parameters=parameters,
        summary={
            "events": count,
            "cargoes": cargoes,
            "provenance": dict(provenance),
            "flows": flows_by_year(bound, growth_pct),
        },
        note=note.strip(),
        duration_ms=duration,
        # Wall clock, not now(): several computations may share one transaction.
        created_at=datetime.now(UTC),
    )
    db.add(record)
    db.commit()
    return {"id": record.id, "duration_ms": duration, "events": count, "cargoes": cargoes, **overview(db)}
