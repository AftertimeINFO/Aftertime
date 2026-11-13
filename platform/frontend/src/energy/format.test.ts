import { describe, expect, it } from "vitest";
import { assetTitle, fmtKv, fmtMw, voltageColor, VOLTAGE_CLASSES } from "./format";

describe("energy format", () => {
  it("colours voltages by class and treats unknown as the lowest class", () => {
    expect(voltageColor(750)).toBe(VOLTAGE_CLASSES[0].color);
    expect(voltageColor(330)).toBe(VOLTAGE_CLASSES[1].color);
    expect(voltageColor(110)).toBe(VOLTAGE_CLASSES[4].color);
    expect(voltageColor(null)).toBe(VOLTAGE_CLASSES[VOLTAGE_CLASSES.length - 1].color);
  });
  it("formats voltages and power", () => {
    expect(fmtKv([330, 110])).toBe("330 / 110 кВ");
    expect(fmtKv([])).toBe("—");
    expect(fmtMw(2520)).toMatch(/2\s?520 МВт/);
    expect(fmtMw(13_835)).toMatch(/13,8 ГВт/);
  });
  it("names assets without a name by kind, ref and voltage", () => {
    expect(assetTitle({ name: "Київська", kind: "substation" })).toBe("Київська");
    expect(assetTitle({ ref: "Л-301", kind: "line" })).toBe("ЛЕП Л-301");
    expect(assetTitle({ kind: "substation", max_voltage_kv: 330 })).toBe("Підстанція 330 кВ без назви");
  });
});
