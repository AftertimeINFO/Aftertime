import { Suspense, lazy } from "react";
import BalancePage from "./BalancePage";
import type { TabKind } from "./tabs";

// Model Lab, the world player (MapLibre) and the entity browser load on demand.
const App = lazy(() => import("./App"));
const WorldPlayback = lazy(() => import("./WorldPlayback"));
const WorldEntities = lazy(() => import("./WorldEntities"));
const EnergyPage = lazy(() => import("./energy/EnergyPage"));
const PromotePage = lazy(() => import("./PromotePage"));
const ComputePage = lazy(() => import("./ComputePage"));
const ReportPage = lazy(() => import("./ReportPage"));
const MovementsPage = lazy(() => import("./MovementsPage"));

const loading = <div className="shell-loading">Завантаження…</div>;

/** The page shown in a tab of the given kind. */
export function TabPage({ kind }: { kind: TabKind }) {
  const page =
    kind === "balance" ? <BalancePage />
    : kind === "turnover" || kind === "chart" ? <ReportPage kind={kind} />
    : kind === "movements" ? <MovementsPage />
    : kind === "world" ? <WorldPlayback />
    : kind === "entities" ? <WorldEntities />
    : kind === "energy" ? <EnergyPage />
    : kind === "lab" ? <App />
    : kind === "compute" ? <ComputePage />
    : <PromotePage />;
  return <Suspense fallback={loading}>{page}</Suspense>;
}
