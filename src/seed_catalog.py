from __future__ import annotations

import sqlite3


SEED_AUTHOR_USER_ID = "seed_author_001"
SEED_AUTHOR_DISPLAY_NAME = "Seed Kitchen"
SEED_DIETITIAN_USER_ID = "seed_dietitian_001"
SEED_DIETITIAN_DISPLAY_NAME = "Seed Dietitian"
SEED_REVIEWER_USER_ID = "seed_reviewer_001"
SEED_REVIEWER_DISPLAY_NAME = "Seed Reviewer"


BASE_FOOD_ITEMS = [
    {
        "item_name": "Chicken Breast",
        "mass_quantity": 140.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "notes": "Seed base food for protein-heavy recipe testing.",
    },
    {
        "item_name": "Romaine Lettuce",
        "mass_quantity": 47.0,
        "mass_unit": "g",
        "volume_quantity": 2.0,
        "volume_unit": "cup",
        "notes": "Seed leafy green base food for salad recipes.",
    },
    {
        "item_name": "Celery",
        "mass_quantity": 101.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "notes": "Seed vegetable base food for aromatic crunch.",
    },
    {
        "item_name": "Red Onion",
        "mass_quantity": 160.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "notes": "Seed aromatic base food for flavor balance.",
    },
    {
        "item_name": "Mayo",
        "mass_quantity": 218.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "notes": "Seed emulsified condiment for dressing and salad testing.",
    },
    {
        "item_name": "Dijon Mustard",
        "mass_quantity": 250.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "notes": "Seed condiment for recipe balance testing.",
    },
    {
        "item_name": "Lemon Juice",
        "mass_quantity": 244.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "notes": "Seed acidic liquid ingredient.",
    },
    {
        "item_name": "Salt",
        "mass_quantity": 288.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "notes": "Seed seasoning staple.",
    },
    {
        "item_name": "Black Pepper",
        "mass_quantity": 96.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "notes": "Seed dry seasoning staple.",
    },
    {
        "item_name": "Olive Oil",
        "mass_quantity": 216.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "notes": "Seed cooking fat for dressing and finish testing.",
    },
    {
        "item_name": "Garlic",
        "mass_quantity": 136.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "notes": "Seed aromatic seasoning ingredient.",
    },
    {
        "item_name": "Parsley",
        "mass_quantity": 30.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "notes": "Seed herb ingredient.",
    },
    {
        "item_name": "Cucumber",
        "mass_quantity": 104.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "notes": "Seed fresh produce item.",
    },
    {
        "item_name": "Tomato",
        "mass_quantity": 180.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "notes": "Seed fresh produce item.",
    },
    {
        "item_name": "Carrot",
        "mass_quantity": 128.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "notes": "Seed root vegetable item.",
    },
    {
        "item_name": "Cooked White Rice",
        "mass_quantity": 158.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "notes": "Seed starch base food for bowl and side recipes.",
    },
    {
        "item_name": "Chicken Stock",
        "mass_quantity": 240.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "notes": "Seed liquid ingredient for rice and sauce recipes.",
    },
    {
        "item_name": "Butter",
        "mass_quantity": 227.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "notes": "Seed fat ingredient for flavor and texture.",
    },
    {
        "item_name": "Breadcrumbs",
        "mass_quantity": 108.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "notes": "Seed dry topping ingredient.",
    },
    {
        "item_name": "Parmesan Cheese",
        "mass_quantity": 100.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "notes": "Seed finishing cheese ingredient.",
    },
]


