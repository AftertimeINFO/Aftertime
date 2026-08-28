export const DEFAULT_SCENARIO_ID = "storm-arwen-2021";

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
