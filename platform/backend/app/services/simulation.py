from dataclasses import asdict, dataclass
from math import fabs

from app.schemas import AmmoniaSimulationRequest


@dataclass(frozen=True)
class Recommendation:
    action: str
    effect: str
    lead_time_hours: float
    new_availability: float
    recovered_kg: float
    compensated_delivered_kg: float


def _r(value: float, digits: int = 3) -> float:
    return round(value, digits)


def simulate_ammonia(request: AmmoniaSimulationRequest) -> dict:
    availability = {
        "gas": request.gas_availability,
        "grid": request.grid_availability,
        "logistics": request.logistics_availability,
        "workforce": request.workforce_availability,
    }
    bottleneck, limiting = min(availability.items(), key=lambda item: item[1])
    gross_before_yield = (
        request.target_delivered_kg
        / (1 - request.transit_loss)
        / (1 - request.storage_loss)
        / request.process_yield
    )
    produced = gross_before_yield * request.process_yield
    theoretical_delivered = produced * (1 - request.storage_loss) * (1 - request.transit_loss)
    delivered = theoretical_delivered * limiting

    nitrogen = produced * 28 / 34 * limiting
    hydrogen = produced * 6 / 34 * limiting
    nitrogen_out = produced * limiting * 14 / 17
    hydrogen_out = produced * limiting * 3 / 17
    balance_error = fabs(nitrogen - nitrogen_out) + fabs(hydrogen - hydrogen_out)

    actions = {
        "gas": ("Enable backup gas supply", "Feedstock and energy supply restored to 92%", 8.0, 0.92),
        "grid": ("Enable backup power", "Power availability restored to 95%", 2.0, 0.95),
        "logistics": (
            "Reroute through the road terminal",
            "Delivery availability restored to 86%",
            12.0,
            0.86,
        ),
        "workforce": (
            "Call in the qualified reserve shift",
            "Workforce availability restored to 96%",
            6.0,
            0.96,
        ),
    }
    action, effect, lead, replacement = actions[bottleneck]
    compensated_limit = min(
        replacement if key == bottleneck else value for key, value in availability.items()
    )
    compensated = theoretical_delivered * compensated_limit
    confidence = max(0.4, min(0.95, 0.9 - (1 - limiting) * 0.35 - 0.06))
    uncertainty = 0.035 + (1 - confidence) * 0.18
    duration = 18 * (1 / limiting)

    recommendation = Recommendation(
        action=action,
        effect=effect,
        lead_time_hours=lead,
        new_availability=replacement,
        recovered_kg=_r(max(0, compensated - delivered)),
        compensated_delivered_kg=_r(compensated),
    )
    return {
        "model_version": "ammonia-circuit-v0.3",
        "target_delivered_kg": _r(request.target_delivered_kg),
        "achievable_delivered_kg": _r(delivered),
        "shortfall_kg": _r(max(0, request.target_delivered_kg - delivered)),
        "lower_kg": _r(delivered * (1 - uncertainty)),
        "upper_kg": _r(min(request.target_delivered_kg, delivered * (1 + uncertainty))),
        "confidence": _r(confidence),
        "bottleneck": bottleneck,
        "bottleneck_availability": _r(limiting),
        "expected_hours": _r(duration, 1),
        "inputs": {
            "nitrogen_kg": _r(nitrogen),
            "hydrogen_kg": _r(hydrogen),
            "natural_gas_gj": _r(gross_before_yield * 28 / 1000 * limiting),
            "electricity_mwh": _r(gross_before_yield * 0.7 / 1000 * limiting),
            "water_kg": _r(gross_before_yield * 1.58 * limiting),
        },
        "outputs": {
            "produced_ammonia_kg": _r(produced * limiting),
            "storage_loss_kg": _r(produced * request.storage_loss * limiting),
            "transit_loss_kg": _r(
                produced * (1 - request.storage_loss) * request.transit_loss * limiting
            ),
            "delivered_kg": _r(delivered),
        },
        "conservation": {
            "nitrogen_in_kg": _r(nitrogen),
            "nitrogen_out_kg": _r(nitrogen_out),
            "hydrogen_in_kg": _r(hydrogen),
            "hydrogen_out_kg": _r(hydrogen_out),
            "error_kg": _r(balance_error, 8),
            "closed": balance_error < 0.001,
        },
        "recommendation": asdict(recommendation),
    }
