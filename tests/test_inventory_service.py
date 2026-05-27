import sqlite3
from datetime import date

from services.inventory_service import (
    add_inventory_location_break,
    build_inventory_item_interpretation,
    create_inventory_location,
    get_inventory_dashboard,
    get_inventory_location_detail,
    move_inventory_count_row,
    save_inventory_location_item,
    transfer_inventory_location_item,
    update_inventory_location_item,
)
from services.inventory_bridge_service import (
    create_inventory_catalog_item,
    create_inventory_item_match,
    get_inventory_availability_for_items,
    resolve_inventory_for_recipe_item,
)
from services.item_service import create_base_food
from services.inventory_usage_service import get_inventory_item_detail, get_inventory_item_usage
from services.menu_forecast_service import save_menu_forecast_yield
from services.menu_service import create_menu, replace_menu_slot_items
from services.production_record_service import ensure_production_record, save_production_record_line
from services.recipe_service import create_recipe
from queries.menu_forecast import get_menu_forecast_page


def _live_base_food(isolated_db, name: str) -> int:
    item_id = create_base_food(item_name=name, mass_quantity=1, mass_unit="lb")
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (item_id,))
    conn.commit()
    conn.close()
    return item_id


def test_inventory_location_item_updates_current_on_hand(isolated_db):
    item_id = _live_base_food(isolated_db, "Inventory Apples")
    location_id = create_inventory_location(
        location_name="Walk-In Cooler",
        actor_user_id="dev_user_001",
        actor_display_name="Plato Choi",
    )

    save_inventory_location_item(
        inventory_location_id=location_id,
        item_id=item_id,
        quantity="12.5",
        unit="lb",
    )
    dashboard = get_inventory_dashboard()

    assert dashboard["current_on_hand"][0]["item_name"] == "Inventory Apples"
    assert dashboard["current_on_hand"][0]["quantity_display"] == "12.5"
    assert dashboard["current_on_hand"][0]["unit"] == "lb"
    assert dashboard["current_on_hand"][0]["display_quantity_display"] == "12.5"
    assert dashboard["current_on_hand"][0]["display_unit"] == "lb"
    assert dashboard["current_on_hand"][0]["item_category"] == "produce"


def test_location_item_update_replaces_quantity(isolated_db):
    item_id = _live_base_food(isolated_db, "Inventory Rice")
    location_id = create_inventory_location(
        location_name="Dry Storage",
        actor_user_id="dev_user_001",
        actor_display_name="Plato Choi",
    )
    save_inventory_location_item(
        inventory_location_id=location_id,
        item_id=item_id,
        quantity="20",
        unit="lb",
    )
    detail = get_inventory_location_detail(location_id)
    update_inventory_location_item(
        inventory_location_item_id=detail["item_rows"][0]["inventory_location_item_id"],
        quantity="14",
        unit="lb",
    )
    dashboard = get_inventory_dashboard()

    assert len(dashboard["current_on_hand"]) == 1
    assert dashboard["current_on_hand"][0]["quantity_display"] == "14"


def test_inventory_location_tree_includes_sub_storage(isolated_db):
    parent_id = create_inventory_location(
        location_name="Main Freezer",
        actor_user_id="dev_user_001",
        actor_display_name="Plato Choi",
    )
    create_inventory_location(
        parent_inventory_location_id=parent_id,
        location_name="Rack A",
        actor_user_id="dev_user_001",
        actor_display_name="Plato Choi",
    )

    dashboard = get_inventory_dashboard()

    assert dashboard["location_tree"][0]["location_name"] == "Main Freezer"
    assert dashboard["location_tree"][0]["children"][0]["location_name"] == "Rack A"


def test_duplicate_sub_storage_names_are_scoped_to_parent(isolated_db):
    freezer_id = create_inventory_location(
        location_name="Scoped Freezer",
        actor_user_id="dev_user_001",
        actor_display_name="Plato Choi",
    )
    cooler_id = create_inventory_location(
        location_name="Scoped Cooler",
        actor_user_id="dev_user_001",
        actor_display_name="Plato Choi",
    )

    first_left_wall_id = create_inventory_location(
        parent_inventory_location_id=freezer_id,
        location_name="Left Wall",
        actor_user_id="dev_user_001",
        actor_display_name="Plato Choi",
    )
    second_left_wall_id = create_inventory_location(
        parent_inventory_location_id=cooler_id,
        location_name="Left Wall",
        actor_user_id="dev_user_001",
        actor_display_name="Plato Choi",
    )

    assert first_left_wall_id != second_left_wall_id


