CREATE TABLE IF NOT EXISTS item_event (
    item_event_id INTEGER PRIMARY KEY AUTOINCREMENT,

    item_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    actor_user_id TEXT NOT NULL,
    actor_display_name TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    event_summary TEXT NOT NULL,
    action_code TEXT,
    from_status TEXT,
    to_status TEXT,
    reason_text TEXT,
    created_at TEXT NOT NULL,

    FOREIGN KEY (item_id) REFERENCES item(item_id) ON DELETE CASCADE,

    CHECK (trim(event_type) != ''),
    CHECK (trim(event_summary) != '')
);

CREATE INDEX IF NOT EXISTS idx_item_event_item
ON item_event(item_id);

CREATE INDEX IF NOT EXISTS idx_item_event_type
ON item_event(event_type);
