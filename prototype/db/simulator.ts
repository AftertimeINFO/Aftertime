export type CircuitInputs = {
  targetDeliveredKg: number;
  gasAvailability: number;
  gridAvailability: number;
  logisticsAvailability: number;
  workforceAvailability: number;
  storageLoss: number;
  transitLoss: number;
  processYield: number;
};

export type CircuitResult = ReturnType<typeof simulateAmmoniaCircuit>;

const clamp = (value: number, low = 0, high = 1) => Math.max(low, Math.min(high, value));
const round = (value: number, digits = 3) => Number(value.toFixed(digits));

export function simulateAmmoniaCircuit(input: CircuitInputs) {
  const availability = {
    gas: clamp(input.gasAvailability),
    grid: clamp(input.gridAvailability),
    logistics: clamp(input.logisticsAvailability),
    workforce: clamp(input.workforceAvailability),
  };
  const limitingEntry = Object.entries(availability).sort((a, b) => a[1] - b[1])[0];
  const bottleneck = limitingEntry[0] as keyof typeof availability;
  const bottleneckAvailability = limitingEntry[1];

  const targetDeliveredKg = Math.max(0, input.targetDeliveredKg);
  const requiredAtStorageExit = targetDeliveredKg / (1 - clamp(input.transitLoss, 0, 0.2));
  const requiredGrossAmmoniaKg =
    requiredAtStorageExit /
    (1 - clamp(input.storageLoss, 0, 0.2)) /
    clamp(input.processYield, 0.5, 1);

  // N₂ + 3H₂ → 2NH₃: 28 kg N₂ + 6 kg H₂ → 34 kg NH₃.
  const producedAmmoniaKg = requiredGrossAmmoniaKg * input.processYield;
  const nitrogenKg = producedAmmoniaKg * (28 / 34);
  const hydrogenKg = producedAmmoniaKg * (6 / 34);
  const naturalGasGJ = requiredGrossAmmoniaKg * (28 / 1000);
  const electricityMWh = requiredGrossAmmoniaKg * (0.7 / 1000);
  const waterKg = requiredGrossAmmoniaKg * 1.58;
  const theoreticalDeliveredKg = requiredGrossAmmoniaKg * input.processYield *
    (1 - input.storageLoss) * (1 - input.transitLoss);
  const achievableDeliveredKg = theoreticalDeliveredKg * bottleneckAvailability;

  const nitrogenInKg = nitrogenKg * bottleneckAvailability;
  const hydrogenInKg = hydrogenKg * bottleneckAvailability;
  // Storage and transit losses remain matter inside the wider circuit boundary.
  const nitrogenInProductKg = producedAmmoniaKg * bottleneckAvailability * (14 / 17);
  const hydrogenInProductKg = producedAmmoniaKg * bottleneckAvailability * (3 / 17);
  const atomBalanceErrorKg =
    Math.abs(nitrogenInKg - nitrogenInProductKg) +
    Math.abs(hydrogenInKg - hydrogenInProductKg);

  const baseDurationHours = 18;
  const delayHours = round(baseDurationHours * (1 / Math.max(bottleneckAvailability, 0.05) - 1), 1);
  const expectedHours = round(baseDurationHours + delayHours, 1);
  const confidence = clamp(0.9 - (1 - bottleneckAvailability) * 0.35 - 0.06);
  const uncertainty = 0.035 + (1 - confidence) * 0.18;

  const actions = {
    gas: {
      action: "Подключить резерв газа на смену",
      effect: "Восстановить подачу сырья и энергии до 92%",
      leadTimeHours: 8,
      newAvailability: 0.92,
    },
    grid: {
      action: "Перевести критические нагрузки на резервное питание",
      effect: "Поднять доступность электроснабжения до 95%",
      leadTimeHours: 2,
      newAvailability: 0.95,
    },
    logistics: {
      action: "Перенаправить партию через автомобильный терминал",
      effect: "Поднять доступность доставки до 86%",
      leadTimeHours: 12,
      newAvailability: 0.86,
    },
    workforce: {
      action: "Вызвать резервную квалифицированную смену",
      effect: "Восстановить кадровую доступность до 96%",
      leadTimeHours: 6,
      newAvailability: 0.96,
    },
  } as const;
  const recommendation = actions[bottleneck];
  const compensatedAvailability = Math.min(
    ...Object.entries(availability).map(([key, value]) =>
      key === bottleneck ? recommendation.newAvailability : value),
  );
  const compensatedDeliveredKg = theoreticalDeliveredKg * compensatedAvailability;

  return {
    modelVersion: "ammonia-circuit-v0.2",
    targetDeliveredKg: round(targetDeliveredKg),
    achievableDeliveredKg: round(achievableDeliveredKg),
    shortfallKg: round(Math.max(0, targetDeliveredKg - achievableDeliveredKg)),
    lowerKg: round(achievableDeliveredKg * (1 - uncertainty)),
    upperKg: round(Math.min(targetDeliveredKg, achievableDeliveredKg * (1 + uncertainty))),
    confidence: round(confidence),
    bottleneck,
    bottleneckAvailability: round(bottleneckAvailability),
    expectedHours,
    delayHours,
    inputs: {
      nitrogenKg: round(nitrogenKg * bottleneckAvailability),
      hydrogenKg: round(hydrogenKg * bottleneckAvailability),
      naturalGasGJ: round(naturalGasGJ * bottleneckAvailability),
      electricityMWh: round(electricityMWh * bottleneckAvailability),
      waterKg: round(waterKg * bottleneckAvailability),
    },
    outputs: {
      grossAmmoniaKg: round(requiredGrossAmmoniaKg * input.processYield * bottleneckAvailability),
      storageLossKg: round(requiredGrossAmmoniaKg * input.processYield * input.storageLoss * bottleneckAvailability),
      transitLossKg: round(requiredAtStorageExit * input.transitLoss * bottleneckAvailability),
      deliveredKg: round(achievableDeliveredKg),
    },
    conservation: {
      nitrogenInKg: round(nitrogenInKg),
      nitrogenOutKg: round(nitrogenInProductKg),
      hydrogenInKg: round(hydrogenInKg),
      hydrogenOutKg: round(hydrogenInProductKg),
      errorKg: round(atomBalanceErrorKg, 6),
      closed: atomBalanceErrorKg < 0.001,
    },
    recommendation: {
      ...recommendation,
      compensatedDeliveredKg: round(compensatedDeliveredKg),
      recoveredKg: round(compensatedDeliveredKg - achievableDeliveredKg),
    },
  };
}

export const baseCircuitInputs: CircuitInputs = {
  targetDeliveredKg: 1000,
  gasAvailability: 0.92,
  gridAvailability: 0.95,
  logisticsAvailability: 0.9,
  workforceAvailability: 0.96,
  storageLoss: 0.002,
  transitLoss: 0.001,
  processYield: 0.985,
};
