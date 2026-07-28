import Dashboard from "./dashboard";
import { getWorldSnapshot } from "../db/world";

export const dynamic = "force-dynamic";

export default async function Home() {
  const snapshot = await getWorldSnapshot();
  return <Dashboard snapshot={snapshot} />;
}
