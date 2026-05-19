ALTER TABLE production_record_line
ADD COLUMN end_service_variance_quantity REAL;

ALTER TABLE production_record_line
ADD COLUMN end_service_variance_unit TEXT;

ALTER TABLE production_record_line
ADD COLUMN implied_demand_quantity REAL;

ALTER TABLE production_record_line
ADD COLUMN implied_demand_unit TEXT;

ALTER TABLE production_record_line
ADD COLUMN forecast_error_quantity REAL;

ALTER TABLE production_record_line
ADD COLUMN forecast_error_unit TEXT;

ALTER TABLE production_record_line
ADD COLUMN forecast_error_percent REAL;

ALTER TABLE production_record_line
ADD COLUMN forecast_accuracy_level TEXT;

ALTER TABLE production_record_line
ADD COLUMN reason_code TEXT;

ALTER TABLE production_record_line
ADD COLUMN reason_note TEXT;
