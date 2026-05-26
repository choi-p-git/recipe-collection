CREATE TABLE IF NOT EXISTS item (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,

    item_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    item_type TEXT NOT NULL,
    item_category TEXT NOT NULL DEFAULT 'grocery',

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

    CHECK (item_category IN ('meat', 'grocery', 'frozen', 'beverages', 'dairy', 'bakery', 'produce')),

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
    menu_start_date TEXT,
    menu_end_date TEXT,
    status TEXT NOT NULL,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    CHECK (trim(menu_name) != ''),
    CHECK (menu_length_weeks > 0),
    CHECK (menu_start_date IS NULL OR date(menu_start_date) IS NOT NULL),
    CHECK (menu_end_date IS NULL OR date(menu_end_date) IS NOT NULL),
    CHECK (menu_start_date IS NULL OR menu_end_date IS NULL OR date(menu_end_date) >= date(menu_start_date)),
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
    user_serving_size_quantity REAL,
    user_serving_size_unit TEXT,
    desired_portions REAL,
    forecast_display_unit TEXT,
    case_quantity REAL,
    case_pack_quantity REAL,
    case_subunit_quantity REAL,
    case_subunit_unit TEXT,
    calculated_forecast_quantity REAL,
    calculated_forecast_unit TEXT,
    item_case_pack_id INTEGER,
    case_basis_component_item_id INTEGER,
    case_basis_component_name TEXT,
    case_basis_view_mode TEXT,
    case_basis_row_key TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (menu_slot_item_id) REFERENCES menu_slot_item(menu_slot_item_id) ON DELETE CASCADE,
    FOREIGN KEY (item_case_pack_id) REFERENCES item_case_pack(item_case_pack_id),
    FOREIGN KEY (case_basis_component_item_id) REFERENCES item(item_id),

    CHECK (forecast_yield_quantity >= 0),
    CHECK (trim(forecast_yield_unit) != ''),
    CHECK (
        user_serving_size_quantity IS NULL
        OR user_serving_size_quantity > 0
    ),
    CHECK (
        (user_serving_size_quantity IS NULL AND user_serving_size_unit IS NULL)
        OR (user_serving_size_quantity IS NOT NULL AND trim(user_serving_size_unit) != '')
    ),
    CHECK (
        desired_portions IS NULL
        OR desired_portions > 0
    ),
    CHECK (
        case_quantity IS NULL
        OR case_quantity >= 0
    ),
    CHECK (
        case_pack_quantity IS NULL
        OR case_pack_quantity > 0
    ),
    CHECK (
        case_subunit_quantity IS NULL
        OR case_subunit_quantity > 0
    )
);

CREATE TABLE IF NOT EXISTS item_case_pack (
    item_case_pack_id INTEGER PRIMARY KEY AUTOINCREMENT,

    item_id INTEGER NOT NULL,
    pack_quantity REAL NOT NULL,
    subunit_quantity REAL NOT NULL,
    subunit_unit TEXT NOT NULL,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (item_id) REFERENCES item(item_id) ON DELETE CASCADE,

    CHECK (pack_quantity > 0),
    CHECK (subunit_quantity > 0),
    CHECK (trim(subunit_unit) != '')
);

CREATE TABLE IF NOT EXISTS menu_forecast_batch_split (
    menu_forecast_batch_split_id INTEGER PRIMARY KEY AUTOINCREMENT,

    menu_slot_item_id INTEGER NOT NULL,
    batch_sequence INTEGER NOT NULL,
    batch_percent REAL NOT NULL,
    planned_time TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (menu_slot_item_id) REFERENCES menu_slot_item(menu_slot_item_id) ON DELETE CASCADE,

    CHECK (batch_sequence >= 1),
    CHECK (batch_percent > 0),
    CHECK (batch_percent <= 100),
    CHECK (
        planned_time IS NULL
        OR trim(planned_time) != ''
    ),

    UNIQUE (menu_slot_item_id, batch_sequence)
);

