CREATE TABLE `technologies` (
  `id` text PRIMARY KEY NOT NULL,
  `name` text NOT NULL,
  `category` text NOT NULL,
  `input_form` text NOT NULL,
  `output_form` text NOT NULL,
  `efficiency` real NOT NULL,
  `useful_effect` text NOT NULL,
  `waste_effect` text NOT NULL,
  `model_version` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `principle_systems` (
  `id` text PRIMARY KEY NOT NULL,
  `name` text NOT NULL,
  `system_type` text NOT NULL,
  `purpose` text NOT NULL,
  `input_form` text NOT NULL,
  `output_form` text NOT NULL,
  `model_version` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `end_products` (
  `id` text PRIMARY KEY NOT NULL,
  `name` text NOT NULL,
  `product_type` text NOT NULL,
  `rated_power_kw` real NOT NULL,
  `transformation` text NOT NULL,
  `useful_output` text NOT NULL,
  `waste_output` text NOT NULL,
  `coefficient` real NOT NULL
);
--> statement-breakpoint
CREATE TABLE `test_models` (
  `id` text PRIMARY KEY NOT NULL,
  `name` text NOT NULL,
  `description` text NOT NULL,
  `status` text NOT NULL,
  `duration_hours` real NOT NULL,
  `model_version` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `test_model_components` (
  `id` text PRIMARY KEY NOT NULL,
  `test_model_id` text NOT NULL,
  `component_kind` text NOT NULL,
  `component_id` text NOT NULL,
  `sequence_no` integer NOT NULL,
  `branch` text NOT NULL,
  `quantity` real NOT NULL
);
--> statement-breakpoint
CREATE TABLE `territorial_units` (
  `id` text PRIMARY KEY NOT NULL,
  `name` text NOT NULL,
  `unit_type` text NOT NULL,
  `country_code` text,
  `centroid_lat` real,
  `centroid_lon` real,
  `location_precision` text NOT NULL,
  `estimated_users` integer,
  `user_count_uncertainty` real,
  `epistemic_status` text NOT NULL,
  `source_id` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `real_systems` (
  `id` text PRIMARY KEY NOT NULL,
  `name` text NOT NULL,
  `system_type` text NOT NULL,
  `principle_system_id` text NOT NULL,
  `latitude` real,
  `longitude` real,
  `location_precision_m` real,
  `territory_id` text,
  `actuality` text NOT NULL,
  `status` text NOT NULL,
  `source_id` text NOT NULL
);
