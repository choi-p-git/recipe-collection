import sqlite3
import random
from datetime import date

from dev_automation import (
    AutomationConfig,
    InventoryAutomationConfig,
    _build_inventory_count_payload,
    _inventory_count_type_options,
    run_dev_inventory_automation,
    run_dev_menu_automation,
)


def test_dev_menu_automation_creates_draft_menu_forecasts_and_records(isolated_db):
    result = run_dev_menu_automation(
        AutomationConfig(
            menu_name="Automation Smoke Menu",
            start_date=date(2026, 6, 1),
            weeks=1,
            service_days=("monday", "tuesday"),
            meal_periods=("breakfast",),
            concepts=("hot_line",),
            min_items_per_slot=3,
            max_items_per_slot=3,
            random_seed=7,
        )
    )

    assert result["slot_count"] == 2
    assert result["assignment_count"] == 6
    assert result["forecast_count"] == 6
    assert result["production_record_count"] == 2
    assert result["draft_record_count"] == 2
    assert result["posted_record_count"] == 0
    assert result["production_record_line_count"] > 0
    assert sum(result["scenario_counts"].values()) == result["production_record_line_count"]

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT menu_name, menu_start_date, menu_end_date, status
        FROM menu
        WHERE menu_id = ?
        """,
        (result["menu_id"],),
    )
    menu_row = cursor.fetchone()
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM menu_forecast mf
        JOIN menu_slot_item msi
          ON msi.menu_slot_item_id = mf.menu_slot_item_id
        JOIN menu_slot ms
          ON ms.menu_slot_id = msi.menu_slot_id
        WHERE ms.menu_id = ?
        """,
        (result["menu_id"],),
    )
    forecast_count = cursor.fetchone()[0]
    cursor.execute(
        """
        SELECT COUNT(*), SUM(CASE WHEN status = 'draft' THEN 1 ELSE 0 END)
        FROM production_record
        WHERE menu_id = ?
        """,
        (result["menu_id"],),
    )
    record_count, draft_count = cursor.fetchone()
    cursor.execute(
        """
        SELECT
            forecast_accuracy_level,
            forecast_quantity,
            end_service_variance_quantity
        FROM production_record_line prl
        JOIN production_record pr
          ON pr.production_record_id = prl.production_record_id
        WHERE pr.menu_id = ?
          AND prl.actual_quantity IS NOT NULL
          AND prl.end_service_variance_quantity IS NOT NULL
        """,
        (result["menu_id"],),
    )
    production_rows = cursor.fetchall()
    accuracy_levels = {row[0] for row in production_rows}
    variance_percents = [
        abs(float(variance_quantity) / float(forecast_quantity))
        for _, forecast_quantity, variance_quantity in production_rows
        if float(forecast_quantity or 0) > 0
    ]
    conn.close()

    assert menu_row == ("Automation Smoke Menu", "2026-06-01", "2026-06-07", "draft")
    assert forecast_count == result["forecast_count"]
    assert record_count == result["production_record_count"]
    assert draft_count == result["draft_record_count"]
    assert accuracy_levels <= {"accurate", "review", "miss"}
    assert accuracy_levels
    assert variance_percents
    assert max(variance_percents) <= 0.201
    assert any(percent > 0 for percent in variance_percents)


def test_dev_menu_automation_can_post_records_when_requested(isolated_db):
    result = run_dev_menu_automation(
        AutomationConfig(
            menu_name="Automation Posted Menu",
            start_date=date(2026, 6, 1),
            weeks=1,
            service_days=("monday",),
            meal_periods=("breakfast",),
            concepts=("hot_line",),
            min_items_per_slot=1,
            max_items_per_slot=1,
            random_seed=11,
            post_records=True,
        )
    )

    assert result["production_record_count"] == 1
    assert result["posted_record_count"] == 1
    assert result["draft_record_count"] == 0

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT status FROM production_record WHERE menu_id = ?",
        (result["menu_id"],),
    )
    assert cursor.fetchone()[0] == "posted"
    conn.close()


