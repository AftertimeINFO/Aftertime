#!/bin/sh
set -eu

mode="${1:-api}"

if [ "$mode" = "api" ]; then
  # Each model layer (dev, preprod, prod) has its own database: create missing ones.
  python -m app.layers ensure
  python -m app.layers urls | while read -r layer url; do
    echo "migrating layer $layer"
    DATABASE_URL="$url" alembic upgrade head
    # World core type lattice and predicate vocabulary: additive and idempotent, every layer.
    python -m app.seed --world-core --layer "$layer"
  done
  # Demo data is bootstrap-only and lives in DEV. Existing user models are never overwritten.
  python -m app.seed --if-empty --layer dev
  # New versioned participant/process pilots are additive and safe to reconcile on restart.
  python -m app.seed --participants --layer dev
  # Pilot run (Saudi Arabia to India crude, 2023, assumed figures): DEV only, generated once.
  python -m app.seed --world-pilot --layer dev
  # Grid scenarios (historical replays and what-if examples): additive, by id, every layer.
  python -m app.layers urls | while read -r layer url; do
    python -m app.seed --grid-scenarios --layer "$layer"
  done
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000
fi

if [ "$mode" = "worker" ]; then
  exec python -m app.worker
fi

if [ "$mode" = "grid-worker" ]; then
  exec python -m app.grid.worker
fi

exec "$@"