RECIPE_ITEMS = [
    {
        "item_name": "Lemon Herb Mayo",
        "yield_quantity": 2.0,
        "yield_unit": "cup",
        "mass_quantity": 465.0,
        "mass_unit": "g",
        "volume_quantity": 2.0,
        "volume_unit": "cup",
        "serving_size_quantity": 2.0,
        "serving_size_unit": "tbs",
        "serving_count": 16.0,
        "primary_cooking_method_code": "no_cooking",
        "instructions_text": "1. Add mayo, lemon juice, and dijon to a bowl.\n2. Fold in parsley, salt, and black pepper.\n3. Mix until smooth and chilled.",
        "notes": "Seed simple recipe for dressing and condiment scaling tests.",
        "concept_classification": "sauce",
        "meal_classification": "condiment",
        "haccp_process_classification": "cold_holding",
        "components": [
            ("Mayo", 1.75, "cup"),
            ("Lemon Juice", 2.0, "tbs"),
            ("Parsley", 2.0, "tbs"),
            ("Dijon Mustard", 1.0, "tbs"),
            ("Salt", 0.5, "tsp"),
            ("Black Pepper", 0.25, "tsp"),
        ],
    },
    {
        "item_name": "Seasoned Rice",
        "yield_quantity": 3.0,
        "yield_unit": "qt",
        "mass_quantity": 1350.0,
        "mass_unit": "g",
        "volume_quantity": 3.0,
        "volume_unit": "qt",
        "serving_size_quantity": 0.75,
        "serving_size_unit": "cup",
        "serving_count": 16.0,
        "primary_cooking_method_code": "simmer",
        "instructions_text": "1. Warm stock and butter together until the butter melts.\n2. Fold the liquid into the cooked rice with salt.\n3. Hold warm and fluff before service.",
        "notes": "Seed simple recipe for starch and side scaling tests.",
        "concept_classification": "side",
        "meal_classification": "lunch",
        "haccp_process_classification": "cook_chill",
        "components": [
            ("Cooked White Rice", 7.0, "cup"),
            ("Chicken Stock", 1.0, "cup"),
            ("Butter", 4.0, "tbs"),
            ("Salt", 1.5, "tsp"),
        ],
    },
    {
        "item_name": "Chicken Salad",
        "yield_quantity": 3.0,
        "yield_unit": "qt",
        "mass_quantity": 1600.0,
        "mass_unit": "g",
        "volume_quantity": 3.0,
        "volume_unit": "qt",
        "serving_size_quantity": 0.5,
        "serving_size_unit": "cup",
        "serving_count": 24.0,
        "primary_cooking_method_code": "no_cooking",
        "instructions_text": "1. Fold mayo, dijon, and lemon juice together.\n2. Add chicken, celery, and onion.\n3. Season with salt and black pepper, then chill.",
        "notes": "Seed simple recipe used as a parent for complex recipe testing.",
        "concept_classification": "entree",
        "meal_classification": "lunch",
        "haccp_process_classification": "cold_holding",
        "components": [
            ("Chicken Breast", 2.5, "lb"),
            ("Mayo", 1.5, "cup"),
            ("Celery", 2.0, "cup"),
            ("Red Onion", 0.5, "cup"),
            ("Dijon Mustard", 0.25, "cup"),
            ("Lemon Juice", 2.0, "tbs"),
            ("Salt", 2.0, "tsp"),
            ("Black Pepper", 1.0, "tsp"),
        ],
    },
    {
        "item_name": "Garlic Breadcrumb Topping",
        "yield_quantity": 6.0,
        "yield_unit": "cup",
        "mass_quantity": 690.0,
        "mass_unit": "g",
        "volume_quantity": 6.0,
        "volume_unit": "cup",
        "serving_size_quantity": 2.0,
        "serving_size_unit": "tbs",
        "serving_count": 48.0,
        "primary_cooking_method_code": "bake",
        "instructions_text": "1. Toss breadcrumbs, parmesan, garlic, parsley, and oil together.\n2. Spread on a tray and bake until lightly toasted.\n3. Cool before using as a topping.",
        "notes": "Seed simple recipe for garnish and textural testing.",
        "concept_classification": "topping",
        "meal_classification": "condiment",
        "haccp_process_classification": "cook_serve",
        "components": [
            ("Breadcrumbs", 5.0, "cup"),
            ("Parmesan Cheese", 1.0, "cup"),
            ("Garlic", 4.0, "tbs"),
            ("Olive Oil", 0.5, "cup"),
            ("Parsley", 0.25, "cup"),
            ("Salt", 1.0, "tsp"),
            ("Black Pepper", 0.5, "tsp"),
        ],
    },
    {
        "item_name": "Garden Salad Mix",
        "yield_quantity": 4.0,
        "yield_unit": "qt",
        "mass_quantity": 1250.0,
        "mass_unit": "g",
        "volume_quantity": 4.0,
        "volume_unit": "qt",
        "serving_size_quantity": 1.0,
        "serving_size_unit": "cup",
        "serving_count": 16.0,
        "primary_cooking_method_code": "no_cooking",
        "instructions_text": "1. Combine romaine, cucumber, tomato, and carrot.\n2. Dress lightly with oil and lemon juice.\n3. Season with salt and black pepper before service.",
        "notes": "Seed simple recipe for fresh vegetable side testing.",
        "concept_classification": "side",
        "meal_classification": "lunch",
        "haccp_process_classification": "cold_holding",
        "components": [
            ("Romaine Lettuce", 8.0, "cup"),
            ("Cucumber", 3.0, "cup"),
            ("Tomato", 3.0, "cup"),
            ("Carrot", 2.0, "cup"),
            ("Olive Oil", 0.5, "cup"),
            ("Lemon Juice", 0.25, "cup"),
            ("Salt", 2.0, "tsp"),
            ("Black Pepper", 1.0, "tsp"),
        ],
    },
    {
        "item_name": "Chicken Salad Plate",
        "yield_quantity": 8.0,
        "yield_unit": "each",
        "mass_quantity": 2800.0,
        "mass_unit": "g",
        "volume_quantity": 5.0,
        "volume_unit": "qt",
        "serving_size_quantity": 1.0,
        "serving_size_unit": "each",
        "serving_count": 8.0,
        "primary_cooking_method_code": "no_cooking",
        "instructions_text": "1. Portion the chicken salad and garden salad onto plates.\n2. Finish with chopped parsley.\n3. Hold cold until service.",
        "notes": "Seed complex recipe using a simple recipe plus fresh side.",
        "concept_classification": "entree",
        "meal_classification": "lunch",
        "haccp_process_classification": "cold_holding",
        "components": [
            ("Chicken Salad", 2.0, "qt"),
            ("Garden Salad Mix", 2.0, "qt"),
            ("Parsley", 0.25, "cup"),
        ],
    },
    {
        "item_name": "Crispy Chicken Rice Bowl",
        "yield_quantity": 10.0,
        "yield_unit": "each",
        "mass_quantity": 3600.0,
        "mass_unit": "g",
        "volume_quantity": 5.5,
        "volume_unit": "qt",
        "serving_size_quantity": 1.0,
        "serving_size_unit": "each",
        "serving_count": 10.0,
        "primary_cooking_method_code": "bake",
        "instructions_text": "1. Portion seasoned rice into bowls.\n2. Top with chicken salad, tomatoes, and breadcrumb topping.\n3. Garnish with parsley before service.",
        "notes": "Seed complex recipe for nested scaling and flattening tests.",
        "concept_classification": "entree",
        "meal_classification": "lunch",
        "haccp_process_classification": "cook_serve",
        "components": [
            ("Seasoned Rice", 2.0, "qt"),
            ("Chicken Salad", 1.5, "qt"),
            ("Garlic Breadcrumb Topping", 1.0, "cup"),
            ("Tomato", 2.0, "cup"),
            ("Parsley", 0.25, "cup"),
        ],
    },
    {
        "item_name": "Deli Chicken Salad Meal Prep",
        "yield_quantity": 12.0,
        "yield_unit": "each",
        "mass_quantity": 4500.0,
        "mass_unit": "g",
        "volume_quantity": 7.0,
        "volume_unit": "qt",
        "serving_size_quantity": 1.0,
        "serving_size_unit": "each",
        "serving_count": 12.0,
        "primary_cooking_method_code": "no_cooking",
        "instructions_text": "1. Portion chicken salad, seasoned rice, and garden salad into containers.\n2. Add lemon herb mayo as a finishing condiment.\n3. Chill and label for meal prep service.",
        "notes": "Seed complex recipe for nested mixed-component testing.",
        "concept_classification": "entree",
        "meal_classification": "lunch",
        "haccp_process_classification": "cold_holding",
        "components": [
            ("Chicken Salad", 2.0, "qt"),
            ("Seasoned Rice", 1.5, "qt"),
            ("Garden Salad Mix", 1.5, "qt"),
            ("Lemon Herb Mayo", 0.5, "cup"),
        ],
    },
]


