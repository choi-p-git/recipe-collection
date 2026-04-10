import sqlite3

from services.item_service import (
    DuplicateItemNameError,
    create_base_food,
    get_next_available_item_name,
    normalize_item_name,
    update_base_food,
)


def test_normalize_item_name_trims_and_collapses_spaces():
    assert normalize_item_name("  Honey   Ham  ") == "Honey Ham"


def test_create_base_food_returns_item_id_and_inserts_row(isolated_db):
    item_id = create_base_food(
        item_name="Spinach",
        notes="Washed and ready.",
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT item_name, item_type, author_user_id, yield_quantity, yield_unit, notes
        FROM item
        WHERE item_id = ?
        """,
        (item_id,),
    )
    row = cursor.fetchone()
    conn.close()

    assert row == ("Spinach", "base_food", "system_base_food", None, None, "Washed and ready.")


def test_create_base_food_duplicate_name_raises_suggestion(isolated_db):
    create_base_food(item_name="Mayonnaise")
    create_base_food(item_name="Mayonnaise (1)")

    try:
        create_base_food(item_name="  mayonnaise  ")
        assert False, "Expected DuplicateItemNameError"
    except DuplicateItemNameError as exc:
        assert exc.suggested_name == "mayonnaise (2)"


def test_get_next_available_item_name_uses_highest_suffix(isolated_db):
    create_base_food(item_name="Tomato")
    create_base_food(item_name="Tomato (1)")
    create_base_food(item_name="Tomato (3)")

    assert get_next_available_item_name("Tomato") == "Tomato (4)"


def test_update_base_food_updates_name_and_notes(isolated_db):
    item_id = create_base_food(item_name="Celery", notes="Old note")

    update_base_food(item_id=item_id, item_name="Fresh Celery", notes="New note")

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT item_name, notes FROM item WHERE item_id = ?", (item_id,))
    row = cursor.fetchone()
    conn.close()

    assert row == ("Fresh Celery", "New note")
