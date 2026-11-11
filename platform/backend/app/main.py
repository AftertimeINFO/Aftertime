from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app import __version__
from app.api.routes import router
from app.api.model_lab import router as model_lab_router
from app.api.world import router as world_router
from app.config import settings
from app.db import engine

app = FastAPI(
    title="Aftertime Platform API",
    version=__version__,
    description="Physical world model, simulation and planning API",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(model_lab_router)
app.include_router(world_router)


@app.get("/health")
def health() -> dict:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "service": "aftertime-api",
        "version": __version__,
        "environment": settings.environment,
    }
