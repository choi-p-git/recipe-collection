import sqlite3

from services.inventory_service import create_inventory_location, save_inventory_location_item
from services.item_service import create_base_food
from services.recipe_service import create_recipe


def test_index_and_form_routes_render(app_client):
    assert app_client.get("/").status_code == 200
    base_food_page = app_client.get("/recipe-collection/new/base-food")
    assert base_food_page.status_code == 200
    assert "Yield Quantity" not in base_food_page.get_data(as_text=True)
    recipe_page = app_client.get("/recipe-collection/new/recipe")
    assert recipe_page.status_code == 200
    recipe_page_text = recipe_page.get_data(as_text=True)
    assert "Yield Mass Quantity" in recipe_page_text
    assert "Official Serving Count" not in recipe_page_text
    assert '<option value="pan_full_4"' not in recipe_page_text
    assert app_client.get("/login").status_code == 200
    assert app_client.get("/preferences").status_code == 200
    assert app_client.get("/menus").status_code == 200
    assert app_client.get("/menus/new").status_code == 200

    new_menu_page = app_client.get("/menus/new").get_data(as_text=True)
    assert 'type="date"' in new_menu_page
    assert "data-menu-date-range" in new_menu_page
    assert "data-menu-date-summary" in new_menu_page


def test_new_base_food_post_redirects_to_item_detail(app_client):
    response = app_client.post(
        "/recipe-collection/new/base-food",
        data={
            "item_name": "Honey Ham",
            "notes": "Thin sliced.",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/recipe-collection/items/" in response.headers["Location"]


def test_item_detail_route_renders_base_food(app_client):
    item_id = create_base_food(item_name="Shredded Carrots")

    response = app_client.get(f"/recipe-collection/items/{item_id}")

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
        "/recipe-collection/api/recipes",
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
    response = app_client.get(f"/recipe-collection/items/{payload['recipe_item_id']}")
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
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-17",
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

    delete_response = app_client.post(
        f"/menus/{menu_row[0]}/delete",
        follow_redirects=False,
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM menu WHERE menu_id = ?", (menu_row[0],))
    menu_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM menu_slot WHERE menu_id = ?", (menu_row[0],))
    slot_count = cursor.fetchone()[0]
    conn.close()

    assert delete_response.status_code == 302
    assert delete_response.headers["Location"].endswith("/menus")
    assert menu_count == 0
    assert slot_count == 0


def test_new_menu_post_requires_date_range(app_client):
    response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Missing Date Menu",
            "service_days": ["monday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Menu start date and end date are required." in page


def test_menu_detail_route_renders_week_overview(app_client):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Week Test Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-17",
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


def test_my_menus_route_renders_current_user_menus(app_client, monkeypatch):
    from datetime import date

    import app as app_module

    monkeypatch.setattr(app_module, "_current_service_date", lambda: date(2026, 5, 20))

    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Owner Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-24",
            "service_days": ["monday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )

    assert create_response.status_code == 302
    menu_location = create_response.headers["Location"]

    response = app_client.get("/menus")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "My Menus" in page
    assert "Owner Menu" in page
    assert "2026-05-04 to 2026-05-24" in page
    assert "Current week 3" in page
    assert f"{menu_location}?week=3" in page
    assert "Open Current Week" in page
    assert "Future Menu Workspaces" in page


def test_my_menus_route_shows_delete_action(app_client):
    app_client.post(
        "/menus/new",
        data={
            "menu_name": "Delete Action Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
            "menu_start_date": "2026-05-18",
            "menu_end_date": "2026-05-22",
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
    assert "May 18" in page
    assert "Pending Assignment" in page
    assert "menu_slot_assign.js" in page


def test_menu_detail_route_shows_delete_action(app_client):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Delete Detail Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
    assert "Edit Menu Config" in page
    assert "Delete Menu" in page
    assert "Forecasting" in page
    assert "Production Record" in page
    assert "/forecast" in page
    assert "/forecast?week=1" in page
    assert "/production-record" in page
    assert "/production-record?week=1" in page
    assert "/print?week=1" in page
    assert "Bulk Slot Actions" in page
    assert "Update Bulk Mode" in page
    assert "menu_detail.js" in page
    assert "Menu Summary" in page


def test_menu_detail_route_shows_service_dates(app_client):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Dated Detail Menu",
            "menu_start_date": "2026-05-18",
            "menu_end_date": "2026-05-31",
            "service_days": ["monday", "wednesday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_location = create_response.headers["Location"]

    response = app_client.get(f"{menu_location}?week=2")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Week 2 Overview" in page
    assert "May 25" in page
    assert "May 27" in page


def test_menu_detail_route_defaults_to_current_menu_week(app_client, monkeypatch):
    from datetime import date

    import app as app_module

    monkeypatch.setattr(app_module, "_current_service_date", lambda: date(2026, 5, 20))

    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Current Week Detail Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-24",
            "service_days": ["monday", "wednesday"],
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
    assert "Week 3 Overview" in page
    assert "May 18" in page
    assert "May 20" in page


def test_menu_forecast_route_renders_day_recipes_in_menu_order(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Forecast Route Rice")
    lunch_recipe_id = create_recipe(
        {
            "item_name": "Forecast Route Bowl",
            "yield_quantity": 12,
            "yield_unit": "each",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Build bowls"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 2,
                    "component_unit": "cup",
                }
            ],
        }
    )
    dinner_recipe_id = create_recipe(
        {
            "item_name": "Forecast Route Supper",
            "yield_quantity": 3,
            "yield_unit": "gal",
            "primary_cooking_method_code": "simmer",
            "instruction_steps": ["Simmer"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "lb",
                }
            ],
        }
    )
    base_food_slot_item_id = create_base_food(item_name="Forecast Route Apple")

    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Forecast Route Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-06-07",
            "service_days": ["monday", "wednesday"],
            "meal_periods": ["lunch", "dinner"],
            "concepts": ["hot_line", "salad_bar"],
            "menu_length_weeks": "5",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE item SET status = 'live' WHERE item_id IN (?, ?, ?, ?)",
        (base_food_id, lunch_recipe_id, dinner_recipe_id, base_food_slot_item_id),
    )
    cursor.execute(
        """
        SELECT menu_slot_id, meal_period, concept_name
        FROM menu_slot
        WHERE menu_id = ?
          AND week_number = 3
          AND day_of_week = 'wednesday'
        """,
        (menu_id,),
    )
    slot_lookup = {
        (meal_period, concept_name): menu_slot_id
        for menu_slot_id, meal_period, concept_name in cursor.fetchall()
    }
    conn.commit()
    conn.close()
    inventory_location_id = create_inventory_location(
        location_name="Forecast Route Storage",
        actor_user_id="dev_user_001",
        actor_display_name="Plato Choi",
    )
    save_inventory_location_item(
        inventory_location_id=inventory_location_id,
        item_id=base_food_slot_item_id,
        count_each_quantity="9",
        unit_of_measurement="Lb",
        count_type="counted_by_each_only",
    )

    app_client.post(
        f"/menus/{menu_id}/slots/{slot_lookup[('lunch', 'hot_line')]}/assign",
        data={"week": "3", "selected_item_ids": [str(lunch_recipe_id), str(base_food_slot_item_id)]},
        follow_redirects=False,
    )
    app_client.post(
        f"/menus/{menu_id}/slots/{slot_lookup[('dinner', 'salad_bar')]}/assign",
        data={"week": "3", "selected_item_ids": [str(dinner_recipe_id)]},
        follow_redirects=False,
    )

    response = app_client.get(f"/menus/{menu_id}/forecast?week=3&day=wednesday")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Items For Wednesday, Week 3" in page
    assert "Cycle Weeks 1-4" in page
    assert "Forecast Route Bowl" in page
    assert "Forecast Route Supper" in page
    assert "Forecast Route Apple" in page
    assert page.index("Forecast Route Bowl") < page.index("Forecast Route Supper")
    assert "<th>Batches</th>" in page
    assert "<th>Scale by Yield</th>" in page
    assert "<th>User Serving Size</th>" in page
    assert "<th>Desired Portions</th>" in page
    assert "<th>Portions Made</th>" in page
    assert "<th>Inventory</th>" in page
    assert "9 lb on hand" in page
    assert "menu_forecast.js" in page
    assert "data-forecast-control" in page
    assert "data-batch-display-unit" in page
    assert "data-production-display-control" in page
    assert "data-user-serving-control" in page
    assert "data-desired-portions" in page
    assert "data-user-serving-result" in page
    assert '<option value="each" selected>each</option>' in page
    assert '<option value="gal" selected>gal</option>' in page


def test_menu_forecast_shows_item_occurrence_history(app_client, isolated_db):
    base_food_id = create_base_food(item_name="History Forecast Apple")
    recipe_id = create_recipe(
        {
            "item_name": "History Forecast Crisp",
            "yield_quantity": 10,
            "yield_unit": "each",
            "primary_cooking_method_code": "bake",
            "instruction_steps": ["Bake"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 2,
                    "component_unit": "each",
                }
            ],
        }
    )
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "History Forecast Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
            "service_days": ["monday", "wednesday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (base_food_id, recipe_id))
    cursor.execute(
        """
        SELECT menu_slot_id, day_of_week
        FROM menu_slot
        WHERE menu_id = ?
        ORDER BY day_of_week
        """,
        (menu_id,),
    )
    slot_lookup = {day_of_week: menu_slot_id for menu_slot_id, day_of_week in cursor.fetchall()}
    conn.commit()
    conn.close()

    for day in ("monday", "wednesday"):
        app_client.post(
            f"/menus/{menu_id}/slots/{slot_lookup[day]}/assign",
            data={"week": "1", "selected_item_ids": [str(recipe_id), str(base_food_id)]},
            follow_redirects=False,
        )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT msi.menu_slot_item_id, msi.item_id
        FROM menu_slot_item msi
        JOIN menu_slot ms
          ON ms.menu_slot_id = msi.menu_slot_id
        WHERE ms.menu_id = ?
          AND ms.day_of_week = 'monday'
        """,
        (menu_id,),
    )
    monday_slot_items = {item_id: menu_slot_item_id for menu_slot_item_id, item_id in cursor.fetchall()}
    conn.close()

    for item_id, quantity in ((recipe_id, "10"), (base_food_id, "4")):
        response = app_client.put(
            f"/api/menus/{menu_id}/forecast/{monday_slot_items[item_id]}",
            json={
                "forecast_yield_quantity": quantity,
                "forecast_yield_unit": "each",
            },
        )
        assert response.status_code == 200

    app_client.get(f"/menus/{menu_id}/production-record?week=1&day=monday")

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT prl.production_record_line_id, prl.item_id
        FROM production_record_line prl
        JOIN production_record pr
          ON pr.production_record_id = prl.production_record_id
        WHERE pr.menu_id = ?
          AND pr.week_number = 1
          AND pr.day_of_week = 'monday'
        """,
        (menu_id,),
    )
    line_lookup = {item_id: line_id for line_id, item_id in cursor.fetchall()}
    conn.close()

    for item_id, actual_quantity, variance_quantity in ((recipe_id, "9", "1"), (base_food_id, "5", "0")):
        response = app_client.put(
            f"/api/menus/{menu_id}/production-record/lines/{line_lookup[item_id]}",
            json={
                "actual_quantity": actual_quantity,
                "actual_unit": "each",
                "end_service_variance_quantity": variance_quantity,
                "end_service_variance_unit": "each",
                "reason_code": "as_expected",
            },
        )
        assert response.status_code == 200

    forecast_response = app_client.get(f"/menus/{menu_id}/forecast?week=1&day=wednesday")
    forecast_page = forecast_response.get_data(as_text=True)

    assert forecast_response.status_code == 200
    assert "History Forecast Crisp" in forecast_page
    assert "History Forecast Apple" in forecast_page
    assert "History" in forecast_page
    assert "Current Menu" in forecast_page
    assert "May 4" in forecast_page
    assert "Forecast 10 each" in forecast_page
    assert "Actual 9 each" in forecast_page
    assert "Demand 8 each" in forecast_page
    assert "Forecast 4 each" in forecast_page
    assert "Actual 5 each" in forecast_page
    assert f"/menus/{menu_id}/service-context?week=1&amp;day=monday" in forecast_page

    context_response = app_client.get(f"/menus/{menu_id}/service-context?week=1&day=monday")
    context_page = context_response.get_data(as_text=True)

    assert context_response.status_code == 200
    assert "Combined Context View" in context_page
    assert "History Forecast Menu" in context_page
    assert "Forecasting" in context_page
    assert "Production Record" in context_page
    assert "Forecast Context" in context_page
    assert "Production Record Context" in context_page
    assert "History Forecast Crisp" in context_page
    assert "Forecast 10 each" not in context_page
    assert "<td>10 each</td>" in context_page
    assert "<td>9 each</td>" in context_page
    assert "<td>1 each</td>" in context_page
    assert "<td>8 each</td>" in context_page


def test_api_update_menu_forecast_persists_scale_by_yield(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Forecast Save Base")
    recipe_id = create_recipe(
        {
            "item_name": "Forecast Save Recipe",
            "yield_quantity": 10,
            "yield_unit": "each",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Portion"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "lb",
                }
            ],
        }
    )
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Forecast Save Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (base_food_id, recipe_id))
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    app_client.post(
        f"/menus/{menu_id}/slots/{menu_slot_id}/assign",
        data={"week": "1", "selected_item_ids": [str(recipe_id)]},
        follow_redirects=False,
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_slot_item_id FROM menu_slot_item WHERE menu_slot_id = ?", (menu_slot_id,))
    menu_slot_item_id = cursor.fetchone()[0]
    conn.close()

    response = app_client.put(
        f"/api/menus/{menu_id}/forecast/{menu_slot_item_id}",
        json={
            "forecast_yield_quantity": "24",
            "forecast_yield_unit": "each",
            "user_serving_size_quantity": "6",
            "user_serving_size_unit": "oz",
            "desired_portions": "80",
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["forecast"]["forecast_yield_quantity"] == 24
    assert payload["forecast"]["forecast_yield_unit"] == "each"
    assert payload["forecast"]["user_serving_size_quantity"] == 6
    assert payload["forecast"]["user_serving_size_unit"] == "oz"
    assert payload["forecast"]["desired_portions"] == 80

    batch_response = app_client.put(
        f"/api/menus/{menu_id}/forecast/{menu_slot_item_id}/batches",
        json={
            "batch_splits": [
                {"batch_percent": "50", "planned_time": "11:00"},
                {"batch_quantity": "6", "planned_time": "11:30"},
                {"batch_quantity": "6", "planned_time": "12:00"},
            ],
        },
    )
    batch_payload = batch_response.get_json()

    assert batch_response.status_code == 200
    assert batch_payload["ok"] is True
    assert [split["batch_percent_display"] for split in batch_payload["batch_plan"]["batch_splits"]] == ["50", "25", "25"]

    page_response = app_client.get(f"/menus/{menu_id}/forecast?week=1&day=monday")
    page = page_response.get_data(as_text=True)

    assert page_response.status_code == 200
    assert 'value="24"' in page
    assert 'value="6"' in page
    assert 'value="80"' in page
    assert '<option value="oz" selected>oz</option>' in page
    assert "✓ Saved" in page
    assert "Production Summary" in page
    assert "Forecast Save Recipe" in page
    assert "<th>Recipe Yield</th>" not in page
    assert f"/recipe-collection/items/{recipe_id}?scale_quantity=24" in page
    assert f"forecast_menu_slot_item_id={menu_slot_item_id}" in page
    assert "24 each" in page
    assert "Batch 1:" in page
    assert "12 each" in page
    assert "(50%)" in page
    assert "@ 11:00" in page


    advanced_response = app_client.get(
        f"/menus/{menu_id}/forecast/recipes/{recipe_id}/advanced"
        f"?menu_slot_item_id={menu_slot_item_id}&week=1&day=monday",
        follow_redirects=True,
    )
    advanced_page = advanced_response.get_data(as_text=True)

    assert advanced_response.status_code == 200
    assert 'name="user_serving_size_quantity"' in advanced_page
    assert 'value="6"' in advanced_page
    assert 'name="desired_portions"' in advanced_page
    assert 'value="80"' in advanced_page
    assert '<option value="oz" selected>oz</option>' in advanced_page


def test_menu_forecast_defaults_to_current_menu_week(app_client, isolated_db, monkeypatch):
    from datetime import date

    import app as app_module

    monkeypatch.setattr(app_module, "_current_service_date", lambda: date(2026, 5, 20))

    base_food_id = create_base_food(item_name="Current Week Forecast Base")
    recipe_id = create_recipe(
        {
            "item_name": "Current Week Forecast Entree",
            "yield_quantity": 8,
            "yield_unit": "each",
            "primary_cooking_method_code": "bake",
            "instruction_steps": ["Bake"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "lb",
                }
            ],
        }
    )
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Current Week Forecast Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-24",
            "service_days": ["monday", "wednesday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (base_food_id, recipe_id))
    cursor.execute(
        """
        SELECT menu_length_weeks
        FROM menu
        WHERE menu_id = ?
        """,
        (menu_id,),
    )
    menu_length_weeks = cursor.fetchone()[0]
    cursor.execute(
        """
        SELECT menu_slot_id
        FROM menu_slot
        WHERE menu_id = ?
          AND week_number = 3
          AND day_of_week = 'wednesday'
        """,
        (menu_id,),
    )
    menu_slot_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    app_client.post(
        f"/menus/{menu_id}/slots/{menu_slot_id}/assign",
        data={"week": "3", "selected_item_ids": [str(recipe_id)]},
        follow_redirects=False,
    )

    page_response = app_client.get(f"/menus/{menu_id}/forecast")
    page = page_response.get_data(as_text=True)

    assert page_response.status_code == 200
    assert menu_length_weeks == 3
    assert "Items For Wednesday, Week 3" in page
    assert "May 20" in page
    assert "Current Week Forecast Entree" in page


def test_production_record_route_defaults_to_current_service_day(app_client, isolated_db, monkeypatch):
    from datetime import date

    import app as app_module

    monkeypatch.setattr(app_module, "_current_day_of_week", lambda: "wednesday")
    monkeypatch.setattr(app_module, "_current_service_date", lambda: date(2026, 5, 20))

    base_food_id = create_base_food(item_name="Current Day Record Base")
    recipe_id = create_recipe(
        {
            "item_name": "Current Day Record Soup",
            "yield_quantity": 8,
            "yield_unit": "each",
            "primary_cooking_method_code": "simmer",
            "instruction_steps": ["Cook"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "cup",
                }
            ],
        }
    )
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Current Day Record Menu",
            "menu_start_date": "2026-05-18",
            "menu_end_date": "2026-05-22",
            "service_days": ["monday", "wednesday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (base_food_id, recipe_id))
    cursor.execute(
        "SELECT menu_slot_id FROM menu_slot WHERE menu_id = ? AND day_of_week = 'wednesday'",
        (menu_id,),
    )
    menu_slot_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    app_client.post(
        f"/menus/{menu_id}/slots/{menu_slot_id}/assign",
        data={"week": "1", "selected_item_ids": [str(recipe_id)]},
        follow_redirects=False,
    )

    page_response = app_client.get(f"/menus/{menu_id}/production-record")
    page = page_response.get_data(as_text=True)

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM production_record pr
        JOIN production_record_line prl
          ON pr.production_record_id = prl.production_record_id
        WHERE pr.menu_id = ?
          AND pr.week_number = 1
          AND pr.day_of_week = 'wednesday'
          AND prl.item_id = ?
        """,
        (menu_id, recipe_id),
    )
    record_count = cursor.fetchone()[0]
    conn.close()

    assert page_response.status_code == 200
    assert "Week 1 | Wednesday" in page
    assert "May 20" in page
    assert "Previous Service Day: May 18" in page
    assert "Next Service Day" in page
    assert "Current Day Record Soup" in page
    assert record_count == 1


def test_production_record_route_snapshots_forecast_and_saves_variance(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Production Record Base")
    recipe_id = create_recipe(
        {
            "item_name": "Production Record Soup",
            "yield_quantity": 10,
            "yield_unit": "each",
            "primary_cooking_method_code": "simmer",
            "instruction_steps": ["Cook"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "cup",
                }
            ],
        }
    )
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Production Record Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (base_food_id, recipe_id))
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    app_client.post(
        f"/menus/{menu_id}/slots/{menu_slot_id}/assign",
        data={"week": "1", "selected_item_ids": [str(recipe_id)]},
        follow_redirects=False,
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_slot_item_id FROM menu_slot_item WHERE menu_slot_id = ?", (menu_slot_id,))
    menu_slot_item_id = cursor.fetchone()[0]
    conn.close()

    forecast_response = app_client.put(
        f"/api/menus/{menu_id}/forecast/{menu_slot_item_id}",
        json={
            "forecast_yield_quantity": "10",
            "forecast_yield_unit": "each",
        },
    )
    assert forecast_response.status_code == 200

    page_response = app_client.get(f"/menus/{menu_id}/production-record?week=1&day=monday")
    page = page_response.get_data(as_text=True)

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT prl.production_record_line_id
        FROM production_record_line prl
        JOIN production_record pr
          ON pr.production_record_id = prl.production_record_id
        WHERE pr.menu_id = ?
          AND pr.week_number = 1
          AND pr.day_of_week = 'monday'
          AND prl.item_id = ?
        """,
        (menu_id, recipe_id),
    )
    production_record_line_id = cursor.fetchone()[0]
    conn.close()

    assert page_response.status_code == 200
    assert "Production Record" in page
    assert "Production Record Soup" in page
    assert "10 each" in page
    assert "End of Service Variance" in page
    assert "Forecast Accuracy" in page
    assert "data-production-record-summary" in page
    assert 'data-unrecorded-count="1"' in page
    assert 'type="text"' in page
    assert 'inputmode="decimal"' in page
    assert "Use Forecast" in page
    assert "Zero Leftover" in page
    assert "Extra Guests" in page
    assert "As Expected" in page
    assert '<select id="production_week" name="week">' in page
    assert "production_record.js" in page
    assert "data-production-record-line" in page

    save_response = app_client.put(
        f"/api/menus/{menu_id}/production-record/lines/{production_record_line_id}",
        json={
            "actual_quantity": "10",
            "actual_unit": "each",
            "end_service_variance_quantity": "1",
            "end_service_variance_unit": "each",
            "reason_code": "other",
            "reason_note": "Late lunch rush",
            "notes": "Use kettle B next time",
        },
    )
    payload = save_response.get_json()

    assert save_response.status_code == 200
    assert payload["line"]["actual_quantity"] == 10
    assert payload["line"]["end_service_variance_quantity"] == 1
    assert payload["line"]["implied_demand_quantity"] == 9
    assert payload["line"]["forecast_error_quantity"] == 1
    assert payload["line"]["forecast_error_percent"] == 10
    assert payload["line"]["forecast_accuracy_level"] == "review"
    assert payload["line"]["reason_code"] == "other"
    assert payload["line"]["reason_note"] == "Late lunch rush"
    assert payload["line"]["notes"] == "Use kettle B next time"

    formula_response = app_client.put(
        f"/api/menus/{menu_id}/production-record/lines/{production_record_line_id}",
        json={
            "actual_quantity": "(4+6)*2",
            "actual_unit": "each",
            "end_service_variance_quantity": "-",
            "end_service_variance_unit": "each",
            "reason_code": "as_expected",
        },
    )
    formula_payload = formula_response.get_json()

    assert formula_response.status_code == 200
    assert formula_payload["line"]["actual_quantity"] == 20
    assert formula_payload["line"]["actual_quantity_formula"] == "(4+6)*2"
    assert formula_payload["line"]["end_service_variance_quantity"] is None
    assert formula_payload["line"]["end_service_variance_quantity_formula"] == "-"

    formula_page_response = app_client.get(f"/menus/{menu_id}/production-record?week=1&day=monday")
    formula_page = formula_page_response.get_data(as_text=True)

    assert formula_page_response.status_code == 200
    assert 'data-formula-value="(4+6)*2"' in formula_page
    assert 'data-formula-value="-"' in formula_page

    draft_formula_response = app_client.put(
        f"/api/menus/{menu_id}/production-record/lines/{production_record_line_id}",
        json={
            "actual_quantity": "2-",
            "actual_unit": "each",
            "end_service_variance_quantity": "0",
            "end_service_variance_unit": "each",
        },
    )
    draft_formula_payload = draft_formula_response.get_json()

    assert draft_formula_response.status_code == 200
    assert draft_formula_payload["line"]["actual_quantity"] is None
    assert draft_formula_payload["line"]["actual_quantity_formula"] == "2-"
    assert draft_formula_payload["line"]["end_service_variance_quantity"] == 0

    invalid_formula_response = app_client.put(
        f"/api/menus/{menu_id}/production-record/lines/{production_record_line_id}",
        json={
            "actual_quantity": "2..5",
            "actual_unit": "each",
            "end_service_variance_quantity": "0",
            "end_service_variance_unit": "each",
        },
    )
    invalid_formula_payload = invalid_formula_response.get_json()

    assert invalid_formula_response.status_code == 400
    assert "formula is incomplete or invalid" in invalid_formula_payload["error"]

    shortage_response = app_client.put(
        f"/api/menus/{menu_id}/production-record/lines/{production_record_line_id}",
        json={
            "actual_quantity": "11",
            "actual_unit": "each",
            "end_service_variance_quantity": "-1",
            "end_service_variance_unit": "each",
            "reason_code": "extra_guests",
        },
    )
    shortage_payload = shortage_response.get_json()

    assert shortage_response.status_code == 200
    assert shortage_payload["line"]["end_service_variance_quantity"] == -1
    assert shortage_payload["line"]["implied_demand_quantity"] == 12
    assert shortage_payload["line"]["forecast_error_quantity"] == -2
    assert shortage_payload["line"]["forecast_error_percent"] == -20
    assert shortage_payload["line"]["forecast_accuracy_level"] == "miss"
    assert shortage_payload["line"]["reason_code"] == "extra_guests"
    assert shortage_payload["line"]["reason_note"] == ""

    accurate_response = app_client.put(
        f"/api/menus/{menu_id}/production-record/lines/{production_record_line_id}",
        json={
            "actual_quantity": "10",
            "actual_unit": "each",
            "end_service_variance_quantity": "0.0004",
            "end_service_variance_unit": "each",
            "reason_code": "as_expected",
        },
    )
    accurate_payload = accurate_response.get_json()

    assert accurate_response.status_code == 200
    assert accurate_payload["line"]["end_service_variance_quantity_display"] == "0"
    assert accurate_payload["line"]["forecast_error_quantity_display"] == "0"
    assert accurate_payload["line"]["forecast_error_percent_display"] == "0.004"
    assert "according to taste" not in str(accurate_payload)

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE production_record_line
        SET forecast_quantity = 1,
            forecast_unit = 'pan_half_4'
        WHERE production_record_line_id = ?
        """,
        (production_record_line_id,),
    )
    conn.commit()
    conn.close()

    pan_response = app_client.put(
        f"/api/menus/{menu_id}/production-record/lines/{production_record_line_id}",
        json={
            "actual_quantity": "1",
            "actual_unit": "pan_half_4",
            "end_service_variance_quantity": "0",
            "end_service_variance_unit": "pan_half_4",
            "reason_code": "as_expected",
        },
    )
    pan_payload = pan_response.get_json()

    assert pan_response.status_code == 200
    assert pan_payload["line"]["implied_demand_unit"] == "pan_half_4"
    assert pan_payload["line"]["implied_demand_unit_label"] == 'Half pan, 4"'

    missing_post_response = app_client.post(
        f"/menus/{menu_id}/production-record/999999/post",
        data={"week": "1", "day": "monday"},
        follow_redirects=True,
    )
    assert "Production record not found." in missing_post_response.get_data(as_text=True)

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT pr.production_record_id
        FROM production_record_line prl
        JOIN production_record pr
          ON pr.production_record_id = prl.production_record_id
        WHERE prl.production_record_line_id = ?
        """,
        (production_record_line_id,),
    )
    production_record_id = cursor.fetchone()[0]
    conn.close()

    post_response = app_client.post(
        f"/menus/{menu_id}/production-record/{production_record_id}/post",
        data={"week": "1", "day": "monday"},
        follow_redirects=True,
    )
    post_page = post_response.get_data(as_text=True)

    assert post_response.status_code == 200
    assert "Production record posted." in post_page
    assert "Posted Production Record" in post_page
    assert "Status: Posted" in post_page
    assert "Print" in post_page
    assert "Use kettle B next time" in post_page
    assert "As Expected" in post_page
    assert "Entry View" in post_page
    assert "History" in post_page
    assert "Export CSV" in post_page

    history_response = app_client.get(f"/menus/{menu_id}/production-record/history")
    history_page = history_response.get_data(as_text=True)

    assert history_response.status_code == 200
    assert "Production Record History" in history_page
    assert "Production Record Menu" in history_page
    assert "May 4" in history_page
    assert "Posted" in history_page
    assert "1 of 1" in history_page
    assert "Accurate 1" in history_page
    assert "Review 0" in history_page
    assert "Miss 0" in history_page
    assert "Reporting Summary" in history_page
    assert "Top Reasons" in history_page
    assert "Leftover / Shortage By Item" in history_page
    assert "reason_sort=lines&amp;reason_dir=desc" in history_page
    assert "variance_sort=leftover&amp;variance_dir=desc" in history_page
    assert "variance_sort=shortage&amp;variance_dir=desc" in history_page
    assert "<td>As Expected</td>" in history_page
    assert "<td>1</td>" in history_page
    assert "Production Record Soup" in history_page
    assert "0 Half pan, 4&#34;" in history_page
    assert "Leftover Occurrences" in history_page
    assert "Shortage Occurrences" in history_page
    assert "production_record_history.js" in history_page
    assert 'name="accuracy"' in history_page
    assert 'name="reason_code"' in history_page
    assert 'name="item"' in history_page
    assert f"/menus/{menu_id}/production-record?week=1&amp;day=monday" in history_page
    assert f"/menus/{menu_id}/production-record/{production_record_id}/review" in history_page
    assert f"/menus/{menu_id}/production-record/{production_record_id}/export.csv" in history_page
    assert f"/menus/{menu_id}/service-context?week=1&amp;day=monday" in history_page

    filtered_history_response = app_client.get(
        f"/menus/{menu_id}/production-record/history?status=posted&accuracy=accurate&reason_code=as_expected&item=Soup"
    )
    filtered_history_page = filtered_history_response.get_data(as_text=True)

    assert filtered_history_response.status_code == 200
    assert "Production Record Soup" in filtered_history_page
    assert 'value="posted" selected' in filtered_history_page
    assert 'value="accurate" selected' in filtered_history_page
    assert 'value="as_expected" selected' in filtered_history_page
    assert 'value="Soup"' in filtered_history_page

    empty_filtered_history_response = app_client.get(
        f"/menus/{menu_id}/production-record/history?date_from=2026-05-05"
    )
    empty_filtered_history_page = empty_filtered_history_response.get_data(as_text=True)

    assert empty_filtered_history_response.status_code == 200
    assert "No production records have been started for this menu." in empty_filtered_history_page

    facts_response = app_client.get(f"/api/menus/{menu_id}/production-record/posted-facts")
    facts_payload = facts_response.get_json()
    facts_contract = facts_payload["contract"]
    fact = facts_contract["facts"][0]

    assert facts_response.status_code == 200
    assert facts_payload["ok"] is True
    assert facts_contract["contract_version"] == "production_record.posted_facts.v1"
    assert facts_contract["source"] == "posted_production_records"
    assert facts_contract["summary"]["record_count"] == 1
    assert facts_contract["summary"]["line_count"] == 1
    assert facts_contract["summary"]["accurate"] == 1
    assert fact["source"] == "production_record_line"
    assert fact["source_status"] == "posted"
    assert fact["production_record_id"] == production_record_id
    assert fact["production_record_line_id"] == production_record_line_id
    assert fact["menu_id"] == menu_id
    assert fact["service_date"] == "2026-05-04"
    assert fact["week_number"] == 1
    assert fact["day_of_week"] == "monday"
    assert fact["item_id"] == recipe_id
    assert fact["item_name"] == "Production Record Soup"
    assert fact["forecast_quantity"] is not None
    assert fact["forecast_unit"]
    assert fact["actual_production_quantity"] == 1
    assert fact["actual_production_unit"] == "pan_half_4"
    assert fact["end_service_variance_quantity"] == 0
    assert fact["leftover_quantity"] == 0
    assert fact["shortage_quantity"] == 0
    assert fact["implied_demand_quantity"] == 1
    assert fact["forecast_error_quantity"] == 0
    assert fact["forecast_accuracy_level"] == "accurate"
    assert fact["reason_code"] == "as_expected"
    assert fact["has_line_notes"] is True

    csv_response = app_client.get(f"/menus/{menu_id}/production-record/{production_record_id}/export.csv")
    csv_body = csv_response.get_data(as_text=True)

    assert csv_response.status_code == 200
    assert csv_response.mimetype == "text/csv"
    assert "attachment; filename=production-record-menu-" in csv_response.headers["Content-Disposition"]
    assert "Forecast Quantity,Forecast Unit,Actual Quantity,Actual Unit" in csv_body
    assert "Production Record Menu" in csv_body
    assert "Production Record Soup" in csv_body
    assert "Half pan, 4\"" in csv_body
    assert "As Expected" in csv_body
    assert "Use kettle B next time" in csv_body

    posted_entry_response = app_client.get(f"/menus/{menu_id}/production-record?week=1&day=monday")
    posted_entry_page = posted_entry_response.get_data(as_text=True)

    assert posted_entry_response.status_code == 200
    assert "Review Posted Record" in posted_entry_page
    assert "This production record is posted and locked for editing." in posted_entry_page

    locked_response = app_client.put(
        f"/api/menus/{menu_id}/production-record/lines/{production_record_line_id}",
        json={
            "actual_quantity": "2",
            "actual_unit": "pan_half_4",
            "end_service_variance_quantity": "0",
            "end_service_variance_unit": "pan_half_4",
        },
    )
    locked_payload = locked_response.get_json()

    assert locked_response.status_code == 400
    assert "cannot be edited" in locked_payload["error"]


def test_posted_production_facts_exclude_drafts(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Draft Contract Base")
    recipe_id = create_recipe(
        {
            "item_name": "Draft Contract Soup",
            "yield_quantity": 8,
            "yield_unit": "each",
            "primary_cooking_method_code": "simmer",
            "instruction_steps": ["Cook"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "cup",
                }
            ],
        }
    )
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Draft Contract Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (base_food_id, recipe_id))
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    app_client.post(
        f"/menus/{menu_id}/slots/{menu_slot_id}/assign",
        data={"week": "1", "selected_item_ids": [str(recipe_id)]},
        follow_redirects=False,
    )
    app_client.get(f"/menus/{menu_id}/production-record?week=1&day=monday")

    response = app_client.get(f"/api/menus/{menu_id}/production-record/posted-facts")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["contract"]["summary"]["record_count"] == 0
    assert payload["contract"]["facts"] == []


def test_production_record_history_route_renders_empty_state(app_client):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Empty History Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
            "service_days": ["monday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])

    response = app_client.get(f"/menus/{menu_id}/production-record/history")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Production Record History" in page
    assert "Empty History Menu" in page
    assert "No production records have been started for this menu." in page
    assert "Current Production Record" in page


def test_inventory_foundation_routes_create_count_and_current_on_hand(app_client, isolated_db):
    item_id = create_base_food(item_name="Route Inventory Onions", mass_quantity=1, mass_unit="lb")
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (item_id,))
    conn.commit()
    conn.close()

    location_response = app_client.post(
        "/inventory/locations",
        data={"location_name": "Walk-In Freezer"},
        follow_redirects=True,
    )
    location_page = location_response.get_data(as_text=True)

    assert location_response.status_code == 200
    assert "Inventory location created." in location_page
    assert "Walk-In Freezer" in location_page
    assert "Add Location" in location_page

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT inventory_location_id FROM inventory_location WHERE location_name = 'Walk-In Freezer'")
    location_id = cursor.fetchone()[0]
    conn.close()

    sub_location_response = app_client.post(
        "/inventory/locations",
        data={
            "parent_inventory_location_id": str(location_id),
            "location_name": "Rack A",
            "return_to": "edit",
        },
        follow_redirects=False,
    )
    assert sub_location_response.status_code == 302
    assert f"/inventory/locations/{location_id}/edit" in sub_location_response.headers["Location"]

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT inventory_location_id FROM inventory_location WHERE location_name = 'Rack A'")
    sub_location_id = cursor.fetchone()[0]
    conn.close()

    line_response = app_client.post(
        f"/inventory/locations/{sub_location_id}/items",
        data={
            "item_id": str(item_id),
            "count_each_quantity": "2",
            "count_case_quantity": "1",
            "pack_quantity": "4",
            "pack_size_text": "5 lb",
            "unit_of_measurement": "Case",
            "count_type": "counted_by_each_and_case",
        },
        follow_redirects=True,
    )
    line_page = line_response.get_data(as_text=True)

    assert line_response.status_code == 200
    assert "Inventory Management" in line_page
    assert "Inventory item count saved." in line_page
    assert "Route Inventory Onions" in line_page
    assert 'value="2"' in line_page
    assert 'value="1"' in line_page
    assert "4 packs x 5 lb" in line_page
    assert "1.5 case" in line_page
    assert "Price history" in line_page
    assert "Transfer Route Inventory Onions" in line_page
    assert "Print" in line_page

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT inventory_location_item_id FROM inventory_location_item WHERE inventory_location_id = ? AND item_id = ?",
        (sub_location_id, item_id),
    )
    location_item_id = cursor.fetchone()[0]
    conn.close()

    api_response = app_client.put(
        f"/api/inventory/location-items/{location_item_id}",
        json={
            "inventory_location_id": sub_location_id,
            "count_each_quantity": "3",
            "count_case_quantity": "1",
            "pack_quantity": "4",
            "pack_size_text": "5 lb",
            "unit_of_measurement": "Case",
            "count_type": "counted_by_each_and_case",
        },
    )
    api_payload = api_response.get_json()

    assert api_response.status_code == 200
    assert api_payload["ok"] is True
    assert api_payload["line"]["quantity_display"] == "1.75"
    assert api_payload["line"]["display_quantity_display"] == "1.75"
    assert api_payload["line"]["display_unit_label"] == "case"

    dashboard_response = app_client.get("/inventory")
    dashboard_page = dashboard_response.get_data(as_text=True)

    assert dashboard_response.status_code == 200
    assert "Current On Hand" in dashboard_page
    assert "Route Inventory Onions" in dashboard_page
    assert f"/inventory/items/{item_id}" in dashboard_page
    assert f"/recipe-collection/items/{item_id}" not in dashboard_page
    assert "<th>Category</th>" in dashboard_page
    assert "Produce" in dashboard_page
    assert "1.75 case" in dashboard_page
    assert "Count Roll-Down" in dashboard_page
    assert "Location Breakdown" in dashboard_page
    assert "Enter Count" in dashboard_page

    detail_response = app_client.get(f"/inventory/items/{item_id}")
    detail_page = detail_response.get_data(as_text=True)

    assert detail_response.status_code == 200
    assert "Route Inventory Onions" in detail_page
    assert "Current Counts" in detail_page
    assert "Upcoming Menu Usage" in detail_page
    assert "Past Menu Usage" in detail_page
    assert "Each 3 / Case 1" in detail_page
    assert "1.75 case" in detail_page

    print_response = app_client.get(f"/inventory/locations/{sub_location_id}/print")
    print_page = print_response.get_data(as_text=True)

    assert print_response.status_code == 200
    assert "Inventory count sheet" in print_page
    assert "Route Inventory Onions" in print_page
    assert "1.75 case" in print_page


def test_production_record_post_requires_recorded_lines(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Incomplete Production Base")
    recipe_id = create_recipe(
        {
            "item_name": "Incomplete Production Soup",
            "yield_quantity": 10,
            "yield_unit": "each",
            "primary_cooking_method_code": "simmer",
            "instruction_steps": ["Cook"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "cup",
                }
            ],
        }
    )
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Incomplete Production Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (base_food_id, recipe_id))
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    app_client.post(
        f"/menus/{menu_id}/slots/{menu_slot_id}/assign",
        data={"week": "1", "selected_item_ids": [str(recipe_id)]},
        follow_redirects=False,
    )
    page_response = app_client.get(f"/menus/{menu_id}/production-record?week=1&day=monday")

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT production_record_id FROM production_record WHERE menu_id = ?", (menu_id,))
    production_record_id = cursor.fetchone()[0]
    conn.close()

    post_response = app_client.post(
        f"/menus/{menu_id}/production-record/{production_record_id}/post",
        data={"week": "1", "day": "monday"},
        follow_redirects=True,
    )
    page = post_response.get_data(as_text=True)

    assert page_response.status_code == 200
    assert post_response.status_code == 200
    assert "Record every production line before posting." in page
    assert "Status: Draft" in page


