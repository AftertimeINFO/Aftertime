import argparse

from app.db import SessionLocal
from app.models import SyncJob
from app.sync.runner import run_sync_job


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronize an Aftertime data source")
    parser.add_argument("--source", required=True, choices=["chebi", "worldbank"])
    parser.add_argument("--external-id")
    parser.add_argument("--country", default="UA")
    parser.add_argument("--indicator", default="AG.CON.FERT.ZS")
    args = parser.parse_args()
    parameters = (
        {"external_id": args.external_id}
        if args.source == "chebi" and args.external_id
        else {"country": args.country, "indicator": args.indicator}
    )
    with SessionLocal() as db:
        job = SyncJob(source_id=args.source, parameters=parameters)
        db.add(job)
        db.commit()
        db.refresh(job)
        run_sync_job(db, job)
        print(f"{job.id}: {job.status.value}, written={job.records_written}")


if __name__ == "__main__":
    main()
