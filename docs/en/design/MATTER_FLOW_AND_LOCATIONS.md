---
document_id: aftertime.design.matter-flow-and-locations
revision: 2
status: draft
language: en
canonical: true
translation: ../../uk/design/MATTER_FLOW_AND_LOCATIONS.md
---

# Matter flow and Earth locations: design proposal

[en](MATTER_FLOW_AND_LOCATIONS.md) · [uk](../../uk/design/MATTER_FLOW_AND_LOCATIONS.md)

This is a draft design proposal. It extends the [system model](../SYSTEM_MODEL.md)
to a deeper level of the balance of matter. It does not yet describe an
implemented feature.

## 1. Goal

Model where matter is on Earth and how it moves, at a level detailed enough to
follow a single substance from its natural reservoir to its transformation:

```text
deposit → field storage → vessel → sea route → import terminal → tank farm → refinery → products
```

The first version is approximate. It derives plausible movements from annual
statistics, while each deposit carries an explicit, sourced estimate of its
quantity, and each substance is a catalogued entity.

The model MUST keep the core invariant per substance, location and period:

```text
opening stock + inflows − outflows ± transformations = closing stock
```

A mismatch is stored as an unexplained residual, never hidden.

## 2. Design principles

### 2.1 Universal storage

The storage MUST NOT contain domain-specific tables such as `substance`,
`facility`, `location`, `stock` or `shipment`. Every thing the model knows is an
**entity**; every connection is a **relation**; every measured or estimated
quantity is an **observation**; every change is an **event**. Domain types are
data, not schema.

Adding a new kind of thing (an aquifer, a pipeline, a hydrogen carrier) MUST be
possible by adding entities and relations only, without a migration.

### 2.2 Emergence

Properties of a whole emerge from its parts and their interactions:

- A higher-level entity (refinery, port, country, ocean) is a composition of
  lower-level entities through `part_of` relations.
- A quantity is stored only at the level where it was observed. At other levels
  it is derived by aggregation over the composition and marked
  `epistemic_status = derived`.
- When a stored value at a higher level disagrees with the aggregate of its
  parts, both are kept and the difference is recorded as a residual.
- Behaviour (what an entity can hold, consume, produce or carry) comes from the
  relations of its type and its parts, not from the table it lives in.

Examples: a country's oil stock is the sum of oil portions located inside it; a
refinery's capacity emerges from its process units; a tanker's cargo emerges
from the portions it currently holds.

## 3. Current state of the platform

| Area | State |
| --- | --- |
| Generic core | `entities` (`kind`, `level`, `attributes`), `relations` (subject, predicate, object, coefficient, unit, confidence, source, validity), `observations` (subject, property, value, unit, uncertainty low/high, epistemic status, valid/recorded time, evidence), `sources`. This is the right foundation. |
| Domain-specific leftovers | `process_models`, `routes`. To be folded into the generic core. |
| Spatial | No geometry, no PostGIS, no map library. |
| Ledger | None in `platform/`. `prototype/db/schema.ts` has `events` and double-entry `postings`. |
| Simulation | Model Lab: tick-based discrete-event engine with timeline, seek and playback. Deliberately non-spatial. |
| Importers | ChEBI, World Bank Indicators. |

Consequence: the world model extends the existing generic core instead of
creating new domain tables. Model Lab stays abstract; projection of Lab circuits
onto the world model follows ROADMAP Phase 3.

## 4. Universal core

### 4.1 Tables

The core keeps four existing tables and adds three universal ones.

