import { index, real, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const entities = sqliteTable("entities", {
  id: text("id").primaryKey(),
  kind: text("kind").notNull(),
  level: text("level").notNull(),
  name: text("name").notNull(),
  symbol: text("symbol"),
  description: text("description"),
  jurisdiction: text("jurisdiction"),
  validFrom: text("valid_from"),
  validTo: text("valid_to"),
});

export const relations = sqliteTable("relations", {
  id: text("id").primaryKey(),
  subjectId: text("subject_id").notNull(),
  predicate: text("predicate").notNull(),
  objectId: text("object_id").notNull(),
  coefficient: real("coefficient"),
  unit: text("unit"),
  confidence: real("confidence").notNull().default(1),
  sourceId: text("source_id"),
  validFrom: text("valid_from"),
  validTo: text("valid_to"),
}, (table) => [
  index("relations_subject_idx").on(table.subjectId),
  index("relations_object_idx").on(table.objectId),
]);

export const sources = sqliteTable("sources", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  url: text("url").notNull(),
  license: text("license"),
  retrievedAt: text("retrieved_at").notNull(),
});

export const externalIdentities = sqliteTable("external_identities", {
  id: text("id").primaryKey(),
  entityId: text("entity_id").notNull(),
  namespace: text("namespace").notNull(),
  externalId: text("external_id").notNull(),
  sourceId: text("source_id").notNull(),
  mappingType: text("mapping_type").notNull().default("exact_match"),
  confidence: real("confidence").notNull().default(1),
});

export const facilities = sqliteTable("facilities", {
  entityId: text("entity_id").primaryKey(),
  facilityType: text("facility_type").notNull(),
  status: text("status").notNull(),
  latitude: real("latitude"),
  longitude: real("longitude"),
  nominalCapacity: real("nominal_capacity"),
  availableCapacity: real("available_capacity"),
  capacityUnit: text("capacity_unit"),
  availability: real("availability").notNull().default(1),
});

export const capabilities = sqliteTable("capabilities", {
  id: text("id").primaryKey(),
  ownerEntityId: text("owner_entity_id").notNull(),
  action: text("action").notNull(),
  outputEntityId: text("output_entity_id").notNull(),
  maxRate: real("max_rate").notNull(),
  availableRate: real("available_rate").notNull(),
  unit: text("unit").notNull(),
  confidence: real("confidence").notNull(),
  modelVersion: text("model_version").notNull(),
});

export const dependencies = sqliteTable("dependencies", {
  id: text("id").primaryKey(),
  capabilityId: text("capability_id").notNull(),
  dependencyEntityId: text("dependency_entity_id").notNull(),
  dependencyType: text("dependency_type").notNull(),
  requiredAmount: real("required_amount"),
  unit: text("unit"),
  currentAvailability: real("current_availability").notNull(),
  criticality: real("criticality").notNull(),
  recoveryDays: real("recovery_days"),
});

export const observations = sqliteTable("observations", {
  id: text("id").primaryKey(),
  subjectEntityId: text("subject_entity_id").notNull(),
  property: text("property").notNull(),
  value: real("value").notNull(),
  unit: text("unit").notNull(),
  realityClass: text("reality_class").notNull(),
  epistemicStatus: text("epistemic_status").notNull(),
  validTime: text("valid_time").notNull(),
  recordedTime: text("recorded_time").notNull(),
  sourceId: text("source_id").notNull(),
  uncertaintyLow: real("uncertainty_low"),
  uncertaintyHigh: real("uncertainty_high"),
});

export const events = sqliteTable("events", {
  id: text("id").primaryKey(),
  eventType: text("event_type").notNull(),
  name: text("name").notNull(),
  actuality: text("actuality").notNull(),
  status: text("status").notNull(),
  startedAt: text("started_at").notNull(),
  endedAt: text("ended_at"),
  locationEntityId: text("location_entity_id"),
  actorEntityId: text("actor_entity_id"),
  modelVersion: text("model_version"),
});

export const postings = sqliteTable("postings", {
  id: text("id").primaryKey(),
  eventId: text("event_id").notNull(),
  entityId: text("entity_id").notNull(),
  role: text("role").notNull(),
  direction: text("direction").notNull(),
  quantity: real("quantity").notNull(),
  unit: text("unit").notNull(),
  abstractionLevel: text("abstraction_level").notNull(),
  sourceId: text("source_id"),
});

