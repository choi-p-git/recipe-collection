import sqlite3
from datetime import date

from dev_automation import AutomationConfig, run_dev_menu_automation


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
