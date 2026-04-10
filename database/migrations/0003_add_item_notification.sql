CREATE TABLE IF NOT EXISTS item_notification (
    item_notification_id INTEGER PRIMARY KEY AUTOINCREMENT,

    item_id INTEGER NOT NULL,
    notification_type TEXT NOT NULL,
    actor_user_id TEXT NOT NULL,
    actor_display_name TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    message_text TEXT NOT NULL,
    recipient_user_id TEXT,
    recipient_role TEXT,
    is_acknowledged INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,

    FOREIGN KEY (item_id) REFERENCES item(item_id) ON DELETE CASCADE,

    CHECK (trim(notification_type) != ''),
    CHECK (trim(message_text) != ''),
    CHECK (recipient_user_id IS NOT NULL OR recipient_role IS NOT NULL),
    CHECK (is_acknowledged IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_item_notification_item
ON item_notification(item_id);

CREATE INDEX IF NOT EXISTS idx_item_notification_recipient_user
ON item_notification(recipient_user_id);

CREATE INDEX IF NOT EXISTS idx_item_notification_recipient_role
ON item_notification(recipient_role);
