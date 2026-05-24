import sqlite3

import pytest

from services.item_service import create_base_food
from services.menu_forecast_service import (
    InvalidMenuForecastBatchError,
    build_menu_forecast_production_summary,
    save_menu_forecast_batch_splits,
    save_menu_forecast_yield,
)
from services.menu_service import create_menu, replace_menu_slot_items
from services.recipe_service import create_recipe


def test_build_menu_forecast_production_summary_rolls_assignments_up_by_recipe():
    rows = [
        {
            "item_id": 20,
            "recipe_name": "Apple Crisp",
            "meal_period_label": "Lunch",
            "concept_label": "Hot Line",
            "menu_order": (0, 0, 1, "apple crisp", 20),
            "yield_quantity": 1,
            "yield_unit": "each",
            "mass_quantity": None,
            "mass_unit": "",
            "volume_quantity": None,
            "volume_unit": "",
            "forecast_quantity": "1",
            "forecast_unit": "each",
            "desired_portions": "",
            "batch_splits": [],
        },
        {
            "item_id": 10,
            "recipe_name": "Tomato Soup",
            "meal_period_label": "Dinner",
            "concept_label": "Hot Line",
            "menu_order": (1, 0, 1, "tomato soup", 10),
            "yield_quantity": 2,
            "yield_unit": "gal",
            "mass_quantity": None,
            "mass_unit": "",
            "volume_quantity": 2,
            "volume_unit": "gal",
            "forecast_quantity": "3",
            "forecast_unit": "gal",
            "desired_portions": "48",
            "batch_splits": [
                {
                    "batch_sequence": 1,
                    "batch_percent": 50,
                    "batch_percent_display": "50",
                    "batch_quantity": 1.5,
                    "batch_quantity_display": "1.5",
                    "batch_unit": "gal",
                    "planned_time": "11:00",
                },
                {
                    "batch_sequence": 2,
                    "batch_percent": 50,
                    "batch_percent_display": "50",
                    "batch_quantity": 1.5,
                    "batch_quantity_display": "1.5",
                    "batch_unit": "gal",
                    "planned_time": "11:30",
                },
            ],
        },
        {
            "item_id": 10,
            "recipe_name": "Tomato Soup",
            "meal_period_label": "Lunch",
            "concept_label": "Hot Line",
            "menu_order": (0, 0, 2, "tomato soup", 10),
            "yield_quantity": 2,
            "yield_unit": "gal",
            "mass_quantity": None,
            "mass_unit": "",
            "volume_quantity": 2,
            "volume_unit": "gal",
            "forecast_quantity": "8",
            "forecast_unit": "qt",
            "desired_portions": "32",
            "batch_splits": [
                {
                    "batch_sequence": 1,
                    "batch_percent": 25,
                    "batch_percent_display": "25",
                    "batch_quantity": 2,
                    "batch_quantity_display": "2",
                    "batch_unit": "qt",
                    "planned_time": "17:00",
                },
                {
                    "batch_sequence": 2,
                    "batch_percent": 75,
                    "batch_percent_display": "75",
                    "batch_quantity": 6,
                    "batch_quantity_display": "6",
                    "batch_unit": "qt",
                    "planned_time": "17:30",
                },
            ],
        },
    ]

    summary = build_menu_forecast_production_summary(rows)

    assert summary["warnings"] == []
    assert len(summary["rows"]) == 2
    assert [row["recipe_name"] for row in summary["rows"]] == ["Apple Crisp", "Tomato Soup"]
    rollup = summary["rows"][1]
    assert rollup["recipe_name"] == "Tomato Soup"
    assert rollup["assignment_count"] == 2
    assert rollup["total_forecast_quantity_display"] == "5"
    assert rollup["total_forecast_unit"] == "gal"
    assert "qt" in rollup["display_unit_options"]
    assert "pan_full_4" in rollup["display_unit_options"]
    assert rollup["batch_count_display"] == "2.5"
    assert rollup["desired_portions_display"] == "80"
    assert rollup["batch_summary"][0]["total_quantity_display"] == "2"
    assert rollup["batch_summary"][0]["combined_percent_display"] == "40"
    assert rollup["batch_summary"][1]["total_quantity_display"] == "3"
    assert rollup["batch_summary"][1]["combined_percent_display"] == "60"


def test_build_menu_forecast_production_summary_warns_for_unset_forecasts():
    summary = build_menu_forecast_production_summary(
        [
            {
                "item_id": 11,
                "recipe_name": "Unset Recipe",
                "meal_period_label": "Lunch",
                "concept_label": "Hot Line",
                "yield_quantity": 12,
                "yield_unit": "each",
                "mass_quantity": None,
                "mass_unit": "",
                "volume_quantity": None,
                "volume_unit": "",
                "forecast_quantity": "0",
                "forecast_unit": "each",
                "desired_portions": "",
            }
        ]
    )

    assert summary["rows"][0]["batch_count_display"] == "0"
    assert "without a forecast yield" in summary["warnings"][0]


