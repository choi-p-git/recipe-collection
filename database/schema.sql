CREATE TABLE IF NOT EXISTS item (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,

    item_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    item_type TEXT NOT NULL,

    author_user_id TEXT NOT NULL,
    author_display_name TEXT NOT NULL,

    yield_quantity REAL,
    yield_unit TEXT,

    mass_quantity REAL,
    mass_unit TEXT,
    volume_quantity REAL,
    volume_unit TEXT,
    nutrition_group TEXT,
    kcal_per_serving REAL,
    nutrition_serving_mass_quantity REAL,
    nutrition_serving_mass_unit TEXT,
    nutrition_serving_volume_quantity REAL,
    nutrition_serving_volume_unit TEXT,

    serving_size_quantity REAL,
    serving_size_unit TEXT,
    serving_count REAL,

    instructions_text TEXT,
    primary_cooking_method_code TEXT,

    status TEXT NOT NULL,
    requires_resubmission INTEGER NOT NULL DEFAULT 0,

    notes TEXT,
    concept_classification TEXT,
    meal_classification TEXT,
    haccp_process_classification TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    CHECK (item_type IN ('base_food', 'recipe')),

    CHECK (status IN ('submitted', 'reviewed', 'approved', 'analyzed', 'live', 'rejected')),

    CHECK (requires_resubmission IN (0, 1)),

    CHECK (
        (item_type = 'recipe' AND instructions_text IS NOT NULL AND primary_cooking_method_code IS NOT NULL)
        OR
        (item_type = 'base_food')
    ),

    CHECK (
        (
            item_type = 'recipe'
            AND yield_quantity IS NOT NULL
            AND yield_quantity > 0
            AND yield_unit IS NOT NULL
            AND trim(yield_unit) != ''
        )
        OR
        (
            item_type = 'base_food'
        )
    ),

    CHECK (
        mass_quantity IS NULL OR mass_quantity > 0
    ),

    CHECK (
        volume_quantity IS NULL OR volume_quantity > 0
    ),

    CHECK (
        kcal_per_serving IS NULL OR kcal_per_serving >= 0
    ),

    CHECK (
        nutrition_serving_mass_quantity IS NULL OR nutrition_serving_mass_quantity > 0
    ),

    CHECK (
        nutrition_serving_volume_quantity IS NULL OR nutrition_serving_volume_quantity > 0
    ),

    CHECK (
        serving_size_quantity IS NULL OR serving_size_quantity > 0
    ),

    CHECK (
        serving_count IS NULL OR serving_count > 0
    )
);

CREATE TABLE IF NOT EXISTS recipe_component (
    recipe_component_id INTEGER PRIMARY KEY AUTOINCREMENT,

    parent_recipe_item_id INTEGER NOT NULL,
    component_item_id INTEGER NOT NULL,

    component_quantity REAL NOT NULL CHECK (component_quantity > 0),
    component_unit TEXT NOT NULL,

    component_sequence INTEGER,
    component_notes TEXT,

    FOREIGN KEY (parent_recipe_item_id) REFERENCES item(item_id) ON DELETE CASCADE,
    FOREIGN KEY (component_item_id) REFERENCES item(item_id),

    CHECK (parent_recipe_item_id != component_item_id)
);

CREATE TABLE IF NOT EXISTS item_note (
    item_note_id INTEGER PRIMARY KEY AUTOINCREMENT,

    item_id INTEGER NOT NULL,
    author_user_id TEXT NOT NULL,
    author_display_name TEXT NOT NULL,
    author_role TEXT NOT NULL,
    note_text TEXT NOT NULL,
    recipient_user_id TEXT,
    recipient_role TEXT,
    is_acknowledged INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,

    FOREIGN KEY (item_id) REFERENCES item(item_id) ON DELETE CASCADE,

    CHECK (trim(note_text) != ''),
    CHECK (recipient_user_id IS NOT NULL OR recipient_role IS NOT NULL),
    CHECK (is_acknowledged IN (0, 1))
);

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

CREATE TABLE IF NOT EXISTS menu_forecast (
    menu_forecast_id INTEGER PRIMARY KEY AUTOINCREMENT,

    menu_slot_item_id INTEGER NOT NULL UNIQUE,
    forecast_yield_quantity REAL NOT NULL DEFAULT 0,
    forecast_yield_unit TEXT NOT NULL,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (menu_slot_item_id) REFERENCES menu_slot_item(menu_slot_item_id) ON DELETE CASCADE,

    CHECK (forecast_yield_quantity >= 0),
    CHECK (trim(forecast_yield_unit) != '')
);

CREATE INDEX IF NOT EXISTS idx_item_type
ON item(item_type);

CREATE INDEX IF NOT EXISTS idx_item_status
ON item(status);

CREATE INDEX IF NOT EXISTS idx_item_author_user_id
ON item(author_user_id);

CREATE INDEX IF NOT EXISTS idx_item_primary_cooking_method_code
ON item(primary_cooking_method_code);

CREATE INDEX IF NOT EXISTS idx_recipe_component_parent
ON recipe_component(parent_recipe_item_id);

CREATE INDEX IF NOT EXISTS idx_recipe_component_component
ON recipe_component(component_item_id);

CREATE INDEX IF NOT EXISTS idx_item_note_item
ON item_note(item_id);

CREATE INDEX IF NOT EXISTS idx_item_note_recipient_user
ON item_note(recipient_user_id);

CREATE INDEX IF NOT EXISTS idx_item_note_recipient_role
ON item_note(recipient_role);

CREATE INDEX IF NOT EXISTS idx_item_event_item
ON item_event(item_id);

CREATE INDEX IF NOT EXISTS idx_item_event_type
ON item_event(event_type);

CREATE INDEX IF NOT EXISTS idx_item_notification_item
ON item_notification(item_id);

CREATE INDEX IF NOT EXISTS idx_item_notification_recipient_user
ON item_notification(recipient_user_id);

CREATE INDEX IF NOT EXISTS idx_item_notification_recipient_role
ON item_notification(recipient_role);

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

CREATE INDEX IF NOT EXISTS idx_menu_forecast_slot_item_id
ON menu_forecast(menu_slot_item_id);
