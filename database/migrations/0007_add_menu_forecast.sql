CREATE TABLE IF NOT EXISTS menu_forecast (
    menu_forecast_id INTEGER PRIMARY KEY AUTOINCREMENT,

    menu_slot_item_id INTEGER NOT NULL UNIQUE,
    forecast_yield_quantity REAL NOT NULL DEFAULT 0,
    forecast_yield_unit TEXT NOT NULL,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (menu_slot_item_id) REFERENCES menu_slot_item(menu_slot_item_id) ON DELETE CASCADE,

    CHECK (forecast_yield_quantity >= 0),
    CHECK (trim(forecast_yield_unit) != '')
);

CREATE INDEX IF NOT EXISTS idx_menu_forecast_slot_item_id
ON menu_forecast(menu_slot_item_id);
