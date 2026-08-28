import json
import random
import sys
from datetime import datetime, timedelta


class APIGroup:
    def __init__(self, ctx, group):
        self.ctx, self.group = ctx, group

    def _record(self, action, **payload):
        item = {"group": self.group, "action": action, **payload}
        self.ctx.operations.append(item)
        return item


class ClockAPI(APIGroup):
    @property
    def now(self): return self.ctx.time
    def schedule(self, seconds, event_type, payload=None, target=None, priority=100, **meta):
        return self.ctx.schedule(seconds, event_type, payload, target, priority, **meta)
    def cancel(self, event_id): return self._record("cancel", event_id=event_id)


class EventsAPI(APIGroup):
    def emit(self, event_type, payload=None, target=None, priority=100, **meta):
        return self.ctx.emit(event_type, payload, target, priority, **meta)
    def subscribe(self, event_type): return self._record("subscribe", event_type=event_type)


class NodesAPI(APIGroup):
    def get(self, node_id): return self.ctx.snapshot.get("nodes", {}).get(node_id)
    def read_state(self, node_id): return (self.get(node_id) or {}).get("state", {})
    def patch_state(self, node_id, patch): return self._record("patch_state", node_id=node_id, patch=patch)
    def command(self, node_id, command, payload=None): return self._record("command", node_id=node_id, command=command, payload=payload or {})


class ResourcesAPI(APIGroup):
    def query(self, resource_id): return self.ctx.snapshot.get("resources", {}).get(resource_id, {})
    def reserve(self, resource_id, quantity=1, unit="item", **details): return self._record("reserve", resource_id=resource_id, quantity=quantity, unit=unit, details=details)
    def release(self, resource_id, quantity=1, unit="item", **details): return self._record("release", resource_id=resource_id, quantity=quantity, unit=unit, details=details)
    def consume(self, resource_id, quantity=1, unit="item", **details): return self._record("consume", resource_id=resource_id, quantity=quantity, unit=unit, details=details)
    def produce(self, resource_id, quantity=1, unit="item", **details): return self._record("produce", resource_id=resource_id, quantity=quantity, unit=unit, details=details)
    def transfer(self, resource_id, quantity, source, target, unit="item"): return self._record("transfer", resource_id=resource_id, quantity=quantity, unit=unit, details={"source": source, "target": target})


class WorkAPI(APIGroup):
    def create(self, **fields): return self._record("create", fields=fields)
    def update(self, work_id, **fields): return self._record("update", work_id=work_id, fields=fields)
    def complete(self, work_id, **result): return self._record("complete", work_id=work_id, result=result)


class MetricsAPI(APIGroup):
    def publish(self, metric_id, value, unit="", **dimensions): return self._record("publish", metric_id=metric_id, value=value, unit=unit, dimensions=dimensions)


class FlowsAPI(APIGroup):
    def publish(self, source, target, flow_type, value, unit): return self._record("publish", source=source, target=target, flow_type=flow_type, value=value, unit=unit)


class TimelineAPI(APIGroup):
    def configure(self, start, incident, end):
        self.ctx.timeline_contract = {"start": start.isoformat() if hasattr(start, "isoformat") else start, "incident": incident.isoformat() if hasattr(incident, "isoformat") else incident, "end": end.isoformat() if hasattr(end, "isoformat") else end}
        return self.ctx.timeline_contract


class Context:
    def __init__(self, data):
        self.time = datetime.fromisoformat(data["time"])
        self.parameters = data.get("parameters", {})
        self.state = data.get("state", {})
        self.inputs = data.get("inputs", {})
        self.outputs = {}
        self.logs = []
        self.emitted = []
        self.scheduled = []
        self.operations = []
        self.timeline_contract = data.get("timeline", {})
        self.snapshot = data.get("snapshot", {})
        self.random = random.Random(data.get("seed", 42))
        self.clock = ClockAPI(self, "clock")
        self.events = EventsAPI(self, "events")
        self.nodes = NodesAPI(self, "nodes")
        self.resources = ResourcesAPI(self, "resources")
        self.work = WorkAPI(self, "work")
        self.metrics = MetricsAPI(self, "metrics")
        self.flows = FlowsAPI(self, "flows")
        self.timeline = TimelineAPI(self, "timeline")

    def log(self, message, **fields):
        self.logs.append({"message": str(message), **fields})

    def emit(self, event_type, payload=None, target=None, priority=100, **meta):
        self.emitted.append({"event_type": event_type, "payload": payload or {}, "target": target, "priority": priority, **meta})

    def schedule(self, seconds, event_type, payload=None, target=None, priority=100, **meta):
        at = self.time + timedelta(seconds=float(seconds))
        self.scheduled.append({"at": at.isoformat(), "event_type": event_type, "payload": payload or {}, "target": target, "priority": priority, **meta})


def main():
    request = json.load(sys.stdin)
    namespace = {"__builtins__": __builtins__}
    code = compile(request["code"], "<component>", "exec")
    exec(code, namespace, namespace)
    ctx = Context(request["context"])
    action = request["action"]
    if action == "validate":
        result = namespace.get("validate", lambda parameters: [])(ctx.parameters) or []
    elif action == "configure":
        result = namespace.get("configure", lambda context: None)(ctx)
    elif action == "before_start":
        result = namespace.get("before_start", lambda context: None)(ctx)
    elif action == "scenario_event":
        result = namespace.get("on_scenario_event", lambda context, event: None)(ctx, request.get("event", {}))
    elif action == "command":
        result = namespace.get("on_command", lambda context, command: None)(ctx, request.get("event", {}))
    elif action == "transition":
        result = namespace.get("on_transition", lambda context, transition: None)(ctx, request.get("event", {}))
    elif action == "collect":
        result = namespace.get("collect", lambda context: None)(ctx)
    elif action == "describe_panels":
        result = namespace.get("describe_panels", lambda: [])() or []
    elif action == "initialize":
        result = namespace.get("initialize", lambda context: None)(ctx)
    elif action == "event":
        result = namespace.get("on_event", lambda context, event: None)(ctx, request.get("event", {}))
    elif action == "finalize":
        result = namespace.get("finalize", lambda context: None)(ctx)
    else:
        result = namespace.get("on_tick", lambda context, dt: None)(ctx, float(request.get("dt", 0)))
    json.dump({"result": result, "state": ctx.state, "outputs": ctx.outputs, "logs": ctx.logs[-100:], "emitted": ctx.emitted, "scheduled": ctx.scheduled, "operations": ctx.operations, "timeline": ctx.timeline_contract}, sys.stdout)


if __name__ == "__main__":
    main()
