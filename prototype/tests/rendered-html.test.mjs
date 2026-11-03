import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { baseCircuitInputs, simulateAmmoniaCircuit } from "../db/simulator.ts";
import { defaultSimulationInputs, simulateModelLab } from "../db/model-lab.ts";

const root = new URL("../", import.meta.url);

test("world model uses the persistent D1 binding", async () => {
  const [hosting, page, world] = await Promise.all([
    readFile(new URL(".openai/hosting.json", root), "utf8"),
    readFile(new URL("app/page.tsx", root), "utf8"),
    readFile(new URL("db/world.ts", root), "utf8"),
  ]);

  assert.equal(JSON.parse(hosting).d1, "DB");
  assert.match(page, /getWorldSnapshot/);
  assert.match(world, /env\.DB/);
  assert.match(world, /INSERT OR IGNORE INTO scenarios/);
  assert.match(world, /INSERT OR IGNORE INTO dependencies/);
});

test("dashboard exposes the complete territory-free Model Lab workflow", async () => {
  const dashboard = await readFile(new URL("app/dashboard.tsx", root), "utf8");

  for (const view of ["run", "scheme", "incidents", "recovery", "qualification", "catalog"]) {
    assert.match(dashboard, new RegExp(`"${view}"`));
  }
  assert.match(dashboard, /БЕЗ ТЕРИТОРІЙ/);
  assert.match(dashboard, /ImpactContract/);
  assert.match(dashboard, /Black start/);
  assert.doesNotMatch(dashboard, /latitude|longitude|centroid_lat|centroid_lon/);
});

test("generated migration contains Model Lab catalogs and indexes", async () => {
  const migration = await readFile(new URL("drizzle/0003_common_archangel.sql", root), "utf8");
  for (const table of ["lab_components", "lab_connections", "lab_scenarios", "lab_inventory_pools", "lab_crew_pools"]) {
    assert.ok(migration.includes("CREATE TABLE `" + table + "`"));
  }
  assert.match(migration, /idx_lab_components_parent/);
  assert.match(migration, /idx_lab_scenarios_category/);
  assert.doesNotMatch(migration, /latitude|longitude|territory_id|country_code/);
});

test("baseline Model Lab run closes balance and serves demand", () => {
  const baseline = simulateModelLab({
    generation_loss: 0, transfer_loss: 0, gas_loss: 0, voltage_stress: 0,
    scada_available: 1, system_separation: 0, black_start_required: 0,
    damaged_assets: 0, hazard_delay_hours: 0, repair_hours: 0,
    transformer_spares: 0, line_kits: 0, repeat_damage: 0,
  }, defaultSimulationInputs);

  assert.equal(baseline.balance.closed, true);
  assert.equal(baseline.grid.blackSystem, false);
  assert.equal(baseline.grid.islandCount, 1);
  assert.equal(baseline.flows.unservedEnergy, 0);
  assert.ok(baseline.environment.fridgeHeatToRoom > baseline.environment.fridgeHeatRemoved);
  assert.ok(baseline.environment.visibleRadiation > baseline.environment.outboundRadiation);
});

test("system damage propagates to islands, black start, inventory and critical services", () => {
  const damaged = simulateModelLab({
    generation_loss: 0.62, transfer_loss: 0.68, gas_loss: 0.08, voltage_stress: 0.75,
    scada_available: 0, system_separation: 1, black_start_required: 1,
    damaged_assets: 14, hazard_delay_hours: 24, repair_hours: 220,
    transformer_spares: 4, line_kits: 12, repeat_damage: 1,
  }, defaultSimulationInputs);

  assert.equal(damaged.grid.blackSystem, true);
  assert.ok(damaged.grid.islandCount > 1);
  assert.ok(damaged.flows.unservedEnergy > 0);
  assert.equal(damaged.recovery.externalAssistance, true);
  assert.ok(damaged.recovery.transformerShortage > 0);
  assert.ok(damaged.affectedGroups.some((group) => group.affected));
  assert.ok(damaged.timeline.some((event) => event.title.includes("Black start")));
});

test("generated migration contains the core temporal world-model tables", async () => {
  const migration = await readFile(
    new URL("drizzle/0000_chemical_rawhide_kid.sql", root),
    "utf8",
  );

  for (const table of [
    "entities",
    "relations",
    "capabilities",
    "dependencies",
    "events",
    "postings",
    "scenarios",
    "model_runs",
    "sources",
  ]) {
    assert.match(migration, new RegExp(`CREATE TABLE \\\`${table}\\\``));
  }
});

test("one-tonne ammonia circuit closes atomic balance", () => {
  const result = simulateAmmoniaCircuit(baseCircuitInputs);

  assert.equal(result.targetDeliveredKg, 1000);
  assert.equal(result.conservation.closed, true);
  assert.ok(result.conservation.errorKg < 0.001);
  assert.equal(result.bottleneck, "logistics");
  assert.ok(result.achievableDeliveredKg > 899);
  assert.ok(result.achievableDeliveredKg < 901);
});

test("gas and rail disruptions propagate and produce compensating actions", () => {
  const gasStress = simulateAmmoniaCircuit({
    ...baseCircuitInputs,
    gasAvailability: 0.35,
  });
  const railStress = simulateAmmoniaCircuit({
    ...baseCircuitInputs,
    logisticsAvailability: 0.42,
  });

  assert.equal(gasStress.bottleneck, "gas");
  assert.match(gasStress.recommendation.action, /резерв газа/i);
  assert.ok(gasStress.recommendation.recoveredKg > 0);
  assert.equal(railStress.bottleneck, "logistics");
  assert.match(railStress.recommendation.action, /автомобильный терминал/i);
  assert.ok(railStress.expectedHours > 40);
});
