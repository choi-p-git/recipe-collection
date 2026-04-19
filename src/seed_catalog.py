from __future__ import annotations

import csv
import io
import re
import sqlite3
import zipfile
from functools import lru_cache
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
USDA_ZIP_PATH = PROJECT_ROOT / "database" / "FoodData_Central_sr_legacy_food_csv_2018-04.zip"
USDA_ZIP_PREFIX = "FoodData_Central_sr_legacy_food_csv_2018-04/"

SEED_AUTHOR_USER_ID = "seed_author_001"
SEED_AUTHOR_DISPLAY_NAME = "Seed Kitchen"
SEED_DIETITIAN_USER_ID = "seed_dietitian_001"
SEED_DIETITIAN_DISPLAY_NAME = "Seed Dietitian"
SEED_REVIEWER_USER_ID = "seed_reviewer_001"
SEED_REVIEWER_DISPLAY_NAME = "Seed Reviewer"

SEED_TARGET_BASE_FOOD_COUNT = 1000
SEED_TARGET_SIMPLE_RECIPE_COUNT = 500
SEED_TARGET_COMPLEX_RECIPE_COUNT = 500

VOLUME_UNIT_TO_ML = {
    "tsp": 4.92892,
    "tbs": 14.7868,
    "cup": 236.588,
    "pt": 473.176,
    "qt": 946.353,
    "gal": 3785.41,
    "ml": 1.0,
    "l": 1000.0,
}
MASS_UNIT_TO_G = {
    "g": 1.0,
    "kg": 1000.0,
    "oz": 28.3495,
    "lb": 453.592,
}
COOKING_METHOD_CODES = [
    "no_cooking",
    "bake",
    "simmer",
    "saute",
    "steam",
    "boil",
    "grill",
    "stir_fry",
]
CONCEPT_CLASSIFICATIONS = [
    "entree",
    "side",
    "sauce",
    "salad",
    "grain",
    "vegetable",
    "protein",
    "condiment",
]
MEAL_CLASSIFICATIONS = [
    "breakfast",
    "lunch",
    "dinner",
    "side",
    "condiment",
]
HACCP_CLASSIFICATIONS = [
    "cold_holding",
    "cook_serve",
    "cook_chill",
]

