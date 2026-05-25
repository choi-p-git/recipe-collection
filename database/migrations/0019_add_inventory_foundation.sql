CREATE TABLE IF NOT EXISTS inventory_location (
    inventory_location_id INTEGER PRIMARY KEY AUTOINCREMENT,

    location_name TEXT NOT NULL COLLATE NOCASE,
    status TEXT NOT NULL DEFAULT 'active',
    created_by_user_id TEXT NOT NULL,
    created_by_display_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    CHECK (trim(location_name) != ''),
    CHECK (status IN ('active', 'inactive'))
);

CREATE INDEX IF NOT EXISTS idx_inventory_location_status
ON inventory_location(status);