def test_each_and_case_count_normalizes_quantity(isolated_db):
    item_id = _live_base_food(isolated_db, "Inventory Chicken")
    location_id = create_inventory_location(
        location_name="Case Count Freezer",
        actor_user_id="dev_user_001",
        actor_display_name="Plato Choi",
    )

    save_inventory_location_item(
        inventory_location_id=location_id,
        item_id=item_id,
        count_each_quantity="2",
        count_case_quantity="1",
        pack_quantity="6",
        pack_size_text="5 lb",
        unit_of_measurement="Case",
        count_type="counted_by_each_and_case",
    )
    detail = get_inventory_location_detail(location_id)

    assert detail["item_rows"][0]["quantity_display"] == "1.33"
    assert detail["item_rows"][0]["display_quantity_display"] == "1.33"
    assert detail["item_rows"][0]["display_unit"] == "case"
    assert detail["item_rows"][0]["pack_summary"] == "6 packs x 5 lb"
    assert "counted by each and case" in detail["item_rows"][0]["interpretation"]


def test_current_on_hand_prefers_case_display_for_case_counts(isolated_db):
    item_id = _live_base_food(isolated_db, "Inventory Pasta")
    location_id = create_inventory_location(
        location_name="Case Display Dry Storage",
        actor_user_id="dev_user_001",
        actor_display_name="Plato Choi",
    )

    save_inventory_location_item(
        inventory_location_id=location_id,
        item_id=item_id,
        count_case_quantity="2",
        pack_quantity="8",
        pack_size_text="5 lb",
        unit_of_measurement="Case",
        count_type="counted_by_case_only",
    )
    dashboard = get_inventory_dashboard()

    assert dashboard["current_on_hand"][0]["quantity_display"] == "2"
    assert dashboard["current_on_hand"][0]["display_quantity_display"] == "2"
    assert dashboard["current_on_hand"][0]["display_unit"] == "case"
    assert dashboard["current_on_hand"][0]["display_unit_label"] == "case"


def test_current_on_hand_displays_small_case_counts_as_each(isolated_db):
    item_id = _live_base_food(isolated_db, "Inventory Pepper")
    location_id = create_inventory_location(
        location_name="Small Case Display Cooler",
        actor_user_id="dev_user_001",
        actor_display_name="Plato Choi",
    )

    save_inventory_location_item(
        inventory_location_id=location_id,
        item_id=item_id,
        count_each_quantity="1",
        pack_quantity="8",
        pack_size_text="5 lb",
        unit_of_measurement="Case",
        count_type="counted_by_each_and_case",
    )
    dashboard = get_inventory_dashboard()
    detail = get_inventory_location_detail(location_id)

    assert dashboard["current_on_hand"][0]["quantity_display"] == "0.12"
    assert dashboard["current_on_hand"][0]["display_quantity_display"] == "1"
    assert dashboard["current_on_hand"][0]["display_unit"] == "each"
    assert dashboard["current_on_hand"][0]["item_category"] == "produce"
    assert detail["item_rows"][0]["display_quantity_display"] == "1"
    assert detail["item_rows"][0]["display_unit"] == "each"


def test_current_on_hand_keeps_case_uom_each_only_counts_as_each(isolated_db):
    item_id = _live_base_food(isolated_db, "Inventory Case Each Apples")
    location_id = create_inventory_location(
        location_name="Case Each Display Pantry",
        actor_user_id="dev_user_001",
        actor_display_name="Plato Choi",
    )

    save_inventory_location_item(
        inventory_location_id=location_id,
        item_id=item_id,
        count_each_quantity="8",
        pack_quantity="8",
        pack_size_text="4 lb",
        unit_of_measurement="Case",
        count_type="counted_by_each_only",
    )
    dashboard = get_inventory_dashboard()
    detail = get_inventory_location_detail(location_id)

    assert dashboard["current_on_hand"][0]["quantity_display"] == "8"
    assert dashboard["current_on_hand"][0]["display_quantity_display"] == "8"
    assert dashboard["current_on_hand"][0]["display_unit"] == "each"
    assert detail["item_rows"][0]["display_quantity_display"] == "8"
    assert detail["item_rows"][0]["display_unit"] == "each"


def test_inventory_item_interpretation_uses_singular_pack_verb():
    interpretation = build_inventory_item_interpretation(
        item_name="Bacon",
        pack_quantity="1",
        pack_size_text="5 lb",
        unit_of_measurement="Case",
        count_type="counted_by_case_only",
    )

    assert "there is 1 pack of 5 lb Bacon" in interpretation


