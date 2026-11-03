# Aftertime Platform

## Model Lab

Локальна робоча Model Lab доступна на `http://localhost:8083` після запуску
`docker compose up --build -d`. Інтерфейс дозволяє складати граф із компонентів,
редагувати параметри та Python-контракти, окремо тестувати вузли, публікувати
незмінні snapshots, керувати модельним часом і вручну або за календарем
викликати аварійні події. PostgreSQL зберігає моделі, події, checkpoints,
журнали, ремонтні ресурси та результати запусків.

Кваліфікаційний gate перевіряється через `GET /api/v1/lab/qualification` і
охоплює 15 історично мотивованих системних профілів без координат та реальних
ідентифікаторів активів.

A complete local product edition of Aftertime. It runs with Docker and includes:

- PostgreSQL — system world model, observation history, and calculation results;
- FastAPI — API, domain operations, and forecasting engine;
- Redis — background job transport;
- worker — external source synchronization;
- React/TypeScript — operator interface;
- Alembic — controlled schema migrations.

## Quick start

Requirement: Docker Desktop with Docker Compose v2.

```bash
cd platform
docker compose up --build -d
```

After startup:

- interface: http://localhost:8083
- API: http://localhost:8000
- OpenAPI: http://localhost:8000/docs
- health check: http://localhost:8000/health

Check status:

```bash
docker compose ps
docker compose logs -f api worker frontend
```

Stop:

```bash
docker compose down
```

PostgreSQL and Redis data are preserved in named Docker volumes. To remove all
local data:

```bash
docker compose down -v
```

## Data synchronization

Included adapters:

- `chebi` — ChEBI 2.0 chemical entities;
- `worldbank` — World Bank Indicators API.

Start ChEBI synchronization through the API:

```bash
curl -X POST http://localhost:8000/api/v1/sync/jobs \
  -H "Content-Type: application/json" \
  -d '{"source_id":"chebi","parameters":{"external_ids":["16134","18276","17790"]}}'
```

Or run it directly inside the container:

```bash
docker compose exec api python -m app.sync_cli --source chebi --external-id 16134
docker compose exec api python -m app.sync_cli --source worldbank
```

Job status:

```bash
curl http://localhost:8000/api/v1/sync/jobs
```

## Tests

```bash
docker compose run --rm api python -m pytest
```

Tests cover atomic balance, failure propagation, and the selection of
compensating actions.

## Main API endpoints

- `GET /api/v1/world/summary`
- `GET /api/v1/entities`
- `GET /api/v1/scenarios`
- `POST /api/v1/simulations/ammonia`
- `GET /api/v1/sync/jobs`
- `POST /api/v1/sync/jobs`

## Architecture principles

1. Observed reality is separated from model estimates.
2. Every external record retains its source and provenance evidence.
3. A model is versioned together with its calculation result.
4. State is stored in PostgreSQL; the frontend is not a source of truth.
5. Synchronization runs in a worker process and does not block the API.
6. Physical checks run before a result is used for planning.

See [ARCHITECTURE.md](ARCHITECTURE.md).