def test_build_menu_forecast_production_summary_keeps_unforecasted_base_food_recordable():
    summary = build_menu_forecast_production_summary(
        [
            {
                "item_id": 12,
                "recipe_name": "Unforecasted Apples",
                "item_type": "base_food",
                "meal_period_label": "Lunch",
                "concept_label": "Hot Line",
                "yield_quantity": None,
                "yield_unit": "",
                "mass_quantity": 1,
                "mass_unit": "lb",
                "volume_quantity": None,
                "volume_unit": "",
                "forecast_quantity": "0",
                "forecast_unit": "each",
                "desired_portions": "",
            }
        ]
    )

    assert len(summary["rows"]) == 1
    assert summary["rows"][0]["recipe_name"] == "Unforecasted Apples"
    assert summary["rows"][0]["total_forecast_quantity_display"] == "0"
    assert summary["rows"][0]["total_forecast_unit"] == "lb"
    assert "without a forecast yield" in summary["warnings"][0]


def test_save_menu_forecast_batch_splits_persists_percentage_splits(isolated_db):
    base_food_id = create_base_food(item_name="Batch Split Base")
    recipe_id = create_recipe(
        {
            "item_name": "Batch Split Recipe",
            "yield_quantity": 10,
            "yield_unit": "lb",
            "primary_cooking_method_code": "fry",
            "instruction_steps": ["Cook"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "lb",
                }
            ],
        }
    )
    menu_id = create_menu(
        menu_name="Batch Split Menu",
        author_user_id="dev_user_001",
        author_display_name="Plato Choi",
        service_days=["monday"],
        meal_periods=["lunch"],
        concepts=["hot_line"],
        menu_length_weeks=1,
        allowed_service_days=["monday"],
        allowed_meal_periods=["lunch"],
        allowed_concepts=["hot_line"],
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (base_food_id, recipe_id))
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    replace_menu_slot_items(
        menu_slot_id=menu_slot_id,
        selected_item_ids=[recipe_id],
        actor_user_id="dev_user_001",
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_slot_item_id FROM menu_slot_item WHERE menu_slot_id = ?", (menu_slot_id,))
    menu_slot_item_id = cursor.fetchone()[0]
    conn.close()

    save_menu_forecast_yield(
        menu_id=menu_id,
        menu_slot_item_id=menu_slot_item_id,
        actor_user_id="dev_user_001",
        forecast_yield_quantity=100,
        forecast_yield_unit="lb",
    )
    batch_plan = save_menu_forecast_batch_splits(
        menu_id=menu_id,
        menu_slot_item_id=menu_slot_item_id,
        actor_user_id="dev_user_001",
        batch_splits=[
            {"batch_percent": "50", "planned_time": "11:00"},
            {"batch_quantity": "25", "planned_time": "11:30"},
            {"batch_quantity": "25", "planned_time": "12:00"},
        ],
    )

    assert [split["batch_percent_display"] for split in batch_plan["batch_splits"]] == ["50", "25", "25"]
    assert [split["batch_quantity_display"] for split in batch_plan["batch_splits"]] == ["50", "25", "25"]


def test_save_menu_forecast_yield_supports_case_mode_for_base_food(isolated_db):
    base_food_id = create_base_food(item_name="Case Mode Fries")
    menu_id = create_menu(
        menu_name="Case Mode Menu",
        author_user_id="dev_user_001",
        author_display_name="Plato Choi",
        service_days=["monday"],
        meal_periods=["lunch"],
        concepts=["hot_line"],
        menu_length_weeks=1,
        allowed_service_days=["monday"],
        allowed_meal_periods=["lunch"],
        allowed_concepts=["hot_line"],
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (base_food_id,))
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    replace_menu_slot_items(
        menu_slot_id=menu_slot_id,
        selected_item_ids=[base_food_id],
        actor_user_id="dev_user_001",
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_slot_item_id FROM menu_slot_item WHERE menu_slot_id = ?", (menu_slot_id,))
    menu_slot_item_id = cursor.fetchone()[0]
    conn.close()

    forecast = save_menu_forecast_yield(
        menu_id=menu_id,
        menu_slot_item_id=menu_slot_item_id,
        actor_user_id="dev_user_001",
        forecast_yield_quantity=3,
        forecast_yield_unit="case",
        user_serving_size_quantity=4,
        user_serving_size_unit="oz",
        desired_portions=80,
        case_pack_quantity=5,
        case_subunit_quantity=10,
        case_subunit_unit="lb",
    )

    assert forecast["forecast_yield_quantity"] == 3
    assert forecast["forecast_yield_unit"] == "case"
    assert forecast["case_pack_quantity"] == 5
    assert forecast["case_subunit_quantity"] == 10
    assert forecast["case_subunit_unit"] == "lb"
    assert forecast["calculated_forecast_quantity"] == 150
    assert forecast["calculated_forecast_unit"] == "lb"
    assert forecast["user_serving_size_quantity"] is None
    assert forecast["desired_portions"] is None

    batch_plan = save_menu_forecast_batch_splits(
        menu_id=menu_id,
        menu_slot_item_id=menu_slot_item_id,
        actor_user_id="dev_user_001",
        batch_splits=[
            {"batch_percent": "50"},
            {"batch_percent": "25"},
            {"batch_percent": "25"},
        ],
    )

    assert batch_plan["forecast_yield_quantity"] == 3
    assert batch_plan["forecast_yield_unit"] == "case"
    assert batch_plan["effective_forecast_quantity"] == 150
    assert batch_plan["effective_forecast_unit"] == "lb"
    assert [split["batch_quantity_display"] for split in batch_plan["batch_splits"]] == ["1.5", "0.75", "0.75"]
    assert [split["batch_unit"] for split in batch_plan["batch_splits"]] == ["case", "case", "case"]
    assert [split["effective_batch_quantity"] for split in batch_plan["batch_splits"]] == [75, 37.5, 37.5]


def test_save_menu_forecast_yield_preserves_saved_serving_fields_when_omitted(isolated_db):
    base_food_id = create_base_food(item_name="Serving Preserve Base")
    recipe_id = create_recipe(
        {
            "item_name": "Serving Preserve Recipe",
            "yield_quantity": 10,
            "yield_unit": "each",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "lb",
                }
            ],
        }
    )
    menu_id = create_menu(
        menu_name="Serving Preserve Menu",
        author_user_id="dev_user_001",
        author_display_name="Plato Choi",
        service_days=["monday"],
        meal_periods=["lunch"],
        concepts=["hot_line"],
        menu_length_weeks=1,
        allowed_service_days=["monday"],
        allowed_meal_periods=["lunch"],
        allowed_concepts=["hot_line"],
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (base_food_id, recipe_id))
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    replace_menu_slot_items(
        menu_slot_id=menu_slot_id,
        selected_item_ids=[recipe_id],
        actor_user_id="dev_user_001",
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_slot_item_id FROM menu_slot_item WHERE menu_slot_id = ?", (menu_slot_id,))
    menu_slot_item_id = cursor.fetchone()[0]
    conn.close()

    save_menu_forecast_yield(
        menu_id=menu_id,
        menu_slot_item_id=menu_slot_item_id,
        actor_user_id="dev_user_001",
        forecast_yield_quantity=20,
        forecast_yield_unit="each",
        user_serving_size_quantity=2,
        user_serving_size_unit="each",
        desired_portions=10,
    )
    updated = save_menu_forecast_yield(
        menu_id=menu_id,
        menu_slot_item_id=menu_slot_item_id,
        actor_user_id="dev_user_001",
        forecast_yield_quantity=5,
        forecast_yield_unit="lb",
    )

    assert updated["user_serving_size_quantity"] == 2
    assert updated["user_serving_size_unit"] == "each"
    assert updated["desired_portions"] == 10


def test_save_menu_forecast_batch_splits_requires_total_100(isolated_db):
    base_food_id = create_base_food(item_name="Batch Percent Base")
    recipe_id = create_recipe(
        {
            "item_name": "Batch Percent Recipe",
            "yield_quantity": 10,
            "yield_unit": "lb",
            "primary_cooking_method_code": "fry",
            "instruction_steps": ["Cook"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "lb",
                }
            ],
        }
    )
    menu_id = create_menu(
        menu_name="Batch Percent Menu",
        author_user_id="dev_user_001",
        author_display_name="Plato Choi",
        service_days=["monday"],
        meal_periods=["lunch"],
        concepts=["hot_line"],
        menu_length_weeks=1,
        allowed_service_days=["monday"],
        allowed_meal_periods=["lunch"],
        allowed_concepts=["hot_line"],
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (base_food_id, recipe_id))
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    replace_menu_slot_items(
        menu_slot_id=menu_slot_id,
        selected_item_ids=[recipe_id],
        actor_user_id="dev_user_001",
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_slot_item_id FROM menu_slot_item WHERE menu_slot_id = ?", (menu_slot_id,))
    menu_slot_item_id = cursor.fetchone()[0]
    conn.close()

    save_menu_forecast_yield(
        menu_id=menu_id,
        menu_slot_item_id=menu_slot_item_id,
        actor_user_id="dev_user_001",
        forecast_yield_quantity=100,
        forecast_yield_unit="lb",
    )

    with pytest.raises(InvalidMenuForecastBatchError):
        save_menu_forecast_batch_splits(
            menu_id=menu_id,
            menu_slot_item_id=menu_slot_item_id,
            actor_user_id="dev_user_001",
            batch_splits=[{"batch_percent": "50"}],
        )
