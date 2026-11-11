#!/bin/sh
set -eu

mode="${1:-api}"

if [ "$mode" = "api" ]; then
  alembic upgrade head
  # Demo data is bootstrap-only. Existing user models are never overwritten on restart.
  python -m app.seed --if-empty
  # New versioned participant/process pilots are additive and safe to reconcile on restart.
  python -m app.seed --participants
  # World core type lattice and predicate vocabulary: additive and idempotent.
  python -m app.seed --world-core
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000
fi

if [ "$mode" = "worker" ]; then
  exec python -m app.worker
fi

exec "$@"
