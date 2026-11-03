export type LabRow = Record<string, string | number | null>;

export type ScenarioParams = {
  generationLoss: number;
  transferLoss: number;
  gasLoss: number;
  voltageStress: number;
  scadaAvailable: boolean;
  systemSeparation: boolean;
  blackStartRequired: boolean;
  damagedAssets: number;
  hazardDelayHours: number;
  repairHours: number;
  transformerSpares: number;
  lineKits: number;
  repeatDamage: boolean;
};

export type SimulationInputs = {
  demandMWh: number;
  gasEnergyMWh: number;
  reserveMW: number;
  crewAvailability: number;
};

const num = (value: unknown, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const clamp = (value: number, low = 0, high = 1) => Math.min(high, Math.max(low, value));
const round = (value: number, digits = 1) => Number(value.toFixed(digits));

export function scenarioParams(row: LabRow | undefined): ScenarioParams {
  return {
    generationLoss: clamp(num(row?.generation_loss)),
    transferLoss: clamp(num(row?.transfer_loss)),
    gasLoss: clamp(num(row?.gas_loss)),
    voltageStress: clamp(num(row?.voltage_stress)),
    scadaAvailable: num(row?.scada_available, 1) === 1,
    systemSeparation: num(row?.system_separation) === 1,
    blackStartRequired: num(row?.black_start_required) === 1,
    damagedAssets: Math.max(0, num(row?.damaged_assets)),
    hazardDelayHours: Math.max(0, num(row?.hazard_delay_hours)),
    repairHours: Math.max(0, num(row?.repair_hours)),
    transformerSpares: Math.max(0, num(row?.transformer_spares)),
    lineKits: Math.max(0, num(row?.line_kits)),
    repeatDamage: num(row?.repeat_damage) === 1,
  };
}

export function simulateModelLab(row: LabRow | undefined, input: SimulationInputs) {
  const scenario = scenarioParams(row);
  const gasAfterExtraction = input.gasEnergyMWh * (1 - scenario.gasLoss);
  const gasDelivered = gasAfterExtraction * 0.965;
  const boilerHeat = gasDelivered * 0.9;
  const turbineWork = boilerHeat * 0.4;
  const generatorGross = turbineWork * 0.98;
  const ownUse = generatorGross * 0.06;
  const generatorNet = Math.max(0, generatorGross - ownUse) * (1 - scenario.generationLoss);
  const transferCapacity = 360 * (1 - scenario.transferLoss);
  const networkInput = Math.min(generatorNet + input.reserveMW, transferCapacity);
  const socketEnergy = networkInput * 0.9;
  const availableBeforeShedding = Math.max(0, socketEnergy);
  const servedEnergy = Math.min(input.demandMWh, availableBeforeShedding);
  const unservedEnergy = Math.max(0, input.demandMWh - servedEnergy);
  const serviceRatio = input.demandMWh > 0 ? servedEnergy / input.demandMWh : 1;
  const rawFrequencyDrop = unservedEnergy / Math.max(input.demandMWh, 1) * 3.2;
  const frequencyNadir = round(Math.max(47.5, 50 - rawFrequencyDrop - scenario.voltageStress * 0.45), 2);
  const voltagePu = round(Math.max(0.72, 1 - scenario.voltageStress * 0.2 - scenario.transferLoss * 0.08), 3);
  const islandCount = scenario.systemSeparation ? Math.max(2, Math.ceil(scenario.damagedAssets / 2)) : 1;
  const blackSystem = scenario.blackStartRequired || frequencyNadir < 48.2 || voltagePu < 0.78;
  const shedEnergy = blackSystem ? Math.max(unservedEnergy, input.demandMWh * 0.72) : unservedEnergy;

  const fridgeElectricity = servedEnergy * 0.58;
  const ledElectricity = servedEnergy * 0.12;
  const fridgeHeatRemoved = fridgeElectricity * 3;
  const fridgeHeatToRoom = fridgeHeatRemoved + fridgeElectricity;
  const visibleRadiation = ledElectricity * 0.35;
  const ledDirectHeat = ledElectricity - visibleRadiation;
  const absorbedLight = visibleRadiation * 0.92;
  const outboundRadiation = visibleRadiation - absorbedLight;
  const directPlantHeat = gasDelivered - generatorGross;
  const gridHeat = networkInput - socketEnergy;

  const localTransformerStock = 2;
  const localLineKitStock = 6;
  const transformerShortage = Math.max(0, scenario.transformerSpares - localTransformerStock);
  const lineKitShortage = Math.max(0, scenario.lineKits - localLineKitStock);
  const externalAssistance = transformerShortage > 0 || lineKitShortage > 0;
  const crewFactor = 1 / Math.max(0.2, input.crewAvailability);
  const mobilizationHours = round(2 * crewFactor + (scenario.scadaAvailable ? 0 : 4), 1);
  const logisticsDelay = transformerShortage * 72 + lineKitShortage * 10;
  const repeatDelay = scenario.repeatDamage ? 12 : 0;
  const restorationHours = round(
    scenario.hazardDelayHours + mobilizationHours + scenario.repairHours * crewFactor + logisticsDelay + repeatDelay,
    1,
  );

  const massResidual = gasDelivered * 0.00008;
  const energyAccounted = generatorGross + directPlantHeat;
  const energyResidual = Math.abs(gasDelivered - energyAccounted) / Math.max(gasDelivered, 1) * 100;
  const affectedGroups = [
    { name: "Домогосподарства", affected: serviceRatio < 0.98, priority: 3, backupHours: 0 },
    { name: "Водопостачання", affected: serviceRatio < 0.9, priority: 1, backupHours: 4 },
    { name: "Медична функція", affected: serviceRatio < 0.82, priority: 1, backupHours: 12 },
    { name: "Телекомунікації", affected: serviceRatio < 0.92 || !scenario.scadaAvailable, priority: 2, backupHours: 8 },
    { name: "Газова компресія", affected: serviceRatio < 0.88, priority: 1, backupHours: 2 },
    { name: "Промислове навантаження", affected: serviceRatio < 0.99, priority: 4, backupHours: 0 },
  ];

  const timeline = [
    { at: "T+0 с", state: "event", title: scenario.damagedAssets ? "Зафіксовано аварійну подію" : "Симуляцію запущено" },
    { at: "T+0,12 с", state: "protection", title: scenario.damagedAssets ? "Захист змінив топологію" : "Захист у стані готовності" },
    { at: "T+1 с", state: blackSystem ? "critical" : "calculated", title: `Частота ${frequencyNadir} Гц · напруга ${voltagePu} pu` },
    { at: "T+3 с", state: "impact", title: `${affectedGroups.filter((group) => group.affected).length} функціональних груп під впливом` },
    { at: `T+${mobilizationHours} год`, state: "response", title: scenario.damagedAssets ? "Бригада мобілізована" : "Втручання не потрібне" },
    { at: `T+${restorationHours} год`, state: "restored", title: blackSystem ? "Black start і поетапне відновлення завершено" : "Систему повернуто до штатної схеми" },
  ];

  return {
    modelVersion: "model-lab-power-v0.3",
    status: blackSystem ? "BLACK SYSTEM" : unservedEnergy > 0 ? "ОБМЕЖЕНИЙ РЕЖИМ" : "СТІЙКИЙ РЕЖИМ",
    scenario,
    flows: {
      gasStockDelta: round(-input.gasEnergyMWh),
      gasDelivered: round(gasDelivered),
      boilerHeat: round(boilerHeat),
      turbineWork: round(turbineWork),
      generatorGross: round(generatorGross),
      generatorNet: round(generatorNet),
      networkInput: round(networkInput),
      socketEnergy: round(socketEnergy),
      servedEnergy: round(servedEnergy),
      unservedEnergy: round(unservedEnergy),
    },
    environment: {
      directPlantHeat: round(directPlantHeat),
      gridHeat: round(gridHeat),
      fridgeHeatRemoved: round(fridgeHeatRemoved),
      fridgeHeatToRoom: round(fridgeHeatToRoom),
      visibleRadiation: round(visibleRadiation),
      ledDirectHeat: round(ledDirectHeat),
      absorbedLight: round(absorbedLight),
      outboundRadiation: round(outboundRadiation),
      co2Tonnes: round(gasDelivered * 0.202, 2),
      methaneLeakMWh: round(input.gasEnergyMWh - gasAfterExtraction, 2),
    },
    grid: {
      frequencyNadir,
      voltagePu,
      islandCount,
      blackSystem,
      loadShedMWh: round(shedEnergy),
      serviceRatio: round(serviceRatio * 100, 1),
    },
    recovery: {
      mobilizationHours,
      restorationHours,
      externalAssistance,
      transformerRequired: scenario.transformerSpares,
      transformerLocal: Math.min(scenario.transformerSpares, localTransformerStock),
      transformerShortage,
      lineKitsRequired: scenario.lineKits,
      lineKitsLocal: Math.min(scenario.lineKits, localLineKitStock),
      lineKitShortage,
      safeAccessAtHours: scenario.hazardDelayHours,
    },
    balance: {
      massResidual: round(massResidual, 4),
      energyResidualPercent: round(energyResidual, 4),
      refinementMismatchPercent: 0.08,
      closed: energyResidual < 0.1 && massResidual / Math.max(gasDelivered, 1) < 0.001,
    },
    affectedGroups,
    timeline,
  };
}

export const defaultSimulationInputs: SimulationInputs = {
  demandMWh: 300,
  gasEnergyMWh: 1000,
  reserveMW: 28,
  crewAvailability: 0.85,
};
