import { describe, expect, it } from "vitest";

import { periodBounds, quarterPeriod, resolveContext } from "./appContext";
import { collapsedBelow, formatAmount, scopePath, searchScopes, visibleRows, type BalanceRow, type ScopeTree } from "./balance";

const values = { opening: 0, inflow: 0, outflow: 0, transform: 0, carrier: 0, revision: 0, closing: 0, residual: 0, internal: 0 };
const row = (id: string, depth: number, parent: string | null, group = false): BalanceRow => ({ id, name: id, symbol: null, depth, parent, group, values });

const rows = [
  row("substance", 0, null, true),
  row("crude", 1, "substance", true),
  row("arab-light", 2, "crude"),
  row("refined", 1, "substance", true),
  row("diesel", 2, "refined"),
  row("other", 0, null),
];

describe("balance rows", () => {
  it("hides every descendant of a collapsed group", () => {
    expect(visibleRows(rows, new Set(["substance"])).map((r) => r.id)).toEqual(["substance", "other"]);
    expect(visibleRows(rows, new Set(["crude"])).map((r) => r.id)).toEqual(["substance", "crude", "refined", "diesel", "other"]);
  });

  it("collapses groups from a depth", () => {
    expect([...collapsedBelow(rows, 1)]).toEqual(["crude", "refined"]);
  });

  it("formats amounts with a real minus and without float noise", () => {
    expect(formatAmount(-36_555_000_000, "Mt")).toBe("−36,6");
    expect(formatAmount(-3_655_000_000, "Mt")).toBe("−3,655");
    expect(formatAmount(1e-7, "t")).toBe("0");
    expect(formatAmount(7_311_000_000, "Mt", true)).toBe("+7,311");
  });
});

describe("scopes", () => {
  const tree: ScopeTree = {
    axes: [
      { id: "geo", name: "Географія", roots: [{ id: "earth", name: "Earth", kind: "place", children: [{ id: "india", name: "India", kind: "place", children: [{ id: "jamnagar", name: "Jamnagar refinery", kind: "asset", children: [] }] }] }] },
      { id: "control", name: "Власність", roots: [{ id: "control:all", name: "Усі актори", kind: "group", children: [{ id: "reliance", name: "Reliance", kind: "actor", children: [] }] }] },
    ],
  };

  it("builds the breadcrumb path on the right axis", () => {
    expect(scopePath(tree, "jamnagar")?.path.map((n) => n.id)).toEqual(["earth", "india", "jamnagar"]);
    expect(scopePath(tree, "reliance")?.axis.id).toBe("control");
    expect(scopePath(tree, "nowhere")).toBeNull();
  });

  it("searches by name", () => {
    expect(searchScopes(tree.axes[0], "jam").map((r) => r.node.id)).toEqual(["jamnagar"]);
  });
});

describe("app context", () => {
  it("prefers URL over storage and repairs invalid values", () => {
    const context = resolveContext("?layer=PROD&from=2023-04-01&to=2023-01-01", { scope: "india", from: "bad" });
    expect(context).toEqual({ layer: "prod", scope: "india", from: "2023-04-01", to: "2023-04-01" });
    expect(resolveContext("?layer=qa", null).layer).toBe("dev");
  });

  it("turns an inclusive period into API bounds", () => {
    expect(periodBounds("2023-01-01", "2023-12-31")).toEqual({ from: "2023-01-01T00:00:00Z", to: "2024-01-01T00:00:00Z" });
    expect(quarterPeriod(2023, 1)).toEqual({ from: "2023-01-01", to: "2023-03-31" });
  });
});
