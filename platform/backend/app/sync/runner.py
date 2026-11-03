from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import Entity, Source, SyncJob, SyncStatus
from app.sync.adapters import ADAPTERS


def run_sync_job(db: Session, job: SyncJob) -> None:
    source = db.get(Source, job.source_id)
    if source is None:
        raise ValueError(f"Unknown source {job.source_id}")
    adapter_type = ADAPTERS.get(source.adapter)
    if adapter_type is None:
        raise ValueError(f"Source adapter {source.adapter!r} is not executable")

    job.status = SyncStatus.running
    job.started_at = datetime.now(UTC)
    db.commit()
    try:
        parameters = {**source.configuration, **job.parameters}
        records = adapter_type().fetch(parameters)
        job.records_seen = len(records)
        written = 0
        for record in records:
            entity_id = f"{source.id}:{record.external_id}"
            entity = db.get(Entity, entity_id)
            if entity is None:
                entity = Entity(id=entity_id)
                db.add(entity)
            entity.kind = record.kind
            entity.level = record.level
            entity.name = record.name
            entity.symbol = record.symbol
            entity.attributes = {
                **record.attributes,
                "external_id": record.external_id,
                "source_id": source.id,
                "evidence": record.evidence,
            }
            written += 1
        job.records_written = written
        job.status = SyncStatus.succeeded
        job.finished_at = datetime.now(UTC)
        source.last_success_at = job.finished_at
        db.commit()
    except Exception as exc:
        db.rollback()
        current = db.get(SyncJob, job.id)
        if current:
            current.status = SyncStatus.failed
            current.error = str(exc)[:4000]
            current.finished_at = datetime.now(UTC)
            db.commit()
        raise
