CREATE TABLE `circuit_runs` (
	`id` text PRIMARY KEY NOT NULL,
	`scenario_id` text NOT NULL,
	`model_version` text NOT NULL,
	`target_quantity` real NOT NULL,
	`delivered_quantity` real NOT NULL,
	`lower_quantity` real NOT NULL,
	`upper_quantity` real NOT NULL,
	`unit` text NOT NULL,
	`bottleneck` text NOT NULL,
	`confidence` real NOT NULL,
	`expected_hours` real NOT NULL,
	`conservation_error` real NOT NULL,
	`run_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `interventions` (
	`id` text PRIMARY KEY NOT NULL,
	`circuit_run_id` text NOT NULL,
	`action` text NOT NULL,
	`target_entity_id` text NOT NULL,
	`lead_time_hours` real NOT NULL,
	`recovered_quantity` real NOT NULL,
	`unit` text NOT NULL,
	`status` text NOT NULL,
	`rationale` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `inventory_lots` (
	`id` text PRIMARY KEY NOT NULL,
	`entity_id` text NOT NULL,
	`container_entity_id` text NOT NULL,
	`owner_entity_id` text NOT NULL,
	`quantity` real NOT NULL,
	`unit` text NOT NULL,
	`quality_status` text NOT NULL,
	`observed_at` text NOT NULL,
	`source_id` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `process_flows` (
	`id` text PRIMARY KEY NOT NULL,
	`process_id` text NOT NULL,
	`entity_id` text NOT NULL,
	`direction` text NOT NULL,
	`role` text NOT NULL,
	`amount_per_unit` real NOT NULL,
	`unit` text NOT NULL,
	`uncertainty` real DEFAULT 0 NOT NULL
);
--> statement-breakpoint
CREATE TABLE `process_models` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`action` text NOT NULL,
	`owner_entity_id` text NOT NULL,
	`model_version` text NOT NULL,
	`duration_hours` real NOT NULL,
	`yield_factor` real NOT NULL,
	`valid_from` text NOT NULL,
	`source_id` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `transport_routes` (
	`id` text PRIMARY KEY NOT NULL,
	`origin_entity_id` text NOT NULL,
	`destination_entity_id` text NOT NULL,
	`mode` text NOT NULL,
	`distance_km` real NOT NULL,
	`capacity_per_day` real NOT NULL,
	`capacity_unit` text NOT NULL,
	`duration_hours` real NOT NULL,
	`availability` real NOT NULL,
	`loss_factor` real NOT NULL,
	`recovery_hours` real NOT NULL
);
