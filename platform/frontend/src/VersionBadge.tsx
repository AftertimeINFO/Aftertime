import { useEffect, useState } from "react";
import { request } from "./api";

/** UI and API versions; the API one is shown only when it differs. */
export default function VersionBadge() {
  const ui = typeof __APP_VERSION__ === "string" ? __APP_VERSION__ : "dev";
  const [api, setApi] = useState<string | null>(null);
  useEffect(() => {
    request<{ api: string }>("/world/version").then((v) => setApi(v.api)).catch(() => setApi("?"));
  }, []);
  return (
    <span className="world-version" title={`UI ${ui} · API ${api ?? "…"}`}>
      v{ui}{api && api !== ui ? ` · API ${api}` : ""}
    </span>
  );
}
