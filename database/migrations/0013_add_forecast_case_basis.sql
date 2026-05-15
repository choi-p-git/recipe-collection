ALTER TABLE menu_forecast
ADD COLUMN case_basis_component_item_id INTEGER REFERENCES item(item_id);

ALTER TABLE menu_forecast
ADD COLUMN case_basis_component_name TEXT;

ALTER TABLE menu_forecast
ADD COLUMN case_basis_view_mode TEXT;
