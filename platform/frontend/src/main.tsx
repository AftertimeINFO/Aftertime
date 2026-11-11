import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

// The world player pulls in MapLibre; load it only on /world.
const WorldPlayback = lazy(() => import("./WorldPlayback"));
const WorldEntities = lazy(() => import("./WorldEntities"));

const path = window.location.pathname;
const page = path.startsWith("/world/entities") ? (
  <Suspense fallback={null}>
    <WorldEntities />
  </Suspense>
) : path.startsWith("/world") ? (
  <Suspense fallback={null}>
    <WorldPlayback />
  </Suspense>
) : (
  <App />
);

createRoot(document.getElementById("root")!).render(<StrictMode>{page}</StrictMode>);
