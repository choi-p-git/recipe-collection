PRAGMA foreign_keys = OFF;

CREATE TABLE inventory_location_new (
    inventory_location_id INTEGER PRIMARY KEY AUTOINCREMENT,

    parent_inventory_location_id INTEGER,
    location_name TEXT NOT NULL COLLATE NOCASE,
    status TEXT NOT NULL DEFAULT 'active',
    created_by_user_id TEXT NOT NULL,
    created_by_display_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    CHECK (trim(location_name) != ''),
    CHECK (status IN ('active', 'inactive'))
);

INSERT INTO inventory_location_new (
    inventory_location_id,
    parent_inventory_location_id,
    location_name,
    status,
    created_by_user_id,
    created_by_display_name,
    created_at,
    updated_at
)
SELECT
    inventory_location_id,
    parent_inventory_location_id,
    location_name,
    status,
    created_by_user_id,
    created_by_display_name,
    created_at,
    updated_at
FROM inventory_location;

DROP TABLE inventory_location;
ALTER TABLE inventory_location_new RENAME TO inventory_location;

CREATE TABLE inventory_location_item_new (
    inventory_location_item_id INTEGER PRIMARY KEY AUTOINCREMENT,

    inventory_location_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    quantity REAL NOT NULL DEFAULT 0,
    unit TEXT NOT NULL,
    count_each_quantity REAL NOT NULL DEFAULT 0,
    count_case_quantity REAL NOT NULL DEFAULT 0,
    pack_quantity REAL,
    pack_size_text TEXT,
    unit_of_measurement TEXT NOT NULL DEFAULT 'Case',
    count_type TEXT NOT NULL DEFAULT 'counted_by_each_only',
    display_sequence INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (inventory_location_id) REFERENCES inventory_location(inventory_location_id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES item(item_id),

    CHECK (quantity >= 0),
    CHECK (trim(unit) != ''),
    CHECK (count_each_quantity >= 0),
    CHECK (count_case_quantity >= 0),
    CHECK (pack_quantity IS NULL OR pack_quantity > 0),
    CHECK (pack_size_text IS NULL OR trim(pack_size_text) != ''),
    CHECK (unit_of_measurement IN ('Case', 'Each', 'Kg', 'Lb')),
    CHECK (count_type IN ('counted_by_each_only', 'counted_by_case_only', 'counted_by_each_and_case')),

    UNIQUE (inventory_location_id, item_id)
);

INSERT INTO inventory_location_item_new (
    inventory_location_item_id,
    inventory_location_id,
    item_id,
    quantity,
    unit,
    count_each_quantity,
    count_case_quantity,
    pack_quantity,
    pack_size_text,
    unit_of_measurement,
    count_type,
    display_sequence,
    created_at,
    updated_at
)
SELECT
    inventory_location_item_id,
    inventory_location_id,
    item_id,
    quantity,
    unit,
    quantity,
    0,
    pack_size_quantity,
    CASE
        WHEN pack_size_quantity IS NOT NULL AND pack_size_unit IS NOT NULL
        THEN printf('%g %s', pack_size_quantity, pack_size_unit)
        ELSE NULL
    END,
    CASE
        WHEN unit IN ('kg', 'g') THEN 'Kg'
        WHEN unit IN ('lb', 'oz') THEN 'Lb'
        WHEN unit = 'each' THEN 'Each'
        ELSE 'Case'
    END,
    'counted_by_each_only',
    inventory_location_item_id,
    created_at,
    updated_at
FROM inventory_location_item;

DROP TABLE inventory_location_item;
ALTER TABLE inventory_location_item_new RENAME TO inventory_location_item;

CREATE TABLE IF NOT EXISTS inventory_location_break (
    inventory_location_break_id INTEGER PRIMARY KEY AUTOINCREMENT,

    inventory_location_id INTEGER NOT NULL,
    break_label TEXT NOT NULL,
    display_sequence INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (inventory_location_id) REFERENCES inventory_location(inventory_location_id) ON DELETE CASCADE,

    CHECK (trim(break_label) != '')
);

PRAGMA foreign_keys = ON;

CREATE INDEX IF NOT EXISTS idx_inventory_location_status
ON inventory_location(status);

CREATE INDEX IF NOT EXISTS idx_inventory_location_parent
ON inventory_location(parent_inventory_location_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_location_root_name
ON inventory_location(location_name)
WHERE parent_inventory_location_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_location_parent_name
ON inventory_location(parent_inventory_location_id, location_name)
WHERE parent_inventory_location_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_inventory_location_item_location
ON inventory_location_item(inventory_location_id);

CREATE INDEX IF NOT EXISTS idx_inventory_location_item_item
ON inventory_location_item(item_id);

CREATE INDEX IF NOT EXISTS idx_inventory_location_item_sequence
ON inventory_location_item(inventory_location_id, display_sequence);

CREATE INDEX IF NOT EXISTS idx_inventory_location_break_location
ON inventory_location_break(inventory_location_id);