| Table | Status | Purpose |
| --- | --- | --- |
| `entities` | existing | Anything: a type, a place, a deposit, a portion of matter, a vessel, a process, an event. |
| `relations` | existing, extended | Typed, time-valid, weighted links. Adds `cause_event_id` (the event that created or ended the link). |
| `observations` | existing, extended | Numeric properties with uncertainty and provenance. Adds `cause_event_id`. |
| `sources` | existing | Provenance and licence. |
| `entity_extents` | new | Spatial aspect of any entity: `entity_id`, `geom` (PostGIS geometry, SRID 4326), `z_min_m`, `z_max_m`, `z_surface_ref`, `valid_from`, `valid_to`, `source_id`. |
| `events` | new | Append-only ledger header: `id`, `event_type_id` (an entity), `occurred_at`, `recorded_at`, `scenario_id`, `run_id`, `source_id`, `provenance` (`statistic`, `derived`, `assumed`). |
| `postings` | new | Signed changes caused by an event: `event_id`, `entity_id`, `property`, `delta`, `unit`. Postings of one event that move matter MUST sum to zero per conserved quantity. |

`entity_extents` is a universal aspect: any entity may have zero, one or several
extents over time (a moving vessel has a track; a border changes).

`entities.kind` and `entities.level` remain as denormalised cache labels for
fast filtering. The authoritative type is the `instance_of` relation.

### 4.2 Types are entities

A type is an entity that other entities point to with `instance_of`. Types form
a lattice with `subclass_of`. The substance catalogue, facility kinds, Earth
layers and event kinds are all such type entities.

```text
Thing
├─ Material ─ Substance ─ Crude oil ─ Arab Light
│                       └─ Refined product ─ Gasoline, Diesel, Jet fuel, Fuel oil
├─ Place ─ Sphere, Layer, Water body, Region, Geologic unit, Deposit
├─ Portion            (a bounded quantity of one material)
├─ Asset ─ Storage, Vessel, Pipeline segment, Terminal, Process unit
├─ Process            (transformation template)
├─ Actor ─ State, Company
└─ Event type ─ Transfer (─ Extract, Load, Discharge), Depart, Arrive, Transform
```

Type-level knowledge is stored as observations and relations on the type
entity: density and lower heating value of a substance, element composition
(`composed_of` with coefficients), external codes (HS, UN CPC, IEA/JODI, Wikidata,
PubChem, ChEBI) in `attributes.external_ids`.

All conserved quantities are posted in kilograms. Volumes and energy are
derived through the type's density and heating value.

### 4.3 Predicate vocabulary

| Predicate | Meaning |
| --- | --- |
| `instance_of`, `subclass_of` | Typing. |
| `part_of` | Composition; drives emergence and aggregation. |
| `located_in` | Containment of a portion or asset in a place or asset; time-valid. |
| `overlaps`, `adjacent_to` | Spatial relations computed from extents. |
| `connects` | A route or segment links two places or assets. |
| `passes_through` | A route passes a chokepoint. |
| `consumes`, `produces` | Process input and output, with `coefficient` per kg of reference input. |
| `can_hold`, `capacity_of` | What an asset type can contain; capacity as coefficient. |
| `operated_by`, `owned_by`, `jurisdiction_of` | Control. |
| `same_as` | Crosswalk between duplicate entities from different sources. |

The vocabulary is itself data and can grow; the list above is the minimum for
the pilot.

## 5. Places: Earth as composition

### 5.1 Approaches reviewed

- **Compartment (box) models.** SimpleBox and USEtox nest scales
  (local ⊂ regional ⊂ continental ⊂ global) with well-mixed compartments and
  mass transfer between them.
- **Earth system models** (CESM, CMIP6) split by component and use discrete
  vertical levels.
- **Vocabularies.** ENVO and NASA SWEET for spheres and layers; GeoNames feature
  classes; Marine Regions gazetteer (MRGID, IHO sea areas); GeoSciML / INSPIRE
  for geology and mineral resources; Wikidata as a crosswalk hub.
- **Grids.** H3 and S2 are 2D only. Common practice is a 2D cell or polygon plus
  a vertical band, which is what `entity_extents` stores.

### 5.2 Place composition

Places are entities typed under `Place`, composed with `part_of`, each with an
extent.

