import sqlite3

import pytest

from services.item_service import create_base_food
from services.recipe_service import InvalidRecipePayloadError, create_recipe, update_recipe


def test_create_recipe_inserts_recipe_and_components(isolated_db):
    mayo_id = create_base_food(item_name="Mayonnaise", yield_quantity=1, yield_unit="qt")
    spinach_id = create_base_food(item_name="Spinach", yield_quantity=2, yield_unit="lb")

    recipe_id = create_recipe(
        {
            "item_name": "Spinach Salad",
            "yield_quantity": 4,
            "yield_unit": "each",
            "serving_size_quantity": 1,
            "serving_size_unit": "cup",
            "serving_count": 4,
            "notes": "Serve chilled.",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Wash spinach", "Toss with mayonnaise"],
            "ingredients": [
                {
                    "component_item_id": spinach_id,
                    "component_quantity": 1,
                    "component_unit": "lb",
                },
                {
                    "component_item_id": mayo_id,
                    "component_quantity": 4,
                    "component_unit": "oz",
                },
            ],
        }
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT item_name, item_type, primary_cooking_method_code, instructions_text
        FROM item
        WHERE item_id = ?
        """,
        (recipe_id,),
    )
    recipe_row = cursor.fetchone()

    cursor.execute(
        """
        SELECT component_item_id, component_quantity, component_unit, component_sequence
        FROM recipe_component
        WHERE parent_recipe_item_id = ?
        ORDER BY component_sequence
        """,
        (recipe_id,),
    )
    component_rows = cursor.fetchall()
    conn.close()

    assert recipe_row == (
        "Spinach Salad",
        "recipe",
        "no_cooking",
        "1. Wash spinach\n2. Toss with mayonnaise",
    )
    assert component_rows == [
        (spinach_id, 1.0, "lb", 1),
        (mayo_id, 4.0, "oz", 2),
    ]


def test_update_recipe_replaces_fields_and_components(isolated_db):
    mayo_id = create_base_food(item_name="Mayo", notes="Base")
    greens_id = create_base_food(item_name="Greens", notes="Base")

    recipe_id = create_recipe(
        {
            "item_name": "Initial Salad",
            "yield_quantity": 2,
            "yield_unit": "each",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {
                    "component_item_id": greens_id,
                    "component_quantity": 1,
                    "component_unit": "lb",
                }
            ],
        }
    )

    update_recipe(
        recipe_id,
        {
            "item_name": "Updated Salad",
            "yield_quantity": 4,
            "yield_unit": "each",
            "notes": "Updated note",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix greens", "Add mayo"],
            "ingredients": [
                {
                    "component_item_id": greens_id,
                    "component_quantity": 2,
                    "component_unit": "lb",
                },
                {
                    "component_item_id": mayo_id,
                    "component_quantity": 3,
                    "component_unit": "oz",
                },
            ],
            "concept_classification": "Salads",
        },
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT item_name, notes, concept_classification, instructions_text FROM item WHERE item_id = ?",
        (recipe_id,),
    )
    recipe_row = cursor.fetchone()
    cursor.execute(
        """
        SELECT component_item_id, component_quantity, component_unit
        FROM recipe_component
        WHERE parent_recipe_item_id = ?
        ORDER BY component_sequence
        """,
        (recipe_id,),
    )
    component_rows = cursor.fetchall()
    conn.close()

    assert recipe_row == (
        "Updated Salad",
        "Updated note",
        "Salads",
        "1. Mix greens\n2. Add mayo",
    )
    assert component_rows == [
        (greens_id, 2.0, "lb"),
        (mayo_id, 3.0, "oz"),
    ]


@pytest.mark.parametrize(
    ("payload", "expected_message"),
    [
        (
            {
                "item_name": "Bad Recipe",
                "yield_quantity": 0,
                "yield_unit": "each",
                "primary_cooking_method_code": "bake",
                "instruction_steps": ["Step"],
                "ingredients": [{"component_item_id": 1, "component_quantity": 1, "component_unit": "oz"}],
            },
            "Yield quantity must be greater than 0.",
        ),
        (
            {
                "item_name": "Bad Recipe",
                "yield_quantity": 1,
                "yield_unit": "each",
                "primary_cooking_method_code": "",
                "instruction_steps": ["Step"],
                "ingredients": [{"component_item_id": 1, "component_quantity": 1, "component_unit": "oz"}],
            },
            "Primary cooking method is required.",
        ),
        (
            {
                "item_name": "Bad Recipe",
                "yield_quantity": 1,
                "yield_unit": "each",
                "primary_cooking_method_code": "bake",
                "instruction_steps": [],
                "ingredients": [],
            },
            "At least one non-empty instruction step is required.",
        ),
    ],
)
def test_create_recipe_validation_errors(isolated_db, payload, expected_message):
    with pytest.raises((ValueError, InvalidRecipePayloadError), match=expected_message):
        create_recipe(payload)
