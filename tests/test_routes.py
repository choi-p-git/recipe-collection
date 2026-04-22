import sqlite3

from services.item_service import create_base_food
from services.recipe_service import create_recipe


def test_index_and_form_routes_render(app_client):
    assert app_client.get("/").status_code == 200
    base_food_page = app_client.get("/new/base-food")
    assert base_food_page.status_code == 200
    assert "Yield Quantity" not in base_food_page.get_data(as_text=True)
    recipe_page = app_client.get("/new/recipe")
    assert recipe_page.status_code == 200
    assert "Yield Mass Quantity" in recipe_page.get_data(as_text=True)
    assert "Official Serving Count" not in recipe_page.get_data(as_text=True)
    assert app_client.get("/login").status_code == 200
    assert app_client.get("/preferences").status_code == 200
    assert app_client.get("/menus").status_code == 200
    assert app_client.get("/menus/new").status_code == 200


def test_new_base_food_post_redirects_to_item_detail(app_client):
    response = app_client.post(
        "/new/base-food",
        data={
            "item_name": "Honey Ham",
            "notes": "Thin sliced.",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/items/" in response.headers["Location"]


def test_item_detail_route_renders_base_food(app_client):
    item_id = create_base_food(item_name="Shredded Carrots")

    response = app_client.get(f"/items/{item_id}")

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Base Food" in page
    assert "Shredded Carrots" in page
    assert "Yield" not in page
    assert "Ingredients" not in page
    assert "Method Steps" not in page
    assert "Classification" not in page
    assert "Workflow History" in page
    assert "Base Food created." in page
    assert "Nutrition Authority" not in page


def test_item_detail_route_renders_recipe(app_client):
    dressing_id = create_base_food(item_name="Salad Dressing")

    create_response = app_client.post(
        "/api/recipes",
        json={
            "item_name": "Dressed Greens",
            "yield_quantity": 2,
            "yield_unit": "each",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix greens", "Add dressing"],
            "ingredients": [
                {
                    "component_item_id": dressing_id,
                    "component_quantity": 4,
                    "component_unit": "oz",
                }
            ],
        },
    )

    payload = create_response.get_json()
    response = app_client.get(f"/items/{payload['recipe_item_id']}")
    page = response.get_data(as_text=True)

    assert create_response.status_code == 200
    assert response.status_code == 200
    assert "Recipe" in page
    assert "Primary Cooking Method:" in page
    assert "no cooking" in page
    assert "Ingredients" in page
    assert "Method Steps" in page


def test_new_menu_post_creates_menu_and_materializes_slots(app_client, isolated_db):
    response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Spring Menu",
            "service_days": ["monday", "wednesday"],
            "meal_periods": ["lunch", "dinner"],
            "concepts": ["hot_line", "salad_bar"],
            "menu_length_weeks": "2",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/menus/" in response.headers["Location"]

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_id, menu_name, status FROM menu")
    menu_row = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) FROM menu_slot WHERE menu_id = ?", (menu_row[0],))
    slot_count = cursor.fetchone()[0]
    conn.close()

    assert menu_row[1:] == ("Spring Menu", "draft")
    assert slot_count == 16


def test_menu_detail_route_renders_week_overview(app_client):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Week Test Menu",
            "service_days": ["monday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line", "salad_bar"],
            "menu_length_weeks": "2",
        },
        follow_redirects=False,
    )
    menu_location = create_response.headers["Location"]

    response = app_client.get(f"{menu_location}?week=2")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Week Test Menu" in page
    assert "Week 2 Overview" in page
    assert "Hot Line" in page
    assert "Salad Bar" in page