def test_production_record_renders_unforecasted_base_food_lines(app_client, isolated_db):
    base_food_id = create_base_food(
        item_name="Unforecasted Record Apple",
        mass_quantity=1,
        mass_unit="lb",
    )
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Unforecasted Record Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-31",
            "service_days": ["tuesday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "4",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (base_food_id,))
    cursor.execute(
        """
        SELECT menu_slot_id
        FROM menu_slot
        WHERE menu_id = ?
          AND week_number = 4
          AND day_of_week = 'tuesday'
        """,
        (menu_id,),
    )
    menu_slot_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    app_client.post(
        f"/menus/{menu_id}/slots/{menu_slot_id}/assign",
        data={"week": "4", "selected_item_ids": [str(base_food_id)]},
        follow_redirects=False,
    )

    response = app_client.get(f"/menus/{menu_id}/production-record?week=4&day=tuesday")
    page = response.get_data(as_text=True)

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM production_record_line prl
        JOIN production_record pr
          ON pr.production_record_id = prl.production_record_id
        WHERE pr.menu_id = ?
          AND pr.week_number = 4
          AND pr.day_of_week = 'tuesday'
        """,
        (menu_id,),
    )
    line_count = cursor.fetchone()[0]
    conn.close()

    assert response.status_code == 200
    assert "Unforecasted Record Apple" in page
    assert "0 lb" in page
    assert line_count == 1


def test_api_update_menu_forecast_rejects_invalid_quantity(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Forecast Invalid Base")
    recipe_id = create_recipe(
        {
            "item_name": "Forecast Invalid Recipe",
            "yield_quantity": 5,
            "yield_unit": "each",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Set"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "lb",
                }
            ],
        }
    )
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Forecast Invalid Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (base_food_id, recipe_id))
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    app_client.post(
        f"/menus/{menu_id}/slots/{menu_slot_id}/assign",
        data={"week": "1", "selected_item_ids": [str(recipe_id)]},
        follow_redirects=False,
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_slot_item_id FROM menu_slot_item WHERE menu_slot_id = ?", (menu_slot_id,))
    menu_slot_item_id = cursor.fetchone()[0]
    conn.close()

    response = app_client.put(
        f"/api/menus/{menu_id}/forecast/{menu_slot_item_id}",
        json={
            "forecast_yield_quantity": "-1",
            "forecast_yield_unit": "each",
        },
    )
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["ok"] is False
    assert "cannot be negative" in payload["error"]


def test_menu_forecast_case_mode_persists_calculated_yield(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Forecast Case Fries")
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Forecast Case Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (base_food_id,))
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    app_client.post(
        f"/menus/{menu_id}/slots/{menu_slot_id}/assign",
        data={"week": "1", "selected_item_ids": [str(base_food_id)]},
        follow_redirects=False,
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_slot_item_id FROM menu_slot_item WHERE menu_slot_id = ?", (menu_slot_id,))
    menu_slot_item_id = cursor.fetchone()[0]
    conn.close()

    response = app_client.put(
        f"/api/menus/{menu_id}/forecast/{menu_slot_item_id}",
        json={
            "forecast_yield_quantity": "3",
            "forecast_yield_unit": "case",
            "case_pack_quantity": "5",
            "case_subunit_quantity": "10",
            "case_subunit_unit": "lb",
            "case_basis_component_item_id": str(base_food_id),
            "case_basis_component_name": "Forecast Case Fries",
            "case_basis_view_mode": "base",
            "case_basis_row_key": str(base_food_id),
            "user_serving_size_quantity": "4",
            "user_serving_size_unit": "oz",
            "desired_portions": "80",
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["forecast"]["forecast_yield_unit"] == "case"
    assert payload["forecast"]["calculated_forecast_quantity"] == 150
    assert payload["forecast"]["calculated_forecast_unit"] == "lb"
    assert payload["forecast"]["case_basis_component_item_id"] == base_food_id
    assert payload["forecast"]["case_basis_component_name"] == "Forecast Case Fries"
    assert payload["forecast"]["case_basis_row_key"] == str(base_food_id)
    assert payload["forecast"]["user_serving_size_quantity"] is None
    assert payload["forecast"]["desired_portions"] is None

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM item_case_pack WHERE item_id = ?", (base_food_id,))
    assert cursor.fetchone()[0] == 0
    conn.close()

    save_case_response = app_client.post(
        f"/api/menus/{menu_id}/forecast/{menu_slot_item_id}/case-packs",
        json={
            "item_id": str(base_food_id),
            "pack_quantity": "5",
            "subunit_quantity": "10",
            "subunit_unit": "lb",
        },
    )
    save_case_payload = save_case_response.get_json()

    assert save_case_response.status_code == 200
    assert save_case_payload["case_pack"]["item_id"] == base_food_id
    assert save_case_payload["case_pack"]["pack_quantity"] == 5
    assert save_case_payload["case_pack"]["subunit_quantity"] == 10
    assert save_case_payload["case_pack"]["subunit_unit"] == "lb"

    duplicate_case_response = app_client.post(
        f"/api/menus/{menu_id}/forecast/{menu_slot_item_id}/case-packs",
        json={
            "item_id": str(base_food_id),
            "pack_quantity": "5.0",
            "subunit_quantity": "10.000",
            "subunit_unit": "lb",
        },
    )
    duplicate_case_payload = duplicate_case_response.get_json()

    assert duplicate_case_response.status_code == 400
    assert "already saved" in duplicate_case_payload["error"]

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO item_case_pack (
            item_id,
            pack_quantity,
            subunit_quantity,
            subunit_unit,
            created_at,
            updated_at
        )
        VALUES (?, 5, 10, 'lb', datetime('now'), datetime('now'))
        """,
        (base_food_id,),
    )
    conn.commit()
    conn.close()

    page_response = app_client.get(f"/menus/{menu_id}/forecast?week=1&day=monday")
    page = page_response.get_data(as_text=True)

    assert page_response.status_code == 200
    assert '<option value="case" selected>case</option>' in page
    assert 'value="5"' in page
    assert 'value="10"' in page
    assert '<option value="lb" selected>lb</option>' in page
    assert "Linked to Forecast Case Fries" in page
    assert "data-case-config" in page
    assert "data-save-case-pack" in page
    assert "data-case-pack-options" in page
    assert page.count('"pack_quantity": 5.0') == 1
    assert "data-production-display-unit" in page
    assert "150 lb" in page

    zero_response = app_client.put(
        f"/api/menus/{menu_id}/forecast/{menu_slot_item_id}",
        json={
            "forecast_yield_quantity": "0",
            "forecast_yield_unit": "case",
            "case_pack_quantity": "5",
            "case_subunit_quantity": "10",
            "case_subunit_unit": "lb",
        },
    )
    zero_payload = zero_response.get_json()

    assert zero_response.status_code == 200
    assert zero_payload["forecast"]["case_quantity"] == 0
    assert zero_payload["forecast"]["calculated_forecast_quantity"] == 0


