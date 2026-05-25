PRAGMA foreign_keys = OFF;

CREATE TABLE IF NOT EXISTS inventory_catalog_item (
    inventory_catalog_item_id INTEGER PRIMARY KEY AUTOINCREMENT,

    display_name TEXT NOT NULL COLLATE NOCASE,
    vendor_name TEXT,
    vendor_item_code TEXT,
    purchase_uom TEXT,
    pack_quantity REAL,
    pack_size_text TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    CHECK (trim(display_name) != ''),
    CHECK (vendor_name IS NULL OR trim(vendor_name) != ''),
    CHECK (vendor_item_code IS NULL OR trim(vendor_item_code) != ''),
    CHECK (purchase_uom IS NULL OR trim(purchase_uom) != ''),
    CHECK (pack_quantity IS NULL OR pack_quantity > 0),
    CHECK (pack_size_text IS NULL OR trim(pack_size_text) != ''),
    CHECK (status IN ('active', 'review_needed', 'inactive'))
);

CREATE TABLE IF NOT EXISTS inventory_item_match (
    inventory_item_match_id INTEGER PRIMARY KEY AUTOINCREMENT,

    recipe_collection_item_id INTEGER NOT NULL,
    inventory_catalog_item_id INTEGER NOT NULL,
    match_type TEXT NOT NULL,
    confidence_score REAL NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (recipe_collection_item_id) REFERENCES item(item_id),
    FOREIGN KEY (inventory_catalog_item_id) REFERENCES inventory_catalog_item(inventory_catalog_item_id),

    CHECK (match_type IN ('manual', 'legacy_item', 'invoice_auto', 'name_match', 'vendor_code')),
    CHECK (confidence_score >= 0 AND confidence_score <= 1),
    CHECK (status IN ('active', 'review_needed', 'rejected', 'inactive'))
);

CREATE TABLE inventory_location_item_new (
    inventory_location_item_id INTEGER PRIMARY KEY AUTOINCREMENT,

    inventory_location_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    inventory_catalog_item_id INTEGER,
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
    FOREIGN KEY (inventory_catalog_item_id) REFERENCES inventory_catalog_item(inventory_catalog_item_id),

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
    inventory_catalog_item_id,
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
    NULL,
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
FROM inventory_location_item;

DROP TABLE inventory_location_item;
ALTER TABLE inventory_location_item_new RENAME TO inventory_location_item;

PRAGMA foreign_keys = ON;

CREATE INDEX IF NOT EXISTS idx_inventory_catalog_item_status
ON inventory_catalog_item(status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_catalog_item_vendor_code
ON inventory_catalog_item(vendor_name, vendor_item_code)
WHERE vendor_name IS NOT NULL
  AND vendor_item_code IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_inventory_item_match_recipe_item
ON inventory_item_match(recipe_collection_item_id);

CREATE INDEX IF NOT EXISTS idx_inventory_item_match_catalog_item
ON inventory_item_match(inventory_catalog_item_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_item_match_active_recipe_item
ON inventory_item_match(recipe_collection_item_id)
WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_inventory_location_item_location
ON inventory_location_item(inventory_location_id);

CREATE INDEX IF NOT EXISTS idx_inventory_location_item_item
ON inventory_location_item(item_id);

CREATE INDEX IF NOT EXISTS idx_inventory_location_item_catalog
ON inventory_location_item(inventory_catalog_item_id);

CREATE INDEX IF NOT EXISTS idx_inventory_location_item_sequence
ON inventory_location_item(inventory_location_id, display_sequence);