def test_break_rows_can_be_ordered_with_items(isolated_db):
    item_id = _live_base_food(isolated_db, "Inventory Mushrooms")
    location_id = create_inventory_location(
        location_name="Break Row Cooler",
        actor_user_id="dev_user_001",
        actor_display_name="Plato Choi",
    )
    save_inventory_location_item(
        inventory_location_id=location_id,
        item_id=item_id,
        count_each_quantity="4",
        unit_of_measurement="Each",
        count_type="counted_by_each_only",
    )
    break_id = add_inventory_location_break(
        inventory_location_id=location_id,
        break_label="Shelf 2",
    )

    move_inventory_count_row(row_type="break", row_id=break_id, direction="up")
    detail = get_inventory_location_detail(location_id)

    assert detail["count_rows"][0]["row_type"] == "break"
    assert detail["count_rows"][0]["break_label"] == "Shelf 2"


def test_transfer_item_moves_row_to_target_sub_location(isolated_db):
    item_id = _live_base_food(isolated_db, "Inventory Tomatoes")
    parent_id = create_inventory_location(
        location_name="Transfer Cooler",
        actor_user_id="dev_user_001",
        actor_display_name="Plato Choi",
    )
    source_id = create_inventory_location(
        parent_inventory_location_id=parent_id,
        location_name="Shelf A",
        actor_user_id="dev_user_001",
        actor_display_name="Plato Choi",
    )
    target_id = create_inventory_location(
        parent_inventory_location_id=parent_id,
        location_name="Shelf B",
        actor_user_id="dev_user_001",
        actor_display_name="Plato Choi",
    )
    save_inventory_location_item(
        inventory_location_id=source_id,
        item_id=item_id,
        count_each_quantity="9",
        unit_of_measurement="Each",
        count_type="counted_by_each_only",
    )
    source_detail = get_inventory_location_detail(source_id)

    transfer_inventory_location_item(
        inventory_location_item_id=source_detail["item_rows"][0]["inventory_location_item_id"],
        target_inventory_location_id=target_id,
    )

    assert get_inventory_location_detail(source_id)["item_rows"] == []
    assert get_inventory_location_detail(target_id)["item_rows"][0]["item_name"] == "Inventory Tomatoes"


def test_inventory_count_creates_legacy_catalog_match(isolated_db):
    item_id = _live_base_food(isolated_db, "Inventory Lentils")
    location_id = create_inventory_location(
        location_name="Bridge Dry Storage",
        actor_user_id="dev_user_001",
        actor_display_name="Plato Choi",
    )

    save_inventory_location_item(
        inventory_location_id=location_id,
        item_id=item_id,
        count_each_quantity="2",
        count_case_quantity="1",
        pack_quantity="4",
        pack_size_text="10 lb",
        unit_of_measurement="Case",
        count_type="counted_by_each_and_case",
    )

    match = resolve_inventory_for_recipe_item(item_id)

    assert match["match_status"] == "active"
    assert match["match_type"] == "legacy_item"
    assert match["catalog_item"]["display_name"] == "Inventory Lentils"
    assert match["catalog_item"]["pack_quantity_display"] == "4"
    assert match["catalog_item"]["pack_size_text"] == "10 lb"


def test_inventory_availability_contract_returns_match_and_on_hand(isolated_db):
    item_id = _live_base_food(isolated_db, "Inventory Farro")
    location_id = create_inventory_location(
        location_name="Bridge Cooler",
        actor_user_id="dev_user_001",
        actor_display_name="Plato Choi",
    )
    save_inventory_location_item(
        inventory_location_id=location_id,
        item_id=item_id,
        count_each_quantity="8",
        unit_of_measurement="Lb",
        count_type="counted_by_each_only",
    )

    availability = get_inventory_availability_for_items([item_id])

    assert availability == [
        {
            "recipe_collection_item_id": item_id,
            "recipe_collection_item_name": "Inventory Farro",
            "inventory_catalog_item_id": availability[0]["inventory_catalog_item_id"],
            "inventory_catalog_display_name": "Inventory Farro",
            "match_type": "legacy_item",
            "confidence_score": 1.0,
            "match_status": "active",
            "on_hand_unit": "lb",
            "on_hand_quantity": 8.0,
            "on_hand_quantity_display": "8",
            "location_count": 1,
            "last_counted_at": availability[0]["last_counted_at"],
            "purchase_uom": "Lb",
            "pack_quantity": None,
            "pack_quantity_display": "",
            "pack_size_text": "",
        }
    ]


