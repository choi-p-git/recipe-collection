import sqlite3

import pytest

from services.menu_service import InvalidMenuPayloadError, create_menu


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