MANUAL_BASE_FOOD_ITEMS: list[dict] = [
    {
        "item_name": "Chicken Breast",
        "mass_quantity": 140.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "nutrition_group": "Poultry Products",
        "kcal_per_serving": 231.0,
        "nutrition_serving_mass_quantity": 140.0,
        "nutrition_serving_mass_unit": "g",
        "nutrition_serving_volume_quantity": 1.0,
        "nutrition_serving_volume_unit": "cup",
        "notes": "Seed base food for protein-heavy recipe testing.",
    },
    {
        "item_name": "Romaine Lettuce",
        "mass_quantity": 47.0,
        "mass_unit": "g",
        "volume_quantity": 2.0,
        "volume_unit": "cup",
        "nutrition_group": "Vegetables and Vegetable Products",
        "kcal_per_serving": 8.0,
        "nutrition_serving_mass_quantity": 47.0,
        "nutrition_serving_mass_unit": "g",
        "nutrition_serving_volume_quantity": 1.0,
        "nutrition_serving_volume_unit": "cup",
        "notes": "Seed leafy green base food for salad recipes.",
    },
    {
        "item_name": "Celery",
        "mass_quantity": 101.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "nutrition_group": "Vegetables and Vegetable Products",
        "kcal_per_serving": 14.1,
        "nutrition_serving_mass_quantity": 101.0,
        "nutrition_serving_mass_unit": "g",
        "nutrition_serving_volume_quantity": 1.0,
        "nutrition_serving_volume_unit": "cup",
        "notes": "Seed vegetable base food for aromatic crunch.",
    },
    {
        "item_name": "Red Onion",
        "mass_quantity": 160.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "nutrition_group": "Vegetables and Vegetable Products",
        "kcal_per_serving": 16.0,
        "nutrition_serving_mass_quantity": 40.0,
        "nutrition_serving_mass_unit": "g",
        "nutrition_serving_volume_quantity": 0.25,
        "nutrition_serving_volume_unit": "cup",
        "notes": "Seed aromatic base food for flavor balance.",
    },
    {
        "item_name": "Mayo",
        "mass_quantity": 218.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "nutrition_group": "Fats and Oils",
        "kcal_per_serving": 103.2,
        "nutrition_serving_mass_quantity": 15.0,
        "nutrition_serving_mass_unit": "g",
        "nutrition_serving_volume_quantity": 1.0,
        "nutrition_serving_volume_unit": "tbs",
        "notes": "Seed emulsified condiment for dressing and salad testing.",
    },
    {
        "item_name": "Dijon Mustard",
        "mass_quantity": 250.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "nutrition_group": "Spices and Herbs",
        "kcal_per_serving": 3.0,
        "nutrition_serving_mass_quantity": 5.0,
        "nutrition_serving_mass_unit": "g",
        "nutrition_serving_volume_quantity": 1.0,
        "nutrition_serving_volume_unit": "tsp",
        "notes": "Seed condiment for recipe balance testing.",
    },
    {
        "item_name": "Lemon Juice",
        "mass_quantity": 244.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "nutrition_group": "Fruits and Fruit Juices",
        "kcal_per_serving": 3.4,
        "nutrition_serving_mass_quantity": 15.25,
        "nutrition_serving_mass_unit": "g",
        "nutrition_serving_volume_quantity": 1.0,
        "nutrition_serving_volume_unit": "tbs",
        "notes": "Seed acidic liquid ingredient.",
    },
    {
        "item_name": "Salt",
        "mass_quantity": 288.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "nutrition_group": "Spices and Herbs",
        "kcal_per_serving": 0.0,
        "nutrition_serving_mass_quantity": 6.0,
        "nutrition_serving_mass_unit": "g",
        "nutrition_serving_volume_quantity": 1.0,
        "nutrition_serving_volume_unit": "tsp",
        "notes": "Seed seasoning staple.",
    },
    {
        "item_name": "Black Pepper",
        "mass_quantity": 96.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "nutrition_group": "Spices and Herbs",
        "kcal_per_serving": 5.8,
        "nutrition_serving_mass_quantity": 2.3,
        "nutrition_serving_mass_unit": "g",
        "nutrition_serving_volume_quantity": 1.0,
        "nutrition_serving_volume_unit": "tsp",
        "notes": "Seed dry seasoning staple.",
    },
    {
        "item_name": "Olive Oil",
        "mass_quantity": 216.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "nutrition_group": "Fats and Oils",
        "kcal_per_serving": 119.3,
        "nutrition_serving_mass_quantity": 13.5,
        "nutrition_serving_mass_unit": "g",
        "nutrition_serving_volume_quantity": 1.0,
        "nutrition_serving_volume_unit": "tbs",
        "notes": "Seed cooking fat for dressing and finish testing.",
    },
    {
        "item_name": "Garlic",
        "mass_quantity": 136.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "nutrition_group": "Vegetables and Vegetable Products",
        "kcal_per_serving": 4.2,
        "nutrition_serving_mass_quantity": 2.8,
        "nutrition_serving_mass_unit": "g",
        "nutrition_serving_volume_quantity": 1.0,
        "nutrition_serving_volume_unit": "tsp",
        "notes": "Seed aromatic seasoning ingredient.",
    },
    {
        "item_name": "Parsley",
        "mass_quantity": 30.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "nutrition_group": "Vegetables and Vegetable Products",
        "kcal_per_serving": 1.4,
        "nutrition_serving_mass_quantity": 3.8,
        "nutrition_serving_mass_unit": "g",
        "nutrition_serving_volume_quantity": 1.0,
        "nutrition_serving_volume_unit": "tbs",
        "notes": "Seed herb ingredient.",
    },
    {
        "item_name": "Cucumber",
        "mass_quantity": 104.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "nutrition_group": "Vegetables and Vegetable Products",
        "kcal_per_serving": 7.8,
        "nutrition_serving_mass_quantity": 52.0,
        "nutrition_serving_mass_unit": "g",
        "nutrition_serving_volume_quantity": 0.5,
        "nutrition_serving_volume_unit": "cup",
        "notes": "Seed fresh produce item.",
    },
    {
        "item_name": "Tomato",
        "mass_quantity": 180.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "nutrition_group": "Vegetables and Vegetable Products",
        "kcal_per_serving": 16.2,
        "nutrition_serving_mass_quantity": 90.0,
        "nutrition_serving_mass_unit": "g",
        "nutrition_serving_volume_quantity": 0.5,
        "nutrition_serving_volume_unit": "cup",
        "notes": "Seed fresh produce item.",
    },
    {
        "item_name": "Carrot",
        "mass_quantity": 128.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "nutrition_group": "Vegetables and Vegetable Products",
        "kcal_per_serving": 26.2,
        "nutrition_serving_mass_quantity": 64.0,
        "nutrition_serving_mass_unit": "g",
        "nutrition_serving_volume_quantity": 0.5,
        "nutrition_serving_volume_unit": "cup",
        "notes": "Seed root vegetable item.",
    },
    {
        "item_name": "Cooked White Rice",
        "mass_quantity": 158.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "nutrition_group": "Cereal Grains and Pasta",
        "kcal_per_serving": 120.9,
        "nutrition_serving_mass_quantity": 93.0,
        "nutrition_serving_mass_unit": "g",
        "nutrition_serving_volume_quantity": 0.5,
        "nutrition_serving_volume_unit": "cup",
        "notes": "Seed starch base food for bowl and side recipes.",
    },
    {
        "item_name": "Chicken Stock",
        "mass_quantity": 240.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "nutrition_group": "Soups, Sauces, and Gravies",
        "kcal_per_serving": 14.9,
        "nutrition_serving_mass_quantity": 249.0,
        "nutrition_serving_mass_unit": "g",
        "nutrition_serving_volume_quantity": 1.0,
        "nutrition_serving_volume_unit": "cup",
        "notes": "Seed liquid ingredient for rice and sauce recipes.",
    },
    {
        "item_name": "Butter",
        "mass_quantity": 227.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "nutrition_group": "Dairy and Egg Products",
        "kcal_per_serving": 101.8,
        "nutrition_serving_mass_quantity": 14.2,
        "nutrition_serving_mass_unit": "g",
        "nutrition_serving_volume_quantity": 1.0,
        "nutrition_serving_volume_unit": "tbs",
        "notes": "Seed fat ingredient for flavor and texture.",
    },
    {
        "item_name": "Breadcrumbs",
        "mass_quantity": 108.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "nutrition_group": "Baked Products",
        "kcal_per_serving": 29.9,
        "nutrition_serving_mass_quantity": 11.25,
        "nutrition_serving_mass_unit": "g",
        "nutrition_serving_volume_quantity": 0.25,
        "nutrition_serving_volume_unit": "cup",
        "notes": "Seed dry topping ingredient.",
    },
    {
        "item_name": "Parmesan Cheese",
        "mass_quantity": 100.0,
        "mass_unit": "g",
        "volume_quantity": 1.0,
        "volume_unit": "cup",
        "nutrition_group": "Dairy and Egg Products",
        "kcal_per_serving": 21.0,
        "nutrition_serving_mass_quantity": 5.0,
        "nutrition_serving_mass_unit": "g",
        "nutrition_serving_volume_quantity": 1.0,
        "nutrition_serving_volume_unit": "tbs",
        "notes": "Seed finishing cheese ingredient.",
    },
]

