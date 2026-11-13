import { useState } from "react";
import { FUEL_COLOR, FUEL_LABEL, VOLTAGE_CLASSES } from "./format";

const LOAD_STOPS = [
  { color: "#3fbf7f", label: "< 70%" },
  { color: "#c9d34a", label: "70–90%" },
  { color: "#f0bd63", label: "90–100%" },
  { color: "#ff6a3d", label: "100–120%" },
  { color: "#ff2d55", label: "> 120%" },
];

/** Collapsible map legend; in a run it explains line loading and outages instead of voltage. */
const LEGEND_KEY = "aftertime.energy.legend";

export default function Legend({ simulation }: { simulation: boolean }) {
  const [open, setOpenState] = useState(() => {
    try {
      return window.localStorage.getItem(LEGEND_KEY) !== "closed";
    } catch {
      return true;
    }
  });
  const setOpen = (value: boolean) => {
    setOpenState(value);
    try {
      window.localStorage.setItem(LEGEND_KEY, value ? "open" : "closed");
    } catch {
      // A convenience only.
    }
  };
  return (
    <div className={`en-legend ${open ? "" : "closed"}`}>
      <button className="en-legend-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        Легенда {open ? "▾" : "▸"}
      </button>
      {open && (
        <div className="en-legend-body">
          {simulation ? (
            <>
              <h5>Завантаження ЛЕП</h5>
              {LOAD_STOPS.map((s) => (
                <div key={s.label} className="en-legend-row"><i className="en-legend-line" style={{ background: s.color }} />{s.label}</div>
              ))}
              <div className="en-legend-row"><i className="en-legend-line" style={{ background: "#5b6763" }} />Відключено / знеструмлено</div>
              <div className="en-legend-row"><i className="en-legend-dot hit" />Ціль події</div>
            </>
          ) : (
            <>
              <h5>Напруга</h5>
              {VOLTAGE_CLASSES.slice(0, -1).map((c, i) => (
                <div key={c.label} className="en-legend-row">
                  <i className="en-legend-line" style={{ background: c.color, height: Math.max(1.5, 4 - i * 0.4) }} />{c.label}
                </div>
              ))}
              <div className="en-legend-row"><i className="en-legend-line dashed" />Будується / проєкт</div>
            </>
          )}
          <h5>Електростанції <small>(розмір — потужність)</small></h5>
          <div className="en-legend-fuels">
            {["nuclear", "coal", "gas", "hydro", "wind", "solar"].map((f) => (
              <span key={f}><i className="en-legend-dot" style={{ background: FUEL_COLOR[f] }} />{FUEL_LABEL[f]}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
