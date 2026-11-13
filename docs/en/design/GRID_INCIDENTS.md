---
document_id: aftertime.design.grid-incidents
revision: 3
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
of every run, historical or what-if.

Control areas are territories outside the operator's control between two dates
(occupation and, where it happened, liberation). A snapshot records which areas
each bus lies in; a run puts the areas in force by date. Areas in force at the
start are set aside before the base case is balanced, because the national
demand profile describes controlled territory. An area that changes during the
run is a `control` event. While an area is in force, its buses, plants and
lines leave the system, and the country's demand is spread over the territory
it still controls. This is not counted as an outage: the map shows it in its
own colour.

Areas of the pilot (coarse outlines, about 5–10 km along the front line, dates
from the sources): Crimea from 2014; the occupied parts of Donetsk and Luhansk
oblasts from February 2015 (Law 2268-VIII); from 2022, following the Ministry
for Reintegration list of occupied territories (Order 309):
- the south and the Azov coast from 4 March 2022;
- northern Luhansk oblast from 1 March 2022;
- Sievierodonetsk–Lysychansk–Popasna from 3 July 2022;
- the right bank of Kherson oblast from 2 March to 11 November 2022;
- eastern Kharkiv oblast and Lyman from 1 March to 11 September 2022;
- northern Kyiv oblast from 25 February to 2 April 2022;
- Avdiivka–Kurakhove from 6 January 2025.

The front line after January 2025, and the occupation of Chernihiv and Sumy
oblasts in 2022, are not modelled.

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

The base case is balanced and N-0 secure on the undisturbed system under normal
conditions: missing generation in OSM becomes unmodelled supply spread over the
loads, loads in islands without generation are treated as locally supplied, and
ratings already exceeded by base flows are raised. Everything in force at the
start (damage, occupation, demand and fuel conditions) is applied after that:
units are re-committed and ratings adapted, but no supply is added, so a
standing deficit stays visible. The run summary lists these assumptions.

Protection trips are re-closed after two hours; a line that is still overloaded
trips again. The frequency-dip proxy reacts only to sudden losses (events and
trips), not to the planned daily rise of demand.

Runs are single, ensemble (Monte Carlo over hit probabilities and repair times,
P10–P90 bands) or N-1 screening (substations from 220 kV and lines from 300 kV,
ranked by power not served).

## 5. Historical replays

A historical scenario contains only events with public sources. Targets are
named by rules (kind, name pattern, country) and resolved against the imported
data. Where the exact targets of an attack are not public, the scenario uses
conditional targets chosen at random and says so. Each scenario carries checks
against reported facts; the UI shows model against fact.

A check is either validation or calibration. A calibration check was used to
choose a model parameter and therefore is not independent evidence; the UI marks
it.

Pilot: attacks on the energy system of Ukraine 2022–2026 (a weekly chronology
of generation losses and the system blackout of 23 November 2022).

### 5.1 Calibration of the pilot (revision 3)

Sourced inputs: occupied or destroyed thermal plants (Starobeshivska and Zuivska
from 2017; Luhansk, Zaporizhzhia and Vuhlehirska in 2022; Kurakhove inoperable
from March 2024), Crimea as a control area from 2014, the Zaporizhzhia NPP,
Kakhovka HPP, DniproHES and Trypilska TPP, Zmiivska TPP (Centrenergo lost 100% on
11 April 2024) and DTEK thermal plants at 20% from 29 March 2024 (about 80% of
capacity lost).

One estimated parameter: the share of thermal and hydro capacity available after
the seven waves of 10 October – 23 November 2022 (0.28), calibrated to the 27%
deficit reported by Ukrenergo on 30 November 2022 and lifted on 12 February 2023,
when Ukrenergo reported no deficit.

| Check | Reported | Model | Role |
| --- | --- | --- | --- |
| 23.11.2022, 17:00 Kyiv, consumers without supply | ≥ 50% | 69% | validation |
| 24.11.2022, share of needs not covered | ~50% | 65.2% (limit 65%) ✗ | validation |
| 30.11.2022, 11:00 Kyiv, deficit | 27% | 21% | calibration |
| January 2026, peak deficit | ~7 GW | 4.7 GW | validation |
| January 2026, available generation | ~11 GW | 13.6 GW | validation |

Revision 3 takes the occupied mainland out of the system. This removes about
0.8 GW of occupied plants that had no correction of their own (Sievierodonetsk
CHP, Myronivska TPP, the Lysychansk refinery CHP, the Botiieve and Novoazovsk
wind farms). After that, the 24.11 check falls just outside its tolerance. The
parameter was not re-tuned: re-calibrating to 30.11 would raise the deficit, and
the restart time of the nuclear plants agrees with the IAEA (reconnected on
25.11). The model's recovery between 24.11 and 30.11 is steeper than reported.

## 6. Interface

One workspace, "Energy system", with three modes on one map: Network (explore
the real infrastructure, filters, data gaps, corrections), Replay (historical
incidents) and Scenarios (future what-ifs with a four-step wizard). A run plays
back on the map with a timeline of deficit over time, event markers, KPIs and a
model-against-fact table.

## 7. Known limits

- The engine is quasi-static: it does not model frequency dynamics; the depth of
  a collapse driven by frequency comes from the energy balance, not from the
  dynamics.
- Control areas are coarse outlines; the front line after January 2025 and the
  2022 occupation of Chernihiv and Sumy oblasts are not modelled. Damage left in
  liberated territory (for example Kherson after 11 November 2022) is not
  modelled either.
- Strike targets that are not public are conditional (random) targets.
- Line ratings and reactances are typical values; demand is a national profile.
- OSM capacity coverage varies; unmodelled supply fills national gaps.
- Synchronous areas change by date: UA–RU and UA–BY branches open from
  24 February 2022.