```text
Earth
├─ Atmosphere
│  ├─ Thermosphere      85 000 – 600 000 m
│  ├─ Mesosphere        50 000 – 85 000 m
│  ├─ Stratosphere      11 000 – 50 000 m
│  ├─ Troposphere            0 – 11 000 m (8–18 km by latitude)
│  └─ Boundary layer         0 – ~2 000 m
├─ Hydrosphere
│  ├─ Ocean › sea › gulf / bay / strait (IHO, Marine Regions)
│  │  └─ depth bands: 0–200 m, 200–1 000 m, > 1 000 m, sediment
│  ├─ Inland waters (lakes, rivers)
│  └─ Cryosphere
├─ Land surface: country › admin-1
├─ Pedosphere: soil 0–0.3 m, 0.3–2 m
├─ Lithosphere
│  ├─ Aquifer systems
│  ├─ Sedimentary basins › fields › reservoirs
│  ├─ Mineral deposits
│  └─ Crust: upper, middle, lower
└─ Mantle, core (radial shells)
```

The biosphere is a cross-cutting tag (ENVO biome), not a separate volume.
Administrative and physical places overlap; this is expressed by computed
`overlaps` / `located_in` relations, not by a second hierarchy.

### 5.3 Deposits and resource estimates

A deposit is a place. The matter in it is a **portion** entity
(`instance_of` the substance, `located_in` the deposit). Its quantity is an
observation `mass` on the portion:

| Observation field | Use |
| --- | --- |
| `value` | Best estimate (P50, 2P, or equivalent). |
| `uncertainty_low`, `uncertainty_high` | P90 and P10 (1P and 3P, or equivalent). |
| `epistemic_status` | `estimated`. |
| `evidence` | `{ "system": "PRMS" \| "CRIRSCO" \| "UNFC", "class": "2P" \| "measured" \| "E1F1G1", ... }` |
| `valid_time`, `source_id` | Estimate date and provenance. |

Rules:

- Aggregate on the best estimate. Never sum `uncertainty_high` values.
- Production events post `−mass` on the deposit portion and `+mass` on a new
  portion at field storage. The current remaining quantity emerges from the last
  estimate plus postings since its `valid_time`.
- Conflicting estimates from different sources are kept side by side.

## 6. Movement as events

### 6.1 Portions and the ledger

Moving matter is a sequence of events acting on portions:

- **Split.** A transfer of part of a portion creates a new portion; postings
  `−q` on the source portion and `+q` on the new portion.
- **Relocate.** The new portion gets a `located_in` relation to the destination
  with `valid_from = occurred_at` and `cause_event_id`.
- **Merge.** Discharging into a tank merges portions of the same material:
  postings move mass into the tank's portion; the cargo portion reaches zero and
  its `located_in` ends.
- **Transform.** A process event consumes input portions and creates output
  portions by the process entity's `consumes` / `produces` coefficients. Mass
  MUST balance within declared tolerance; losses are explicit output portions
  located in the atmosphere or a waste place.

A tanker voyage is: `Load` (portion relocated into the vessel), `Depart`,
position samples along the route, `Arrive`, `Discharge`. The vessel's own
position is its time-varying extent.

Stocks are never stored as a separate thing. The stock of a material in a place
at time `t` emerges from portions located there (transitively through
`part_of`) and their postings up to `t`. Snapshots MAY be cached as derived
observations for speed.

### 6.2 Approximation from annual statistics

1. **Country totals.** Production, refinery intake, stock change, imports and
   exports from JODI and the Energy Institute Statistical Review.
2. **Bilateral trade.** CEPII BACI at HS6 (for example `270900` crude,
   `2710xx` products), converted to kilograms. Reconcile with country totals by
   RAS (iterative proportional fitting) so that
   `production + imports − exports − Δstock = refinery intake + other use`.
3. **Asset split.** Distribute each country total across fields, terminals and
   refineries in proportion to capacity (GEM, OGIM, World Port Index).
4. **Terminal pairing.** Assign exporter terminals to importer ports by a
   gravity model or min-cost flow, with cost from sea-route distance.
