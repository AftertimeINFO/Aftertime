import { describe, expect, it } from "vitest";
import { contextOf } from "./appContext";
import { closeIn, kindOfPath, openIn, restoreFor, stripLayer, tabTitle, type TabsState } from "./tabs";

const empty: TabsState = { tabs: [], active: null };

describe("tabs", () => {
  it("maps addresses to pages", () => {
    expect(kindOfPath("/")).toBe("balance");
    expect(kindOfPath("/?scope=place:ghawar")).toBe("balance");
    expect(kindOfPath("/world/entities?id=x")).toBe("entities");
    expect(kindOfPath("/world")).toBe("world");
    expect(kindOfPath("/lab")).toBe("lab");
    expect(kindOfPath("/api/v1/world")).toBeNull();
    expect(stripLayer("/lab?layer=dev&project=p")).toBe("/lab?project=p");
  });

  it("opens every balance in its own tab and focuses other pages", () => {
    let state = openIn(empty, { kind: "balance", scope: "place:earth", scopeName: "Earth" }, "a");
    state = openIn(state, { kind: "world" }, "b");
    state = openIn(state, { kind: "balance", scope: "place:ghawar", scopeName: "Ghawar field" }, "c");
    state = openIn(state, { kind: "balance", scope: "place:earth", scopeName: "Earth" }, "d");
    expect(state.tabs.map((t) => t.id)).toEqual(["a", "b", "c", "d"]);
    expect(state.active).toBe("d");
    expect(tabTitle(state.tabs[2])).toBe("Баланс · Ghawar field");

    const again = openIn(state, { kind: "world", url: "/world?entity=vessel:1" }, "e");
    expect(again.tabs).toHaveLength(4);
    expect(again.active).toBe("b");
    expect(again.tabs[1].url).toBe("/world?entity=vessel%3A1");
    expect(again.tabs[1].rev).toBe(1);
  });

  it("opens a new tab next to the active one", () => {
    let state = openIn(empty, { kind: "balance" }, "a");
    state = openIn(state, { kind: "lab" }, "b");
    state = { ...state, active: "a" };
    state = openIn(state, { kind: "balance", scope: "asset:jamnagar" }, "c");
    expect(state.tabs.map((t) => t.id)).toEqual(["a", "c", "b"]);
  });

  it("closes a tab and activates its neighbour", () => {
    let state = openIn(empty, { kind: "balance" }, "a");
    state = openIn(state, { kind: "lab" }, "b");
    state = openIn(state, { kind: "compute" }, "c");
    state = { ...state, active: "b" };
    expect(closeIn(state, "b")).toMatchObject({ active: "c" });
    expect(closeIn({ ...state, active: "c" }, "c")).toMatchObject({ active: "b" });
    expect(closeIn(state, "a").active).toBe("b");
    expect(closeIn(openIn(empty, { kind: "lab" }, "x"), "x")).toEqual({ tabs: [], active: null });
  });

  it("restores the active tab on reload and opens a tab for a new address", () => {
    const state = openIn(empty, { kind: "balance", scope: "place:ghawar" }, "a");
    const reloaded = restoreFor(state, "/?layer=dev&scope=place:ghawar");
    expect(reloaded.tabs).toHaveLength(1);
    const linked = restoreFor(state, "/world/entities?layer=dev&id=asset:sikka");
    expect(linked.tabs).toHaveLength(2);
    expect(linked.tabs.find((t) => t.id === linked.active)?.url).toBe("/world/entities?id=asset%3Asikka");
  });

  it("gives each tab its own scope and period", () => {
    const base = { layer: "dev" as const, scope: "place:earth", from: "2023-01-01", to: "2023-12-31" };
    const state = openIn(empty, { kind: "balance", scope: "place:ghawar", from: "2028-01-01" }, "a");
    expect(contextOf(base, state.tabs[0])).toEqual({ ...base, scope: "place:ghawar", from: "2028-01-01" });
    expect(contextOf(base, undefined)).toEqual(base);
  });
});

describe("tab address", () => {
  it("puts the scope and period of a balance into the address", async () => {
    const { addressOf } = await import("./tabs");
    const state = openIn(empty, { kind: "balance", scope: "place:ghawar", from: "2024-01-01", to: "2024-12-31" }, "a");
    expect(addressOf(state.tabs[0])).toBe("/?scope=place%3Aghawar&from=2024-01-01&to=2024-12-31");
    expect(addressOf(openIn(empty, { kind: "lab", url: "/lab?project=p" }, "b").tabs[0])).toBe("/lab?project=p");
  });
});

describe("links to another object", () => {
  it("open a new balance tab instead of replacing the active one", () => {
    const state = openIn(empty, { kind: "balance", scope: "place:earth" }, "a");
    const linked = restoreFor(state, "/?scope=asset%3Ajamnagar");
    expect(linked.tabs).toHaveLength(2);
    expect(linked.tabs.find((t) => t.id === linked.active)?.scope).toBe("asset:jamnagar");
  });
});
