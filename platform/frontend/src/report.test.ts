import { describe, expect, it } from "vitest";
import { defaultStep, fitStep, niceTicks, pointLabel, pointsFor, reportUrl } from "./report";
import { addressOf, kindOfPath, openIn, restoreFor, tabTitle, type TabsState } from "./tabs";

const empty: TabsState = { tabs: [], active: null };

describe("report periods", () => {
  it("counts calendar sub-periods and picks a readable step", () => {
    expect(pointsFor("2030-01-01", "2030-12-31", "month")).toBe(12);
    expect(pointsFor("2030-02-15", "2030-04-10", "month")).toBe(3);
    expect(pointsFor("2030-02-15", "2031-01-10", "quarter")).toBe(5);
    expect(pointsFor("2019-01-01", "2050-12-31", "year")).toBe(32);
    expect(defaultStep("2030-01-01", "2030-12-31")).toBe("month");
    expect(defaultStep("2024-01-01", "2030-12-31")).toBe("quarter");
    expect(defaultStep("2019-01-01", "2050-12-31")).toBe("year");
    // A month step over 32 years would give 384 points: the next step that fits is used.
    expect(fitStep("2019-01-01", "2050-12-31", "month")).toBe("year");
    expect(fitStep("2021-01-01", "2030-12-31", "month")).toBe("month");
  });

  it("labels sub-periods by their start", () => {
    expect(pointLabel("2030-03-01T00:00:00+00:00", "month")).toBe("бер 2030");
    expect(pointLabel("2030-04-01", "quarter")).toBe("Q2 2030");
    expect(pointLabel("2030-01-01", "year")).toBe("2030");
  });

  it("makes round ticks that include zero, or span the values", () => {
    expect(niceTicks(-34.9e9, 114.4e9)).toEqual([-50e9, 0, 50e9, 100e9, 150e9]);
    const stock = niceTicks(4780e9, 4929e9, 5, false);
    expect(stock[0]).toBeLessThanOrEqual(4780e9);
    expect(stock[stock.length - 1]).toBeGreaterThanOrEqual(4929e9);
    expect(stock).not.toContain(0);
  });
});

describe("report tabs", () => {
  it("open a new tab per report, titled by row, flow and scope", () => {
    const url = reportUrl("chart", { id: "type:arab-light", name: "Arab Light" }, "substance", "Видобуток → Abqaiq");
    expect(kindOfPath(url)).toBe("chart");
    let state = openIn(empty, { kind: "balance", scope: "place:ghawar", scopeName: "Ghawar field" }, "a");
    state = openIn(state, { kind: "chart", url, scope: "place:ghawar", scopeName: "Ghawar field", from: "2030-01-01", to: "2030-12-31" }, "b");
    state = openIn(state, { kind: "turnover", url: url.replace("/chart", "/turnover"), scope: "place:ghawar", scopeName: "Ghawar field" }, "c");
    state = openIn(state, { kind: "chart", url, scope: "place:earth", scopeName: "Earth" }, "d");
    expect(state.tabs.map((t) => t.kind)).toEqual(["balance", "chart", "turnover", "chart"]);
    expect(tabTitle(state.tabs[1])).toBe("Графік · Arab Light · Видобуток → Abqaiq · Ghawar field");
    expect(tabTitle(state.tabs[2])).toBe("Обороти · Arab Light · Видобуток → Abqaiq · Ghawar field");
    const address = addressOf(state.tabs[1]);
    expect(address.startsWith("/report/chart?")).toBe(true);
    expect(new URLSearchParams(address.split("?")[1]).get("scope")).toBe("place:ghawar");
    // Reloading the address of the active report keeps its tab.
    expect(restoreFor({ ...state, active: "b" }, address).tabs).toHaveLength(4);
  });
});

describe("axis labels", () => {
  it("share one number of decimals", async () => {
    const { tickLabels } = await import("./report");
    expect(tickLabels([-15e9, -10e9, -5e9, 0], 1e9)).toEqual(["-15", "-10", "-5", "0"]);
    expect(tickLabels([4750e9, 4800e9, 4850e9], 1e9).every((label) => !label.includes(","))).toBe(true);
    expect(tickLabels([0, 0.5e9, 1e9], 1e9)).toEqual(["0,0", "0,5", "1,0"]);
  });
});
