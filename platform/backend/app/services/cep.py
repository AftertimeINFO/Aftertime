"""Deterministic CEP evaluator persisted inside a simulation run checkpoint."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any


def _time(value: str | datetime) -> datetime:
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    return result.replace(tzinfo=UTC) if result.tzinfo is None else result


def _value(snapshot: dict[str, Any], address: str) -> Any:
    if address.startswith("component:"):
        _, target, metric = address.split(":", 2)
        return snapshot.get("component", {}).get(target, {}).get(metric)
    current: Any = snapshot
    for part in address.removeprefix("system:").split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _compare(left: Any, operation: str, right: Any, hysteresis: float = 0) -> bool:
    if left is None:
        return False
    if operation == "lt": return left < right - hysteresis
    if operation == "lte": return left <= right - hysteresis
    if operation == "gt": return left > right + hysteresis
    if operation == "gte": return left >= right + hysteresis
    if operation == "eq": return left == right
    if operation == "ne": return left != right
    return False


def _window(history: list[dict[str, Any]], now: datetime, seconds: float) -> list[dict[str, Any]]:
    start = now - timedelta(seconds=max(0, seconds))
    return [item for item in history if _time(item["at"]) >= start]


def evaluate_condition(
    condition: dict[str, Any], history: list[dict[str, Any]], now: datetime,
    memory: dict[str, Any], path: str = "root",
) -> bool:
    operator = condition.get("operator", "compare")
    if operator == "all":
        return all(evaluate_condition(item, history, now, memory, f"{path}.{index}") for index, item in enumerate(condition.get("conditions", [])))
    if operator == "any":
        return any(evaluate_condition(item, history, now, memory, f"{path}.{index}") for index, item in enumerate(condition.get("conditions", [])))
    if operator == "not":
        return not evaluate_condition(condition.get("condition", {}), history, now, memory, f"{path}.not")
    window = _window(history, now, float(condition.get("window_seconds", 0))) if condition.get("window_seconds") is not None else history[-1:]
    if operator == "event":
        return any(condition.get("event_type") in item.get("events", []) for item in window)
    if operator == "sequence":
        wanted = condition.get("event_types", [])
        cursor = 0
        for item in window:
            for event_type in item.get("events", []):
                if cursor < len(wanted) and event_type == wanted[cursor]: cursor += 1
        return bool(wanted) and cursor == len(wanted)
    if operator in {"average", "min", "max", "trend"}:
        values = [_value(item.get("metrics", {}), condition["observable"]) for item in window]
        values = [float(value) for value in values if isinstance(value, (int, float))]
        if not values: return False
        aggregate = sum(values) / len(values) if operator == "average" else min(values) if operator == "min" else max(values) if operator == "max" else values[-1] - values[0]
        return _compare(aggregate, condition.get("comparison", "gt"), float(condition.get("value", 0)), float(condition.get("hysteresis", 0)))
    if operator == "count":
        count = sum(1 for item in window if evaluate_condition(condition.get("condition", {}), [item], _time(item["at"]), memory, f"{path}.count"))
        return _compare(count, condition.get("comparison", "gte"), int(condition.get("value", 1)))
    if operator == "absence":
        return bool(window) and not any(evaluate_condition(condition.get("condition", {}), [item], _time(item["at"]), memory, f"{path}.absence") for item in window)
    if operator == "duration":
        nested = evaluate_condition(condition.get("condition", {}), history[-1:], now, memory, f"{path}.duration")
        key = f"{path}:since"
        if not nested: memory.pop(key, None); return False
        memory.setdefault(key, now.isoformat())
        return (now - _time(memory[key])).total_seconds() >= float(condition.get("seconds", 0))
    current = history[-1] if history else {"metrics": {}}
    left = _value(current.get("metrics", {}), condition.get("observable", ""))
    return _compare(left, condition.get("comparison", "gt"), condition.get("value"), float(condition.get("hysteresis", 0)))


def evaluate_rules(
    rules: list[Any], state: dict[str, Any], now: datetime, metrics: dict[str, Any], events: list[str],
) -> list[dict[str, Any]]:
    cep = state.setdefault("cep", {"history": [], "rules": {}})
    history = cep.setdefault("history", [])
    history.append({"at": now.isoformat(), "metrics": metrics, "events": events})
    max_window = max([float(rule.condition.get("window_seconds", 0)) for rule in rules] + [3600])
    history[:] = _window(history, now, max_window)
    emitted: list[dict[str, Any]] = []
    for rule in rules:
        memory = cep.setdefault("rules", {}).setdefault(rule.id, {})
        matched = evaluate_condition(rule.condition, history, now, memory)
        cooldown = float(rule.condition.get("cooldown_seconds", 0))
        last_emit = _time(memory["last_emit"]) if memory.get("last_emit") else None
        armed = not memory.get("latched", False) or bool(rule.condition.get("repeat", False))
        ready = not last_emit or (now - last_emit).total_seconds() >= cooldown
        if matched and armed and ready:
            emitted.append(dict(rule.emit))
            memory["last_emit"] = now.isoformat()
            memory["latched"] = True
        elif not matched:
            memory["latched"] = False
    return emitted