def database_has_seedable_items(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT COUNT(*) FROM item").fetchone()
    return bool(row and row[0] > 0)


def seed_database_if_empty(conn: sqlite3.Connection) -> bool:
    if database_has_seedable_items(conn):
        return False

    item_ids: dict[str, int] = {}

    for base_food in BASE_FOOD_ITEMS:
        item_id = _insert_item(
            conn,
            item_name=base_food["item_name"],
            item_type="base_food",
            author_user_id=SEED_DIETITIAN_USER_ID,
            author_display_name=SEED_DIETITIAN_DISPLAY_NAME,
            yield_quantity=None,
            yield_unit=None,
            mass_quantity=base_food["mass_quantity"],
            mass_unit=base_food["mass_unit"],
            volume_quantity=base_food["volume_quantity"],
            volume_unit=base_food["volume_unit"],
            serving_size_quantity=None,
            serving_size_unit=None,
            serving_count=1.0,
            instructions_text=None,
            primary_cooking_method_code=None,
            status="live",
            notes=base_food["notes"],
            concept_classification=None,
            meal_classification=None,
            haccp_process_classification=None,
        )
        item_ids[base_food["item_name"]] = item_id
        _record_seed_events(
            conn,
            item_id=item_id,
            item_type="base_food",
            creator_user_id=SEED_DIETITIAN_USER_ID,
            creator_display_name=SEED_DIETITIAN_DISPLAY_NAME,
        )

    for recipe in RECIPE_ITEMS:
        item_id = _insert_item(
            conn,
            item_name=recipe["item_name"],
            item_type="recipe",
            author_user_id=SEED_AUTHOR_USER_ID,
            author_display_name=SEED_AUTHOR_DISPLAY_NAME,
            yield_quantity=recipe["yield_quantity"],
            yield_unit=recipe["yield_unit"],
            mass_quantity=recipe["mass_quantity"],
            mass_unit=recipe["mass_unit"],
            volume_quantity=recipe["volume_quantity"],
            volume_unit=recipe["volume_unit"],
            serving_size_quantity=recipe["serving_size_quantity"],
            serving_size_unit=recipe["serving_size_unit"],
            serving_count=recipe["serving_count"],
            instructions_text=recipe["instructions_text"],
            primary_cooking_method_code=recipe["primary_cooking_method_code"],
            status="live",
            notes=recipe["notes"],
            concept_classification=recipe["concept_classification"],
            meal_classification=recipe["meal_classification"],
            haccp_process_classification=recipe["haccp_process_classification"],
        )
        item_ids[recipe["item_name"]] = item_id

        for sequence, (component_name, quantity, unit) in enumerate(recipe["components"], start=1):
            conn.execute(
                """
                INSERT INTO recipe_component (
                    parent_recipe_item_id,
                    component_item_id,
                    component_quantity,
                    component_unit,
                    component_sequence,
                    component_notes
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    item_ids[component_name],
                    quantity,
                    unit,
                    sequence,
                    None,
                ),
            )

        _record_seed_events(
            conn,
            item_id=item_id,
            item_type="recipe",
            creator_user_id=SEED_AUTHOR_USER_ID,
            creator_display_name=SEED_AUTHOR_DISPLAY_NAME,
        )

    return True


def _insert_item(
    conn: sqlite3.Connection,
    *,
    item_name: str,
    item_type: str,
    author_user_id: str,
    author_display_name: str,
    yield_quantity: float | None,
    yield_unit: str | None,
    mass_quantity: float | None,
    mass_unit: str | None,
    volume_quantity: float | None,
    volume_unit: str | None,
    serving_size_quantity: float | None,
    serving_size_unit: str | None,
    serving_count: float | None,
    instructions_text: str | None,
    primary_cooking_method_code: str | None,
    status: str,
    notes: str | None,
    concept_classification: str | None,
    meal_classification: str | None,
    haccp_process_classification: str | None,
) -> int:
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO item (
            item_name,
            item_type,
            author_user_id,
            author_display_name,
            yield_quantity,
            yield_unit,
            mass_quantity,
            mass_unit,
            volume_quantity,
            volume_unit,
            serving_size_quantity,
            serving_size_unit,
            serving_count,
            instructions_text,
            primary_cooking_method_code,
            status,
            notes,
            concept_classification,
            meal_classification,
            haccp_process_classification,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        (
            item_name,
            item_type,
            author_user_id,
            author_display_name,
            yield_quantity,
            yield_unit,
            mass_quantity,
            mass_unit,
            volume_quantity,
            volume_unit,
            serving_size_quantity,
            serving_size_unit,
            serving_count,
            instructions_text,
            primary_cooking_method_code,
            status,
            notes,
            concept_classification,
            meal_classification,
            haccp_process_classification,
        ),
    )
    return int(cursor.lastrowid)


def _record_seed_events(
    conn: sqlite3.Connection,
    *,
    item_id: int,
    item_type: str,
    creator_user_id: str,
    creator_display_name: str,
) -> None:
    conn.execute(
        """
        INSERT INTO item_event (
            item_id,
            event_type,
            actor_user_id,
            actor_display_name,
            actor_role,
            event_summary,
            action_code,
            from_status,
            to_status,
            reason_text,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            item_id,
            "item_created",
            creator_user_id,
            creator_display_name,
            "standard_user",
            f"{'Base Food' if item_type == 'base_food' else 'Recipe'} created.",
            None,
            None,
            None,
            "Seed catalog bootstrap item.",
        ),
    )

    conn.execute(
        """
        INSERT INTO item_event (
            item_id,
            event_type,
            actor_user_id,
            actor_display_name,
            actor_role,
            event_summary,
            action_code,
            from_status,
            to_status,
            reason_text,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            item_id,
            "status_transition",
            SEED_REVIEWER_USER_ID,
            SEED_REVIEWER_DISPLAY_NAME,
            "reviewer",
            "Status moved from Submitted to Live.",
            "go_live",
            "submitted",
            "live",
            "Seed catalog bootstrap published item.",
        ),
    )