export const scenarios = sqliteTable("scenarios", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  description: text("description").notNull(),
  horizon: text("horizon").notNull(),
  gasAvailability: real("gas_availability").notNull(),
  gridAvailability: real("grid_availability").notNull(),
  logisticsAvailability: real("logistics_availability").notNull(),
  workforceAvailability: real("workforce_availability").notNull(),
  demandGrowth: real("demand_growth").notNull(),
  probability: real("probability").notNull(),
  modelVersion: text("model_version").notNull(),
});

export const modelRuns = sqliteTable("model_runs", {
  id: text("id").primaryKey(),
  scenarioId: text("scenario_id").notNull(),
  runAt: text("run_at").notNull(),
  modelVersion: text("model_version").notNull(),
  expectedOutput: real("expected_output").notNull(),
  lowOutput: real("low_output").notNull(),
  highOutput: real("high_output").notNull(),
  unit: text("unit").notNull(),
  confidence: real("confidence").notNull(),
  limitingFactor: text("limiting_factor").notNull(),
});

export const processModels = sqliteTable("process_models", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  action: text("action").notNull(),
  ownerEntityId: text("owner_entity_id").notNull(),
  modelVersion: text("model_version").notNull(),
  durationHours: real("duration_hours").notNull(),
  yieldFactor: real("yield_factor").notNull(),
  validFrom: text("valid_from").notNull(),
  sourceId: text("source_id").notNull(),
});

export const processFlows = sqliteTable("process_flows", {
  id: text("id").primaryKey(),
  processId: text("process_id").notNull(),
  entityId: text("entity_id").notNull(),
  direction: text("direction").notNull(),
  role: text("role").notNull(),
  amountPerUnit: real("amount_per_unit").notNull(),
  unit: text("unit").notNull(),
  uncertainty: real("uncertainty").notNull().default(0),
});

export const inventoryLots = sqliteTable("inventory_lots", {
  id: text("id").primaryKey(),
  entityId: text("entity_id").notNull(),
  containerEntityId: text("container_entity_id").notNull(),
  ownerEntityId: text("owner_entity_id").notNull(),
  quantity: real("quantity").notNull(),
  unit: text("unit").notNull(),
  qualityStatus: text("quality_status").notNull(),
  observedAt: text("observed_at").notNull(),
  sourceId: text("source_id").notNull(),
});

export const transportRoutes = sqliteTable("transport_routes", {
  id: text("id").primaryKey(),
  originEntityId: text("origin_entity_id").notNull(),
  destinationEntityId: text("destination_entity_id").notNull(),
  mode: text("mode").notNull(),
  distanceKm: real("distance_km").notNull(),
  capacityPerDay: real("capacity_per_day").notNull(),
  capacityUnit: text("capacity_unit").notNull(),
  durationHours: real("duration_hours").notNull(),
  availability: real("availability").notNull(),
  lossFactor: real("loss_factor").notNull(),
  recoveryHours: real("recovery_hours").notNull(),
});

export const circuitRuns = sqliteTable("circuit_runs", {
  id: text("id").primaryKey(),
  scenarioId: text("scenario_id").notNull(),
  modelVersion: text("model_version").notNull(),
  targetQuantity: real("target_quantity").notNull(),
  deliveredQuantity: real("delivered_quantity").notNull(),
  lowerQuantity: real("lower_quantity").notNull(),
  upperQuantity: real("upper_quantity").notNull(),
  unit: text("unit").notNull(),
  bottleneck: text("bottleneck").notNull(),
  confidence: real("confidence").notNull(),
  expectedHours: real("expected_hours").notNull(),
  conservationError: real("conservation_error").notNull(),
  runAt: text("run_at").notNull(),
});

export const interventions = sqliteTable("interventions", {
  id: text("id").primaryKey(),
  circuitRunId: text("circuit_run_id").notNull(),
  action: text("action").notNull(),
  targetEntityId: text("target_entity_id").notNull(),
  leadTimeHours: real("lead_time_hours").notNull(),
  recoveredQuantity: real("recovered_quantity").notNull(),
  unit: text("unit").notNull(),
  status: text("status").notNull(),
  rationale: text("rationale").notNull(),
});
