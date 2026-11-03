CREATE TABLE `capabilities` (
	`id` text PRIMARY KEY NOT NULL,
	`owner_entity_id` text NOT NULL,
	`action` text NOT NULL,
	`output_entity_id` text NOT NULL,
	`max_rate` real NOT NULL,
	`available_rate` real NOT NULL,
	`unit` text NOT NULL,
	`confidence` real NOT NULL,
	`model_version` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `dependencies` (
	`id` text PRIMARY KEY NOT NULL,
	`capability_id` text NOT NULL,
	`dependency_entity_id` text NOT NULL,
	`dependency_type` text NOT NULL,
	`required_amount` real,
	`unit` text,
	`current_availability` real NOT NULL,
	`criticality` real NOT NULL,
	`recovery_days` real
);
--> statement-breakpoint
CREATE TABLE `entities` (
	`id` text PRIMARY KEY NOT NULL,
	`kind` text NOT NULL,
	`level` text NOT NULL,
	`name` text NOT NULL,
	`symbol` text,
	`description` text,
	`jurisdiction` text,
	`valid_from` text,
	`valid_to` text
);
--> statement-breakpoint
CREATE TABLE `events` (
	`id` text PRIMARY KEY NOT NULL,
	`event_type` text NOT NULL,
	`name` text NOT NULL,
	`actuality` text NOT NULL,
	`status` text NOT NULL,
	`started_at` text NOT NULL,
	`ended_at` text,
	`location_entity_id` text,
	`actor_entity_id` text,
	`model_version` text
);
--> statement-breakpoint
CREATE TABLE `external_identities` (
	`id` text PRIMARY KEY NOT NULL,
	`entity_id` text NOT NULL,
	`namespace` text NOT NULL,
	`external_id` text NOT NULL,
	`source_id` text NOT NULL,
	`mapping_type` text DEFAULT 'exact_match' NOT NULL,
	`confidence` real DEFAULT 1 NOT NULL
);
--> statement-breakpoint
CREATE TABLE `facilities` (
	`entity_id` text PRIMARY KEY NOT NULL,
	`facility_type` text NOT NULL,
	`status` text NOT NULL,
	`latitude` real,
	`longitude` real,
	`nominal_capacity` real,
	`available_capacity` real,
	`capacity_unit` text,
	`availability` real DEFAULT 1 NOT NULL
);
--> statement-breakpoint
CREATE TABLE `model_runs` (
	`id` text PRIMARY KEY NOT NULL,
	`scenario_id` text NOT NULL,
	`run_at` text NOT NULL,
	`model_version` text NOT NULL,
	`expected_output` real NOT NULL,
	`low_output` real NOT NULL,
	`high_output` real NOT NULL,
	`unit` text NOT NULL,
	`confidence` real NOT NULL,
	`limiting_factor` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `observations` (
	`id` text PRIMARY KEY NOT NULL,
	`subject_entity_id` text NOT NULL,
	`property` text NOT NULL,
	`value` real NOT NULL,
	`unit` text NOT NULL,
	`reality_class` text NOT NULL,
	`epistemic_status` text NOT NULL,
	`valid_time` text NOT NULL,
	`recorded_time` text NOT NULL,
	`source_id` text NOT NULL,
	`uncertainty_low` real,
	`uncertainty_high` real
);
--> statement-breakpoint
CREATE TABLE `postings` (
	`id` text PRIMARY KEY NOT NULL,
	`event_id` text NOT NULL,
	`entity_id` text NOT NULL,
	`role` text NOT NULL,
	`direction` text NOT NULL,
	`quantity` real NOT NULL,
	`unit` text NOT NULL,
	`abstraction_level` text NOT NULL,
	`source_id` text
);
--> statement-breakpoint
CREATE TABLE `relations` (
	`id` text PRIMARY KEY NOT NULL,
	`subject_id` text NOT NULL,
	`predicate` text NOT NULL,
	`object_id` text NOT NULL,
	`coefficient` real,
	`unit` text,
	`confidence` real DEFAULT 1 NOT NULL,
	`source_id` text,
	`valid_from` text,
	`valid_to` text
);
--> statement-breakpoint
CREATE INDEX `relations_subject_idx` ON `relations` (`subject_id`);--> statement-breakpoint
CREATE INDEX `relations_object_idx` ON `relations` (`object_id`);--> statement-breakpoint
CREATE TABLE `scenarios` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`description` text NOT NULL,
	`horizon` text NOT NULL,
	`gas_availability` real NOT NULL,
	`grid_availability` real NOT NULL,
	`logistics_availability` real NOT NULL,
	`workforce_availability` real NOT NULL,
	`demand_growth` real NOT NULL,
	`probability` real NOT NULL,
	`model_version` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `sources` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`url` text NOT NULL,
	`license` text,
	`retrieved_at` text NOT NULL
);
