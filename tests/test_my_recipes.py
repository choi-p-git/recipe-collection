import sqlite3

from queries.my_recipes import get_my_recipes
from services.item_service import create_base_food
from services.recipe_service import MOCK_RECIPE_AUTHOR_USER_ID, create_recipe


def _set_recipe_status(isolated_db, recipe_id: int, status: str, updated_at: str) -> None:
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE item
        SET status = ?, updated_at = ?
        WHERE item_id = ?
        """,
        (status, updated_at, recipe_id),
    )
    conn.commit()
    conn.close()


def _insert_other_user_recipe(isolated_db) -> int:
    conn = sqlite3.connect(isolated_db)
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
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        (
            "Other User Recipe",
            "recipe",
            "other_user_001",
            "Other User",
            1,
            "each",
            None,
            None,
            None,
            "1. Other step",
            "bake",
            "submitted",
            None,
            None,
            None,
            None,
        ),
    )
    recipe_id = int(cursor.lastrowid)
    conn.commit()
    conn.close()
    return recipe_id


def test_get_my_recipes_returns_only_current_user_recipes(isolated_db):
    base_food_id = create_base_food(item_name="Olive Oil")

    recipe_id = create_recipe(
        {
            "item_name": "Current User Recipe",
            "yield_quantity": 2,
            "yield_unit": "each",
            "primary_cooking_method_code": "bake",
            "instruction_steps": ["Mix", "Bake"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 2,
                    "component_unit": "oz",
                }
            ],
        }
    )
    _insert_other_user_recipe(isolated_db)

    page_data = get_my_recipes(MOCK_RECIPE_AUTHOR_USER_ID)

    assert [recipe["item_id"] for recipe in page_data["recipes"]] == [recipe_id]


def test_get_my_recipes_filters_and_sorts_results(isolated_db):
    base_food_id = create_base_food(item_name="Butter")

    first_recipe_id = create_recipe(
        {
            "item_name": "Banana Bread",
            "yield_quantity": 1,
            "yield_unit": "each",
            "primary_cooking_method_code": "bake",
            "instruction_steps": ["Mix", "Bake"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "oz",
                }
            ],
        }
    )
    second_recipe_id = create_recipe(
        {
            "item_name": "Apple Tart",
            "yield_quantity": 1,
            "yield_unit": "each",
            "primary_cooking_method_code": "bake",
            "instruction_steps": ["Assemble", "Bake"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "oz",
                }
            ],
        }
    )

    _set_recipe_status(isolated_db, first_recipe_id, "reviewed", "2026-04-10 08:00:00")
    _set_recipe_status(isolated_db, second_recipe_id, "submitted", "2026-04-10 09:00:00")

    filtered = get_my_recipes(MOCK_RECIPE_AUTHOR_USER_ID, status="reviewed", sort="name_asc")
    sorted_page = get_my_recipes(MOCK_RECIPE_AUTHOR_USER_ID, sort="name_asc")

    assert [recipe["item_id"] for recipe in filtered["recipes"]] == [first_recipe_id]
    assert [recipe["item_name"] for recipe in sorted_page["recipes"]] == ["Apple Tart", "Banana Bread"]

