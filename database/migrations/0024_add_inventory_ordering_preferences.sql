CREATE TABLE IF NOT EXISTS inventory_ordering_preference (
    inventory_ordering_preference_id INTEGER PRIMARY KEY AUTOINCREMENT,

    user_id TEXT NOT NULL,
    item_category TEXT NOT NULL,
    vendor_name TEXT NOT NULL,
    ordering_frequency TEXT NOT NULL DEFAULT 'weekly',
    delivery_days_json TEXT NOT NULL,
    cutoff_day TEXT NOT NULL,
    cutoff_time TEXT NOT NULL,
    preferred_lead_days INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    CHECK (trim(user_id) != ''),
    CHECK (item_category IN ('meat', 'grocery', 'frozen', 'beverages', 'dairy', 'bakery', 'produce')),
    CHECK (trim(vendor_name) != ''),
    CHECK (ordering_frequency IN ('weekly', 'twice_weekly', 'custom')),
    CHECK (json_valid(delivery_days_json)),
    CHECK (cutoff_day IN ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')),
    CHECK (cutoff_time GLOB '[0-2][0-9]:[0-5][0-9]'),
    CHECK (preferred_lead_days >= 0 AND preferred_lead_days <= 14),
    CHECK (status IN ('active', 'inactive')),
    UNIQUE (user_id, item_category)
);

CREATE INDEX IF NOT EXISTS idx_inventory_ordering_preference_user
ON inventory_ordering_preference(user_id);

CREATE INDEX IF NOT EXISTS idx_inventory_ordering_preference_category
ON inventory_ordering_preference(item_category);
