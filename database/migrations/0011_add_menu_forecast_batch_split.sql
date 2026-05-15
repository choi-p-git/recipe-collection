CREATE TABLE IF NOT EXISTS menu_forecast_batch_split (
    menu_forecast_batch_split_id INTEGER PRIMARY KEY AUTOINCREMENT,

    menu_slot_item_id INTEGER NOT NULL,
    batch_sequence INTEGER NOT NULL,
    batch_percent REAL NOT NULL,
    planned_time TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (menu_slot_item_id) REFERENCES menu_slot_item(menu_slot_item_id) ON DELETE CASCADE,

    CHECK (batch_sequence >= 1),
    CHECK (batch_percent > 0),
    CHECK (batch_percent <= 100),
    CHECK (
        planned_time IS NULL
        OR trim(planned_time) != ''
    ),

    UNIQUE (menu_slot_item_id, batch_sequence)
);

CREATE INDEX IF NOT EXISTS idx_menu_forecast_batch_split_slot_item_id
ON menu_forecast_batch_split(menu_slot_item_id);
