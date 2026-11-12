"""Promotion of model versions between layers (DEV → prePROD → PROD).

The source is always the layer of the request; the target is the next layer.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db, layer_session, request_layer
from app.layers import LAYER_POLICY
from app.services.promotion import PromotionError, candidates, history, next_layer, plan_promotion, promote

router = APIRouter(prefix="/api/v1/promotions")


def _target(request: Request) -> str:
    target = next_layer(request_layer(request))
    if not target:
        raise HTTPException(422, "З PROD моделі далі не переносяться")
    return target


@router.get("")
def list_candidates(request: Request, db: Session = Depends(get_db)) -> dict:
    """Published versions of the current layer and their state in the next one."""
    source = request_layer(request)
    target = next_layer(source)
    if target:
        with layer_session(target) as target_db:
            items = candidates(db, target_db)
    else:
        items = candidates(db, None)
    return {
        "source": source,
        "target": target,
        "target_label": LAYER_POLICY[target]["label"] if target else None,
        "items": items,
        "history": history(db),
    }


@router.get("/plan")
def plan(version_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    target = _target(request)
    with layer_session(target) as target_db:
        try:
            return plan_promotion(db, target_db, version_id, request_layer(request), target)
        except PromotionError as exc:
            raise HTTPException(exc.status, exc.detail) from exc


@router.post("")
def run_promotion(body: dict[str, Any], request: Request, db: Session = Depends(get_db)) -> dict:
    version_id = body.get("version_id")
    if not isinstance(version_id, str) or not version_id:
        raise HTTPException(422, "version_id is required")
    target = _target(request)
    with layer_session(target) as target_db:
        try:
            return promote(db, target_db, version_id, request_layer(request), target, str(body.get("note") or "")[:2000])
        except PromotionError as exc:
            target_db.rollback()
            raise HTTPException(exc.status, exc.detail) from exc