def test_menu_forecast_case_overlay_renders_flattened_candidates(app_client, isolated_db):
    chile_id = create_base_food(item_name="Forecast Flat Chile")
    salt_id = create_base_food(item_name="Forecast Flat Salt")
    sauce_id = create_recipe(
        {
            "item_name": "Forecast Flat Sauce",
            "yield_quantity": 1,
            "yield_unit": "qt",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {
                    "component_item_id": chile_id,
                    "component_quantity": 8,
                    "component_unit": "oz",
                }
            ],
        }
    )
    bowl_id = create_recipe(
        {
            "item_name": "Forecast Flat Bowl",
            "yield_quantity": 4,
            "yield_unit": "each",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Assemble"],
            "ingredients": [
                {
                    "component_item_id": sauce_id,
                    "component_quantity": 1,
                    "component_unit": "qt",
                },
                {
                    "component_item_id": salt_id,
                    "component_quantity": 1,
                    "component_unit": "oz",
                },
            ],
        }
    )
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Forecast Flat Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?, ?, ?)", (chile_id, salt_id, sauce_id, bowl_id))
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    app_client.post(
        f"/menus/{menu_id}/slots/{menu_slot_id}/assign",
        data={"week": "1", "selected_item_ids": [str(bowl_id)]},
        follow_redirects=False,
    )

    response = app_client.get(f"/menus/{menu_id}/forecast?week=1&day=monday")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-case-candidates="flattened"' in page
    assert "Forecast Flat Chile" in page
    assert "Forecast Flat Sauce" in page
    assert "menu-forecast-case-candidate-flat depth-1" in page


