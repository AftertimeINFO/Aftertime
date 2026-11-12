import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import AppShell from "./AppShell";
import BalancePage from "./BalancePage";
import "./styles.css";

// Model Lab, the world player (MapLibre) and the entity browser load on demand.
const App = lazy(() => import("./App"));
const WorldPlayback = lazy(() => import("./WorldPlayback"));
const WorldEntities = lazy(() => import("./WorldEntities"));
const PromotePage = lazy(() => import("./PromotePage"));

const path = window.location.pathname;
const loading = <div className="shell-loading">Завантаження…</div>;
const page = path.startsWith("/world/entities") ? (
  <AppShell>
    <Suspense fallback={loading}>
      <WorldEntities />
    </Suspense>
  </AppShell>
) : path.startsWith("/world") ? (
  <AppShell>
    <Suspense fallback={loading}>
      <WorldPlayback />
    </Suspense>
  </AppShell>
) : path.startsWith("/promote") ? (
  <AppShell>
    <Suspense fallback={loading}>
      <PromotePage />
    </Suspense>
  </AppShell>
) : path.startsWith("/lab") ? (
  <AppShell>
    <Suspense fallback={loading}>
      <App />
    </Suspense>
  </AppShell>
) : (
  <AppShell usesScope>
    <BalancePage />
  </AppShell>
);

createRoot(document.getElementById("root")!).render(<StrictMode>{page}</StrictMode>);
