ALTER TABLE production_record_line
ADD COLUMN actual_quantity_formula TEXT;

ALTER TABLE production_record_line
ADD COLUMN end_service_variance_quantity_formula TEXT;