def test_my_menus_route_renders_current_user_menus(app_client):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Owner Menu",
            "service_days": ["monday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )

    assert create_response.status_code == 302

    response = app_client.get("/menus")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "My Menus" in page
    assert "Owner Menu" in page
    assert "Future Menu Workspaces" in page


def test_my_menus_route_shows_delete_action(app_client):
    app_client.post(
        "/menus/new",
        data={
            "menu_name": "Delete Action Menu",
            "service_days": ["monday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )

    response = app_client.get("/menus")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Delete Menu" in page


def test_menu_slot_assign_route_renders_search_and_current_slot(app_client):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Assign Route Menu",
            "service_days": ["monday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_location = create_response.headers["Location"]

    menu_id = int(menu_location.rstrip("/").split("/")[-1])
    response = app_client.get(f"/menus/{menu_id}/slots/1/assign")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Assign Slot Items" in page
    assert "Pending Assignment" in page
    assert "menu_slot_assign.js" in page


def test_menu_detail_route_shows_delete_action(app_client):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Delete Detail Menu",
            "service_days": ["monday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_location = create_response.headers["Location"]

    response = app_client.get(menu_location)
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Delete Menu" in page
    assert "Bulk Slot Actions" in page
    assert "Update Bulk Mode" in page
    assert "menu_detail.js" in page
    assert "Menu Summary" in page


def test_menu_slot_assign_route_renders_search_results(app_client, isolated_db):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Assign Search Menu",
            "service_days": ["monday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])

    base_food_id = create_base_food(item_name="Assign Search Lettuce")
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (base_food_id,))
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    response = app_client.get(f"/menus/{menu_id}/slots/{menu_slot_id}/assign?q=lettuce")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Assign Search Lettuce" in page
    assert "Base Food | ID" in page


def test_menu_slot_assign_post_updates_slot_and_renders_in_menu_overview(app_client, isolated_db):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Assigned Menu",
            "service_days": ["monday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])

    base_food_id = create_base_food(item_name="Assigned Slot Lettuce")
    recipe_id = create_recipe(
        {
            "item_name": "Assigned Slot Salad",
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
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (base_food_id, recipe_id))
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    response = app_client.post(
        f"/menus/{menu_id}/slots/{menu_slot_id}/assign",
        data={
            "week": "1",
            "selected_item_ids": [str(recipe_id), str(base_food_id)],
        },
        follow_redirects=True,
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Menu slot assignments updated." in page
    assert "Assigned Slot Salad" in page
    assert "Assigned Slot Lettuce" in page


def test_copy_and_paste_menu_slot_routes_update_session_and_target_slot(app_client, isolated_db):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Clipboard Route Menu",
            "service_days": ["monday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line", "salad_bar"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])

    first_item_id = create_base_food(item_name="Route Clipboard One")
    second_item_id = create_base_food(item_name="Route Clipboard Two")

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

    app_client.post(
        f"/menus/{menu_id}/slots/{source_slot_id}/assign",
        data={
            "week": "1",
            "selected_item_ids": [str(first_item_id), str(second_item_id)],
        },
        follow_redirects=False,
    )

    copy_response = app_client.post(
        f"/menus/{menu_id}/slots/{source_slot_id}/copy",
        data={"week": "1"},
        follow_redirects=True,
    )
    paste_response = app_client.post(
        f"/menus/{menu_id}/slots/{target_slot_id}/paste",
        data={"week": "1"},
        follow_redirects=True,
    )
    paste_page = paste_response.get_data(as_text=True)

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT item_id, item_sequence
        FROM menu_slot_item
        WHERE menu_slot_id = ?
        ORDER BY item_sequence ASC
        """,
        (target_slot_id,),
    )
    pasted_rows = cursor.fetchall()
    conn.close()

    assert copy_response.status_code == 200
    assert "Copied 2 slot items." in copy_response.get_data(as_text=True)
    assert paste_response.status_code == 200
    assert "Pasted copied slot items." in paste_page
    assert pasted_rows == [(first_item_id, 1), (second_item_id, 2)]


def test_menu_detail_route_renders_bulk_selection_mode(app_client):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Bulk Selection Menu",
            "service_days": ["monday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_location = create_response.headers["Location"]

    response = app_client.get(f"{menu_location}?bulk_action=copy&bulk_scope=cell")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Copy Selected Cells" in page
    assert "Select Slot" in page
    assert "Copy by Cells keeps the selected slots only." in page


def test_menu_detail_route_renders_concept_header_selection_mode(app_client):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Bulk Concept Selection Menu",
            "service_days": ["monday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_location = create_response.headers["Location"]

    response = app_client.get(f"{menu_location}?bulk_action=copy&bulk_scope=concept")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Copy Selected Concepts" in page
    assert "Select Concept" in page
    assert "Select Slot" not in page


def test_menu_detail_route_renders_day_header_selection_mode(app_client):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Bulk Day Selection Menu",
            "service_days": ["monday", "tuesday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_location = create_response.headers["Location"]

    response = app_client.get(f"{menu_location}?bulk_action=clear&bulk_scope=day")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Select Day" in page
    assert "Select Slot" not in page


def test_menu_detail_route_renders_week_clear_confirmation_without_checkboxes(app_client):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Bulk Week Clear Menu",
            "service_days": ["monday", "tuesday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_location = create_response.headers["Location"]

    response = app_client.get(f"{menu_location}?bulk_action=clear&bulk_scope=week")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Clear Week 1" in page
    assert "No cell selection is needed here." in page
    assert "Select Slot" not in page
    assert "Select Day" not in page
    assert "Select Concept" not in page


def test_menu_bulk_copy_and_paste_routes_work_for_cell_mode(app_client, isolated_db):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Bulk Cell Route Menu",
            "service_days": ["monday", "tuesday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])
    base_food_id = create_base_food(item_name="Bulk Cell Route Item")

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT menu_slot_id FROM menu_slot WHERE menu_id = ? ORDER BY menu_slot_id ASC",
        (menu_id,),
    )
    source_slot_id, target_slot_id = [row[0] for row in cursor.fetchall()]
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (base_food_id,))
    conn.commit()
    conn.close()

    app_client.post(
        f"/menus/{menu_id}/slots/{source_slot_id}/assign",
        data={"week": "1", "selected_item_ids": [str(base_food_id)]},
        follow_redirects=False,
    )

    copy_response = app_client.post(
        f"/menus/{menu_id}/bulk-action",
        data={
            "week": "1",
            "action": "copy",
            "scope": "cell",
            "selected_slot_ids": [str(source_slot_id)],
        },
        follow_redirects=True,
    )
    paste_response = app_client.post(
        f"/menus/{menu_id}/bulk-action",
        data={
            "week": "1",
            "action": "paste",
            "selected_slot_ids": [str(target_slot_id)],
        },
        follow_redirects=True,
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT item_id FROM menu_slot_item WHERE menu_slot_id = ?", (target_slot_id,))
    pasted_item_id = cursor.fetchone()[0]
    conn.close()

    assert copy_response.status_code == 200
    assert "Copied 1 cell." in copy_response.get_data(as_text=True)
    assert paste_response.status_code == 200
    assert "Pasted into 1 slot." in paste_response.get_data(as_text=True)
    assert pasted_item_id == base_food_id


def test_menu_bulk_clear_route_supports_day_scope(app_client, isolated_db):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Bulk Day Clear Menu",
            "service_days": ["monday", "tuesday"],
            "meal_periods": ["lunch", "dinner"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])
    base_food_id = create_base_food(item_name="Bulk Day Clear Item")

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (base_food_id,))
    cursor.execute(
        """
        SELECT menu_slot_id
        FROM menu_slot
        WHERE menu_id = ?
          AND week_number = 1
          AND day_of_week = 'monday'
        ORDER BY menu_slot_id ASC
        """,
        (menu_id,),
    )
    monday_slot_id = cursor.fetchone()[0]
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    all_slot_ids = [row[0] for row in cursor.fetchall()]
    conn.commit()
    conn.close()

    for slot_id in all_slot_ids:
        app_client.post(
            f"/menus/{menu_id}/slots/{slot_id}/assign",
            data={"week": "1", "selected_item_ids": [str(base_food_id)]},
            follow_redirects=False,
        )

    response = app_client.post(
        f"/menus/{menu_id}/bulk-action",
        data={
            "week": "1",
            "action": "clear",
            "scope": "day",
            "selected_slot_ids": [str(monday_slot_id)],
        },
        follow_redirects=True,
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM menu_slot_item msi
        JOIN menu_slot ms ON ms.menu_slot_id = msi.menu_slot_id
        WHERE ms.menu_id = ?
          AND ms.day_of_week = 'monday'
        """,
        (menu_id,),
    )
    monday_count = cursor.fetchone()[0]
    conn.close()

    assert response.status_code == 200
    assert "Cleared 2 slots." in response.get_data(as_text=True)
    assert monday_count == 0


def test_clear_menu_slot_route_removes_assignments(app_client, isolated_db):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Clear Route Menu",
            "service_days": ["monday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])
    base_food_id = create_base_food(item_name="Clear Route Lettuce")

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (base_food_id,))
    conn.commit()
    conn.close()

    app_client.post(
        f"/menus/{menu_id}/slots/{menu_slot_id}/assign",
        data={"week": "1", "selected_item_ids": [str(base_food_id)]},
        follow_redirects=False,
    )

    response = app_client.post(
        f"/menus/{menu_id}/slots/{menu_slot_id}/clear",
        data={"week": "1"},
        follow_redirects=True,
    )
    page = response.get_data(as_text=True)

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM menu_slot_item WHERE menu_slot_id = ?", (menu_slot_id,))
    item_count = cursor.fetchone()[0]
    conn.close()

    assert response.status_code == 200
    assert "Cleared slot assignments." in page
    assert item_count == 0


def test_paste_menu_slot_route_requires_copied_items(app_client, isolated_db):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Paste Empty Menu",
            "service_days": ["monday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    conn.close()

    response = app_client.post(
        f"/menus/{menu_id}/slots/{menu_slot_id}/paste",
        data={"week": "1"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "No copied slot items are available to paste." in response.get_data(as_text=True)


def test_delete_menu_route_removes_menu_and_redirects_to_my_menus(app_client, isolated_db):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Delete Route Menu",
            "service_days": ["monday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])

    response = app_client.post(
        f"/menus/{menu_id}/delete",
        follow_redirects=True,
    )
    page = response.get_data(as_text=True)

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM menu WHERE menu_id = ?", (menu_id,))
    menu_count = cursor.fetchone()[0]
    conn.close()

    assert response.status_code == 200
    assert "Menu deleted successfully." in page
    assert menu_count == 0


def test_delete_menu_route_rejects_non_owner(app_client, isolated_db):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Protected Route Menu",
            "service_days": ["monday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])

    app_client.post(
        "/login/select",
        data={"selected_user_id": "reviewer_001"},
        follow_redirects=False,
    )

    response = app_client.post(
        f"/menus/{menu_id}/delete",
        follow_redirects=True,
    )
    page = response.get_data(as_text=True)

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM menu WHERE menu_id = ?", (menu_id,))
    menu_count = cursor.fetchone()[0]
    conn.close()

    assert response.status_code == 200
    assert "You can only delete menus you created." in page
    assert menu_count == 1


def test_new_menu_post_shows_validation_error_for_missing_selections(app_client):
    response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Invalid Menu",
            "menu_length_weeks": "1",
        },
        follow_redirects=True,
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Select at least one service day." in page


def test_preferences_route_updates_current_user_defaults(app_client):
    response = app_client.post(
        "/preferences",
        data={
            "display_mode": "mass",
            "unit_system": "metric",
        },
        follow_redirects=True,
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Preferences updated for Plato Choi." in page
    assert "Mass" in page
    assert "Metric" in page


def test_item_detail_shows_edit_link_for_allowed_roles(app_client):
    item_id = create_base_food(item_name="Editable Celery")
    app_client.post(
        "/login/select",
        data={"selected_user_id": "reviewer_001"},
        follow_redirects=False,
    )

    response = app_client.get(f"/items/{item_id}")

    assert "Edit Item" in response.get_data(as_text=True)


def test_item_detail_hides_edit_link_for_standard_user(app_client):
    item_id = create_base_food(item_name="Readonly Celery")

    response = app_client.get(f"/items/{item_id}")

    assert "Edit Item" not in response.get_data(as_text=True)


def test_recipe_legacy_route_redirects_to_item_detail(app_client):
    item_id = create_base_food(item_name="Pepperoni")

    response = app_client.get(f"/recipes/{item_id}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/items/{item_id}")


def test_api_search_items_returns_json_results(app_client, isolated_db):
    item_id = create_base_food(item_name="Liquid Egg")

    # Route search is restricted to live items only.
    # Direct sqlite use keeps this aligned with the current workflow rule.
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (item_id,))
    conn.commit()
    conn.close()

    response = app_client.get("/api/items/search?q=egg")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["items"]
    assert payload["items"][0]["item_name"] == "Liquid Egg"
    assert payload["has_more"] is False


def test_api_search_items_returns_empty_results_for_short_queries(app_client):
    create_base_food(item_name="Table Salt")

    response = app_client.get("/api/items/search?q=s")

    assert response.status_code == 200
    assert response.get_json()["items"] == []


def test_api_search_items_excludes_non_live_results(app_client, isolated_db):
    live_item_id = create_base_food(item_name="Live Pepper")
    create_base_food(item_name="Submitted Pepper")

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (live_item_id,))
    conn.commit()
    conn.close()

    response = app_client.get("/api/items/search?q=pepper")
    payload = response.get_json()

    assert response.status_code == 200
    assert any(result["item_name"] == "Live Pepper" for result in payload["items"])
    assert all(result["status"] == "live" for result in payload["items"])


def test_api_search_items_supports_offset_pagination(app_client, isolated_db):
    created_ids = []
    for index in range(18):
        created_ids.append(create_base_food(item_name=f"Offset Search Item {index:02d}"))

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE item SET status = 'live' WHERE item_id IN ({})".format(
            ", ".join("?" for _ in created_ids)
        ),
        created_ids,
    )
    conn.commit()
    conn.close()

    response = app_client.get("/api/items/search?q=offset&limit=10&offset=10")
    payload = response.get_json()

    assert response.status_code == 200
    assert len(payload["items"]) == 8
    assert payload["has_more"] is False
    assert payload["next_offset"] == 18


def test_api_search_items_supports_fuzzy_typo_matches(app_client, isolated_db):
    chicken_id = create_base_food(item_name="Chicken Soup Base")
    celery_id = create_base_food(item_name="Celery Soup Base")

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE item SET status = 'live' WHERE item_id IN (?, ?)",
        (chicken_id, celery_id),
    )
    conn.commit()
    conn.close()

    response = app_client.get("/api/items/search?q=chikcen")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["items"]
    assert payload["items"][0]["item_name"] == "Chicken Soup Base"


def test_api_search_items_supports_relaxed_short_query_fallback(app_client, isolated_db):
    mayo_id = create_base_food(item_name="Mayo")

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (mayo_id,))
    conn.commit()
    conn.close()

    default_response = app_client.get("/api/items/search?q=nayo")
    relaxed_response = app_client.get("/api/items/search?q=nayo&relax_short_query=1")

    assert default_response.status_code == 200
    assert default_response.get_json()["items"] == []
    assert relaxed_response.status_code == 200
    assert relaxed_response.get_json()["items"]
    assert relaxed_response.get_json()["items"][0]["item_name"] == "Mayo"


def test_item_detail_returns_404_for_missing_item(app_client):
    response = app_client.get("/items/9999")

    assert response.status_code == 404
    assert "Item not found." in response.get_data(as_text=True)


def test_my_recipes_route_renders_recipe_list_and_filters(app_client, isolated_db):
    dressing_id = create_base_food(item_name="Dijon Dressing")

    app_client.post(
        "/api/recipes",
        json={
            "item_name": "Lunch Salad",
            "yield_quantity": 2,
            "yield_unit": "each",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Prep greens", "Dress salad"],
            "ingredients": [
                {
                    "component_item_id": dressing_id,
                    "component_quantity": 2,
                    "component_unit": "oz",
                }
            ],
        },
    )
    second_response = app_client.post(
        "/api/recipes",
        json={
            "item_name": "Dinner Salad",
            "yield_quantity": 4,
            "yield_unit": "each",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Prep", "Plate"],
            "ingredients": [
                {
                    "component_item_id": dressing_id,
                    "component_quantity": 4,
                    "component_unit": "oz",
                }
            ],
        },
    )

    recipe_id = second_response.get_json()["recipe_item_id"]

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE item SET status = ? WHERE item_id = ?",
        ("reviewed", recipe_id),
    )
    conn.commit()
    conn.close()

    response = app_client.get("/my-recipes?status=reviewed&sort=name_asc")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "My Recipes" in page
    assert "Dinner Salad" in page
    assert "Lunch Salad" not in page
    assert "Reviewed" in page


def test_my_recipes_route_shows_empty_state(app_client):
    response = app_client.get("/my-recipes")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "No recipes found" in page


def test_live_collection_route_lists_live_items_only(app_client, isolated_db):
    live_item_id = create_base_food(item_name="Collection Celery")
    create_base_food(item_name="Collection Draft Celery")

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (live_item_id,))
    conn.commit()
    conn.close()

    response = app_client.get("/collection")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Live Collection" in page
    assert "Collection Celery" in page
    assert "Collection Draft Celery" not in page


def test_live_collection_route_supports_filters_and_pagination(app_client, isolated_db):
    recipe_component_id = create_base_food(item_name="Collection Search Oil")
    created_ids = [recipe_component_id]

    for index in range(18):
        created_ids.append(create_base_food(item_name=f"Browse Chicken {index:02d}"))

    recipe_id = create_recipe(
        {
            "item_name": "Collection Recipe Placeholder",
            "yield_quantity": 1,
            "yield_unit": "each",
            "primary_cooking_method_code": "bake",
            "instruction_steps": ["Mix", "Bake"],
            "ingredients": [
                {
                    "component_item_id": recipe_component_id,
                    "component_quantity": 1,
                    "component_unit": "oz",
                }
            ],
        }
    )
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    created_ids.append(recipe_id)
    cursor.execute(
        "UPDATE item SET status = 'live' WHERE item_id IN ({})".format(
            ", ".join("?" for _ in created_ids)
        ),
        created_ids,
    )
    conn.commit()
    conn.close()

    filtered_response = app_client.get("/collection?q=Browse&item_type=base_food&sort=name_asc&offset=15")
    filtered_page = filtered_response.get_data(as_text=True)
    recipe_only_response = app_client.get("/collection?item_type=recipe")
    recipe_only_page = recipe_only_response.get_data(as_text=True)

    assert filtered_response.status_code == 200
    assert "Browse Chicken 15" in filtered_page
    assert "Previous" in filtered_page
    assert "Next" not in filtered_page or "is-disabled\">Next" in filtered_page
    assert recipe_only_response.status_code == 200
    assert "Collection Recipe Placeholder" in recipe_only_page


def test_live_collection_route_shows_minimum_query_message(app_client):
    response = app_client.get("/collection?q=c")

    assert response.status_code == 200
    assert "Enter at least 2 characters" in response.get_data(as_text=True)


def test_live_collection_route_supports_fuzzy_query_matches(app_client, isolated_db):
    chicken_id = create_base_food(item_name="Chicken Rice Bowl")
    celery_id = create_base_food(item_name="Celery Rice Bowl")

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE item SET status = 'live' WHERE item_id IN (?, ?)",
        (chicken_id, celery_id),
    )
    conn.commit()
    conn.close()

    response = app_client.get("/collection?q=chikcen")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Chicken Rice Bowl" in page


def test_notifications_page_shows_note_notifications(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Notification Base")
    recipe_response = app_client.post(
        "/api/recipes",
        json={
            "item_name": "Notification Route Recipe",
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
        },
    )
    recipe_id = recipe_response.get_json()["recipe_item_id"]
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = ? WHERE item_id = ?", ("reviewed", recipe_id))
    conn.commit()
    conn.close()

    app_client.post(
        "/login/select",
        data={"selected_user_id": "reviewer_001"},
        follow_redirects=False,
    )
    app_client.post(
        f"/items/{recipe_id}/notes",
        data={"note_text": "Please review the revised version."},
        follow_redirects=False,
    )

    app_client.post(
        "/login/select",
        data={"selected_user_id": "dev_user_001"},
        follow_redirects=False,
    )
    response = app_client.get("/notifications")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Notification Route Recipe" in page
    assert "Please review the revised version." in page


def test_admin_send_back_to_review_notifies_reviewer(app_client, isolated_db):
    item_id = create_base_food(item_name="Admin Review Return")
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = ? WHERE item_id = ?", ("approved", item_id))
    conn.commit()
    conn.close()

    app_client.post(
        "/login/select",
        data={"selected_user_id": "admin_001"},
        follow_redirects=False,
    )
    app_client.post(
        f"/workflow/items/{item_id}/transition",
        data={
            "portal_name": "admin",
            "action_code": "send_back_review",
            "target_status": "reviewed",
            "reason_text": "Need reviewer follow-up before analysis resumes.",
        },
        follow_redirects=False,
    )

    app_client.post(
        "/login/select",
        data={"selected_user_id": "reviewer_001"},
        follow_redirects=False,
    )
    response = app_client.get("/notifications")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Admin Review Return" in page
    assert "Item sent back from Approved to Reviewed." in page


def test_reviewer_return_to_submitter_notifies_author(app_client):
    base_food_id = create_base_food(item_name="Workflow Notify Oil")
    recipe_response = app_client.post(
        "/api/recipes",
        json={
            "item_name": "Workflow Notify Recipe",
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
        },
    )
    recipe_id = recipe_response.get_json()["recipe_item_id"]

    app_client.post(
        "/login/select",
        data={"selected_user_id": "reviewer_001"},
        follow_redirects=False,
    )
    app_client.post(
        f"/workflow/items/{recipe_id}/transition",
        data={
            "portal_name": "reviewer",
            "action_code": "return_to_submitter",
            "target_status": "submitted",
            "reason_text": "Please revise the seasoning language.",
        },
        follow_redirects=False,
    )

    app_client.post(
        "/login/select",
        data={"selected_user_id": "dev_user_001"},
        follow_redirects=False,
    )
    response = app_client.get("/notifications")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Workflow Notify Recipe" in page
    assert "Recipe returned to submitter." in page


def test_go_live_requires_recipe_mass_and_volume_measurements(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Go Live Measurement Oil")
    recipe_response = app_client.post(
        "/api/recipes",
        json={
            "item_name": "Go Live Measurement Recipe",
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
        },
    )
    recipe_id = recipe_response.get_json()["recipe_item_id"]

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = ? WHERE item_id = ?", ("analyzed", recipe_id))
    conn.commit()
    conn.close()

    app_client.post(
        "/login/select",
        data={"selected_user_id": "reviewer_001"},
        follow_redirects=False,
    )
    response = app_client.post(
        f"/workflow/items/{recipe_id}/transition",
        data={
            "portal_name": "reviewer",
            "action_code": "go_live",
            "target_status": "live",
        },
        follow_redirects=True,
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Recipes must have both mass and volume yield data before they can go live." in page


def test_live_recipe_edit_notifies_author(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Live Edit Notify Oil")
    recipe_response = app_client.post(
        "/api/recipes",
        json={
            "item_name": "Live Edit Notify Recipe",
            "yield_quantity": 1,
            "yield_unit": "each",
            "mass_quantity": 250,
            "mass_unit": "g",
            "volume_quantity": 2,
            "volume_unit": "cup",
            "primary_cooking_method_code": "bake",
            "instruction_steps": ["Mix", "Bake"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "oz",
                }
            ],
        },
    )
    recipe_id = recipe_response.get_json()["recipe_item_id"]

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = ? WHERE item_id = ?", ("live", recipe_id))
    conn.commit()
    conn.close()

    app_client.post(
        "/login/select",
        data={"selected_user_id": "dietitian_001"},
        follow_redirects=False,
    )
    update_response = app_client.put(
        f"/api/recipes/{recipe_id}",
        json={
            "item_name": "Live Edit Notify Recipe",
            "yield_quantity": 1,
            "yield_unit": "each",
            "mass_quantity": 300,
            "mass_unit": "g",
            "volume_quantity": 2.5,
            "volume_unit": "cup",
            "serving_size_quantity": 0.5,
            "serving_size_unit": "cup",
            "serving_count": 5,
            "primary_cooking_method_code": "bake",
            "instruction_steps": ["Mix", "Bake"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "oz",
                }
            ],
        },
    )
    assert update_response.status_code == 200

    app_client.post(
        "/login/select",
        data={"selected_user_id": "dev_user_001"},
        follow_redirects=False,
    )
    response = app_client.get("/notifications")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Live Edit Notify Recipe" in page
    assert "Live recipe updated." in page


def test_item_detail_view_acknowledges_open_notifications(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Viewed Notification Base")
    recipe_response = app_client.post(
        "/api/recipes",
        json={
            "item_name": "Viewed Notification Recipe",
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
        },
    )
    recipe_id = recipe_response.get_json()["recipe_item_id"]

    app_client.post(
        "/login/select",
        data={"selected_user_id": "reviewer_001"},
        follow_redirects=False,
    )
    app_client.post(
        f"/items/{recipe_id}/notes",
        data={"note_text": "Please revise and resubmit."},
        follow_redirects=False,
    )

    app_client.post(
        "/login/select",
        data={"selected_user_id": "dev_user_001"},
        follow_redirects=False,
    )

    response = app_client.get(f"/items/{recipe_id}")
    notifications_response = app_client.get("/notifications")

    assert response.status_code == 200
    assert "Please revise and resubmit." in response.get_data(as_text=True)
    assert "No open notifications" in notifications_response.get_data(as_text=True)


def test_item_detail_view_acknowledges_workflow_action_notifications(app_client):
    base_food_id = create_base_food(item_name="Workflow Ack Oil")
    recipe_response = app_client.post(
        "/api/recipes",
        json={
            "item_name": "Workflow Ack Recipe",
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
        },
    )
    recipe_id = recipe_response.get_json()["recipe_item_id"]

    app_client.post(
        "/login/select",
        data={"selected_user_id": "reviewer_001"},
        follow_redirects=False,
    )
    app_client.post(
        f"/workflow/items/{recipe_id}/transition",
        data={
            "portal_name": "reviewer",
            "action_code": "return_to_submitter",
            "target_status": "submitted",
            "reason_text": "Please clarify the final plating step.",
        },
        follow_redirects=False,
    )

    app_client.post(
        "/login/select",
        data={"selected_user_id": "dev_user_001"},
        follow_redirects=False,
    )
    response = app_client.get(f"/items/{recipe_id}")
    notifications_response = app_client.get("/notifications")

    assert response.status_code == 200
    assert "Recipe returned to submitter." in response.get_data(as_text=True)
    assert "No open notifications" in notifications_response.get_data(as_text=True)


def test_login_create_user_updates_session(app_client):
    response = app_client.post(
        "/login/create-user",
        data={
            "display_name": "Taylor West",
            "role": "reviewer",
        },
        follow_redirects=True,
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Taylor West" in page
    assert "Reviewer" in page


def test_login_select_changes_current_session_user(app_client):
    response = app_client.post(
        "/login/select",
        data={"selected_user_id": "dietitian_001"},
        follow_redirects=True,
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Dana Reed" in page
    assert "Dietitian" in page


def test_login_debug_override_affects_recipe_authorship(app_client, isolated_db):
    app_client.post(
        "/login/debug-override",
        data={
            "override_user_id": "admin_001",
            "override_role": "super_user",
            "override_display_name": "Morgan Debug",
        },
        follow_redirects=False,
    )

    base_food_id = create_base_food(item_name="Debug Dressing")
    create_response = app_client.post(
        "/api/recipes",
        json={
            "item_name": "Override Recipe",
            "yield_quantity": 1,
            "yield_unit": "each",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "oz",
                }
            ],
        },
    )

    recipe_id = create_response.get_json()["recipe_item_id"]
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT author_user_id, author_display_name FROM item WHERE item_id = ?",
        (recipe_id,),
    )
    row = cursor.fetchone()
    conn.close()

    assert row == ("admin_001", "Morgan Debug")


def test_my_recipes_uses_current_mock_user_scope(app_client):
    app_client.post(
        "/login/select",
        data={"selected_user_id": "dietitian_001"},
        follow_redirects=False,
    )

    response = app_client.get("/my-recipes")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Dana Reed" in page
    assert "No recipes found" in page


def test_reviewer_workflow_portal_requires_access(app_client):
    response = app_client.get("/workflow/reviewer", follow_redirects=False)

    assert response.status_code == 302


def test_reviewer_workflow_portal_lists_submitted_items(app_client):
    app_client.post(
        "/login/select",
        data={"selected_user_id": "reviewer_001"},
        follow_redirects=False,
    )
    item_id = create_base_food(item_name="Pending Carrots")

    response = app_client.get("/workflow/reviewer")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Reviewer Portal" in page
    assert "Pending Carrots" in page
    assert f"Item ID {item_id}" in page


def test_workflow_portal_note_post_preserves_filters(app_client, isolated_db):
    item_id = create_base_food(item_name="Portal Notes Item")
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = ? WHERE item_id = ?", ("approved", item_id))
    conn.commit()
    conn.close()

    app_client.post(
        "/login/select",
        data={"selected_user_id": "dietitian_001"},
        follow_redirects=False,
    )

    response = app_client.get("/workflow/dietitian?status=approved&item_type=base_food&sort=name_asc")

    assert response.status_code == 200
    assert "Post Note" not in response.get_data(as_text=True)


def test_workflow_transition_route_updates_status(app_client, isolated_db):
    app_client.post(
        "/login/select",
        data={"selected_user_id": "reviewer_001"},
        follow_redirects=False,
    )
    item_id = create_base_food(item_name="Review Transition Item")

    response = app_client.post(
        f"/workflow/items/{item_id}/transition",
        data={
            "portal_name": "reviewer",
            "action_code": "advance_reviewed",
            "target_status": "reviewed",
        },
        follow_redirects=False,
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM item WHERE item_id = ?", (item_id,))
    row = cursor.fetchone()
    conn.close()

    assert response.status_code == 302
    assert row == ("reviewed",)


def test_workflow_transition_route_requires_reason_for_return_to_submitter(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Reason Prompt Oil")
    recipe_response = app_client.post(
        "/api/recipes",
        json={
            "item_name": "Reason Prompt Recipe",
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
        },
    )
    recipe_id = recipe_response.get_json()["recipe_item_id"]

    app_client.post(
        "/login/select",
        data={"selected_user_id": "reviewer_001"},
        follow_redirects=False,
    )

    response = app_client.post(
        f"/workflow/items/{recipe_id}/transition",
        data={
            "portal_name": "reviewer",
            "action_code": "return_to_submitter",
            "target_status": "submitted",
            "reason_text": "",
        },
        follow_redirects=True,
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT requires_resubmission FROM item WHERE item_id = ?", (recipe_id,))
    row = cursor.fetchone()
    conn.close()

    assert response.status_code == 200
    assert "Revision request is required." in response.get_data(as_text=True)
    assert row == (0,)


def test_workflow_transition_preserves_portal_filters_and_sort(app_client):
    app_client.post(
        "/login/select",
        data={"selected_user_id": "reviewer_001"},
        follow_redirects=False,
    )
    item_id = create_base_food(item_name="Filtered Celery")

    response = app_client.post(
        f"/workflow/items/{item_id}/transition",
        data={
            "portal_name": "reviewer",
            "action_code": "advance_reviewed",
            "target_status": "reviewed",
            "selected_status": "submitted",
            "selected_item_type": "base_food",
            "selected_sort": "name_asc",
        },
        follow_redirects=False,
    )

    location = response.headers["Location"]

    assert response.status_code == 302
    assert "/workflow/reviewer" in location
    assert "status=submitted" in location
    assert "item_type=base_food" in location
    assert "sort=name_asc" in location


def test_dietitian_workflow_portal_lists_approved_items_only(app_client, isolated_db):
    item_id = create_base_food(item_name="Approved Spinach")
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = ? WHERE item_id = ?", ("approved", item_id))
    conn.commit()
    conn.close()

    app_client.post(
        "/login/select",
        data={"selected_user_id": "dietitian_001"},
        follow_redirects=False,
    )

    response = app_client.get("/workflow/dietitian")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Dietitian Portal" in page
    assert "Approved Spinach" in page


def test_admin_portal_can_view_rejected_items(app_client, isolated_db):
    item_id = create_base_food(item_name="Rejected Lettuce")
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = ? WHERE item_id = ?", ("rejected", item_id))
    conn.commit()
    conn.close()

    app_client.post(
        "/login/select",
        data={"selected_user_id": "admin_001"},
        follow_redirects=False,
    )

    response = app_client.get("/workflow/admin?status=rejected")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Admin Workflow Portal" in page
    assert "Rejected Lettuce" in page


def test_edit_item_route_requires_allowed_role(app_client):
    item_id = create_base_food(item_name="Protected Item")

    response = app_client.get(f"/items/{item_id}/edit", follow_redirects=False)

    assert response.status_code == 302


def test_item_detail_page_shows_note_form_when_recipient_is_available(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Detail Notes Base")
    recipe_response = app_client.post(
        "/api/recipes",
        json={
            "item_name": "Detail Notes Recipe",
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
        },
    )
    recipe_id = recipe_response.get_json()["recipe_item_id"]
    app_client.post(
        "/login/select",
        data={"selected_user_id": "reviewer_001"},
        follow_redirects=False,
    )

    response = app_client.get(f"/items/{recipe_id}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Workflow Notes" in page
    assert "Post note to Plato Choi" in page
    assert "Recipe created." in page


def test_live_item_detail_hides_workflow_notes(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Live Notes Base")
    recipe_response = app_client.post(
        "/api/recipes",
        json={
            "item_name": "Live Notes Recipe",
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
        },
    )
    recipe_id = recipe_response.get_json()["recipe_item_id"]

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = ? WHERE item_id = ?", ("live", recipe_id))
    conn.commit()
    conn.close()

    response = app_client.get(f"/items/{recipe_id}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Workflow Notes" not in page
    assert "Post Note" not in page
    assert "Workflow History" not in page


def test_live_item_detail_shows_advanced_workflow_toggle_for_reviewer(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Live Toggle Base")
    recipe_response = app_client.post(
        "/api/recipes",
        json={
            "item_name": "Live Toggle Recipe",
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
        },
    )
    recipe_id = recipe_response.get_json()["recipe_item_id"]

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = ? WHERE item_id = ?", ("live", recipe_id))
    conn.commit()
    conn.close()

    app_client.post(
        "/login/select",
        data={"selected_user_id": "reviewer_001"},
        follow_redirects=False,
    )

    response = app_client.get(f"/items/{recipe_id}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Show Advanced Workflow" in page
    assert "Show Technical Details" in page
    assert "Workflow History" not in page
    assert "Workflow Notes" not in page
    assert "Scaling Foundation" not in page
    assert "Audit" not in page


def test_live_recipe_detail_supports_flattened_ingredient_toggle(app_client, isolated_db):
    salt_id = create_base_food(item_name="Flatten Salt")
    oil_id = create_base_food(item_name="Flatten Oil")
    sauce_id = create_recipe(
        {
            "item_name": "Flatten Sauce",
            "yield_quantity": 2,
            "yield_unit": "cup",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Whisk"],
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
            "item_name": "Flatten Parent Recipe",
            "yield_quantity": 1,
            "yield_unit": "each",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Assemble"],
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
        (salt_id, oil_id, sauce_id, recipe_id),
    )
    conn.commit()
    conn.close()

    default_response = app_client.get(f"/items/{recipe_id}")
    flattened_response = app_client.get(f"/items/{recipe_id}?ingredient_view=flattened")
    default_page = default_response.get_data(as_text=True)
    flattened_page = flattened_response.get_data(as_text=True)

    assert default_response.status_code == 200
    assert "Hierarchical Ingredients" in default_page
    assert "Flattened Ingredients" in default_page
    assert flattened_response.status_code == 200
    assert "Flattened Ingredients" in flattened_page
    assert "according to taste" in flattened_page
    assert "Flattened Sub-Recipe | ID" in flattened_page
    assert "Called from Flatten Parent Recipe" in flattened_page
    assert "From Flatten Sauce" in flattened_page


def test_live_recipe_flattened_view_applies_same_family_conversion(app_client, isolated_db):
    oil_id = create_base_food(item_name="Mismatch Oil")
    sauce_id = create_recipe(
        {
            "item_name": "Mismatch Sauce",
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
            "item_name": "Mismatch Parent Recipe",
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

    response = app_client.get(f"/items/{recipe_id}?ingredient_view=flattened")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Flattening warnings" not in page
    assert "Mismatch Oil" in page
    assert "Called from Mismatch Parent Recipe" in page
    assert "From Mismatch Sauce" in page


def test_recipe_detail_shows_scaling_foundation_summary(app_client, isolated_db):
    oil_id = create_base_food(item_name="Scaling Oil")
    child_recipe_id = create_recipe(
        {
            "item_name": "Scaling Child",
            "yield_quantity": 2,
            "yield_unit": "qt",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {
                    "component_item_id": oil_id,
                    "component_quantity": 2,
                    "component_unit": "oz",
                }
            ],
        }
    )
    recipe_id = create_recipe(
        {
            "item_name": "Scaling Parent",
            "yield_quantity": 1,
            "yield_unit": "gal",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Build"],
            "ingredients": [
                {
                    "component_item_id": child_recipe_id,
                    "component_quantity": 1,
                    "component_unit": "cup",
                }
            ],
        }
    )

    app_client.post(
        "/login/select",
        data={"selected_user_id": "reviewer_001"},
        follow_redirects=False,
    )
    response = app_client.get(f"/items/{recipe_id}?technical_view=advanced")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Scaling Foundation" in page
    assert "Same-Family Conversion" in page
    assert "Same-family conversion ready" in page


def test_standard_user_does_not_see_technical_details_toggle(app_client):
    oil_id = create_base_food(item_name="No Technical Toggle Oil")
    recipe_id = create_recipe(
        {
            "item_name": "No Technical Toggle Recipe",
            "yield_quantity": 1,
            "yield_unit": "each",
            "mass_quantity": 300,
            "mass_unit": "g",
            "volume_quantity": 1,
            "volume_unit": "qt",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {"component_item_id": oil_id, "component_quantity": 1, "component_unit": "oz"},
            ],
        }
    )

    response = app_client.get(f"/items/{recipe_id}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Show Technical Details" not in page
    assert "Scaling Foundation" not in page
    assert "Audit" not in page


def test_live_recipe_flattened_view_warns_on_cycle_detection(app_client, isolated_db):
    base_id = create_base_food(item_name="Cycle Base")
    recipe_a_id = create_recipe(
        {
            "item_name": "Cycle Recipe A",
            "yield_quantity": 1,
            "yield_unit": "cup",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix A"],
            "ingredients": [
                {
                    "component_item_id": base_id,
                    "component_quantity": 1,
                    "component_unit": "oz",
                }
            ],
        }
    )
    recipe_b_id = create_recipe(
        {
            "item_name": "Cycle Recipe B",
            "yield_quantity": 1,
            "yield_unit": "cup",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix B"],
            "ingredients": [
                {
                    "component_item_id": recipe_a_id,
                    "component_quantity": 1,
                    "component_unit": "cup",
                }
            ],
        }
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE recipe_component SET component_item_id = ?, component_unit = 'cup' WHERE parent_recipe_item_id = ?",
        (recipe_b_id, recipe_a_id),
    )
    cursor.execute(
        "UPDATE item SET status = 'live' WHERE item_id IN (?, ?, ?)",
        (base_id, recipe_a_id, recipe_b_id),
    )
    conn.commit()
    conn.close()

    response = app_client.get(f"/items/{recipe_a_id}?ingredient_view=flattened")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Flattening warnings" in page
    assert "Cycle detected while flattening" in page


def test_live_recipe_detail_supports_scaled_hierarchical_view(app_client, isolated_db):
    oil_id = create_base_food(item_name="Route Scaled Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Route Scaled Recipe",
            "yield_quantity": 2,
            "yield_unit": "qt",
            "mass_quantity": 1000,
            "mass_unit": "g",
            "volume_quantity": 2,
            "volume_unit": "qt",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {"component_item_id": oil_id, "component_quantity": 8, "component_unit": "oz"},
            ],
        }
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (oil_id, recipe_id))
    conn.commit()
    conn.close()

    response = app_client.get(f"/items/{recipe_id}?scale_quantity=1&scale_unit=qt")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Scale Recipe" in page
    assert "Scaling to 1.0 qt" in page
    assert "base yield 2.0 qt." in page
    assert "Scaled Ingredients" in page


def test_live_recipe_detail_supports_scaled_flattened_view(app_client, isolated_db):
    oil_id = create_base_food(item_name="Route Flat Oil")
    sauce_id = create_recipe(
        {
            "item_name": "Route Flat Sauce",
            "yield_quantity": 2,
            "yield_unit": "cup",
            "mass_quantity": 500,
            "mass_unit": "g",
            "volume_quantity": 2,
            "volume_unit": "cup",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Whisk"],
            "ingredients": [
                {"component_item_id": oil_id, "component_quantity": 4, "component_unit": "oz"},
            ],
        }
    )
    recipe_id = create_recipe(
        {
            "item_name": "Route Flat Parent",
            "yield_quantity": 1,
            "yield_unit": "each",
            "mass_quantity": 300,
            "mass_unit": "g",
            "volume_quantity": 1,
            "volume_unit": "each",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Assemble"],
            "ingredients": [
                {"component_item_id": sauce_id, "component_quantity": 1, "component_unit": "cup"},
            ],
        }
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?, ?)", (oil_id, sauce_id, recipe_id))
    conn.commit()
    conn.close()

    response = app_client.get(f"/items/{recipe_id}?ingredient_view=flattened&scale_quantity=2&scale_unit=each")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Scaled Flattened Ingredients" in page
    assert "Scaling to 2.0 each" in page
    assert "base yield 1.0 each." in page
    assert "Route Flat Sauce" in page


def test_live_recipe_detail_shows_scaling_warning_for_incompatible_target_unit(app_client, isolated_db):
    oil_id = create_base_food(item_name="Route Warning Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Route Warning Recipe",
            "yield_quantity": 2,
            "yield_unit": "qt",
            "mass_quantity": 1000,
            "mass_unit": "g",
            "volume_quantity": 2,
            "volume_unit": "qt",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {"component_item_id": oil_id, "component_quantity": 8, "component_unit": "oz"},
            ],
        }
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (oil_id, recipe_id))
    conn.commit()
    conn.close()

    response = app_client.get(f"/items/{recipe_id}?scale_quantity=1&scale_unit=each")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Scale target unit &#39;each&#39; is not convertible to recipe yield unit &#39;qt&#39;." in page


def test_live_recipe_detail_supports_recipe_bridge_scaling(app_client, isolated_db):
    oil_id = create_base_food(item_name="Route Bridge Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Route Bridge Recipe",
            "yield_quantity": 2,
            "yield_unit": "qt",
            "mass_quantity": 2000,
            "mass_unit": "g",
            "volume_quantity": 2,
            "volume_unit": "qt",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {"component_item_id": oil_id, "component_quantity": 8, "component_unit": "oz"},
            ],
        }
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (oil_id, recipe_id))
    conn.commit()
    conn.close()

    response = app_client.get(f"/items/{recipe_id}?scale_quantity=1&scale_unit=kg")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Scaling to 1.0 kg" in page
    assert "base yield 2.0 qt." in page
    assert "Scaled Ingredients" in page


def test_live_each_recipe_detail_supports_mass_scaling_via_official_batch_basis(app_client, isolated_db):
    oil_id = create_base_food(item_name="Route Each Mass Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Route Each Mass Recipe",
            "yield_quantity": 10,
            "yield_unit": "each",
            "mass_quantity": 1000,
            "mass_unit": "g",
            "volume_quantity": 1,
            "volume_unit": "qt",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {"component_item_id": oil_id, "component_quantity": 5, "component_unit": "oz"},
            ],
        }
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (oil_id, recipe_id))
    conn.commit()
    conn.close()

    response = app_client.get(f"/items/{recipe_id}?scale_quantity=500&scale_unit=g")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Scaling to 500.0 g" in page
    assert "base yield 10.0 each." in page
    assert "Scaling factor anchored through official batch basis" in page
    assert "1000" in page
    assert "2.5" in page
    assert "oz" in page


def test_live_recipe_detail_shows_measurement_equivalent_for_scaled_base_food(app_client, isolated_db):
    oil_id = create_base_food(item_name="Route Equivalent Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Route Equivalent Recipe",
            "yield_quantity": 2,
            "yield_unit": "qt",
            "mass_quantity": 2000,
            "mass_unit": "g",
            "volume_quantity": 2,
            "volume_unit": "qt",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {"component_item_id": oil_id, "component_quantity": 0.5, "component_unit": "cup"},
            ],
        }
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE item
        SET status = 'live',
            mass_quantity = 216,
            mass_unit = 'g',
            volume_quantity = 1,
            volume_unit = 'cup'
        WHERE item_id = ?
        """,
        (oil_id,),
    )
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (oil_id, recipe_id))
    conn.commit()
    conn.close()

    response = app_client.get(f"/items/{recipe_id}?scale_quantity=1&scale_unit=kg")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Official mass equivalent:" in page
    assert "54" in page


def test_live_recipe_detail_volume_mode_cascades_to_smaller_unit(app_client, isolated_db):
    oil_id = create_base_food(item_name="Route Volume Cascade Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Route Volume Cascade Recipe",
            "yield_quantity": 1,
            "yield_unit": "each",
            "mass_quantity": 400,
            "mass_unit": "g",
            "volume_quantity": 2,
            "volume_unit": "cup",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {"component_item_id": oil_id, "component_quantity": 0.5, "component_unit": "cup"},
            ],
        }
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE item
        SET status = 'live',
            mass_quantity = 216,
            mass_unit = 'g',
            volume_quantity = 1,
            volume_unit = 'cup'
        WHERE item_id = ?
        """,
        (oil_id,),
    )
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (oil_id, recipe_id))
    conn.commit()
    conn.close()

    response = app_client.get(f"/items/{recipe_id}?display_mode=volume&unit_system=imperial")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "8" in page
    assert "tbs" in page
    assert "Official mass equivalent:" not in page


def test_live_recipe_detail_mass_mode_keeps_each_components_as_each(app_client, isolated_db):
    tortilla_id = create_base_food(item_name="Route Tortilla")
    recipe_id = create_recipe(
        {
            "item_name": "Route Tortilla Recipe",
            "yield_quantity": 1,
            "yield_unit": "each",
            "mass_quantity": 300,
            "mass_unit": "g",
            "volume_quantity": 2,
            "volume_unit": "cup",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Assemble"],
            "ingredients": [
                {"component_item_id": tortilla_id, "component_quantity": 1.25, "component_unit": "each"},
            ],
        }
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE item
        SET status = 'live',
            mass_quantity = 60,
            mass_unit = 'g',
            volume_quantity = 1,
            volume_unit = 'each'
        WHERE item_id = ?
        """,
        (tortilla_id,),
    )
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (tortilla_id, recipe_id))
    conn.commit()
    conn.close()

    response = app_client.get(f"/items/{recipe_id}?display_mode=mass&unit_system=metric")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "1.25" in page
    assert "each" in page


def test_live_recipe_detail_uses_saved_user_display_preferences_by_default(app_client, isolated_db):
    oil_id = create_base_food(item_name="Route Saved Preference Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Route Saved Preference Recipe",
            "yield_quantity": 1,
            "yield_unit": "each",
            "mass_quantity": 400,
            "mass_unit": "g",
            "volume_quantity": 2,
            "volume_unit": "cup",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {"component_item_id": oil_id, "component_quantity": 0.5, "component_unit": "cup"},
            ],
        }
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE item
        SET status = 'live',
            mass_quantity = 216,
            mass_unit = 'g',
            volume_quantity = 1,
            volume_unit = 'cup'
        WHERE item_id = ?
        """,
        (oil_id,),
    )
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (oil_id, recipe_id))
    conn.commit()
    conn.close()

    app_client.post(
        "/preferences",
        data={
            "display_mode": "volume",
            "unit_system": "imperial",
        },
        follow_redirects=False,
    )

    response = app_client.get(f"/items/{recipe_id}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "8" in page
    assert "tbs" in page
    assert "Official mass equivalent:" not in page


def test_live_recipe_detail_shows_measurement_equivalent_for_scaled_flattened_base_food(app_client, isolated_db):
    oil_id = create_base_food(item_name="Route Flat Equivalent Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Route Flat Equivalent Recipe",
            "yield_quantity": 2,
            "yield_unit": "kg",
            "mass_quantity": 2000,
            "mass_unit": "g",
            "volume_quantity": 2,
            "volume_unit": "qt",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {"component_item_id": oil_id, "component_quantity": 108, "component_unit": "g"},
            ],
        }
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE item
        SET status = 'live',
            mass_quantity = 216,
            mass_unit = 'g',
            volume_quantity = 1,
            volume_unit = 'cup'
        WHERE item_id = ?
        """,
        (oil_id,),
    )
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (oil_id, recipe_id))
    conn.commit()
    conn.close()

    response = app_client.get(
        f"/items/{recipe_id}?ingredient_view=flattened&scale_quantity=1&scale_unit=qt"
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Scaled Flattened Ingredients" in page
    assert "Official volume equivalent:" in page
    assert "0.25" in page
    assert "cup" in page


def test_live_item_detail_advanced_view_reveals_workflow_history_and_notes_for_reviewer(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Live Advanced Base")
    recipe_response = app_client.post(
        "/api/recipes",
        json={
            "item_name": "Live Advanced Recipe",
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
        },
    )
    recipe_id = recipe_response.get_json()["recipe_item_id"]

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = ? WHERE item_id = ?", ("live", recipe_id))
    conn.commit()
    conn.close()

    app_client.post(
        "/login/select",
        data={"selected_user_id": "reviewer_001"},
        follow_redirects=False,
    )

    response = app_client.get(f"/items/{recipe_id}?workflow_view=advanced")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Hide Advanced Workflow" in page
    assert "Workflow History" in page
    assert "Workflow Notes" in page


def test_live_item_detail_standard_user_cannot_enable_advanced_workflow(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Live Standard Base")
    recipe_response = app_client.post(
        "/api/recipes",
        json={
            "item_name": "Live Standard Recipe",
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
        },
    )
    recipe_id = recipe_response.get_json()["recipe_item_id"]

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = ? WHERE item_id = ?", ("live", recipe_id))
    conn.commit()
    conn.close()

    response = app_client.get(f"/items/{recipe_id}?workflow_view=advanced")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Show Advanced Workflow" not in page
    assert "Workflow History" not in page
    assert "Workflow Notes" not in page


def test_edit_base_food_route_updates_item(app_client, isolated_db):
    item_id = create_base_food(item_name="Old Celery", notes="Old note")
    app_client.post(
        "/login/select",
        data={"selected_user_id": "reviewer_001"},
        follow_redirects=False,
    )

    response = app_client.post(
        f"/items/{item_id}/edit",
        data={
            "item_name": "New Celery",
            "notes": "Updated note",
        },
        follow_redirects=False,
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT item_name, notes FROM item WHERE item_id = ?", (item_id,))
    row = cursor.fetchone()
    conn.close()

    assert response.status_code == 302
    assert row == ("New Celery", "Updated note")


def test_edit_base_food_route_allows_dietitian_nutrition_authority_updates(app_client, isolated_db):
    item_id = create_base_food(item_name="Dietitian Celery", notes="Old note")
    app_client.post(
        "/login/select",
        data={"selected_user_id": "dietitian_001"},
        follow_redirects=False,
    )

    response = app_client.post(
        f"/items/{item_id}/edit",
        data={
            "item_name": "Dietitian Celery",
            "notes": "Nutrition entered",
            "mass_quantity": "120",
            "mass_unit": "g",
            "volume_quantity": "1",
            "volume_unit": "cup",
            "nutrition_group": "Vegetable",
            "kcal_per_serving": "16",
            "nutrition_serving_mass_quantity": "100",
            "nutrition_serving_mass_unit": "g",
            "nutrition_serving_volume_quantity": "1",
            "nutrition_serving_volume_unit": "cup",
        },
        follow_redirects=False,
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT nutrition_group, kcal_per_serving
        FROM item
        WHERE item_id = ?
        """,
        (item_id,),
    )
    row = cursor.fetchone()
    conn.close()

    assert response.status_code == 302
    assert row == ("Vegetable", 16.0)


def test_base_food_detail_shows_nutrition_authority_only_for_privileged_technical_view(app_client, isolated_db):
    item_id = create_base_food(item_name="Privileged Nutrition Celery")
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE item
        SET nutrition_group = ?, kcal_per_serving = ?, nutrition_serving_mass_quantity = ?, nutrition_serving_mass_unit = ?
        WHERE item_id = ?
        """,
        ("Vegetable", 16, 100, "g", item_id),
    )
    conn.commit()
    conn.close()

    standard_response = app_client.get(f"/items/{item_id}")
    standard_page = standard_response.get_data(as_text=True)

    app_client.post(
        "/login/select",
        data={"selected_user_id": "dietitian_001"},
        follow_redirects=False,
    )
    privileged_response = app_client.get(f"/items/{item_id}?technical_view=advanced")
    privileged_page = privileged_response.get_data(as_text=True)

    assert standard_response.status_code == 200
    assert "Nutrition Authority" not in standard_page
    assert privileged_response.status_code == 200
    assert "Nutrition Authority" in privileged_page
    assert "Vegetable" in privileged_page


def test_base_food_detail_supports_privileged_conversion_preview(app_client, isolated_db):
    item_id = create_base_food(item_name="Preview Olive Oil")
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE item
        SET status = 'live',
            mass_quantity = 216,
            mass_unit = 'g',
            volume_quantity = 1,
            volume_unit = 'cup'
        WHERE item_id = ?
        """,
        (item_id,),
    )
    conn.commit()
    conn.close()

    app_client.post(
        "/login/select",
        data={"selected_user_id": "dietitian_001"},
        follow_redirects=False,
    )
    response = app_client.get(f"/items/{item_id}?technical_view=advanced&convert_quantity=1&convert_unit=tbs")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Convert Base Food" in page
    assert "1.0 tbs" in page
    assert "maps to 13.5" in page
    assert "official mass" in page


def test_base_food_detail_conversion_preview_shows_warning_for_incompatible_unit(app_client, isolated_db):
    item_id = create_base_food(item_name="Preview Salt")
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE item
        SET status = 'live',
            mass_quantity = 288,
            mass_unit = 'g',
            volume_quantity = 1,
            volume_unit = 'cup'
        WHERE item_id = ?
        """,
        (item_id,),
    )
    conn.commit()
    conn.close()

    app_client.post(
        "/login/select",
        data={"selected_user_id": "dietitian_001"},
        follow_redirects=False,
    )
    response = app_client.get(f"/items/{item_id}?technical_view=advanced&convert_quantity=1&convert_unit=each")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Conversion warnings" in page
    assert "not convertible" in page


def test_edit_recipe_route_renders_for_allowed_role(app_client):
    base_food_id = create_base_food(item_name="Edit Dressing")
    recipe_response = app_client.post(
        "/api/recipes",
        json={
            "item_name": "Edit Recipe",
            "yield_quantity": 1,
            "yield_unit": "each",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "oz",
                }
            ],
        },
    )
    recipe_id = recipe_response.get_json()["recipe_item_id"]

    app_client.post(
        "/login/select",
        data={"selected_user_id": "admin_001"},
        follow_redirects=False,
    )

    response = app_client.get(f"/items/{recipe_id}/edit")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Edit Recipe" in page
    assert "Edit Recipe" in page


def test_api_update_recipe_updates_existing_recipe(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Edit Oil")
    create_response = app_client.post(
        "/api/recipes",
        json={
            "item_name": "Editable Recipe",
            "yield_quantity": 1,
            "yield_unit": "each",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "oz",
                }
            ],
        },
    )
    recipe_id = create_response.get_json()["recipe_item_id"]

    app_client.post(
        "/login/select",
        data={"selected_user_id": "dietitian_001"},
        follow_redirects=False,
    )

    response = app_client.put(
        f"/api/recipes/{recipe_id}",
        json={
            "item_name": "Updated Editable Recipe",
            "yield_quantity": 2,
            "yield_unit": "each",
            "notes": "Updated by dietitian",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix", "Plate"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 2,
                    "component_unit": "oz",
                }
            ],
            "meal_classification": "Lunch",
        },
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT item_name, notes, meal_classification, author_display_name FROM item WHERE item_id = ?",
        (recipe_id,),
    )
    row = cursor.fetchone()
    conn.close()

    assert response.status_code == 200
    assert row == (
        "Updated Editable Recipe",
        "Updated by dietitian",
        "Lunch",
        "Plato Choi",
    )


def test_returned_recipe_can_be_edited_by_author_and_clears_resubmission_flag(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Resubmit Detail Oil")
    create_response = app_client.post(
        "/api/recipes",
        json={
            "item_name": "Returned Recipe",
            "yield_quantity": 1,
            "yield_unit": "each",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "oz",
                }
            ],
        },
    )
    recipe_id = create_response.get_json()["recipe_item_id"]

    app_client.post(
        "/login/select",
        data={"selected_user_id": "reviewer_001"},
        follow_redirects=False,
    )
    app_client.post(
        f"/workflow/items/{recipe_id}/transition",
        data={
            "portal_name": "reviewer",
            "action_code": "return_to_submitter",
            "target_status": "submitted",
            "reason_text": "Please add a clearer final step.",
        },
        follow_redirects=False,
    )

    app_client.post(
        "/login/select",
        data={"selected_user_id": "dev_user_001"},
        follow_redirects=False,
    )

    edit_page = app_client.get(f"/items/{recipe_id}/edit")
    update_response = app_client.put(
        f"/api/recipes/{recipe_id}",
        json={
            "item_name": "Returned Recipe Revised",
            "yield_quantity": 1,
            "yield_unit": "each",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix", "Serve"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "oz",
                }
            ],
        },
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT item_name, requires_resubmission FROM item WHERE item_id = ?",
        (recipe_id,),
    )
    row = cursor.fetchone()
    conn.close()

    assert edit_page.status_code == 200
    assert update_response.status_code == 200
    assert row == ("Returned Recipe Revised", 0)


def test_item_detail_history_shows_transition_reason_and_note_event(app_client, isolated_db):
    base_food_id = create_base_food(item_name="History Detail Oil")
    recipe_response = app_client.post(
        "/api/recipes",
        json={
            "item_name": "History Detail Recipe",
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
        },
    )
    recipe_id = recipe_response.get_json()["recipe_item_id"]

    app_client.post(
        "/login/select",
        data={"selected_user_id": "reviewer_001"},
        follow_redirects=False,
    )
    app_client.post(
        f"/items/{recipe_id}/notes",
        data={"note_text": "Please check the seasoning wording."},
        follow_redirects=False,
    )
    app_client.post(
        f"/workflow/items/{recipe_id}/transition",
        data={
            "portal_name": "reviewer",
            "action_code": "return_to_submitter",
            "target_status": "submitted",
            "reason_text": "Clarify the final plating step.",
        },
        follow_redirects=False,
    )

    app_client.post(
        "/login/select",
        data={"selected_user_id": "dev_user_001"},
        follow_redirects=False,
    )
    response = app_client.get(f"/items/{recipe_id}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Workflow History" in page
    assert "Workflow note posted to Plato Choi." in page
    assert "Recipe returned to submitter." in page
    assert "Reason:" in page
    assert "Clarify the final plating step." in page