CREATE TABLE IF NOT EXISTS production_record (
    production_record_id INTEGER PRIMARY KEY AUTOINCREMENT,

    menu_id INTEGER NOT NULL,
    week_number INTEGER NOT NULL,
    day_of_week TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (menu_id) REFERENCES menu(menu_id) ON DELETE CASCADE,

    CHECK (week_number >= 1),
    CHECK (day_of_week IN (
        'sunday',
        'monday',
        'tuesday',
        'wednesday',
        'thursday',
        'friday',
        'saturday'
    )),
    CHECK (status IN ('draft', 'posted')),

    UNIQUE (menu_id, week_number, day_of_week)
);

CREATE TABLE IF NOT EXISTS production_record_line (
    production_record_line_id INTEGER PRIMARY KEY AUTOINCREMENT,

    production_record_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    recipe_name TEXT NOT NULL,
    assignment_count INTEGER NOT NULL DEFAULT 0,
    slot_labels_json TEXT NOT NULL DEFAULT '[]',

    forecast_quantity REAL NOT NULL DEFAULT 0,
    forecast_unit TEXT NOT NULL,
    actual_quantity REAL,
    actual_quantity_formula TEXT,
    actual_unit TEXT,
    variance_quantity REAL,
    variance_unit TEXT,
    variance_percent REAL,
    variance_level TEXT,
    end_service_variance_quantity REAL,
    end_service_variance_quantity_formula TEXT,
    end_service_variance_unit TEXT,
    implied_demand_quantity REAL,
    implied_demand_unit TEXT,
    forecast_error_quantity REAL,
    forecast_error_unit TEXT,
    forecast_error_percent REAL,
    forecast_accuracy_level TEXT,
    reason_code TEXT,
    reason_note TEXT,
    notes TEXT,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (production_record_id) REFERENCES production_record(production_record_id) ON DELETE CASCADE,
    FOREIGN KEY (item_id) REFERENCES item(item_id),

    CHECK (assignment_count >= 0),
    CHECK (forecast_quantity >= 0),
    CHECK (trim(forecast_unit) != ''),
    CHECK (
        actual_quantity IS NULL
        OR actual_quantity >= 0
    ),
    CHECK (
        (actual_quantity IS NULL AND actual_unit IS NULL)
        OR (actual_quantity IS NOT NULL AND trim(actual_unit) != '')
    ),
    CHECK (
        variance_level IS NULL
        OR variance_level IN ('normal', 'mild', 'severe')
    ),
    CHECK (
        forecast_accuracy_level IS NULL
        OR forecast_accuracy_level IN ('accurate', 'review', 'miss')
    ),

    UNIQUE (production_record_id, item_id)
);

CREATE TABLE IF NOT EXISTS inventory_location (
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

CREATE TABLE IF NOT EXISTS inventory_location_item (
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

CREATE INDEX IF NOT EXISTS idx_item_type
ON item(item_type);

CREATE INDEX IF NOT EXISTS idx_item_category
ON item(item_category);

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

CREATE INDEX IF NOT EXISTS idx_menu_forecast_batch_split_slot_item_id
ON menu_forecast_batch_split(menu_slot_item_id);

CREATE INDEX IF NOT EXISTS idx_production_record_menu_day
ON production_record(menu_id, week_number, day_of_week);

CREATE INDEX IF NOT EXISTS idx_production_record_line_record_id
ON production_record_line(production_record_id);

CREATE INDEX IF NOT EXISTS idx_production_record_line_item_id
ON production_record_line(item_id);

CREATE INDEX IF NOT EXISTS idx_item_case_pack_item_id
ON item_case_pack(item_id);

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

CREATE INDEX IF NOT EXISTS idx_inventory_location_item_catalog
ON inventory_location_item(inventory_catalog_item_id);

CREATE INDEX IF NOT EXISTS idx_inventory_location_item_sequence
ON inventory_location_item(inventory_location_id, display_sequence);

CREATE INDEX IF NOT EXISTS idx_inventory_location_break_location
ON inventory_location_break(inventory_location_id);

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
