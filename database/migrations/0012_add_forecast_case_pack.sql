CREATE TABLE IF NOT EXISTS item_case_pack (
    item_case_pack_id INTEGER PRIMARY KEY AUTOINCREMENT,

    item_id INTEGER NOT NULL,
    pack_quantity REAL NOT NULL,
    subunit_quantity REAL NOT NULL,
    subunit_unit TEXT NOT NULL,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (item_id) REFERENCES item(item_id) ON DELETE CASCADE,

    CHECK (pack_quantity > 0),
    CHECK (subunit_quantity > 0),
    CHECK (trim(subunit_unit) != '')
);

CREATE INDEX IF NOT EXISTS idx_item_case_pack_item_id
ON item_case_pack(item_id);

ALTER TABLE menu_forecast
ADD COLUMN forecast_display_unit TEXT;

ALTER TABLE menu_forecast
ADD COLUMN case_quantity REAL;

ALTER TABLE menu_forecast
ADD COLUMN case_pack_quantity REAL;

ALTER TABLE menu_forecast
ADD COLUMN case_subunit_quantity REAL;

ALTER TABLE menu_forecast
ADD COLUMN case_subunit_unit TEXT;

ALTER TABLE menu_forecast
ADD COLUMN calculated_forecast_quantity REAL;

ALTER TABLE menu_forecast
ADD COLUMN calculated_forecast_unit TEXT;

ALTER TABLE menu_forecast
ADD COLUMN item_case_pack_id INTEGER REFERENCES item_case_pack(item_case_pack_id);

UPDATE menu_forecast
SET forecast_display_unit = forecast_yield_unit,
    calculated_forecast_quantity = forecast_yield_quantity,
    calculated_forecast_unit = forecast_yield_unit
WHERE forecast_display_unit IS NULL;
