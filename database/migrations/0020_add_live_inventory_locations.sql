ALTER TABLE inventory_location
ADD COLUMN parent_inventory_location_id INTEGER;

CREATE TABLE IF NOT EXISTS inventory_location_item (
    inventory_location_item_id INTEGER PRIMARY KEY AUTOINCREMENT,

    inventory_location_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    quantity REAL NOT NULL DEFAULT 0,
    unit TEXT NOT NULL,
    pack_size_quantity REAL,
    pack_size_unit TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (inventory_location_id) REFERENCES inventory_location(inventory_location_id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES item(item_id),

    CHECK (quantity >= 0),
    CHECK (trim(unit) != ''),
    CHECK (pack_size_quantity IS NULL OR pack_size_quantity > 0),
    CHECK (pack_size_unit IS NULL OR trim(pack_size_unit) != ''),

    UNIQUE (inventory_location_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_inventory_location_parent
ON inventory_location(parent_inventory_location_id);

CREATE INDEX IF NOT EXISTS idx_inventory_location_item_location
ON inventory_location_item(inventory_location_id);

CREATE INDEX IF NOT EXISTS idx_inventory_location_item_item
ON inventory_location_item(item_id);