def test_dev_menu_automation_repeats_cycle_assignments(isolated_db):
    result = run_dev_menu_automation(
        AutomationConfig(
            menu_name="Automation Repeating Menu",
            start_date=date(2026, 6, 1),
            weeks=5,
            menu_cycle_weeks=2,
            service_days=("monday",),
            meal_periods=("breakfast",),
            concepts=("hot_line",),
            min_items_per_slot=3,
            max_items_per_slot=3,
            random_seed=13,
        )
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            ms.week_number,
            msi.item_id
        FROM menu_slot ms
        JOIN menu_slot_item msi
          ON msi.menu_slot_id = ms.menu_slot_id
        WHERE ms.menu_id = ?
        ORDER BY ms.week_number ASC, ms.menu_slot_id ASC, msi.item_sequence ASC
        """,
        (result["menu_id"],),
    )
    rows = cursor.fetchall()
    conn.close()

    assignments_by_week = {}
    for week_number, item_id in rows:
        assignments_by_week.setdefault(week_number, []).append(item_id)
    assert result["weeks"] == 5
    assert result["menu_cycle_weeks"] == 2
    assert assignments_by_week[3] == assignments_by_week[1]
    assert assignments_by_week[4] == assignments_by_week[2]
    assert assignments_by_week[5] == assignments_by_week[1]


def test_dev_inventory_automation_populates_locations_and_menu_ingredients(isolated_db):
    menu_result = run_dev_menu_automation(
        AutomationConfig(
            menu_name="Inventory Automation Source Menu",
            start_date=date(2026, 6, 1),
            weeks=1,
            service_days=("monday",),
            meal_periods=("breakfast",),
            concepts=("hot_line",),
            min_items_per_slot=3,
            max_items_per_slot=3,
            random_seed=17,
        )
    )

    inventory_result = run_dev_inventory_automation(
        InventoryAutomationConfig(
            menu_ids=(menu_result["menu_id"],),
            random_seed=23,
        )
    )

    assert inventory_result["menu_ids"] == [menu_result["menu_id"]]
    assert inventory_result["root_location_count"] == 3
    assert inventory_result["sub_location_count"] == 6
    assert inventory_result["inventory_item_count"] > 0
    assert sum(inventory_result["count_type_counts"].values()) == inventory_result["inventory_item_count"]
    assert sum(inventory_result["location_counts"].values()) == inventory_result["inventory_item_count"]
    assert set(inventory_result["count_type_counts"]) == {
        "counted_by_each_only",
        "counted_by_case_only",
        "counted_by_each_and_case",
    }

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM inventory_location
        WHERE parent_inventory_location_id IS NULL
          AND location_name IN ('Dry Pantry', 'Walk-In Cooler', 'Walk-In Freezer')
        """
    )
    root_count = cursor.fetchone()[0]
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM inventory_location
        WHERE parent_inventory_location_id IS NOT NULL
          AND location_name IN ('Left Wall', 'Right Wall')
        """
    )
    sub_count = cursor.fetchone()[0]
    cursor.execute(
        """
        SELECT
            COUNT(*),
            COUNT(DISTINCT inventory_location_id),
            SUM(CASE WHEN unit_of_measurement = 'Case' THEN 1 ELSE 0 END),
            SUM(CASE WHEN pack_quantity BETWEEN 1 AND 10 THEN 1 ELSE 0 END),
            SUM(CASE WHEN pack_size_text LIKE '% lb' THEN 1 ELSE 0 END)
        FROM inventory_location_item
        """
    )
    item_count, used_location_count, case_uom_count, pack_quantity_count, pack_size_count = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) FROM inventory_item_match WHERE status = 'active'")
    active_match_count = cursor.fetchone()[0]
    conn.close()

    assert root_count == 3
    assert sub_count == 6
    assert item_count == inventory_result["inventory_item_count"]
    assert used_location_count > 0
    assert case_uom_count == item_count
    assert pack_quantity_count == item_count
    assert pack_size_count == item_count
    assert active_match_count >= item_count


def test_dev_inventory_automation_requires_populated_menu(isolated_db):
    try:
        run_dev_inventory_automation(InventoryAutomationConfig(menu_ids=(9999,)))
    except ValueError as exc:
        assert "No live base-food ingredients" in str(exc)
    else:
        raise AssertionError("Expected inventory automation to require populated menu ingredients.")


def test_inventory_count_type_options_follow_uom():
    assert _inventory_count_type_options("Each") == ("counted_by_each_only",)
    assert _inventory_count_type_options("Case") == (
        "counted_by_each_only",
        "counted_by_case_only",
        "counted_by_each_and_case",
    )

    payload = _build_inventory_count_payload(
        rng=random.Random(3),
        source_count=5,
        count_type="counted_by_case_only",
        unit_of_measurement="Each",
    )

    assert payload["unit_of_measurement"] == "Each"
    assert payload["count_type"] == "counted_by_each_only"
    assert payload["count_case_quantity"] == 0.0
    assert payload["count_each_quantity"] > 0
