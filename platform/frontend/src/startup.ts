export const DEFAULT_SCENARIO_ID = "southwest-2011";

type AutoStartState = {
  scenarioId: string;
  scenarioModelVersionId?: string;
  loadedModelVersionId?: string;
  timelineReady: boolean;
  runExists: boolean;
  alreadyRequested: boolean;
};

export function shouldAutoStartDefaultScenario(state: AutoStartState): boolean {
  return Boolean(
    state.scenarioId === DEFAULT_SCENARIO_ID &&
      state.scenarioModelVersionId &&
      state.loadedModelVersionId === state.scenarioModelVersionId &&
      state.timelineReady &&
      !state.runExists &&
      !state.alreadyRequested,
  );
}

export function runModelVersionId(
  scenarioModelVersionId: string | undefined,
  publishedModelVersionId: string,
): string {
  return scenarioModelVersionId || publishedModelVersionId;
}