def test_manual_inventory_match_can_exist_without_count_rows(isolated_db):
    item_id = _live_base_food(isolated_db, "Inventory Polenta")
    catalog_item_id = create_inventory_catalog_item(
        display_name="Vendor Yellow Polenta",
        vendor_name="Kitchen Vendor",
        vendor_item_code="POL-10",
        purchase_uom="Case",
        pack_quantity="6",
        pack_size_text="5 lb",
    )
    create_inventory_item_match(
        recipe_collection_item_id=item_id,
        inventory_catalog_item_id=catalog_item_id,
        match_type="manual",
        confidence_score="0.95",
    )

    availability = get_inventory_availability_for_items([item_id])

    assert availability[0]["inventory_catalog_item_id"] == catalog_item_id
    assert availability[0]["inventory_catalog_display_name"] == "Vendor Yellow Polenta"
    assert availability[0]["match_type"] == "manual"
    assert availability[0]["confidence_score"] == 0.95
    assert availability[0]["on_hand_quantity_display"] == "0"
    assert availability[0]["purchase_uom"] == "Case"


def test_inventory_item_detail_groups_recipe_usage_and_count_rolldown(isolated_db):
    ingredient_id = _live_base_food(isolated_db, "Inventory Usage Carrot")
    recipe_id = create_recipe(
        {
            "item_name": "Inventory Usage Soup",
            "yield_quantity": 10,
            "yield_unit": "lb",
            "primary_cooking_method_code": "simmer",
            "instruction_steps": ["Cook"],
            "ingredients": [
                {
                    "component_item_id": ingredient_id,
                    "component_quantity": 2,
                    "component_unit": "lb",
                }
            ],
        }
    )
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (recipe_id,))
    conn.commit()
    conn.close()
    location_id = create_inventory_location(
        location_name="Usage Cooler",
        actor_user_id="dev_user_001",
        actor_display_name="Plato Choi",
    )
    save_inventory_location_item(
        inventory_location_id=location_id,
        item_id=ingredient_id,
        count_each_quantity="3",
        count_case_quantity="1",
        pack_quantity="4",
        pack_size_text="5 lb",
        unit_of_measurement="Case",
        count_type="counted_by_each_and_case",
    )

    future_menu_id = create_menu(
        menu_name="Inventory Future Menu",
        author_user_id="dev_user_001",
        author_display_name="Plato Choi",
        service_days=["monday"],
        meal_periods=["lunch"],
        concepts=["hot_line"],
        menu_length_weeks=1,
        menu_start_date="2026-06-01",
        menu_end_date="2026-06-07",
        require_date_range=True,
        allowed_service_days=["monday"],
        allowed_meal_periods=["lunch"],
        allowed_concepts=["hot_line"],
    )
    past_menu_id = create_menu(
        menu_name="Inventory Past Menu",
        author_user_id="dev_user_001",
        author_display_name="Plato Choi",
        service_days=["monday"],
        meal_periods=["lunch"],
        concepts=["hot_line"],
        menu_length_weeks=1,
        menu_start_date="2026-05-04",
        menu_end_date="2026-05-10",
        require_date_range=True,
        allowed_service_days=["monday"],
        allowed_meal_periods=["lunch"],
        allowed_concepts=["hot_line"],
    )
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (future_menu_id,))
    future_slot_id = cursor.fetchone()[0]
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (past_menu_id,))
    past_slot_id = cursor.fetchone()[0]
    conn.close()
    replace_menu_slot_items(menu_slot_id=future_slot_id, selected_item_ids=[recipe_id], actor_user_id="dev_user_001")
    replace_menu_slot_items(menu_slot_id=past_slot_id, selected_item_ids=[recipe_id], actor_user_id="dev_user_001")
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT msi.menu_slot_item_id, ms.menu_id
        FROM menu_slot_item msi
        JOIN menu_slot ms ON ms.menu_slot_id = msi.menu_slot_id
        WHERE ms.menu_id IN (?, ?)
        ORDER BY ms.menu_id ASC
        """,
        (past_menu_id, future_menu_id),
    )
    slot_items = {menu_id: slot_item_id for slot_item_id, menu_id in cursor.fetchall()}
    conn.close()
    for menu_id, slot_item_id in slot_items.items():
        save_menu_forecast_yield(
            menu_id=menu_id,
            menu_slot_item_id=slot_item_id,
            actor_user_id="dev_user_001",
            forecast_yield_quantity=12,
            forecast_yield_unit="lb",
        )
    past_forecast_page = get_menu_forecast_page(past_menu_id, week_number=1, day_of_week="monday")
    record = ensure_production_record(
        menu_id=past_menu_id,
        week_number=1,
        day_of_week="monday",
        production_summary=past_forecast_page["production_summary"],
        actor_user_id="dev_user_001",
    )
    save_production_record_line(
        menu_id=past_menu_id,
        production_record_line_id=record["lines"][0]["production_record_line_id"],
        actor_user_id="dev_user_001",
        actual_quantity="12",
        actual_unit="lb",
        end_service_variance_quantity="1",
        end_service_variance_unit="lb",
        reason_code="as_expected",
    )
    future_forecast_page = get_menu_forecast_page(future_menu_id, week_number=1, day_of_week="monday")
    future_record = ensure_production_record(
        menu_id=future_menu_id,
        week_number=1,
        day_of_week="monday",
        production_summary=future_forecast_page["production_summary"],
        actor_user_id="dev_user_001",
    )
    save_production_record_line(
        menu_id=future_menu_id,
        production_record_line_id=future_record["lines"][0]["production_record_line_id"],
        actor_user_id="dev_user_001",
        actual_quantity="12",
        actual_unit="lb",
        end_service_variance_quantity="0",
        end_service_variance_unit="lb",
        reason_code="as_expected",
    )

    detail = get_inventory_item_detail(ingredient_id)

    assert detail["item"]["item_name"] == "Inventory Usage Carrot"
    assert detail["summary"]["current_on_hand_display"] == "1.75 case"
    assert detail["summary"]["count_location_count"] == 1
    assert detail["summary"]["next_usage_display"] == "Jun 1"
    assert detail["summary"]["next_needed_display"] == "2.4 lb"
    assert detail["summary"]["total_usage_count"] == 2
    assert detail["count_rolldown"][0]["count_each_quantity_display"] == "3"
    assert detail["count_rolldown"][0]["count_case_quantity_display"] == "1"
    assert detail["upcoming"][0]["menu_item_name"] == "Inventory Usage Soup"
    assert detail["upcoming"][0]["menu_name"] == "Inventory Future Menu"
    assert detail["upcoming"][0]["needed_display"] == "2.4 lb"
    assert detail["upcoming"][0]["actual_quantity_display"] == "12"
    assert detail["past"][0]["menu_item_name"] == "Inventory Usage Soup"
    assert detail["past"][0]["needed_display"] == "2.4 lb"
    assert detail["past"][0]["actual_quantity_display"] == "12"
    assert detail["past"][0]["variance_quantity_display"] == "1"


def test_inventory_usage_needed_quantity_uses_recipe_mass_volume_bridge(isolated_db):
    ingredient_id = _live_base_food(isolated_db, "Inventory Usage Apple")
    recipe_id = create_recipe(
        {
            "item_name": "Inventory Usage Apple Salad",
            "yield_quantity": 1.25,
            "yield_unit": "qt",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {
                    "component_item_id": ingredient_id,
                    "component_quantity": 1.5,
                    "component_unit": "cup",
                }
            ],
        }
    )
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE item
        SET status = 'live',
            mass_quantity = 600,
            mass_unit = 'g',
            volume_quantity = 1.25,
            volume_unit = 'qt'
        WHERE item_id = ?
        """,
        (recipe_id,),
    )
    conn.commit()
    conn.close()
    menu_id = create_menu(
        menu_name="Inventory Bridge Needed Menu",
        author_user_id="dev_user_001",
        author_display_name="Plato Choi",
        service_days=["tuesday"],
        meal_periods=["lunch"],
        concepts=["hot_line"],
        menu_length_weeks=1,
        menu_start_date="2026-05-26",
        menu_end_date="2026-05-26",
        require_date_range=True,
        allowed_service_days=["tuesday"],
        allowed_meal_periods=["lunch"],
        allowed_concepts=["hot_line"],
    )
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_slot_id FROM menu_slot WHERE menu_id = ?", (menu_id,))
    slot_id = cursor.fetchone()[0]
    conn.close()
    replace_menu_slot_items(menu_slot_id=slot_id, selected_item_ids=[recipe_id], actor_user_id="dev_user_001")
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT menu_slot_item_id FROM menu_slot_item WHERE menu_slot_id = ?", (slot_id,))
    slot_item_id = cursor.fetchone()[0]
    conn.close()
    save_menu_forecast_yield(
        menu_id=menu_id,
        menu_slot_item_id=slot_item_id,
        actor_user_id="dev_user_001",
        forecast_yield_quantity=1889.07,
        forecast_yield_unit="g",
    )

    usage = get_inventory_item_usage(ingredient_id, today=date(2026, 5, 26))

    assert usage["upcoming"][0]["forecast_quantity_display"] == "1889.07"
    assert usage["upcoming"][0]["forecast_unit"] == "g"
    assert usage["upcoming"][0]["needed_display"] == "4.72 cup"
