import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import AppShell from "./AppShell";
import { getContext } from "./appContext";
import { initTabs } from "./tabs";
import "./styles.css";

// Every page opens in a tab; the address the window was opened with selects or opens one.
const { scope, from, to } = getContext();
initTabs({ scope, from, to });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppShell />
  </StrictMode>,
);
