ALTER TABLE item ADD COLUMN nutrition_group TEXT;

ALTER TABLE item ADD COLUMN kcal_per_serving REAL;

ALTER TABLE item ADD COLUMN nutrition_serving_mass_quantity REAL;

ALTER TABLE item ADD COLUMN nutrition_serving_mass_unit TEXT;

ALTER TABLE item ADD COLUMN nutrition_serving_volume_quantity REAL;

ALTER TABLE item ADD COLUMN nutrition_serving_volume_unit TEXT;