def test_advanced_case_forecast_calculates_recipe_yield_and_allows_serving_size(app_client, isolated_db):
    sauce_id = create_base_food(item_name="Forecast Case Sauce")
    recipe_id = create_recipe(
        {
            "item_name": "Forecast Case Bowl",
            "yield_quantity": 4,
            "yield_unit": "each",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Assemble"],
            "ingredients": [
                {
                    "component_item_id": sauce_id,
                    "component_quantity": 1,
                    "component_unit": "qt",
                }
            ],
        }
    )
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Forecast Case Recipe Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (sauce_id, recipe_id))
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    cursor.execute(
        """
        SELECT recipe_component_id
        FROM recipe_component
        WHERE parent_recipe_item_id = ?
          AND component_item_id = ?
        """,
        (recipe_id, sauce_id),
    )
    recipe_component_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    app_client.post(
        f"/menus/{menu_id}/slots/{menu_slot_id}/assign",
        data={"week": "1", "selected_item_ids": [str(recipe_id)]},
        follow_redirects=False,
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_slot_item_id FROM menu_slot_item WHERE menu_slot_id = ?", (menu_slot_id,))
    menu_slot_item_id = cursor.fetchone()[0]
    conn.close()

    response = app_client.put(
        f"/api/menus/{menu_id}/forecast/{menu_slot_item_id}",
        json={
            "forecast_yield_quantity": "2",
            "forecast_yield_unit": "case",
            "case_pack_quantity": "1",
            "case_subunit_quantity": "2",
            "case_subunit_unit": "qt",
            "case_basis_component_item_id": str(sauce_id),
            "case_basis_component_name": "Forecast Case Sauce",
            "case_basis_view_mode": "hierarchical",
            "case_basis_row_key": str(recipe_component_id),
            "user_serving_size_quantity": "1",
            "user_serving_size_unit": "each",
            "desired_portions": "16",
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["forecast"]["forecast_yield_unit"] == "case"
    assert payload["forecast"]["calculated_forecast_quantity"] == 16
    assert payload["forecast"]["calculated_forecast_unit"] == "each"
    assert payload["forecast"]["user_serving_size_quantity"] == 1
    assert payload["forecast"]["desired_portions"] == 16


def test_advanced_case_forecast_bridges_ingredient_mass_to_recipe_each(app_client, isolated_db):
    chicken_id = create_base_food(
        item_name="Forecast Case Chicken Breast",
        mass_quantity=10,
        mass_unit="lb",
    )
    recipe_id = create_recipe(
        {
            "item_name": "Forecast Case Chicken Salad Plate",
            "yield_quantity": 8,
            "yield_unit": "each",
            "mass_quantity": 2800,
            "mass_unit": "g",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Plate"],
            "ingredients": [
                {
                    "component_item_id": chicken_id,
                    "component_quantity": 1,
                    "component_unit": "each",
                }
            ],
        }
    )
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Forecast Case Chicken Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (chicken_id, recipe_id))
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    cursor.execute(
        """
        SELECT recipe_component_id
        FROM recipe_component
        WHERE parent_recipe_item_id = ?
          AND component_item_id = ?
        """,
        (recipe_id, chicken_id),
    )
    recipe_component_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    app_client.post(
        f"/menus/{menu_id}/slots/{menu_slot_id}/assign",
        data={"week": "1", "selected_item_ids": [str(recipe_id)]},
        follow_redirects=False,
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_slot_item_id FROM menu_slot_item WHERE menu_slot_id = ?", (menu_slot_id,))
    menu_slot_item_id = cursor.fetchone()[0]
    conn.close()

    response = app_client.put(
        f"/api/menus/{menu_id}/forecast/{menu_slot_item_id}",
        json={
            "forecast_yield_quantity": "1.25",
            "forecast_yield_unit": "case",
            "case_pack_quantity": "4",
            "case_subunit_quantity": "10",
            "case_subunit_unit": "lb",
            "case_basis_component_item_id": str(chicken_id),
            "case_basis_component_name": "Forecast Case Chicken Breast",
            "case_basis_view_mode": "hierarchical",
            "case_basis_row_key": str(recipe_component_id),
            "user_serving_size_quantity": "1",
            "user_serving_size_unit": "each",
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["forecast"]["calculated_forecast_quantity"] == 40
    assert payload["forecast"]["calculated_forecast_unit"] == "each"

    page_response = app_client.get(f"/menus/{menu_id}/forecast?week=1&day=monday")
    page = page_response.get_data(as_text=True)

    assert page_response.status_code == 200
    assert "forecast unit 'lb' cannot roll up" not in page
    assert "40 each" in page


def test_forecast_advanced_scaling_confirms_bottom_up_yield(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Forecast Advanced Base")
    recipe_id = create_recipe(
        {
            "item_name": "Forecast Advanced Recipe",
            "yield_quantity": 2,
            "yield_unit": "qt",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 8,
                    "component_unit": "oz",
                }
            ],
        }
    )
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Forecast Advanced Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (base_food_id, recipe_id))
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    cursor.execute(
        """
        SELECT recipe_component_id
        FROM recipe_component
        WHERE parent_recipe_item_id = ?
        """,
        (recipe_id,),
    )
    recipe_component_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    app_client.post(
        f"/menus/{menu_id}/slots/{menu_slot_id}/assign",
        data={"week": "1", "selected_item_ids": [str(recipe_id)]},
        follow_redirects=False,
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_slot_item_id FROM menu_slot_item WHERE menu_slot_id = ?", (menu_slot_id,))
    menu_slot_item_id = cursor.fetchone()[0]
    conn.close()

    response = app_client.get(
        f"/recipe-collection/items/{recipe_id}"
        f"?scale_mode=ingredient"
        f"&advanced_scale_row_key={recipe_component_id}"
        f"&advanced_scale_quantity=16"
        f"&advanced_scale_unit=oz"
        f"&forecast_menu_id={menu_id}"
        f"&forecast_menu_slot_item_id={menu_slot_item_id}"
        f"&forecast_week=1"
        f"&forecast_day=monday"
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Advanced Ingredient Scaling" in page
    assert "Scaling from 16.0 oz" in page
    assert "to recipe yield 4.0 qt" in page
    assert "Confirm Scaling" in page

    confirm_response = app_client.post(
        f"/menus/{menu_id}/forecast/{menu_slot_item_id}/confirm-scaling",
        data={
            "forecast_yield_quantity": "4",
            "forecast_yield_unit": "qt",
            "user_serving_size_quantity": "8",
            "user_serving_size_unit": "oz",
            "desired_portions": "64",
            "forecast_week": "1",
            "forecast_day": "monday",
        },
        follow_redirects=True,
    )
    forecast_page = confirm_response.get_data(as_text=True)

    assert confirm_response.status_code == 200
    assert "Forecast scaling confirmed." in forecast_page
    assert 'value="4"' in forecast_page
    assert '<option value="qt" selected>qt</option>' in forecast_page
    assert 'value="8"' in forecast_page
    assert 'value="64"' in forecast_page
    assert '<option value="oz" selected>oz</option>' in forecast_page


def test_forecast_yield_scaling_can_confirm_back_to_forecast(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Forecast Yield Confirm Base")
    recipe_id = create_recipe(
        {
            "item_name": "Forecast Yield Confirm Recipe",
            "yield_quantity": 2,
            "yield_unit": "qt",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 8,
                    "component_unit": "oz",
                }
            ],
        }
    )
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Forecast Yield Confirm Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (base_food_id, recipe_id))
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    app_client.post(
        f"/menus/{menu_id}/slots/{menu_slot_id}/assign",
        data={"week": "1", "selected_item_ids": [str(recipe_id)]},
        follow_redirects=False,
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_slot_item_id FROM menu_slot_item WHERE menu_slot_id = ?", (menu_slot_id,))
    menu_slot_item_id = cursor.fetchone()[0]
    conn.close()

    response = app_client.get(
        f"/recipe-collection/items/{recipe_id}"
        f"?scale_quantity=3"
        f"&scale_unit=qt"
        f"&forecast_menu_id={menu_id}"
        f"&forecast_menu_slot_item_id={menu_slot_item_id}"
        f"&forecast_week=1"
        f"&forecast_day=monday"
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Scaling to 3.0 qt" in page
    assert "Confirm Scaling" in page

    confirm_response = app_client.post(
        f"/menus/{menu_id}/forecast/{menu_slot_item_id}/confirm-scaling",
        data={
            "forecast_yield_quantity": "3",
            "forecast_yield_unit": "qt",
            "forecast_week": "1",
            "forecast_day": "monday",
        },
        follow_redirects=True,
    )
    forecast_page = confirm_response.get_data(as_text=True)

    assert confirm_response.status_code == 200
    assert 'value="3"' in forecast_page
    assert '<option value="qt" selected>qt</option>' in forecast_page


def test_advanced_edit_can_scale_yield_from_desired_portions(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Desired Portions Base")
    recipe_id = create_recipe(
        {
            "item_name": "Desired Portions Recipe",
            "yield_quantity": 2,
            "yield_unit": "qt",
            "serving_size_quantity": 1,
            "serving_size_unit": "cup",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Portion"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "lb",
                }
            ],
        }
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (base_food_id, recipe_id))
    conn.commit()
    conn.close()

    response = app_client.get(
        f"/recipe-collection/items/{recipe_id}"
        f"?desired_portions=16"
        f"&user_serving_size_quantity=1"
        f"&user_serving_size_unit=cup"
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Desired portions 16" in page
    assert "scales to 4" in page
    assert "Scaling to 4.0 qt" in page


def test_advanced_scaling_state_survives_display_and_unit_toggles(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Toggle Preserve Base")
    recipe_id = create_recipe(
        {
            "item_name": "Toggle Preserve Recipe",
            "yield_quantity": 2,
            "yield_unit": "qt",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 8,
                    "component_unit": "oz",
                }
            ],
        }
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (base_food_id, recipe_id))
    cursor.execute(
        """
        SELECT recipe_component_id
        FROM recipe_component
        WHERE parent_recipe_item_id = ?
        """,
        (recipe_id,),
    )
    recipe_component_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    response = app_client.get(
        f"/recipe-collection/items/{recipe_id}"
        f"?scale_mode=ingredient"
        f"&advanced_scale_row_key={recipe_component_id}"
        f"&advanced_scale_quantity=16"
        f"&advanced_scale_unit=oz"
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Advanced Ingredient Scaling" in page
    assert "display_mode=mass" in page
    assert "unit_system=metric" in page
    assert "scale_mode=ingredient" in page
    assert f"advanced_scale_row_key={recipe_component_id}" in page
    assert "advanced_scale_quantity=16" in page
    assert "advanced_scale_unit=oz" in page


def test_advanced_scaling_submit_switches_display_mode_to_target_unit_family(app_client, isolated_db):
    base_food_id = create_base_food(
        item_name="Target Family Base",
        mass_quantity=1,
        mass_unit="lb",
        volume_quantity=1,
        volume_unit="qt",
    )
    recipe_id = create_recipe(
        {
            "item_name": "Target Family Recipe",
            "yield_quantity": 2,
            "yield_unit": "qt",
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

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (base_food_id, recipe_id))
    cursor.execute(
        """
        SELECT recipe_component_id
        FROM recipe_component
        WHERE parent_recipe_item_id = ?
        """,
        (recipe_id,),
    )
    recipe_component_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    response = app_client.get(
        f"/recipe-collection/items/{recipe_id}"
        f"?scale_mode=ingredient"
        f"&display_mode=default"
        f"&advanced_scale_submit=1"
        f"&advanced_scale_row_key={recipe_component_id}"
        f"&advanced_scale_quantity=2"
        f"&advanced_scale_unit=qt"
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Scaling from 2.0 qt" in page
    assert "to recipe yield 4.0 qt" in page
    assert '<option value="qt" selected>qt</option>' in page
    display_section = page[page.index("Display Mode</span>"):page.index("Unit System</span>")]
    volume_toggle_index = display_section.index("Volume")
    assert "is-current-toggle" in display_section[volume_toggle_index - 500:volume_toggle_index]
    assert "Official volume equivalent:" not in page

    mass_response = app_client.get(
        f"/recipe-collection/items/{recipe_id}"
        f"?scale_mode=ingredient"
        f"&display_mode=volume"
        f"&advanced_scale_submit=1"
        f"&advanced_scale_row_key={recipe_component_id}"
        f"&advanced_scale_quantity=32"
        f"&advanced_scale_unit=oz"
    )
    mass_page = mass_response.get_data(as_text=True)
    mass_display_section = mass_page[mass_page.index("Display Mode</span>"):mass_page.index("Unit System</span>")]
    mass_toggle_index = mass_display_section.index("Mass")

    assert mass_response.status_code == 200
    assert "Scaling from 32.0 oz" in mass_page
    assert '<option value="oz" selected>oz</option>' in mass_page
    assert "is-current-toggle" in mass_display_section[mass_toggle_index - 500:mass_toggle_index]


def test_flattened_advanced_scaling_preserves_selected_volume_unit(app_client, isolated_db):
    base_food_id = create_base_food(
        item_name="Flattened Preserve Chicken",
        mass_quantity=140,
        mass_unit="g",
        volume_quantity=1,
        volume_unit="cup",
    )
    recipe_id = create_recipe(
        {
            "item_name": "Flattened Preserve Recipe",
            "yield_quantity": 8,
            "yield_unit": "each",
            "mass_quantity": 2800,
            "mass_unit": "g",
            "volume_quantity": 5,
            "volume_unit": "qt",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1.6666666667,
                    "component_unit": "lb",
                }
            ],
        }
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (base_food_id, recipe_id))
    conn.commit()
    conn.close()

    response = app_client.get(
        f"/recipe-collection/items/{recipe_id}"
        f"?ingredient_view=flattened"
        f"&display_mode=mass"
        f"&unit_system=imperial"
        f"&scale_mode=ingredient"
        f"&advanced_scale_submit=1"
        f"&advanced_scale_row_key=0"
        f"&advanced_scale_quantity=5"
        f"&advanced_scale_unit=qt"
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Scaling from 5.0 qt" in page
    assert "1.25" in page
    assert "gal" in page
    assert 'value="5"' in page
    assert '<option value="qt" selected>qt</option>' in page
    assert '<option value="lb" selected>lb</option>' not in page
    assert "ingredient_view=hierarchical" in page
    assert "scale_mode=ingredient" in page
    assert "scale_unit=each" in page
    assert "scale_quantity=29." in page


def test_forecast_bottom_up_scaling_saves_scaled_recipe_mass_unit(app_client, isolated_db):
    base_food_id = create_base_food(
        item_name="Forecast Mass Save Ingredient",
        mass_quantity=1,
        mass_unit="lb",
        volume_quantity=1,
        volume_unit="cup",
    )
    recipe_id = create_recipe(
        {
            "item_name": "Forecast Mass Save Recipe",
            "yield_quantity": 8,
            "yield_unit": "each",
            "mass_quantity": 80,
            "mass_unit": "lb",
            "volume_quantity": 5,
            "volume_unit": "qt",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 10,
                    "component_unit": "lb",
                }
            ],
        }
    )
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Forecast Mass Save Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (base_food_id, recipe_id))
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    cursor.execute(
        """
        SELECT recipe_component_id
        FROM recipe_component
        WHERE parent_recipe_item_id = ?
        """,
        (recipe_id,),
    )
    recipe_component_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    app_client.post(
        f"/menus/{menu_id}/slots/{menu_slot_id}/assign",
        data={"week": "1", "selected_item_ids": [str(recipe_id)]},
        follow_redirects=False,
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_slot_item_id FROM menu_slot_item WHERE menu_slot_id = ?", (menu_slot_id,))
    menu_slot_item_id = cursor.fetchone()[0]
    conn.close()

    response = app_client.get(
        f"/recipe-collection/items/{recipe_id}"
        f"?scale_mode=ingredient"
        f"&advanced_scale_row_key={recipe_component_id}"
        f"&advanced_scale_quantity=20"
        f"&advanced_scale_unit=lb"
        f"&forecast_menu_id={menu_id}"
        f"&forecast_menu_slot_item_id={menu_slot_item_id}"
        f"&forecast_week=1"
        f"&forecast_day=monday"
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Scaling from 20.0 lb" in page
    assert 'name="forecast_yield_quantity" value="160.0"' in page
    assert 'name="forecast_yield_unit" value="lb"' in page

    confirm_response = app_client.post(
        f"/menus/{menu_id}/forecast/{menu_slot_item_id}/confirm-scaling",
        data={
            "forecast_yield_quantity": "160",
            "forecast_yield_unit": "lb",
            "forecast_week": "1",
            "forecast_day": "monday",
        },
        follow_redirects=True,
    )
    forecast_page = confirm_response.get_data(as_text=True)

    assert confirm_response.status_code == 200
    assert 'value="160"' in forecast_page
    assert '<option value="lb" selected>lb</option>' in forecast_page


def test_menu_forecast_route_filters_and_fuzzy_searches_recipes(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Forecast Filter Base")
    recipe_id = create_recipe(
        {
            "item_name": "Forecast Coconut Curry",
            "yield_quantity": 8,
            "yield_unit": "qt",
            "primary_cooking_method_code": "simmer",
            "instruction_steps": ["Cook"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 2,
                    "component_unit": "lb",
                }
            ],
        }
    )
    hidden_recipe_id = create_recipe(
        {
            "item_name": "Forecast Hidden Salad",
            "yield_quantity": 8,
            "yield_unit": "each",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Toss"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "lb",
                }
            ],
        }
    )

    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Forecast Filter Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
            "service_days": ["monday"],
            "meal_periods": ["lunch", "dinner"],
            "concepts": ["hot_line", "salad_bar"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?, ?)", (base_food_id, recipe_id, hidden_recipe_id))
    cursor.execute(
        """
        SELECT menu_slot_id, meal_period, concept_name
        FROM menu_slot
        WHERE menu_id = ?
        """,
        (menu_id,),
    )
    slot_lookup = {
        (meal_period, concept_name): menu_slot_id
        for menu_slot_id, meal_period, concept_name in cursor.fetchall()
    }
    conn.commit()
    conn.close()

    app_client.post(
        f"/menus/{menu_id}/slots/{slot_lookup[('lunch', 'hot_line')]}/assign",
        data={"week": "1", "selected_item_ids": [str(recipe_id)]},
        follow_redirects=False,
    )
    app_client.post(
        f"/menus/{menu_id}/slots/{slot_lookup[('dinner', 'salad_bar')]}/assign",
        data={"week": "1", "selected_item_ids": [str(hidden_recipe_id)]},
        follow_redirects=False,
    )

    response = app_client.get(f"/menus/{menu_id}/forecast?week=1&day=monday&q=cocnut&meal_period=lunch&concept=hot_line")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Forecast Coconut Curry" in page
    assert "Forecast Hidden Salad" not in page
    assert 'value="cocnut"' in page


def test_edit_menu_route_prefills_existing_config(app_client):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Prefill Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-17",
            "service_days": ["monday", "wednesday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "2",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])

    response = app_client.get(f"/menus/{menu_id}/edit")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Edit Menu Config" in page
    assert 'value="Prefill Menu"' in page
    assert "Update Config" in page
    assert "menu_config.js" in page
    assert "data-menu-start-date" in page
    assert "data-menu-end-date" in page


def test_edit_menu_post_updates_config_and_pops_removed_slots(app_client, isolated_db):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Update Route Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-17",
            "service_days": ["monday", "tuesday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line", "salad_bar"],
            "menu_length_weeks": "2",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])
    kept_item_id = create_base_food(item_name="Edit Route Kept Item")

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (kept_item_id,))
    cursor.execute(
        """
        SELECT menu_slot_id
        FROM menu_slot
        WHERE menu_id = ?
          AND week_number = 1
          AND day_of_week = 'monday'
          AND meal_period = 'lunch'
          AND concept_name = 'hot_line'
        """,
        (menu_id,),
    )
    kept_slot_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    app_client.post(
        f"/menus/{menu_id}/slots/{kept_slot_id}/assign",
        data={"week": "1", "selected_item_ids": [str(kept_item_id)]},
        follow_redirects=False,
    )

    response = app_client.post(
        f"/menus/{menu_id}/edit",
        data={
            "menu_name": "Updated Route Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
            "service_days": ["monday", "wednesday"],
            "meal_periods": ["lunch", "dinner"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=True,
    )
    page = response.get_data(as_text=True)

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_name, menu_length_weeks FROM menu WHERE menu_id = ?", (menu_id,))
    menu_row = cursor.fetchone()
    cursor.execute(
        """
        SELECT week_number, day_of_week, meal_period, concept_name
        FROM menu_slot
        WHERE menu_id = ?
        ORDER BY week_number, day_of_week, meal_period, concept_name
        """,
        (menu_id,),
    )
    slot_rows = cursor.fetchall()
    cursor.execute("SELECT item_id FROM menu_slot_item WHERE menu_slot_id = ?", (kept_slot_id,))
    kept_slot_item = cursor.fetchone()[0]
    conn.close()

    assert response.status_code == 200
    assert "config updated successfully." in page
    assert "Updated Route Menu" in page
    assert menu_row == ("Updated Route Menu", 1)
    assert slot_rows == [
        (1, "monday", "dinner", "hot_line"),
        (1, "monday", "lunch", "hot_line"),
        (1, "wednesday", "dinner", "hot_line"),
        (1, "wednesday", "lunch", "hot_line"),
    ]
    assert kept_slot_item == kept_item_id


def test_menu_detail_route_uses_updated_concept_order(app_client):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Concept Order Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
            "service_days": ["monday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line", "salad_bar", "grab_go"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])

    response = app_client.post(
        f"/menus/{menu_id}/edit",
        data={
            "menu_name": "Concept Order Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
            "service_days": ["monday"],
            "meal_periods": ["lunch"],
            "concepts": ["grab_go", "hot_line", "salad_bar"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    detail_response = app_client.get(f"/menus/{menu_id}")
    page = detail_response.get_data(as_text=True)

    grab_go_index = page.index("Grab Go")
    hot_line_index = page.index("Hot Line")
    salad_bar_index = page.index("Salad Bar")

    assert detail_response.status_code == 200
    assert grab_go_index < hot_line_index < salad_bar_index


def test_menu_slot_assign_route_renders_search_results(app_client, isolated_db):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Assign Search Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
    assert f'href="/recipe-collection/items/{base_food_id}"' in page
    assert "Base Food | ID" in page


def test_menu_slot_assign_route_exposes_search_pagination_metadata(app_client, isolated_db):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Assign Search Paging Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
            "service_days": ["monday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])
    created_ids = [
        create_base_food(item_name=f"Assign Paging Item {index:02d}")
        for index in range(18)
    ]

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE item SET status = 'live' WHERE item_id IN ({})".format(
            ", ".join("?" for _ in created_ids)
        ),
        created_ids,
    )
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    menu_slot_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    response = app_client.get(f"/menus/{menu_id}/slots/{menu_slot_id}/assign?q=Assign+Paging")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '"has_more": true' in page
    assert '"next_offset": 15' in page


def test_menu_slot_assign_post_updates_slot_and_renders_in_menu_overview(app_client, isolated_db):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Assigned Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
    assigned_rows = cursor.fetchall()
    conn.close()

    assert response.status_code == 200
    assert "Menu slot assignments updated." in page
    assert "Assigned Slot Salad" in page
    assert "Assigned Slot Lettuce" in page
    assert assigned_rows == [(recipe_id, 1), (base_food_id, 2)]

    week_print_response = app_client.get(f"/menus/{menu_id}/print?week=1")
    week_print_page = week_print_response.get_data(as_text=True)

    assert week_print_response.status_code == 200
    assert "Print Menu" in week_print_page
    assert "Print Week" in week_print_page
    assert "Print Day" in week_print_page
    assert "Assigned Slot Salad" in week_print_page
    assert f"Recipe #{recipe_id}" in week_print_page
    assert f"Base Food #{base_food_id}" in week_print_page

    day_print_response = app_client.get(f"/menus/{menu_id}/print?mode=day&week=1")
    day_print_page = day_print_response.get_data(as_text=True)

    assert day_print_response.status_code == 200
    assert "Planning Notes" in day_print_page
    assert "Monday" in day_print_page
    assert "menu-print-write-line" in day_print_page


def test_copy_and_paste_menu_slot_routes_update_session_and_target_slot(app_client, isolated_db):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Clipboard Route Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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


def test_menu_detail_route_renders_day_header_copy_selection_mode(app_client):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Bulk Day Copy Selection Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
            "service_days": ["monday", "tuesday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_location = create_response.headers["Location"]

    response = app_client.get(f"{menu_location}?bulk_action=copy&bulk_scope=day")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Copy Selected Days" in page
    assert "Select Day" in page
    assert "Select Slot" not in page


def test_menu_detail_route_renders_week_copy_confirmation_without_checkboxes(app_client):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Bulk Week Copy Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-17",
            "service_days": ["monday", "tuesday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "2",
        },
        follow_redirects=False,
    )
    menu_location = create_response.headers["Location"]

    response = app_client.get(f"{menu_location}?bulk_action=copy&bulk_scope=week&week=2")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Copy Week 2" in page
    assert "After copying, you will choose destination weeks from a separate cycle-selection screen." in page
    assert "Select Slot" not in page
    assert "Select Day" not in page
    assert "Select Concept" not in page


def test_menu_detail_route_renders_day_header_selection_mode(app_client):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Bulk Day Selection Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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


def test_menu_bulk_copy_and_paste_routes_work_for_day_mode(app_client, isolated_db):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Bulk Day Route Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
            "service_days": ["monday", "tuesday"],
            "meal_periods": ["lunch", "dinner"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "1",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])
    lunch_item_id = create_base_food(item_name="Bulk Day Lunch Route Item")
    dinner_item_id = create_base_food(item_name="Bulk Day Dinner Route Item")

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT menu_slot_id, day_of_week, meal_period
        FROM menu_slot
        WHERE menu_id = ?
        ORDER BY menu_slot_id ASC
        """,
        (menu_id,),
    )
    slot_rows = cursor.fetchall()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (lunch_item_id, dinner_item_id))
    conn.commit()
    conn.close()

    slot_lookup = {(day, meal_period): menu_slot_id for menu_slot_id, day, meal_period in slot_rows}

    app_client.post(
        f"/menus/{menu_id}/slots/{slot_lookup[('monday', 'lunch')]}/assign",
        data={"week": "1", "selected_item_ids": [str(lunch_item_id)]},
        follow_redirects=False,
    )
    app_client.post(
        f"/menus/{menu_id}/slots/{slot_lookup[('monday', 'dinner')]}/assign",
        data={"week": "1", "selected_item_ids": [str(dinner_item_id)]},
        follow_redirects=False,
    )

    copy_response = app_client.post(
        f"/menus/{menu_id}/bulk-action",
        data={
            "week": "1",
            "action": "copy",
            "scope": "day",
            "selected_slot_ids": [str(slot_lookup[('monday', 'lunch')])],
        },
        follow_redirects=True,
    )
    paste_response = app_client.post(
        f"/menus/{menu_id}/bulk-action",
        data={
            "week": "1",
            "action": "paste",
            "selected_slot_ids": [str(slot_lookup[('tuesday', 'lunch')])],
        },
        follow_redirects=True,
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT item_id FROM menu_slot_item WHERE menu_slot_id = ?", (slot_lookup[('tuesday', 'lunch')],))
    tuesday_lunch_item_id = cursor.fetchone()[0]
    cursor.execute("SELECT item_id FROM menu_slot_item WHERE menu_slot_id = ?", (slot_lookup[('tuesday', 'dinner')],))
    tuesday_dinner_item_id = cursor.fetchone()[0]
    conn.close()

    assert copy_response.status_code == 200
    assert "Copied 1 day." in copy_response.get_data(as_text=True)
    assert paste_response.status_code == 200
    assert "Pasted into 2 slots." in paste_response.get_data(as_text=True)
    assert tuesday_lunch_item_id == lunch_item_id
    assert tuesday_dinner_item_id == dinner_item_id


def test_menu_bulk_copy_week_redirects_to_week_selection_page(app_client, isolated_db):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Bulk Week Route Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-06-14",
            "service_days": ["monday", "tuesday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "6",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT menu_slot_id FROM menu_slot WHERE menu_id = ? AND week_number = 2 ORDER BY menu_slot_id ASC",
        (menu_id,),
    )
    week_two_slot_id = cursor.fetchone()[0]
    conn.close()

    response = app_client.post(
        f"/menus/{menu_id}/bulk-action",
        data={
            "week": "2",
            "action": "copy",
            "scope": "week",
            "selected_slot_ids": [str(week_two_slot_id)],
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert f"/menus/{menu_id}/paste-weeks?source_week=2" in response.headers["Location"]


def test_menu_week_paste_page_renders_cycle_selection_grid(app_client, isolated_db):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Week Paste Page Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-06-28",
            "service_days": ["monday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "8",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT menu_slot_id FROM menu_slot WHERE menu_id = ? AND week_number = 1 ORDER BY menu_slot_id ASC",
        (menu_id,),
    )
    week_one_slot_id = cursor.fetchone()[0]
    conn.close()

    app_client.post(
        f"/menus/{menu_id}/bulk-action",
        data={
            "week": "1",
            "action": "copy",
            "scope": "week",
            "selected_slot_ids": [str(week_one_slot_id)],
        },
        follow_redirects=False,
    )

    response = app_client.get(f"/menus/{menu_id}/paste-weeks?source_week=1")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Paste Week Across Menu Cycle" in page
    assert "Select Matching Cycle Weeks" in page
    assert "Week 1" in page
    assert "Week 8" in page
    assert "May 4" in page
    assert "Jun 22" in page
    assert "Source Week" in page
    assert "menu_week_paste.js" in page


def test_menu_detail_route_redirects_week_clipboard_paste_to_week_selection_link(app_client, isolated_db):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Week Clipboard Link Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-06-07",
            "service_days": ["monday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line"],
            "menu_length_weeks": "5",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT menu_slot_id FROM menu_slot WHERE menu_id = ? AND week_number = 2 ORDER BY menu_slot_id ASC",
        (menu_id,),
    )
    week_two_slot_id = cursor.fetchone()[0]
    conn.close()

    app_client.post(
        f"/menus/{menu_id}/bulk-action",
        data={
            "week": "2",
            "action": "copy",
            "scope": "week",
            "selected_slot_ids": [str(week_two_slot_id)],
        },
        follow_redirects=False,
    )

    response = app_client.get(f"/menus/{menu_id}?week=2&bulk_action=paste")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Choose Destination Weeks" in page
    assert f"/menus/{menu_id}/paste-weeks?source_week=2" in page
    assert "Select Slot" not in page


def test_menu_week_paste_post_applies_copied_week_to_selected_destination(app_client, isolated_db):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Week Paste Apply Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-17",
            "service_days": ["monday", "tuesday"],
            "meal_periods": ["lunch"],
            "concepts": ["hot_line", "salad_bar"],
            "menu_length_weeks": "2",
        },
        follow_redirects=False,
    )
    menu_id = int(create_response.headers["Location"].rstrip("/").split("/")[-1])
    monday_hot_line_id = create_base_food(item_name="Week Route Monday Hot Line")
    monday_salad_bar_id = create_base_food(item_name="Week Route Monday Salad Bar")
    tuesday_hot_line_id = create_base_food(item_name="Week Route Tuesday Hot Line")
    tuesday_salad_bar_id = create_base_food(item_name="Week Route Tuesday Salad Bar")

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT menu_slot_id, week_number, day_of_week, concept_name
        FROM menu_slot
        WHERE menu_id = ?
        ORDER BY menu_slot_id ASC
        """,
        (menu_id,),
    )
    slot_rows = cursor.fetchall()
    cursor.execute(
        "UPDATE item SET status = 'live' WHERE item_id IN (?, ?, ?, ?)",
        (monday_hot_line_id, monday_salad_bar_id, tuesday_hot_line_id, tuesday_salad_bar_id),
    )
    conn.commit()
    conn.close()

    slot_lookup = {
        (week_number, day_of_week, concept_name): menu_slot_id
        for menu_slot_id, week_number, day_of_week, concept_name in slot_rows
    }

    app_client.post(
        f"/menus/{menu_id}/slots/{slot_lookup[(1, 'monday', 'hot_line')]}/assign",
        data={"week": "1", "selected_item_ids": [str(monday_hot_line_id)]},
        follow_redirects=False,
    )
    app_client.post(
        f"/menus/{menu_id}/slots/{slot_lookup[(1, 'monday', 'salad_bar')]}/assign",
        data={"week": "1", "selected_item_ids": [str(monday_salad_bar_id)]},
        follow_redirects=False,
    )
    app_client.post(
        f"/menus/{menu_id}/slots/{slot_lookup[(1, 'tuesday', 'hot_line')]}/assign",
        data={"week": "1", "selected_item_ids": [str(tuesday_hot_line_id)]},
        follow_redirects=False,
    )
    app_client.post(
        f"/menus/{menu_id}/slots/{slot_lookup[(1, 'tuesday', 'salad_bar')]}/assign",
        data={"week": "1", "selected_item_ids": [str(tuesday_salad_bar_id)]},
        follow_redirects=False,
    )

    app_client.post(
        f"/menus/{menu_id}/bulk-action",
        data={
            "week": "1",
            "action": "copy",
            "scope": "week",
            "selected_slot_ids": [str(slot_lookup[(1, 'monday', 'hot_line')])],
        },
        follow_redirects=False,
    )

    response = app_client.post(
        f"/menus/{menu_id}/paste-weeks",
        data={
            "source_week": "1",
            "selected_weeks": ["2"],
        },
        follow_redirects=True,
    )
    page = response.get_data(as_text=True)

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT item_id FROM menu_slot_item WHERE menu_slot_id = ?", (slot_lookup[(2, 'monday', 'hot_line')],))
    week_two_monday_hot_line = cursor.fetchone()[0]
    cursor.execute("SELECT item_id FROM menu_slot_item WHERE menu_slot_id = ?", (slot_lookup[(2, 'monday', 'salad_bar')],))
    week_two_monday_salad_bar = cursor.fetchone()[0]
    cursor.execute("SELECT item_id FROM menu_slot_item WHERE menu_slot_id = ?", (slot_lookup[(2, 'tuesday', 'hot_line')],))
    week_two_tuesday_hot_line = cursor.fetchone()[0]
    cursor.execute("SELECT item_id FROM menu_slot_item WHERE menu_slot_id = ?", (slot_lookup[(2, 'tuesday', 'salad_bar')],))
    week_two_tuesday_salad_bar = cursor.fetchone()[0]
    conn.close()

    assert response.status_code == 200
    assert "Pasted copied week into 1 destination week." in page
    assert week_two_monday_hot_line == monday_hot_line_id
    assert week_two_monday_salad_bar == monday_salad_bar_id
    assert week_two_tuesday_hot_line == tuesday_hot_line_id
    assert week_two_tuesday_salad_bar == tuesday_salad_bar_id


def test_menu_bulk_clear_route_supports_day_scope(app_client, isolated_db):
    create_response = app_client.post(
        "/menus/new",
        data={
            "menu_name": "Bulk Day Clear Menu",
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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
            "menu_start_date": "2026-05-04",
            "menu_end_date": "2026-05-10",
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

    response = app_client.get(f"/recipe-collection/items/{item_id}")

    assert "Edit Item" in response.get_data(as_text=True)


def test_item_detail_hides_edit_link_for_standard_user(app_client):
    item_id = create_base_food(item_name="Readonly Celery")

    response = app_client.get(f"/recipe-collection/items/{item_id}")

    assert "Edit Item" not in response.get_data(as_text=True)


def test_recipe_legacy_route_redirects_to_item_detail(app_client):
    item_id = create_base_food(item_name="Pepperoni")

    response = app_client.get(f"/recipes/{item_id}", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/recipe-collection/items/{item_id}")


def test_recipe_collection_legacy_browser_routes_redirect(app_client):
    item_id = create_base_food(item_name="Legacy Route Pepper")

    legacy_routes = [
        ("/collection?q=pepper", "/recipe-collection?q=pepper"),
        ("/my-recipes?sort=name_asc", "/recipe-collection/my-recipes?sort=name_asc"),
        ("/new/recipe", "/recipe-collection/new/recipe"),
        ("/new/base-food", "/recipe-collection/new/base-food"),
        (f"/items/{item_id}?technical_view=advanced", f"/recipe-collection/items/{item_id}?technical_view=advanced"),
        (f"/items/{item_id}/edit", f"/recipe-collection/items/{item_id}/edit"),
        (f"/items/{item_id}/print", f"/recipe-collection/items/{item_id}/print"),
    ]

    for legacy_path, canonical_path in legacy_routes:
        response = app_client.get(legacy_path, follow_redirects=False)

        assert response.status_code == 301
        assert response.headers["Location"].endswith(canonical_path)


def test_api_search_items_returns_json_results(app_client, isolated_db):
    item_id = create_base_food(item_name="Liquid Egg")

    # Route search is restricted to live items only.
    # Direct sqlite use keeps this aligned with the current workflow rule.
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (item_id,))
    conn.commit()
    conn.close()

    response = app_client.get("/recipe-collection/api/items/search?q=egg")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["items"]
    assert payload["items"][0]["item_name"] == "Liquid Egg"
    assert payload["has_more"] is False


def test_api_search_items_returns_empty_results_for_short_queries(app_client):
    create_base_food(item_name="Table Salt")

    response = app_client.get("/recipe-collection/api/items/search?q=s")

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

    response = app_client.get("/recipe-collection/api/items/search?q=pepper")
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

    response = app_client.get("/recipe-collection/api/items/search?q=offset&limit=10&offset=10")
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

    response = app_client.get("/recipe-collection/api/items/search?q=chikcen")
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

    default_response = app_client.get("/recipe-collection/api/items/search?q=nayo")
    relaxed_response = app_client.get("/recipe-collection/api/items/search?q=nayo&relax_short_query=1")

    assert default_response.status_code == 200
    assert default_response.get_json()["items"] == []
    assert relaxed_response.status_code == 200
    assert relaxed_response.get_json()["items"]
    assert relaxed_response.get_json()["items"][0]["item_name"] == "Mayo"


def test_item_detail_returns_404_for_missing_item(app_client):
    response = app_client.get("/recipe-collection/items/9999")

    assert response.status_code == 404
    assert "Item not found." in response.get_data(as_text=True)


def test_my_recipes_route_renders_recipe_list_and_filters(app_client, isolated_db):
    dressing_id = create_base_food(item_name="Dijon Dressing")

    app_client.post(
        "/recipe-collection/api/recipes",
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
        "/recipe-collection/api/recipes",
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

    response = app_client.get("/recipe-collection/my-recipes?status=reviewed&sort=name_asc")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "My Recipes" in page
    assert "Dinner Salad" in page
    assert "Lunch Salad" not in page
    assert "Reviewed" in page


def test_my_recipes_route_shows_empty_state(app_client):
    response = app_client.get("/recipe-collection/my-recipes")
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

    response = app_client.get("/recipe-collection")
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

    filtered_response = app_client.get("/recipe-collection?q=Browse&item_type=base_food&sort=name_asc&offset=15")
    filtered_page = filtered_response.get_data(as_text=True)
    recipe_only_response = app_client.get("/recipe-collection?item_type=recipe")
    recipe_only_page = recipe_only_response.get_data(as_text=True)

    assert filtered_response.status_code == 200
    assert "Browse Chicken 15" in filtered_page
    assert "Previous" in filtered_page
    assert "Next" not in filtered_page or "is-disabled\">Next" in filtered_page
    assert recipe_only_response.status_code == 200
    assert "Collection Recipe Placeholder" in recipe_only_page


def test_live_collection_route_shows_minimum_query_message(app_client):
    response = app_client.get("/recipe-collection?q=c")

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

    response = app_client.get("/recipe-collection?q=chikcen")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Chicken Rice Bowl" in page


def test_notifications_page_shows_note_notifications(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Notification Base")
    recipe_response = app_client.post(
        "/recipe-collection/api/recipes",
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
        f"/recipe-collection/items/{recipe_id}/notes",
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
        "/recipe-collection/api/recipes",
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
        "/recipe-collection/api/recipes",
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
        "/recipe-collection/api/recipes",
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
        f"/recipe-collection/api/recipes/{recipe_id}",
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
        "/recipe-collection/api/recipes",
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
        f"/recipe-collection/items/{recipe_id}/notes",
        data={"note_text": "Please revise and resubmit."},
        follow_redirects=False,
    )

    app_client.post(
        "/login/select",
        data={"selected_user_id": "dev_user_001"},
        follow_redirects=False,
    )

    response = app_client.get(f"/recipe-collection/items/{recipe_id}")
    notifications_response = app_client.get("/notifications")

    assert response.status_code == 200
    assert "Please revise and resubmit." in response.get_data(as_text=True)
    assert "No open notifications" in notifications_response.get_data(as_text=True)


def test_item_detail_view_acknowledges_workflow_action_notifications(app_client):
    base_food_id = create_base_food(item_name="Workflow Ack Oil")
    recipe_response = app_client.post(
        "/recipe-collection/api/recipes",
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
    response = app_client.get(f"/recipe-collection/items/{recipe_id}")
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
        "/recipe-collection/api/recipes",
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

    response = app_client.get("/recipe-collection/my-recipes")
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
        "/recipe-collection/api/recipes",
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

    response = app_client.get(f"/recipe-collection/items/{item_id}/edit", follow_redirects=False)

    assert response.status_code == 302


def test_item_detail_page_shows_note_form_when_recipient_is_available(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Detail Notes Base")
    recipe_response = app_client.post(
        "/recipe-collection/api/recipes",
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

    response = app_client.get(f"/recipe-collection/items/{recipe_id}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Workflow Notes" in page
    assert "Post note to Plato Choi" in page
    assert "Recipe created." in page


def test_live_item_detail_hides_workflow_notes(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Live Notes Base")
    recipe_response = app_client.post(
        "/recipe-collection/api/recipes",
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

    response = app_client.get(f"/recipe-collection/items/{recipe_id}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Workflow Notes" not in page
    assert "Post Note" not in page
    assert "Workflow History" not in page


def test_live_item_detail_shows_advanced_workflow_toggle_for_reviewer(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Live Toggle Base")
    recipe_response = app_client.post(
        "/recipe-collection/api/recipes",
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

    response = app_client.get(f"/recipe-collection/items/{recipe_id}")
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

    default_response = app_client.get(f"/recipe-collection/items/{recipe_id}")
    flattened_response = app_client.get(f"/recipe-collection/items/{recipe_id}?ingredient_view=flattened")
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

    response = app_client.get(f"/recipe-collection/items/{recipe_id}?ingredient_view=flattened")
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
    response = app_client.get(f"/recipe-collection/items/{recipe_id}?technical_view=advanced")
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

    response = app_client.get(f"/recipe-collection/items/{recipe_id}")
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

    response = app_client.get(f"/recipe-collection/items/{recipe_a_id}?ingredient_view=flattened")
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

    response = app_client.get(
        f"/recipe-collection/items/{recipe_id}?scale_quantity=1&scale_unit=qt"
        f"&user_serving_size_quantity=1&user_serving_size_unit=cup"
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Scale Recipe" in page
    assert "Scaling to 1.0 qt" in page
    assert "base yield 2.0 qt." in page
    assert "Scaled Ingredients" in page


def test_live_recipe_detail_snapshot_reflects_scaled_recipe_values(app_client, isolated_db):
    oil_id = create_base_food(item_name="Route Snapshot Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Route Snapshot Recipe",
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
    cursor.execute(
        """
        UPDATE item
        SET status = 'live',
            serving_size_quantity = 4,
            serving_size_unit = 'oz',
            serving_count = 8
        WHERE item_id = ?
        """,
        (recipe_id,),
    )
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (oil_id,))
    conn.commit()
    conn.close()

    response = app_client.get(
        f"/recipe-collection/items/{recipe_id}?scale_quantity=1&scale_unit=qt"
        f"&user_serving_size_quantity=1&user_serving_size_unit=cup"
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "1.0 qt" in page
    assert "1.102" in page
    assert "lb" in page
    assert "qt" in page
    assert "500.0 g" not in page
    assert "Serving Count:</strong> 4.0" in page
    assert "Serving Size:</strong> 4.0 oz" in page
    assert "User Serving Size" in page
    assert "makes 4 portions" in page


def test_live_recipe_detail_snapshot_uses_unit_system_without_scaling(app_client, isolated_db):
    oil_id = create_base_food(item_name="Route Base Snapshot Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Route Base Snapshot Recipe",
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

    response = app_client.get(f"/recipe-collection/items/{recipe_id}?unit_system=imperial")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "2.205" in page
    assert "lb" in page
    assert "2" in page
    assert "qt" in page
    assert "1000.0 g" not in page


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

    response = app_client.get(f"/recipe-collection/items/{recipe_id}?ingredient_view=flattened&scale_quantity=2&scale_unit=each")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Scaled Flattened Ingredients" in page
    assert "Scaling to 2.0 each" in page
    assert "base yield 1.0 each." in page
    assert "Route Flat Sauce" in page
    assert "Print Recipe" in page

    print_response = app_client.get(f"/recipe-collection/items/{recipe_id}/print?scale_quantity=2&scale_unit=each&display_mode=mass")
    print_page = print_response.get_data(as_text=True)

    assert print_response.status_code == 200
    assert "Kitchen Production Sheet" in print_page
    assert "Route Flat Parent" in print_page
    assert f"Recipe / Item ID {recipe_id}" in print_page
    assert "Scaled Yield" in print_page
    assert "2.0 each" in print_page
    assert "Ingredients" in print_page
    assert "recipe-print-ingredient-sub_recipe depth-0" in print_page
    assert "recipe-print-ingredient-base_food depth-1" in print_page
    assert "Sub-recipe group" in print_page
    assert "Route Flat Oil" in print_page
    assert f"Base Food #{oil_id}" in print_page
    assert "Method" in print_page
    assert "Assemble" in print_page
    assert "HACCP / Process Notes" in print_page
    assert "Production Notes" in print_page


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

    response = app_client.get(f"/recipe-collection/items/{recipe_id}?scale_quantity=1&scale_unit=each")
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

    response = app_client.get(f"/recipe-collection/items/{recipe_id}?scale_quantity=1&scale_unit=kg")
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

    response = app_client.get(f"/recipe-collection/items/{recipe_id}?scale_quantity=500&scale_unit=g")
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

    response = app_client.get(f"/recipe-collection/items/{recipe_id}?scale_quantity=1&scale_unit=kg")
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

    response = app_client.get(f"/recipe-collection/items/{recipe_id}?display_mode=volume&unit_system=imperial")
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

    response = app_client.get(f"/recipe-collection/items/{recipe_id}?display_mode=mass&unit_system=metric")
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

    response = app_client.get(f"/recipe-collection/items/{recipe_id}")
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
        f"/recipe-collection/items/{recipe_id}?ingredient_view=flattened&scale_quantity=1&scale_unit=qt"
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
        "/recipe-collection/api/recipes",
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

    response = app_client.get(f"/recipe-collection/items/{recipe_id}?workflow_view=advanced")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Hide Advanced Workflow" in page
    assert "Workflow History" in page
    assert "Workflow Notes" in page


def test_live_item_detail_standard_user_cannot_enable_advanced_workflow(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Live Standard Base")
    recipe_response = app_client.post(
        "/recipe-collection/api/recipes",
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

    response = app_client.get(f"/recipe-collection/items/{recipe_id}?workflow_view=advanced")
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
        f"/recipe-collection/items/{item_id}/edit",
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
        f"/recipe-collection/items/{item_id}/edit",
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

    standard_response = app_client.get(f"/recipe-collection/items/{item_id}")
    standard_page = standard_response.get_data(as_text=True)

    app_client.post(
        "/login/select",
        data={"selected_user_id": "dietitian_001"},
        follow_redirects=False,
    )
    privileged_response = app_client.get(f"/recipe-collection/items/{item_id}?technical_view=advanced")
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
    response = app_client.get(f"/recipe-collection/items/{item_id}?technical_view=advanced&convert_quantity=1&convert_unit=tbs")
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
    response = app_client.get(f"/recipe-collection/items/{item_id}?technical_view=advanced&convert_quantity=1&convert_unit=each")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Conversion warnings" in page
    assert "not convertible" in page


def test_edit_recipe_route_renders_for_allowed_role(app_client):
    base_food_id = create_base_food(item_name="Edit Dressing")
    recipe_response = app_client.post(
        "/recipe-collection/api/recipes",
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

    response = app_client.get(f"/recipe-collection/items/{recipe_id}/edit")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Edit Recipe" in page
    assert "Edit Recipe" in page


def test_api_update_recipe_updates_existing_recipe(app_client, isolated_db):
    base_food_id = create_base_food(item_name="Edit Oil")
    create_response = app_client.post(
        "/recipe-collection/api/recipes",
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
        f"/recipe-collection/api/recipes/{recipe_id}",
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
        "/recipe-collection/api/recipes",
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

    edit_page = app_client.get(f"/recipe-collection/items/{recipe_id}/edit")
    update_response = app_client.put(
        f"/recipe-collection/api/recipes/{recipe_id}",
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
        "/recipe-collection/api/recipes",
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
        f"/recipe-collection/items/{recipe_id}/notes",
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
    response = app_client.get(f"/recipe-collection/items/{recipe_id}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Workflow History" in page
    assert "Workflow note posted to Plato Choi." in page
    assert "Recipe returned to submitter." in page
    assert "Reason:" in page
    assert "Clarify the final plating step." in page
