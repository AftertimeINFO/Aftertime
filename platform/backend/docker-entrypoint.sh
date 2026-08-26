#!/bin/sh
set -eu

mode="${1:-api}"

if [ "$mode" = "api" ]; then
  alembic upgrade head
  python -m app.seed
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000
fi

if [ "$mode" = "worker" ]; then
  exec python -m app.worker
fi

exec "$@"
