import sqlite3

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
    assert detail["item_rows"][0]["pack_summary"] == "6 packs x 5 lb"
    assert "counted by each and case" in detail["item_rows"][0]["interpretation"]


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
