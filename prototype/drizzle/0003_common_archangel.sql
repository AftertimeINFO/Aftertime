CREATE TABLE `lab_components` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`category` text NOT NULL,
	`level` text NOT NULL,
	`parent_id` text,
	`input_port` text NOT NULL,
	`output_port` text NOT NULL,
	`nominal_value` real,
	`unit` text,
	`repairable` integer DEFAULT 1 NOT NULL,
	`model_version` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_lab_components_parent` ON `lab_components` (`parent_id`);--> statement-breakpoint
CREATE TABLE `lab_connections` (
	`id` text PRIMARY KEY NOT NULL,
	`source_id` text NOT NULL,
	`target_id` text NOT NULL,
	`flow_type` text NOT NULL,
	`efficiency` real NOT NULL,
	`sequence_no` integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE `lab_crew_pools` (
	`id` text PRIMARY KEY NOT NULL,
	`crew_type` text NOT NULL,
	`available` integer NOT NULL,
	`qualifications` text NOT NULL,
	`mobilization_hours` real NOT NULL,
	`shift_hours` real NOT NULL,
	`external_pool` integer DEFAULT 0 NOT NULL
);
--> statement-breakpoint
CREATE TABLE `lab_inventory_pools` (
	`id` text PRIMARY KEY NOT NULL,
	`part_class` text NOT NULL,
	`available` integer NOT NULL,
	`reserved` integer DEFAULT 0 NOT NULL,
	`repairable` integer DEFAULT 0 NOT NULL,
	`external_available` integer DEFAULT 0 NOT NULL,
	`lead_time_hours` real NOT NULL
);
--> statement-breakpoint
CREATE TABLE `lab_scenarios` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`category` text NOT NULL,
	`severity` text NOT NULL,
	`description` text NOT NULL,
	`generation_loss` real DEFAULT 0 NOT NULL,
	`transfer_loss` real DEFAULT 0 NOT NULL,
	`gas_loss` real DEFAULT 0 NOT NULL,
	`voltage_stress` real DEFAULT 0 NOT NULL,
	`scada_available` integer DEFAULT 1 NOT NULL,
	`system_separation` integer DEFAULT 0 NOT NULL,
	`black_start_required` integer DEFAULT 0 NOT NULL,
	`damaged_assets` integer DEFAULT 0 NOT NULL,
	`hazard_delay_hours` real DEFAULT 0 NOT NULL,
	`repair_hours` real DEFAULT 0 NOT NULL,
	`transformer_spares` integer DEFAULT 0 NOT NULL,
	`line_kits` integer DEFAULT 0 NOT NULL,
	`repeat_damage` integer DEFAULT 0 NOT NULL,
	`source_name` text NOT NULL,
	`source_url` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_lab_scenarios_category` ON `lab_scenarios` (`category`);