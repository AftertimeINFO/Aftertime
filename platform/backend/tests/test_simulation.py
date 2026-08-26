from app.schemas import AmmoniaSimulationRequest
from app.services.simulation import simulate_ammonia


def test_atomic_balance_closes() -> None:
    result = simulate_ammonia(AmmoniaSimulationRequest(persist=False))
    assert result["conservation"]["closed"] is True
    assert result["conservation"]["error_kg"] < 0.001
    assert 899 < result["achievable_delivered_kg"] < 901


def test_gas_failure_propagates_to_recommendation() -> None:
    result = simulate_ammonia(AmmoniaSimulationRequest(gas_availability=0.35, persist=False))
    assert result["bottleneck"] == "gas"
    assert "резерв газа" in result["recommendation"]["action"].lower()
    assert result["recommendation"]["recovered_kg"] > 0


def test_logistics_failure_produces_rerouting_plan() -> None:
    result = simulate_ammonia(AmmoniaSimulationRequest(logistics_availability=0.42, persist=False))
    assert result["bottleneck"] == "logistics"
    assert "автомобильный терминал" in result["recommendation"]["action"].lower()
    assert result["expected_hours"] > 40
