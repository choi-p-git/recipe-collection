import sqlite3

import pytest

from services.item_service import create_base_food
from services.recipe_service import create_recipe
from services.menu_service import (
    InvalidMenuPayloadError,
    InvalidMenuSlotAssignmentError,
    create_menu,
    replace_menu_slot_items,
)


def test_create_menu_materializes_expected_slot_count(isolated_db):
    menu_id = create_menu(
        menu_name="Cycle Menu",
        author_user_id="dev_user_001",
        author_display_name="Plato Choi",
        service_days=["monday", "wednesday"],
        meal_periods=["lunch", "dinner"],
        concepts=["hot_line", "salad_bar"],
        menu_length_weeks=2,
        allowed_service_days=["monday", "wednesday", "friday"],
        allowed_meal_periods=["breakfast", "lunch", "dinner"],
        allowed_concepts=["hot_line", "salad_bar", "grab_go"],
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_name, status FROM menu WHERE menu_id = ?", (menu_id,))
    menu_row = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) FROM menu_slot WHERE menu_id = ?", (menu_id,))
    slot_count = cursor.fetchone()[0]
    conn.close()

    assert menu_row == ("Cycle Menu", "draft")
    assert slot_count == 16


def test_create_menu_requires_name_and_selections():
    with pytest.raises(InvalidMenuPayloadError):
        create_menu(
            menu_name="",
            author_user_id="dev_user_001",
            author_display_name="Plato Choi",
            service_days=[],
            meal_periods=[],
            concepts=[],
            menu_length_weeks=0,
            allowed_service_days=["monday"],
            allowed_meal_periods=["lunch"],
            allowed_concepts=["hot_line"],
        )


def test_replace_menu_slot_items_replaces_assignments_with_live_items(isolated_db):
    menu_id = create_menu(
        menu_name="Assign Menu",
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
    base_food_id = create_base_food(item_name="Assign Slot Lettuce")
    recipe_id = create_recipe(
        {
            "item_name": "Assign Slot Salad",
            "yield_quantity": 1,
            "yield_unit": "each",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "cup",
                }
            ],
        }
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (base_food_id, recipe_id))
    conn.commit()
    conn.close()

    replace_menu_slot_items(menu_slot_id=menu_slot_id, selected_item_ids=[recipe_id, base_food_id])

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT item_id, item_sequence
        FROM menu_slot_item
        WHERE menu_slot_id = ?
        ORDER BY item_sequence ASC
        """,
        (menu_slot_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    assert rows == [(recipe_id, 1), (base_food_id, 2)]


def test_replace_menu_slot_items_rejects_non_live_items(isolated_db):
    menu_id = create_menu(
        menu_name="Assign Error Menu",
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
    base_food_id = create_base_food(item_name="Assign Draft Lettuce")

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    conn.close()

    with pytest.raises(InvalidMenuSlotAssignmentError):
        replace_menu_slot_items(menu_slot_id=menu_slot_id, selected_item_ids=[base_food_id])
