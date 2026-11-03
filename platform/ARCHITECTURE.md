# Aftertime Platform architecture

```text
Browser
   │
   ▼
Nginx + React ─────► FastAPI
                       │
                 ┌─────┴─────┐
                 ▼           ▼
             PostgreSQL    Redis
                              │
                              ▼
                         Sync worker
                              │
                    ChEBI / World Bank / ...
```

## Domain layers

### World model

`entities`, `relations`, and `observations` describe entities, causal
relationships, and dated source claims. Extension attributes are stored in
JSONB, while primary fields are indexed relationally.

### Process model

`process_models` stores versioned technological specifications. `routes`
describes spatial constraints and alternative transport methods.

### Forecasting

`scenarios` stores assumptions. Every run is recorded in `simulation_runs`
together with the input request, model version, uncertainty range, physical
reconciliation, and bottleneck explanation.

### Data ingestion

`sources` defines a source and its adapter. `sync_jobs` is the durable ingestion
ledger. Redis is used only as job transport; the job state remains in
PostgreSQL.

## Planned extensions

- bitemporal `valid_time` / `recorded_time` for relationships;
- lot accounting and event ledgers;
- PostGIS for infrastructure networks;
- object storage for immutable raw source snapshots;
- a planner with multiple objective functions;
- authentication, organization workspaces, and role-based access control;
- OpenTelemetry, metrics, and backups.
