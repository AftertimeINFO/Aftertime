import { afterEach, describe, expect, it, vi } from "vitest";

import { request } from "./api";

describe("API regression handling", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows incompatible port diagnostics instead of raw JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      detail: {
        message: "Incompatible ports",
        errors: [
          "Несумісні середовища: emission → natural_gas",
          "Несумісні фізичні величини: co2_mass_flow → gas_energy_flow",
        ],
      },
    }), { status: 422, headers: { "Content-Type": "application/json" } })));

    await expect(request("/lab/test")).rejects.toThrow(
      "Несумісні середовища: emission → natural_gas. " +
      "Несумісні фізичні величини: co2_mass_flow → gas_energy_flow",
    );
  });

  it("does not leave the UI waiting forever when API is unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn((_url: string, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener("abort", () => reject(new DOMException("Timed out", "TimeoutError")));
    })));

    await expect(request("/health", undefined, 5)).rejects.toThrow(
      "Сервер не відповів за 20 секунд. Перевірте стан API/worker.",
    );
  });
});
