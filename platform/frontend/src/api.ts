const API = import.meta.env.VITE_API_URL || "/api/v1";

export type Summary = {
  entities: number;
  relations: number;
  observations: number;
  routes: number;
  sources: number;
  scenarios: number;
  generated_at: string;
};

export type Scenario = {
  id: string;
  name: string;
  description: string;
  probability: number;
  assumptions: Record<string, number>;
  model_version: string;
};

export type SimulationResult = {
  model_version: string;
  target_delivered_kg: number;
  achievable_delivered_kg: number;
  shortfall_kg: number;
  lower_kg: number;
  upper_kg: number;
  confidence: number;
  bottleneck: string;
  expected_hours: number;
  inputs: Record<string, number>;
  outputs: Record<string, number>;
  conservation: {
    nitrogen_in_kg: number;
    nitrogen_out_kg: number;
    hydrogen_in_kg: number;
    hydrogen_out_kg: number;
    error_kg: number;
    closed: boolean;
  };
  recommendation: {
    action: string;
    effect: string;
    lead_time_hours: number;
    recovered_kg: number;
    compensated_delivered_kg: number;
  };
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json() as Promise<T>;
}

export const getSummary = () => request<Summary>("/world/summary");
export const getScenarios = () => request<Scenario[]>("/scenarios");
export const simulate = (body: Record<string, unknown>) =>
  request<SimulationResult>("/simulations/ammonia", {
    method: "POST",
    body: JSON.stringify(body),
  });