5. **Cargo generation.** Split annual pair volumes into typical cargoes (VLCC
   about 2 Mbbl, Suezmax about 1 Mbbl, Aframax about 0.7 Mbbl). Spread
   departures across the year using monthly JODI profiles with seeded jitter.
   Voyage time = route distance / about 13 knots + port time.
6. **Scheduling.** A deterministic, seeded scheduler writes events and postings
   and checks the balance after every event.

Every derived event carries `provenance` and its source chain.

### 6.3 Time

Events have continuous timestamps. Playback samples positions and stocks
daily; sub-day interpolation is a front-end concern.

### 6.4 Playback

- The API serves events and position samples in time windows and supports seek,
  reusing the Model Lab timeline controls.
- Pilot view: 2D map with deck.gl (`TripsLayer` for moving portions, `ArcLayer`
  / `PathLayer` for aggregate flows, glyphs for stock levels).
- Later: 3D globe with CesiumJS (CZML exported from the same ledger) to show
  atmosphere and subsurface layers.

## 7. Open data sources

Accepted licences for the core: public domain, CC0, CC BY, Etalab 2.0, and free
terms that allow redistribution with attribution. Non-commercial (NC) sources
MUST NOT be stored.

### 7.1 Separate ODbL layer

OpenStreetMap data (directly or through Open Infrastructure Map style imports)
is stored in a separate **ODbL layer**, so that share-alike obligations apply to
that layer and not to the whole Aftertime database:

- The layer lives in its own PostgreSQL schema (`odbl`) with the same universal
  tables (`entities`, `relations`, `observations`, `entity_extents`). The core
  schema MUST NOT copy OSM geometry or attributes.
- Every row has a source, and every source has a licence. Licence is a
  propagated property: any derived row (aggregate, event, matched entity,
  computed relation) whose inputs include ODbL rows inherits `ODbL` through its
  source chain.
- Links from core entities to OSM entities use only `same_as` relations stored
  in the ODbL layer.
- Rows tagged `ODbL` MUST be published under ODbL with OSM attribution. Core
  exports MUST exclude them or be released as ODbL in full.
- The pilot MAY use the ODbL layer for asset geometry (terminals, tank farms,
  pipelines) when GEM and OGIM do not cover them; the resulting derived rows
  are then ODbL.

| Layer | Source | Licence | Use |
| --- | --- | --- | --- |
| Atmosphere bands | ISA (ISO 2533), US Standard Atmosphere 1976 | Public reference | Store |
| Countries, admin-1, oceans, lakes | Natural Earth | Public domain | Store |
| Seas, gulfs, straits, EEZ | Marine Regions (IHO) | CC BY | Store |
| Bathymetry | GEBCO | Free with attribution | Store |
| Soil bands | SoilGrids (ISRIC) | CC BY | Store |
| Crust layers | CRUST1.0 | Academic, free | Verify terms |
| Aquifers | WHYMAP (BGR / UNESCO) | Free with attribution | Verify terms |
| Petroleum basins | USGS World Petroleum Assessment | US public domain | Store |
| Mineral deposits | USGS MRDS (legacy) | US public domain | Store |
| Oil and gas fields, reserves | GEM Global Oil and Gas Extraction Tracker | CC BY 4.0 | Store only CC BY releases |
| Pipelines, LNG terminals | GEM Global Gas Infrastructure Tracker | CC BY 4.0 | Store only CC BY releases |
| Wells, refineries, terminals, tanks | EDF OGIM v2.7 (Zenodo) | CC BY 4.0 | Store |
| Ports | NGA World Port Index | US public domain | Store |
| Port calls, chokepoints | IMF PortWatch | IMF terms | Verify terms |
| Bilateral trade | CEPII BACI | Etalab 2.0 | Store |
| Monthly oil and gas | JODI | Free | Verify terms |
| Annual energy | Energy Institute Statistical Review, EIA | Free; EIA public domain | Verify EI terms |
| Substances | PubChem, ChEBI, Wikidata | Public domain, CC BY 4.0, CC0 | Store |
| Admin levels 2–5 | GADM | Non-commercial | Excluded |
| Infrastructure geometry and tags | OpenStreetMap | ODbL | Store in ODbL layer only (7.1) |

