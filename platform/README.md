# Aftertime Platform

Полноценная локальная продуктовая редакция Aftertime. Запускается в Docker и
включает:

- PostgreSQL — системная модель мира, история наблюдений и результаты расчётов;
- FastAPI — API, доменные операции и прогнозный движок;
- Redis — очередь фоновых заданий;
- worker — синхронизация внешних источников;
- React/TypeScript — операторский интерфейс;
- Alembic — контролируемые миграции схемы.

## Быстрый запуск

Требования: Docker Desktop с Docker Compose v2.

```bash
cd platform
docker compose up --build -d
```

После запуска:

- интерфейс: http://localhost:8080
- API: http://localhost:8000
- OpenAPI: http://localhost:8000/docs
- healthcheck: http://localhost:8000/health

Проверка состояния:

```bash
docker compose ps
docker compose logs -f api worker frontend
```

Остановка:

```bash
docker compose down
```

Данные PostgreSQL и Redis сохраняются в именованных Docker volumes. Полное
удаление локальных данных:

```bash
docker compose down -v
```

## Синхронизация данных

В поставку входят адаптеры:

- `chebi` — химические сущности ChEBI 2.0;
- `worldbank` — показатели World Bank Indicators API.

Запуск синхронизации ChEBI через API:

```bash
curl -X POST http://localhost:8000/api/v1/sync/jobs \
  -H "Content-Type: application/json" \
  -d '{"source_id":"chebi","parameters":{"external_ids":["16134","18276","17790"]}}'
```

Или напрямую внутри контейнера:

```bash
docker compose exec api python -m app.sync_cli --source chebi --external-id 16134
docker compose exec api python -m app.sync_cli --source worldbank
```

Состояние заданий:

```bash
curl http://localhost:8000/api/v1/sync/jobs
```

## Тесты

```bash
docker compose run --rm api python -m pytest
```

Проверяются атомарный баланс, распространение отказов и выбор компенсирующих
действий.

## Основные API

- `GET /api/v1/world/summary`
- `GET /api/v1/entities`
- `GET /api/v1/scenarios`
- `POST /api/v1/simulations/ammonia`
- `GET /api/v1/sync/jobs`
- `POST /api/v1/sync/jobs`

## Архитектурные принципы

1. Наблюдаемая реальность отделена от модельных оценок.
2. Все внешние записи сохраняют источник и доказательство происхождения.
3. Модель версионируется вместе с результатом расчёта.
4. Состояние сохраняется в PostgreSQL; frontend не является источником истины.
5. Синхронизация выполняется worker-процессом и не блокирует API.
6. Физические проверки выполняются до использования результата в планировании.

См. [ARCHITECTURE.md](ARCHITECTURE.md).
