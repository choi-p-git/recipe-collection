CREATE TABLE IF NOT EXISTS menu (
    menu_id INTEGER PRIMARY KEY AUTOINCREMENT,

    menu_name TEXT NOT NULL,
    author_user_id TEXT NOT NULL,
    author_display_name TEXT NOT NULL,

    service_days_json TEXT NOT NULL,
    meal_periods_json TEXT NOT NULL,
    concepts_json TEXT NOT NULL,
    menu_length_weeks INTEGER NOT NULL,
    status TEXT NOT NULL,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    CHECK (trim(menu_name) != ''),
    CHECK (menu_length_weeks > 0),
    CHECK (status IN ('draft', 'active', 'archived'))
);

CREATE TABLE IF NOT EXISTS menu_slot (
    menu_slot_id INTEGER PRIMARY KEY AUTOINCREMENT,

    menu_id INTEGER NOT NULL,
    week_number INTEGER NOT NULL,
    day_of_week TEXT NOT NULL,
    meal_period TEXT NOT NULL,
    concept_name TEXT NOT NULL,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (menu_id) REFERENCES menu(menu_id) ON DELETE CASCADE,

    CHECK (week_number >= 1),
    CHECK (
        day_of_week IN (
            'sunday',
            'monday',
            'tuesday',
            'wednesday',
            'thursday',
            'friday',
            'saturday'
        )
    ),
    CHECK (meal_period IN ('breakfast', 'lunch', 'dinner')),
    CHECK (trim(concept_name) != ''),

    UNIQUE (menu_id, week_number, day_of_week, meal_period, concept_name)
);

CREATE TABLE IF NOT EXISTS menu_slot_item (
    menu_slot_item_id INTEGER PRIMARY KEY AUTOINCREMENT,

    menu_slot_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    item_sequence INTEGER NOT NULL,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (menu_slot_id) REFERENCES menu_slot(menu_slot_id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES item(item_id),

    CHECK (item_sequence >= 1),

    UNIQUE (menu_slot_id, item_sequence)
);

CREATE INDEX IF NOT EXISTS idx_menu_author_user_id
ON menu(author_user_id);

CREATE INDEX IF NOT EXISTS idx_menu_status
ON menu(status);

CREATE INDEX IF NOT EXISTS idx_menu_slot_menu_id
ON menu_slot(menu_id);

CREATE INDEX IF NOT EXISTS idx_menu_slot_grid
ON menu_slot(menu_id, week_number, day_of_week, meal_period);

CREATE INDEX IF NOT EXISTS idx_menu_slot_item_slot_id
ON menu_slot_item(menu_slot_id);

CREATE INDEX IF NOT EXISTS idx_menu_slot_item_item_id
ON menu_slot_item(item_id);
