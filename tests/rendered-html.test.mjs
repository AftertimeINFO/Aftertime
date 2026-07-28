import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

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

  for (const view of ["overview", "network", "ledger", "scenarios", "sources"]) {
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
