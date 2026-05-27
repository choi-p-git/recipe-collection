ALTER TABLE inventory_ordering_preference
RENAME TO inventory_ordering_preference_old;

CREATE TABLE inventory_ordering_preference (
    inventory_ordering_preference_id INTEGER PRIMARY KEY AUTOINCREMENT,

    user_id TEXT NOT NULL,
    item_category TEXT NOT NULL,
    vendor_name TEXT NOT NULL,
    ordering_frequency TEXT NOT NULL DEFAULT 'weekly',
    cutoff_rules_json TEXT NOT NULL,
    preferred_lead_days INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    CHECK (trim(user_id) != ''),
    CHECK (item_category IN ('meat', 'grocery', 'frozen', 'beverages', 'dairy', 'bakery', 'produce')),
    CHECK (trim(vendor_name) != ''),
    CHECK (ordering_frequency IN ('weekly', 'twice_weekly', 'custom')),
    CHECK (json_valid(cutoff_rules_json)),
    CHECK (preferred_lead_days >= 0 AND preferred_lead_days <= 14),
    CHECK (status IN ('active', 'inactive')),
    UNIQUE (user_id, item_category)
);

INSERT INTO inventory_ordering_preference (
    inventory_ordering_preference_id,
    user_id,
    item_category,
    vendor_name,
    ordering_frequency,
    cutoff_rules_json,
    preferred_lead_days,
    status,
    created_at,
    updated_at
)
SELECT
    old.inventory_ordering_preference_id,
    old.user_id,
    old.item_category,
    old.vendor_name,
    old.ordering_frequency,
    (
        SELECT json_group_array(
            json_object(
                'delivery_day', json_each.value,
                'cutoff_day', old.cutoff_day,
                'cutoff_time', old.cutoff_time
            )
        )
        FROM json_each(old.delivery_days_json)
    ),
    old.preferred_lead_days,
    old.status,
    old.created_at,
    old.updated_at
FROM inventory_ordering_preference_old old;

DROP TABLE inventory_ordering_preference_old;

CREATE INDEX IF NOT EXISTS idx_inventory_ordering_preference_user
ON inventory_ordering_preference(user_id);

CREATE INDEX IF NOT EXISTS idx_inventory_ordering_preference_category
ON inventory_ordering_preference(item_category);
