from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import (
    Entity,
    Observation,
    Relation,
    Route,
    Scenario,
    SimulationRun,
    Source,
    SyncJob,
)
from app.schemas import AmmoniaSimulationRequest, SyncJobRequest
from app.services.simulation import simulate_ammonia

router = APIRouter(prefix="/api/v1")


@router.get("/world/summary")
def world_summary(db: Session = Depends(get_db)) -> dict:
    def count(model: type) -> int:
        return db.scalar(select(func.count()).select_from(model)) or 0

    latest = db.scalar(select(SimulationRun).order_by(SimulationRun.created_at.desc()).limit(1))
    return {
        "entities": count(Entity),
        "relations": count(Relation),
        "observations": count(Observation),
        "routes": count(Route),
        "sources": count(Source),
        "scenarios": count(Scenario),
        "latest_simulation": latest.result if latest else None,
        "generated_at": datetime.now(UTC).isoformat(),
    }


@router.get("/entities")
def list_entities(
    kind: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[dict]:
    query = select(Entity).order_by(Entity.level, Entity.name).limit(min(limit, 500))
    if kind:
        query = query.where(Entity.kind == kind)
    return [
        {
            "id": item.id,
            "kind": item.kind,
            "level": item.level,
            "name": item.name,
            "symbol": item.symbol,
            "description": item.description,
            "attributes": item.attributes,
        }
        for item in db.scalars(query)
    ]


@router.get("/scenarios")
def list_scenarios(db: Session = Depends(get_db)) -> list[dict]:
    return [
        {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "probability": item.probability,
            "assumptions": item.assumptions,
            "model_version": item.model_version,
        }
        for item in db.scalars(select(Scenario).order_by(Scenario.probability.desc()))
    ]


@router.post("/simulations/ammonia")
def run_ammonia(
    request: AmmoniaSimulationRequest,
    db: Session = Depends(get_db),
) -> dict:
    result = simulate_ammonia(request)
    if request.persist:
        db.add(
            SimulationRun(
                scenario_id=request.scenario_id,
                model_version=result["model_version"],
                request=request.model_dump(),
                result=result,
            )
        )
        db.commit()
    return result


@router.get("/sync/jobs")
def list_sync_jobs(db: Session = Depends(get_db)) -> list[dict]:
    jobs = db.scalars(select(SyncJob).order_by(SyncJob.requested_at.desc()).limit(100))
    return [
        {
            "id": job.id,
            "source_id": job.source_id,
            "status": job.status.value,
            "parameters": job.parameters,
            "records_seen": job.records_seen,
            "records_written": job.records_written,
            "error": job.error,
            "requested_at": job.requested_at,
            "finished_at": job.finished_at,
        }
        for job in jobs
    ]


@router.post("/sync/jobs", status_code=202)
def create_sync_job(request: SyncJobRequest, db: Session = Depends(get_db)) -> dict:
    if not db.get(Source, request.source_id):
        raise HTTPException(status_code=404, detail="Unknown source")
    job = SyncJob(source_id=request.source_id, parameters=request.parameters)
    db.add(job)
    db.commit()
    db.refresh(job)
    Redis.from_url(settings.redis_url, decode_responses=True).rpush("aftertime:sync", job.id)
    return {"id": job.id, "status": job.status.value}
