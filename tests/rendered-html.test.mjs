import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { baseCircuitInputs, simulateAmmoniaCircuit } from "../db/simulator.ts";

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

test("dashboard exposes planning, causality, ledger and evidence views", async () => {
  const dashboard = await readFile(new URL("app/dashboard.tsx", root), "utf8");

  for (const view of ["overview", "network", "ledger", "lab", "scenarios", "sources"]) {
    assert.match(dashboard, new RegExp(`"${view}"`));
  }
  assert.match(dashboard, /Math\.min/);
  assert.match(dashboard, /Трансформации материи и энергии/);
  assert.match(dashboard, /Прогноз будущих состояний/);
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
