---
document_id: aftertime.design.grid-incidents
revision: 1
status: draft
language: en
canonical: true
translation: ../../uk/design/GRID_INCIDENTS.md
---

# Power grid incidents on real infrastructure

[en](GRID_INCIDENTS.md) · [uk](../../uk/design/GRID_INCIDENTS.md)

This is a draft design. It describes how the platform imports real power
infrastructure, builds a network model from it, replays past incidents and
evaluates possible future ones. It applies the ODbL layer rule of
[Matter flow and Earth locations](MATTER_FLOW_AND_LOCATIONS.md), section 7.1.

## 1. Data: OpenStreetMap power infrastructure

- Source: Geofabrik extracts of OpenStreetMap, the same data that Open
  Infrastructure Map shows. The tiles of Open Infrastructure Map are not copied.
- Regions imported: UA, MD, PL, SK, HU, RO, RU (BY is supported).
- Pipeline: `osmium tags-filter` keeps power objects and the nodes they reference;
  pyosmium reads lines, cables, substations, plants, generators and converters;
  rows are upserted by `(osm_type, osm_id)` into `odbl.grid_assets`, so asset ids
  stay stable across imports.
- Tag rules follow the OSM wiki and Open Infrastructure Map: voltages in volts or
  `kV`, power units, `circuits`, lifecycle prefixes, `status`, a past `end_date`
  (retired) and objects tagged both `power=*` and `disused:power=*`.
- Gaps are recorded per object as quality flags (voltage missing, capacity
  missing, unit missing, capacity from generators). The UI lists them.
- Licence: every row is ODbL and carries attribution. Rows live only in the `odbl`
  schema.
- Command:
  `docker compose --profile import run --rm osm-import --region ua,md,pl,sk,hu,ro,ru --fetch`.

## 2. Corrections (overrides)

OSM describes the present. A replay of the past and a realistic present need
dated, sourced corrections: `status` (destroyed, damaged, occupied, disused,
active), `capacity_mw`, `availability`, `in_service_from`, `out_of_service_from`,
`controlled_by`. Every correction MUST have a source URL. Overrides become events
of every run.

## 3. Network model (topology snapshot)

A snapshot is the bus-branch network as it stood on a date:

- each substation becomes one bus per voltage level its lines use; levels are
  joined by transformers;
- OSM line ways are chained through shared end nodes into branches between
  substations or T-junctions; dangling chains are pruned;
- line ends snap to substations within 150 m; plants connect to their own buses
  or to a substation within 3 km (10 km for plants of 300 MW and more);
- reactance and rating come from typical conductors of the voltage class and are
  marked `estimated`;
- load is spread over substations by the number of distribution substations
  nearest to each (OSM density as a demand-density proxy);
- snapshots are cached by a fingerprint of parameters, imported data and
  overrides.

## 4. Engine: quasi-static cascade

Each step of a run:

1. apply the events due (outages, repairs, demand and fuel changes, separation of
   synchronous areas);
2. unit commitment: running capacity follows the merit order (nuclear, hydro,
   renewables, coal, gas, oil) up to the day's peak plus 8% spinning reserve; units
   that are not running start at fuel-specific ramp rates, so a sudden loss
   leaves a deficit that shrinks over hours;
3. islands: in each island generation is dispatched in proportion to what is
   available; a deficit sheds load in proportion (under-frequency load shedding,
   emergency schedules);
4. DC power flow per island; branches loaded above 125% trip (most loaded first)
   and the step repeats until nothing trips;
5. metrics: deficit, energy not served, generation, a frequency-dip proxy,
   islands, elements out; compact states of branches, buses and plants for the map.

The base case is balanced and N-0 secure: missing generation in OSM becomes
unmodelled supply spread over the loads, loads in islands without generation are
treated as locally supplied, and ratings already exceeded by base flows are
raised. The run summary lists these assumptions.

Runs are single, ensemble (Monte Carlo over hit probabilities and repair times,
P10–P90 bands) or N-1 screening (substations from 220 kV and lines from 300 kV,
ranked by power not served).

## 5. Historical replays

A historical scenario contains only events with public sources. Targets are
named by rules (kind, name pattern, country) and resolved against the imported
data. Where the exact targets of an attack are not public, the scenario uses
conditional targets chosen at random and says so. Each scenario carries checks
against reported facts; the UI shows model against fact.

Pilot: attacks on the energy system of Ukraine 2022–2026 (a weekly chronology
of generation losses and the system blackout of 23 November 2022).

## 6. Interface

One workspace, "Energy system", with three modes on one map: Network (explore
the real infrastructure, filters, data gaps, corrections), Replay (historical
incidents) and Scenarios (future what-ifs with a four-step wizard). A run plays
back on the map with a timeline of deficit over time, event markers, KPIs and a
model-against-fact table.

## 7. Known limits

- The engine is quasi-static: it does not model frequency dynamics; a collapse
  driven by frequency (as on 23 November 2022) is underestimated.
- Line ratings and reactances are typical values; demand is a national profile.
- OSM capacity coverage varies; unmodelled supply fills national gaps.
- Synchronous areas change by date: UA–RU and UA–BY branches open from
  24 February 2022.
