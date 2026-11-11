import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

// The world player pulls in MapLibre; load it only on /world.
const WorldPlayback = lazy(() => import("./WorldPlayback"));

const page = window.location.pathname.startsWith("/world") ? (
  <Suspense fallback={null}>
    <WorldPlayback />
  </Suspense>
) : (
  <App />
);

createRoot(document.getElementById("root")!).render(<StrictMode>{page}</StrictMode>);
