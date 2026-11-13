FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# osmium-tool filters OSM extracts for the grid importer (app/grid/osm_import.py).
RUN apt-get update \
    && apt-get install -y --no-install-recommends osmium-tool \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install ".[dev]"

COPY alembic.ini docker-entrypoint.sh ./
COPY migrations ./migrations
COPY app ./app
COPY tests ./tests
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000
CMD ["/app/docker-entrypoint.sh", "api"]