## 8. Reusable open-source components

| Need | Candidate | Licence |
| --- | --- | --- |
| Dynamic MFA reference | ODYM, flodym | MIT |
| Process input/output pattern | Brightway, openLCA | BSD-3, MPL-2.0 |
| Commodity and technology pattern | PyPSA, OSeMOSYS, MESSAGEix, oemof | MIT, Apache-2.0 |
| Queues and berths | SimPy | MIT |
| Sea routes | searoute (Python) | Apache-2.0 |
| 2D animation | deck.gl | MIT |
| 3D globe with altitude | CesiumJS | Apache-2.0 |
| QA rules for OSM power tags | validate-my-grid (Open Energy Transition; fork `russss/validate-my-grid`) | MIT |
| OSM import into PostGIS | imposm3 (upstream `omniscale/imposm3`) | Apache-2.0 |
| OSM infrastructure pipeline, tag mappings, unit parsers, substance classifier for pipelines, stats queries | Open Infrastructure Map (`openinframap/openinframap`: imposm3 → PostGIS → Tegola → MapLibre) | Code BSD-3-Clause; its data is OSM-derived, ODbL |

Open Infrastructure Map is the closest open reference for infrastructure.
Its code (tag-to-class mappings, `pipeline_type(substance)`, power and voltage
parsers, lifecycle prefixes `construction:` / `disused:`, EEZ attribution of
offshore assets) MAY be reused for the ODbL layer importer (section 7.1). Its
own tiles MAY be shown as a display layer with attribution.

No open project was found that combines a substance catalogue, assets, flows
and time playback on a map. Commercial equivalents (Kpler, Vortexa) are closed.

## 9. Pilot

Crude oil, Saudi Arabia → India, 2022–2024:

```text
Ghawar field (Arab Light) → Abqaiq processing → Ras Tanura terminal
→ tanker, Persian Gulf · Strait of Hormuz · Arabian Sea
→ Sikka terminal → Jamnagar refinery → gasoline, diesel, jet fuel, fuel oil
```

It satisfies the system model pilot rule: one material, a bounded territory and
period, several movement and transformation stages, at least two independent
sources (BACI and JODI / Energy Institute), and a measured energy link (heating
value of crude and products).

## 10. Implementation phases

1. Add PostGIS. Add `entity_extents`, `events`, `postings`; add
   `cause_event_id` to `relations` and `observations`. Seed the type lattice and
   predicate vocabulary.
2. Fold `process_models` and `routes` into entities and relations; migrate
   existing substance entities onto `instance_of` the catalogue types.
3. Seed places: atmosphere bands, Natural Earth, Marine Regions; pilot assets
   from GEM, OGIM and World Port Index.
4. Importers: BACI, JODI, Energy Institute; reserve estimates for Ghawar;
   OSM infrastructure into the ODbL layer with licence propagation.
5. Approximation pipeline and deterministic scheduler for the pilot.
6. Emergent aggregation queries (stock by place and time, flows by period) with
   residual reporting.
7. 2D map playback; later 3D globe.

## 11. Decisions

| # | Question | Decision |
| --- | --- | --- |
| 1 | New domain tables or generic core? | Generic core only, designed on emergence. No `substance`, `facility`, `stock` tables (sections 2 and 4). |
| 2 | Pilot corridor and years | Saudi Arabia → India crude, 2022–2024 (section 9). |
| 3 | 2D or 3D first | 2D map for the pilot; 3D globe later from the same ledger. |
| 4 | Licences | Core: public domain, CC0, CC BY, Etalab; no NC. OSM stored in a separate ODbL layer with licence propagation to derived rows (section 7.1). |
| 5 | Time granularity | Continuous event time; daily samples for playback (section 6.3). |
