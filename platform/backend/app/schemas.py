from typing import Any

from pydantic import BaseModel, Field


class AmmoniaSimulationRequest(BaseModel):
    target_delivered_kg: float = Field(default=1000, gt=0, le=1_000_000)
    gas_availability: float = Field(default=0.92, ge=0.05, le=1)
    grid_availability: float = Field(default=0.95, ge=0.05, le=1)
    logistics_availability: float = Field(default=0.90, ge=0.05, le=1)
    workforce_availability: float = Field(default=0.96, ge=0.05, le=1)
    process_yield: float = Field(default=0.985, ge=0.5, le=1)
    storage_loss: float = Field(default=0.002, ge=0, le=0.2)
    transit_loss: float = Field(default=0.001, ge=0, le=0.2)
    persist: bool = True
    scenario_id: str | None = None


class SyncJobRequest(BaseModel):
    source_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)
