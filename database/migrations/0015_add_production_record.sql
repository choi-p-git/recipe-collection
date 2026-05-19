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
    actual_unit TEXT,
    variance_quantity REAL,
    variance_unit TEXT,
    variance_percent REAL,
    variance_level TEXT,
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

    UNIQUE (production_record_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_production_record_menu_day
ON production_record(menu_id, week_number, day_of_week);

CREATE INDEX IF NOT EXISTS idx_production_record_line_record_id
ON production_record_line(production_record_id);

CREATE INDEX IF NOT EXISTS idx_production_record_line_item_id
ON production_record_line(item_id);
