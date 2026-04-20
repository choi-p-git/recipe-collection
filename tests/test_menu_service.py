import sqlite3

import pytest

from services.item_service import create_base_food
from services.recipe_service import create_recipe
from services.menu_service import (
    InvalidMenuDeleteError,
    InvalidMenuPayloadError,
    InvalidMenuSlotActionError,
    InvalidMenuSlotAssignmentError,
    clear_menu_slot,
    create_menu,
    delete_menu,
    get_menu_slot_assignment_ids,
    paste_menu_slot_assignment_ids,
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

    replace_menu_slot_items(
        menu_slot_id=menu_slot_id,
        selected_item_ids=[recipe_id, base_food_id],
        actor_user_id="dev_user_001",
    )

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
        replace_menu_slot_items(
            menu_slot_id=menu_slot_id,
            selected_item_ids=[base_food_id],
            actor_user_id="dev_user_001",
        )


def test_delete_menu_removes_menu_slots_and_assignments(isolated_db):
    menu_id = create_menu(
        menu_name="Delete Menu",
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
    base_food_id = create_base_food(item_name="Delete Menu Lettuce")

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (base_food_id,))
    conn.commit()
    conn.close()

    replace_menu_slot_items(
        menu_slot_id=menu_slot_id,
        selected_item_ids=[base_food_id],
        actor_user_id="dev_user_001",
    )
    delete_menu(menu_id=menu_id, actor_user_id="dev_user_001")

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM menu WHERE menu_id = ?", (menu_id,))
    menu_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM menu_slot WHERE menu_id = ?", (menu_id,))
    slot_count = cursor.fetchone()[0]
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM menu_slot_item msi
        JOIN menu_slot ms ON ms.menu_slot_id = msi.menu_slot_id
        WHERE ms.menu_id = ?
        """,
        (menu_id,),
    )
    item_count = cursor.fetchone()[0]
    conn.close()

    assert menu_count == 0
    assert slot_count == 0
    assert item_count == 0


def test_delete_menu_rejects_non_owner():
    menu_id = create_menu(
        menu_name="Protected Menu",
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

    with pytest.raises(InvalidMenuDeleteError):
        delete_menu(menu_id=menu_id, actor_user_id="reviewer_001")


def test_copy_clear_and_paste_menu_slot_assignments(isolated_db):
    menu_id = create_menu(
        menu_name="Clipboard Menu",
        author_user_id="dev_user_001",
        author_display_name="Plato Choi",
        service_days=["monday"],
        meal_periods=["lunch"],
        concepts=["hot_line", "salad_bar"],
        menu_length_weeks=1,
        allowed_service_days=["monday"],
        allowed_meal_periods=["lunch"],
        allowed_concepts=["hot_line", "salad_bar"],
    )
    first_item_id = create_base_food(item_name="Clipboard Item One")
    second_item_id = create_base_food(item_name="Clipboard Item Two")

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT menu_slot_id FROM menu_slot WHERE menu_id = ? ORDER BY menu_slot_id ASC",
        (menu_id,),
    )
    source_slot_id, target_slot_id = [row[0] for row in cursor.fetchall()]
    cursor.execute(
        "UPDATE item SET status = 'live' WHERE item_id IN (?, ?)",
        (first_item_id, second_item_id),
    )
    conn.commit()
    conn.close()

    replace_menu_slot_items(
        menu_slot_id=source_slot_id,
        selected_item_ids=[first_item_id, second_item_id],
        actor_user_id="dev_user_001",
    )
    copied_item_ids = get_menu_slot_assignment_ids(
        menu_slot_id=source_slot_id,
        actor_user_id="dev_user_001",
    )
    clear_menu_slot(menu_slot_id=source_slot_id, actor_user_id="dev_user_001")
    paste_menu_slot_assignment_ids(
        menu_slot_id=target_slot_id,
        actor_user_id="dev_user_001",
        copied_item_ids=copied_item_ids,
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM menu_slot_item WHERE menu_slot_id = ?",
        (source_slot_id,),
    )
    source_count = cursor.fetchone()[0]
    cursor.execute(
        """
        SELECT item_id, item_sequence
        FROM menu_slot_item
        WHERE menu_slot_id = ?
        ORDER BY item_sequence ASC
        """,
        (target_slot_id,),
    )
    target_rows = cursor.fetchall()
    conn.close()

    assert copied_item_ids == [first_item_id, second_item_id]
    assert source_count == 0
    assert target_rows == [(first_item_id, 1), (second_item_id, 2)]


def test_menu_slot_actions_reject_non_owner(isolated_db):
    menu_id = create_menu(
        menu_name="Protected Slot Menu",
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
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    conn.close()

    with pytest.raises(InvalidMenuSlotActionError):
        get_menu_slot_assignment_ids(menu_slot_id=menu_slot_id, actor_user_id="reviewer_001")

    with pytest.raises(InvalidMenuSlotActionError):
        clear_menu_slot(menu_slot_id=menu_slot_id, actor_user_id="reviewer_001")


def test_paste_menu_slot_assignments_requires_clipboard_data():
    with pytest.raises(InvalidMenuSlotActionError):
        paste_menu_slot_assignment_ids(
            menu_slot_id=1,
            actor_user_id="dev_user_001",
            copied_item_ids=[],
        )
