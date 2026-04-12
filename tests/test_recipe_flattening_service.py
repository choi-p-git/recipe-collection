import sqlite3

from services.item_service import create_base_food
from services.recipe_flattening_service import build_flattened_recipe_view
from services.recipe_service import create_recipe


def test_build_flattened_recipe_view_preserves_order_and_does_not_merge_shared_items(isolated_db):
    oil_id = create_base_food(item_name="Service Flatten Oil")
    salt_id = create_base_food(item_name="Service Flatten Salt")
    sauce_id = create_recipe(
        {
            "item_name": "Service Flatten Sauce",
            "yield_quantity": 2,
            "yield_unit": "cup",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {
                    "component_item_id": oil_id,
                    "component_quantity": 2,
                    "component_unit": "oz",
                },
                {
                    "component_item_id": salt_id,
                    "component_quantity": 0.0008,
                    "component_unit": "tsp",
                },
            ],
        }
    )
    recipe_id = create_recipe(
        {
            "item_name": "Service Flatten Parent",
            "yield_quantity": 1,
            "yield_unit": "each",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Build"],
            "ingredients": [
                {
                    "component_item_id": sauce_id,
                    "component_quantity": 1,
                    "component_unit": "cup",
                },
                {
                    "component_item_id": oil_id,
                    "component_quantity": 1,
                    "component_unit": "oz",
                },
            ],
        }
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE item SET status = 'live' WHERE item_id IN (?, ?, ?, ?)",
        (oil_id, salt_id, sauce_id, recipe_id),
    )
    conn.commit()
    conn.close()

    flattened_view = build_flattened_recipe_view(recipe_id)

    assert flattened_view["available"] is True
    assert flattened_view["warnings"] == []
    assert [row["row_type"] for row in flattened_view["rows"]] == [
        "sub_recipe",
        "base_food",
        "base_food",
        "base_food",
    ]
    assert [row["component_item_name"] for row in flattened_view["rows"]] == [
        "Service Flatten Sauce",
        "Service Flatten Oil",
        "Service Flatten Salt",
        "Service Flatten Oil",
    ]
    assert flattened_view["rows"][0]["depth"] == 0
    assert flattened_view["rows"][1]["depth"] == 1
    assert flattened_view["rows"][2]["quantity_display"] == "according to taste"
    assert flattened_view["rows"][3]["quantity_display"] == "1"
    assert flattened_view["rows"][1]["source_recipe_name"] == "Service Flatten Sauce"
    assert flattened_view["rows"][3]["source_recipe_name"] == "Service Flatten Parent"


def test_build_flattened_recipe_view_applies_same_family_conversion_for_child_recipe_scale(isolated_db):
    oil_id = create_base_food(item_name="Service Mismatch Oil")
    sauce_id = create_recipe(
        {
            "item_name": "Service Mismatch Sauce",
            "yield_quantity": 2,
            "yield_unit": "qt",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {
                    "component_item_id": oil_id,
                    "component_quantity": 8,
                    "component_unit": "oz",
                }
            ],
        }
    )
    recipe_id = create_recipe(
        {
            "item_name": "Service Mismatch Parent",
            "yield_quantity": 1,
            "yield_unit": "each",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Build"],
            "ingredients": [
                {
                    "component_item_id": sauce_id,
                    "component_quantity": 2,
                    "component_unit": "cup",
                }
            ],
        }
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE item SET status = 'live' WHERE item_id IN (?, ?, ?)",
        (oil_id, sauce_id, recipe_id),
    )
    conn.commit()
    conn.close()

    flattened_view = build_flattened_recipe_view(recipe_id)

    assert flattened_view["warnings"] == []
    assert [row["row_type"] for row in flattened_view["rows"]] == ["sub_recipe", "base_food"]
    assert flattened_view["rows"][1]["quantity_display"] == "2"