MANUAL_SIMPLE_RECIPES: list[dict] = [
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
]

MANUAL_COMPLEX_RECIPES: list[dict] = [
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


@lru_cache(maxsize=1)
def get_seed_catalog() -> dict[str, list[dict]]:
    base_foods = _build_seed_base_food_catalog()
    simple_recipes = list(MANUAL_SIMPLE_RECIPES)
    simple_recipes.extend(
        _generate_simple_recipes(
            base_foods=base_foods,
            start_index=len(simple_recipes),
            target_count=SEED_TARGET_SIMPLE_RECIPE_COUNT,
        )
    )

    complex_recipes = list(MANUAL_COMPLEX_RECIPES)
    complex_recipes.extend(
        _generate_complex_recipes(
            base_foods=base_foods,
            simple_recipes=simple_recipes,
            start_index=len(complex_recipes),
            target_count=SEED_TARGET_COMPLEX_RECIPE_COUNT,
        )
    )

    return {
        "base_foods": base_foods,
        "recipes": simple_recipes + complex_recipes,
        "simple_recipes": simple_recipes,
        "complex_recipes": complex_recipes,
    }


def sync_seed_base_food_nutrition(conn: sqlite3.Connection) -> int:
    updated_rows = 0
    for base_food in get_seed_catalog()["base_foods"]:
        cursor = conn.execute(
            """
            UPDATE item
            SET nutrition_group = ?,
                kcal_per_serving = ?,
                nutrition_serving_mass_quantity = ?,
                nutrition_serving_mass_unit = ?,
                nutrition_serving_volume_quantity = ?,
                nutrition_serving_volume_unit = ?,
                updated_at = datetime('now')
            WHERE item_name = ?
              AND item_type = 'base_food'
              AND author_user_id = ?
              AND (
                    nutrition_group IS NULL
                 OR kcal_per_serving IS NULL
                 OR nutrition_serving_mass_quantity IS NULL
                 OR nutrition_serving_mass_unit IS NULL
                 OR nutrition_serving_volume_quantity IS NULL
                 OR nutrition_serving_volume_unit IS NULL
              )
            """,
            (
                base_food["nutrition_group"],
                base_food["kcal_per_serving"],
                base_food["nutrition_serving_mass_quantity"],
                base_food["nutrition_serving_mass_unit"],
                base_food["nutrition_serving_volume_quantity"],
                base_food["nutrition_serving_volume_unit"],
                base_food["item_name"],
                SEED_DIETITIAN_USER_ID,
            ),
        )
        updated_rows += cursor.rowcount
    return updated_rows


def seed_database_if_empty(conn: sqlite3.Connection) -> bool:
    if database_has_seedable_items(conn):
        return False

    catalog = get_seed_catalog()
    item_ids: dict[str, int] = {}

    for base_food in catalog["base_foods"]:
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
            nutrition_group=base_food["nutrition_group"],
            kcal_per_serving=base_food["kcal_per_serving"],
            nutrition_serving_mass_quantity=base_food["nutrition_serving_mass_quantity"],
            nutrition_serving_mass_unit=base_food["nutrition_serving_mass_unit"],
            nutrition_serving_volume_quantity=base_food["nutrition_serving_volume_quantity"],
            nutrition_serving_volume_unit=base_food["nutrition_serving_volume_unit"],
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

    for recipe in catalog["recipes"]:
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
            nutrition_group=None,
            kcal_per_serving=None,
            nutrition_serving_mass_quantity=None,
            nutrition_serving_mass_unit=None,
            nutrition_serving_volume_quantity=None,
            nutrition_serving_volume_unit=None,
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


def _build_seed_base_food_catalog() -> list[dict]:
    used_names = {item["item_name"] for item in MANUAL_BASE_FOOD_ITEMS}
    base_foods = [_enrich_base_food_record(dict(item)) for item in MANUAL_BASE_FOOD_ITEMS]

    if USDA_ZIP_PATH.exists():
        for candidate in _load_usda_base_food_candidates(used_names):
            base_foods.append(candidate)
            used_names.add(candidate["item_name"])
            if len(base_foods) >= SEED_TARGET_BASE_FOOD_COUNT:
                break

    if len(base_foods) < SEED_TARGET_BASE_FOOD_COUNT:
        base_foods.extend(
            _generate_fallback_base_foods(
                start_index=len(base_foods),
                count=SEED_TARGET_BASE_FOOD_COUNT - len(base_foods),
                used_names=used_names,
            )
        )

    return base_foods[:SEED_TARGET_BASE_FOOD_COUNT]


def _load_usda_base_food_candidates(used_names: set[str]) -> list[dict]:
    with zipfile.ZipFile(USDA_ZIP_PATH) as archive:
        food_rows = _read_csv_rows(archive, "food.csv")
        category_rows = _read_csv_rows(archive, "food_category.csv")
        nutrient_rows = _read_csv_rows(archive, "food_nutrient.csv")
        portion_rows = _read_csv_rows(archive, "food_portion.csv")

    category_lookup = {row["id"]: row["description"] for row in category_rows}
    kcal_lookup: dict[str, float] = {}
    for row in nutrient_rows:
        if row["nutrient_id"] == "1008" and row["amount"]:
            kcal_lookup[row["fdc_id"]] = float(row["amount"])

    portion_lookup: dict[str, tuple[float, str, float]] = {}
    for row in portion_rows:
        parsed = _parse_volume_portion(
            f"{row.get('portion_description', '')} {row.get('modifier', '')}",
        )
        if parsed is None or not row.get("gram_weight"):
            continue

        amount, unit = parsed
        gram_weight = float(row["gram_weight"])
        if gram_weight <= 0 or amount <= 0:
            continue

        candidate_score = _volume_unit_priority(unit)
        existing = portion_lookup.get(row["fdc_id"])
        if existing is None or candidate_score < _volume_unit_priority(existing[1]):
            portion_lookup[row["fdc_id"]] = (amount, unit, gram_weight)

    candidates: list[dict] = []
    local_used_names = set(used_names)

    for food in sorted(food_rows, key=lambda row: (category_lookup.get(row["food_category_id"], ""), row["description"])):
        fdc_id = food["fdc_id"]
        if fdc_id not in kcal_lookup or fdc_id not in portion_lookup:
            continue

        amount, unit, gram_weight = portion_lookup[fdc_id]
        item_name = _unique_seed_name(food["description"].strip(), local_used_names, fdc_id=fdc_id)
        local_used_names.add(item_name)
        kcal_per_serving = round(kcal_lookup[fdc_id] * gram_weight / 100.0, 1)

        candidates.append(
            _enrich_base_food_record(
                {
                    "item_name": item_name,
                    "mass_quantity": round(gram_weight, 2),
                    "mass_unit": "g",
                    "volume_quantity": round(amount, 2),
                    "volume_unit": unit,
                    "nutrition_group": category_lookup.get(food["food_category_id"], "USDA Food"),
                    "kcal_per_serving": kcal_per_serving,
                    "nutrition_serving_mass_quantity": round(gram_weight, 2),
                    "nutrition_serving_mass_unit": "g",
                    "nutrition_serving_volume_quantity": round(amount, 2),
                    "nutrition_serving_volume_unit": unit,
                    "notes": f"USDA SR Legacy seed reference (FDC {fdc_id}).",
                }
            )
        )

    return candidates


def _generate_fallback_base_foods(*, start_index: int, count: int, used_names: set[str]) -> list[dict]:
    fallback_items: list[dict] = []
    fallback_groups = ["Vegetable", "Protein", "Grain", "Dairy", "Seasoning"]
    for index in range(count):
        item_name = _unique_seed_name(
            f"Seed Pantry Ingredient {start_index + index + 1:04d}",
            used_names,
        )
        used_names.add(item_name)
        mass_quantity = 100.0 + ((start_index + index) % 9) * 15.0
        fallback_items.append(
            _enrich_base_food_record(
                {
                    "item_name": item_name,
                    "mass_quantity": mass_quantity,
                    "mass_unit": "g",
                    "volume_quantity": 1.0,
                    "volume_unit": "cup",
                    "nutrition_group": fallback_groups[(start_index + index) % len(fallback_groups)],
                    "kcal_per_serving": round(40 + ((start_index + index) % 12) * 12.5, 1),
                    "nutrition_serving_mass_quantity": mass_quantity,
                    "nutrition_serving_mass_unit": "g",
                    "nutrition_serving_volume_quantity": 1.0,
                    "nutrition_serving_volume_unit": "cup",
                    "notes": "Fallback generated seed base food when USDA candidates are exhausted.",
                }
            )
        )
    return fallback_items


def _generate_simple_recipes(*, base_foods: list[dict], start_index: int, target_count: int) -> list[dict]:
    recipes: list[dict] = []
    used_names = {recipe["item_name"] for recipe in MANUAL_SIMPLE_RECIPES}

    for index in range(start_index, target_count):
        sequence = index + 1
        component_count = 3 + (sequence % 4)
        chosen_base_foods = [
            base_foods[(sequence * 7 + offset * 11) % len(base_foods)]
            for offset in range(component_count)
        ]

        components: list[tuple[str, float, str]] = []
        total_mass_g = 0.0
        total_volume_ml = 0.0

        for offset, base_food in enumerate(chosen_base_foods):
            quantity, unit = _build_base_food_component_quantity(base_food, sequence + offset)
            components.append((base_food["item_name"], quantity, unit))
            total_mass_g += _base_food_mass_from_component(base_food, quantity, unit)
            total_volume_ml += _volume_quantity_to_ml(quantity, unit)

        yield_quantity, yield_unit, volume_quantity, volume_unit = _build_recipe_yield_basis(
            total_volume_ml=total_volume_ml,
            sequence=sequence,
        )
        mass_quantity, mass_unit = _build_mass_basis(total_mass_g)
        serving_size_quantity, serving_size_unit, serving_count = _build_serving_basis(
            total_volume_ml=total_volume_ml,
            yield_quantity=yield_quantity,
            yield_unit=yield_unit,
        )

        method_code = COOKING_METHOD_CODES[sequence % len(COOKING_METHOD_CODES)]
        recipe_name = _unique_seed_name(
            f"Simple Seed Recipe {sequence:03d} - {_short_name(chosen_base_foods[0]['item_name'])} and {_short_name(chosen_base_foods[1]['item_name'])}",
            used_names,
        )
        used_names.add(recipe_name)

        recipes.append(
            {
                "item_name": recipe_name,
                "yield_quantity": yield_quantity,
                "yield_unit": yield_unit,
                "mass_quantity": mass_quantity,
                "mass_unit": mass_unit,
                "volume_quantity": volume_quantity,
                "volume_unit": volume_unit,
                "serving_size_quantity": serving_size_quantity,
                "serving_size_unit": serving_size_unit,
                "serving_count": serving_count,
                "primary_cooking_method_code": method_code,
                "instructions_text": _build_simple_instruction_text(chosen_base_foods, method_code),
                "notes": "Generated simple seed recipe using only base foods.",
                "concept_classification": CONCEPT_CLASSIFICATIONS[sequence % len(CONCEPT_CLASSIFICATIONS)],
                "meal_classification": MEAL_CLASSIFICATIONS[sequence % len(MEAL_CLASSIFICATIONS)],
                "haccp_process_classification": HACCP_CLASSIFICATIONS[sequence % len(HACCP_CLASSIFICATIONS)],
                "components": components,
            }
        )

    return recipes


def _generate_complex_recipes(
    *,
    base_foods: list[dict],
    simple_recipes: list[dict],
    start_index: int,
    target_count: int,
) -> list[dict]:
    recipes: list[dict] = []
    used_names = {recipe["item_name"] for recipe in MANUAL_COMPLEX_RECIPES}
    simple_lookup = {recipe["item_name"]: _recipe_canonical_record(recipe) for recipe in simple_recipes}

    for index in range(start_index, target_count):
        sequence = index + 1
        child_a = simple_recipes[(sequence * 3) % len(simple_recipes)]
        child_b = simple_recipes[(sequence * 5 + 7) % len(simple_recipes)]
        base_a = base_foods[(sequence * 9 + 2) % len(base_foods)]
        base_b = base_foods[(sequence * 13 + 5) % len(base_foods)]

        child_a_ratio = 0.5 + ((sequence % 4) * 0.25)
        child_b_ratio = 0.5 + (((sequence + 1) % 4) * 0.25)
        child_a_quantity = round(child_a["yield_quantity"] * child_a_ratio, 2)
        child_b_quantity = round(child_b["yield_quantity"] * child_b_ratio, 2)
        base_a_quantity, base_a_unit = _build_base_food_component_quantity(base_a, sequence * 2)
        base_b_quantity, base_b_unit = _build_base_food_component_quantity(base_b, sequence * 2 + 1)

        components: list[tuple[str, float, str]] = [
            (child_a["item_name"], child_a_quantity, child_a["yield_unit"]),
            (child_b["item_name"], child_b_quantity, child_b["yield_unit"]),
            (base_a["item_name"], base_a_quantity, base_a_unit),
            (base_b["item_name"], base_b_quantity, base_b_unit),
        ]

        total_mass_g = 0.0
        total_volume_ml = 0.0

        for child_recipe, quantity in ((child_a, child_a_quantity), (child_b, child_b_quantity)):
            child_record = simple_lookup[child_recipe["item_name"]]
            ratio = quantity / float(child_recipe["yield_quantity"])
            total_mass_g += child_record["mass_g"] * ratio
            total_volume_ml += child_record["volume_ml"] * ratio

        total_mass_g += _base_food_mass_from_component(base_a, base_a_quantity, base_a_unit)
        total_mass_g += _base_food_mass_from_component(base_b, base_b_quantity, base_b_unit)
        total_volume_ml += _volume_quantity_to_ml(base_a_quantity, base_a_unit)
        total_volume_ml += _volume_quantity_to_ml(base_b_quantity, base_b_unit)

        yield_quantity, yield_unit, volume_quantity, volume_unit = _build_recipe_yield_basis(
            total_volume_ml=total_volume_ml,
            sequence=sequence,
            prefer_each=(sequence % 7 == 0),
        )
        mass_quantity, mass_unit = _build_mass_basis(total_mass_g)
        serving_size_quantity, serving_size_unit, serving_count = _build_serving_basis(
            total_volume_ml=total_volume_ml,
            yield_quantity=yield_quantity,
            yield_unit=yield_unit,
        )
        method_code = COOKING_METHOD_CODES[(sequence + 3) % len(COOKING_METHOD_CODES)]
        recipe_name = _unique_seed_name(
            f"Complex Seed Recipe {sequence:03d} - {_short_name(child_a['item_name'])} with {_short_name(base_a['item_name'])}",
            used_names,
        )
        used_names.add(recipe_name)

        recipes.append(
            {
                "item_name": recipe_name,
                "yield_quantity": yield_quantity,
                "yield_unit": yield_unit,
                "mass_quantity": mass_quantity,
                "mass_unit": mass_unit,
                "volume_quantity": volume_quantity,
                "volume_unit": volume_unit,
                "serving_size_quantity": serving_size_quantity,
                "serving_size_unit": serving_size_unit,
                "serving_count": serving_count,
                "primary_cooking_method_code": method_code,
                "instructions_text": _build_complex_instruction_text(child_a, child_b, base_a, base_b, method_code),
                "notes": "Generated complex seed recipe using both recipes and base foods.",
                "concept_classification": CONCEPT_CLASSIFICATIONS[(sequence + 2) % len(CONCEPT_CLASSIFICATIONS)],
                "meal_classification": MEAL_CLASSIFICATIONS[(sequence + 2) % len(MEAL_CLASSIFICATIONS)],
                "haccp_process_classification": HACCP_CLASSIFICATIONS[(sequence + 1) % len(HACCP_CLASSIFICATIONS)],
                "components": components,
            }
        )

    return recipes


def _enrich_base_food_record(base_food: dict) -> dict:
    enriched = dict(base_food)
    enriched["mass_g"] = _mass_quantity_to_g(enriched["mass_quantity"], enriched["mass_unit"])
    enriched["volume_ml"] = _volume_quantity_to_ml(enriched["volume_quantity"], enriched["volume_unit"])
    return enriched


def _recipe_canonical_record(recipe: dict) -> dict:
    return {
        "mass_g": _mass_quantity_to_g(recipe["mass_quantity"], recipe["mass_unit"]),
        "volume_ml": _volume_quantity_to_ml(recipe["volume_quantity"], recipe["volume_unit"]),
    }


def _build_recipe_yield_basis(*, total_volume_ml: float, sequence: int, prefer_each: bool = False) -> tuple[float, str, float, str]:
    volume_quantity, volume_unit = _select_best_volume_display(total_volume_ml)
    if prefer_each:
        return float(6 + (sequence % 10)), "each", volume_quantity, volume_unit
    return volume_quantity, volume_unit, volume_quantity, volume_unit


def _build_mass_basis(total_mass_g: float) -> tuple[float, str]:
    if total_mass_g >= 1000:
        return round(total_mass_g / 1000.0, 2), "kg"
    return round(total_mass_g, 2), "g"


def _build_serving_basis(*, total_volume_ml: float, yield_quantity: float, yield_unit: str) -> tuple[float, str, float]:
    if yield_unit == "each":
        return 1.0, "each", round(yield_quantity, 2)

    if total_volume_ml >= VOLUME_UNIT_TO_ML["cup"] * 8:
        serving_size_quantity, serving_size_unit = 1.0, "cup"
    elif total_volume_ml >= VOLUME_UNIT_TO_ML["cup"] * 2:
        serving_size_quantity, serving_size_unit = 0.5, "cup"
    else:
        serving_size_quantity, serving_size_unit = 2.0, "tbs"

    serving_count = total_volume_ml / _volume_quantity_to_ml(serving_size_quantity, serving_size_unit)
    return serving_size_quantity, serving_size_unit, round(max(serving_count, 1.0), 2)


def _build_base_food_component_quantity(base_food: dict, sequence: int) -> tuple[float, str]:
    unit = base_food["volume_unit"]
    quantity_map = {
        "tsp": [0.5, 1.0, 2.0, 3.0],
        "tbs": [1.0, 2.0, 3.0, 4.0],
        "cup": [0.25, 0.5, 1.0, 1.5],
        "pt": [0.25, 0.5, 1.0],
        "qt": [0.25, 0.5, 1.0],
        "gal": [0.125, 0.25, 0.5],
        "ml": [30.0, 60.0, 120.0, 180.0],
        "l": [0.25, 0.5, 1.0],
    }
    options = quantity_map.get(unit, [1.0])
    return float(options[sequence % len(options)]), unit


def _base_food_mass_from_component(base_food: dict, quantity: float, unit: str) -> float:
    quantity_ml = _volume_quantity_to_ml(quantity, unit)
    return (quantity_ml / base_food["volume_ml"]) * base_food["mass_g"]


def _select_best_volume_display(total_volume_ml: float) -> tuple[float, str]:
    for unit in ["gal", "qt", "pt", "cup", "tbs", "tsp"]:
        converted = total_volume_ml / VOLUME_UNIT_TO_ML[unit]
        if converted >= 1:
            return round(converted, 2), unit

    if total_volume_ml >= 1000:
        return round(total_volume_ml / 1000.0, 2), "l"
    return round(total_volume_ml, 2), "ml"


def _build_simple_instruction_text(base_foods: list[dict], method_code: str) -> str:
    return (
        f"1. Gather {', '.join(_short_name(item['item_name']) for item in base_foods[:3])}.\n"
        f"2. Combine all components using the {method_code.replace('_', ' ')} workflow.\n"
        "3. Taste, finish, and hold according to service needs."
    )


def _build_complex_instruction_text(child_a: dict, child_b: dict, base_a: dict, base_b: dict, method_code: str) -> str:
    return (
        f"1. Prepare {child_a['item_name']} and {child_b['item_name']}.\n"
        f"2. Add {_short_name(base_a['item_name'])} and {_short_name(base_b['item_name'])} during the {method_code.replace('_', ' ')} finish.\n"
        "3. Portion, garnish, and hold for service."
    )


def _parse_volume_portion(text: str) -> tuple[float, str] | None:
    lowered = re.sub(r"\s+", " ", (text or "").strip().lower())
    patterns = [
        ("gal", r"(?<!\w)(\d+(?:\.\d+)?)?\s*gallons?\b"),
        ("qt", r"(?<!\w)(\d+(?:\.\d+)?)?\s*quarts?\b"),
        ("pt", r"(?<!\w)(\d+(?:\.\d+)?)?\s*pints?\b"),
        ("cup", r"(?<!\w)(\d+(?:\.\d+)?)?\s*cups?\b"),
        ("tbs", r"(?<!\w)(\d+(?:\.\d+)?)?\s*(?:tablespoons?|tbsp)\b"),
        ("tsp", r"(?<!\w)(\d+(?:\.\d+)?)?\s*(?:teaspoons?|tsp)\b"),
        ("l", r"(?<!\w)(\d+(?:\.\d+)?)?\s*liters?\b"),
        ("ml", r"(?<!\w)(\d+(?:\.\d+)?)?\s*(?:ml|milliliters?)\b"),
    ]
    for unit, pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return float(match.group(1) or 1.0), unit
    return None


def _volume_unit_priority(unit: str) -> int:
    preference = {"cup": 0, "tbs": 1, "tsp": 2, "pt": 3, "qt": 4, "gal": 5, "ml": 6, "l": 7}
    return preference.get(unit, 99)


def _unique_seed_name(base_name: str, used_names: set[str], *, fdc_id: str | None = None) -> str:
    cleaned = " ".join(base_name.replace('"', "").split())
    if cleaned not in used_names:
        return cleaned
    if fdc_id:
        candidate = f"{cleaned} (FDC {fdc_id})"
        if candidate not in used_names:
            return candidate
    suffix = 2
    while True:
        candidate = f"{cleaned} ({suffix})"
        if candidate not in used_names:
            return candidate
        suffix += 1


def _short_name(value: str) -> str:
    return value.split(",")[0][:32].strip()


def _mass_quantity_to_g(quantity: float, unit: str) -> float:
    return float(quantity) * MASS_UNIT_TO_G[unit]


def _volume_quantity_to_ml(quantity: float, unit: str) -> float:
    return float(quantity) * VOLUME_UNIT_TO_ML[unit]


def _read_csv_rows(archive: zipfile.ZipFile, filename: str) -> list[dict[str, str]]:
    path = USDA_ZIP_PREFIX + filename
    with archive.open(path) as file_handle:
        return list(csv.DictReader(io.TextIOWrapper(file_handle, encoding="utf-8")))


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
    nutrition_group: str | None,
    kcal_per_serving: float | None,
    nutrition_serving_mass_quantity: float | None,
    nutrition_serving_mass_unit: str | None,
    nutrition_serving_volume_quantity: float | None,
    nutrition_serving_volume_unit: str | None,
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
            nutrition_group,
            kcal_per_serving,
            nutrition_serving_mass_quantity,
            nutrition_serving_mass_unit,
            nutrition_serving_volume_quantity,
            nutrition_serving_volume_unit,
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
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
            nutrition_group,
            kcal_per_serving,
            nutrition_serving_mass_quantity,
            nutrition_serving_mass_unit,
            nutrition_serving_volume_quantity,
            nutrition_serving_volume_unit,
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
    creator_role = "dietitian" if item_type == "base_food" else "standard_user"
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
            creator_role,
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
