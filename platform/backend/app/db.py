from collections.abc import Generator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings
from app.layers import LAYERS, Layer, current_layer


class Base(DeclarativeBase):
    pass


# One engine per layer; each layer has its own database (see app/layers.py).
engines: dict[Layer, Engine] = {
    layer: create_engine(settings.layer_urls[layer], pool_pre_ping=True) for layer in LAYERS
}
sessionmakers: dict[Layer, sessionmaker[Session]] = {
    layer: sessionmaker(bind=engines[layer], expire_on_commit=False) for layer in LAYERS
}

# DEV is the original database: seeds, tests and scripts keep using these names.
engine = engines["dev"]
SessionLocal = sessionmakers["dev"]


def layer_session(layer: Layer | None = None) -> Session:
    """A new session on the given layer, or on the layer of the current request."""
    return sessionmakers[layer or current_layer.get()]()


def session_layer(session: Session) -> Layer:
    """Layer whose database the session is bound to."""
    bind = session.get_bind()
    for layer, layer_engine in engines.items():
        if bind is layer_engine:
            return layer
    return current_layer.get()


def request_layer(request: Request) -> Layer:
    """Layer resolved by the layer middleware in app.main (DEV when absent)."""
    return getattr(request.state, "layer", None) or current_layer.get()


def get_db(request: Request) -> Generator[Session]:
    with layer_session(request_layer(request)) as session:
        yield session
