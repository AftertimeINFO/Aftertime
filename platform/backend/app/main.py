from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import __version__
from app.api.grid import router as grid_router
from app.api.model_lab import router as model_lab_router
from app.api.promotions import router as promotions_router
from app.api.routes import router
from app.api.world import router as world_router
from app.config import settings
from app.db import engine, engines
from app.layers import HEADER, LAYER_POLICY, LAYERS, current_layer, parse_layer, write_denied

app = FastAPI(
    title="Aftertime Platform API",
    version=__version__,
    description="Physical world model, simulation and planning API",
)


@app.middleware("http")
async def layer_middleware(request: Request, call_next):
    """Resolve the model layer of the request and refuse writes the layer does not allow."""
    try:
        layer = parse_layer(request.headers.get(HEADER) or request.query_params.get("layer"))
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    reason = write_denied(layer, request.method, request.url.path)
    if reason:
        return JSONResponse({"detail": reason}, status_code=403)
    request.state.layer = layer
    token = current_layer.set(layer)
    try:
        response = await call_next(request)
    finally:
        current_layer.reset(token)
    response.headers[HEADER] = layer
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[HEADER],
)
# Grid run frames and tiles are large JSON/binary payloads.
app.add_middleware(GZipMiddleware, minimum_size=2048)
app.include_router(router)
app.include_router(model_lab_router)
app.include_router(world_router)
app.include_router(promotions_router)
app.include_router(grid_router)


def layer_available(layer: str) -> bool:
    try:
        with engines[layer].connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@app.get("/api/v1/layers")
def layers() -> dict:
    return {
        "default": "dev",
        "items": [
            {"id": layer, **LAYER_POLICY[layer], "available": layer_available(layer)}
            for layer in LAYERS
        ],
    }


@app.get("/health")
def health() -> dict:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "service": "aftertime-api",
        "version": __version__,
        "environment": settings.environment,
        "layers": {layer: layer_available(layer) for layer in LAYERS},
    }
