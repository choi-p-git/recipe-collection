import os
import sqlite3
import time

from db import garbage_collect_test_tmp


def test_initialize_database_creates_expected_tables(isolated_db):
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    tables = {row[0] for row in cursor.fetchall()}

    conn.close()

    assert "item" in tables
    assert "recipe_component" in tables
    assert "schema_migration" in tables
    assert "item_event" in tables
    assert "item_notification" in tables
    assert "menu_forecast" in tables
    assert "menu_forecast_batch_split" in tables
    assert "item_case_pack" in tables
    assert "production_record" in tables
    assert "production_record_line" in tables


def test_initialize_database_creates_expected_indexes(isolated_db):
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
    indexes = {row[0] for row in cursor.fetchall()}

    conn.close()

    assert "idx_item_type" in indexes
    assert "idx_recipe_component_parent" in indexes
    assert "idx_item_event_item" in indexes
    assert "idx_item_notification_item" in indexes
    assert "idx_menu_forecast_slot_item_id" in indexes
    assert "idx_menu_forecast_batch_split_slot_item_id" in indexes
    assert "idx_item_case_pack_item_id" in indexes
    assert "idx_production_record_menu_day" in indexes
    assert "idx_production_record_line_record_id" in indexes


def test_initialize_database_records_applied_migration_versions(isolated_db):
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT version FROM schema_migration ORDER BY version ASC")
    versions = [row[0] for row in cursor.fetchall()]
    conn.close()

    assert versions == [
        "0001_initial_schema.sql",
        "0002_add_item_event.sql",
        "0003_add_item_notification.sql",
        "0004_add_measurement_authority_fields.sql",
        "0005_add_base_food_nutrition_fields.sql",
        "0006_add_menu_builder_tables.sql",
        "0007_add_menu_forecast.sql",
        "0008_normalize_liter_unit_symbol.sql",
        "0009_add_menu_forecast_user_serving_size.sql",
        "0010_add_menu_forecast_desired_portions.sql",
        "0011_add_menu_forecast_batch_split.sql",
        "0012_add_forecast_case_pack.sql",
        "0013_add_forecast_case_basis.sql",
        "0014_add_forecast_case_basis_row_key.sql",
        "0015_add_production_record.sql",
        "0016_refine_production_record_variance.sql",
        "0017_add_menu_date_range.sql",
        "0018_add_production_record_quantity_formulas.sql",
    ]


def test_schema_allows_base_food_without_yield_but_requires_recipe_yield(isolated_db):
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO item (
            item_name,
            item_type,
            author_user_id,
            author_display_name,
            yield_quantity,
            yield_unit,
            serving_size_quantity,
            serving_size_unit,
            serving_count,
            instructions_text,
            primary_cooking_method_code,
            status,
            notes,
            concept_classification,
            meal_classification,
            haccp_process_classification,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        (
            "Base Food Schema Test",
            "base_food",
            "system_base_food",
            "Base Food Submission",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "submitted",
            None,
            None,
            None,
            None,
        ),
    )

    try:
        cursor.execute(
            """
            INSERT INTO item (
                item_name,
                item_type,
                author_user_id,
                author_display_name,
                yield_quantity,
                yield_unit,
                serving_size_quantity,
                serving_size_unit,
                serving_count,
                instructions_text,
                primary_cooking_method_code,
                status,
                notes,
                concept_classification,
                meal_classification,
                haccp_process_classification,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                "Recipe Schema Test",
                "recipe",
                "dev_user_001",
                "Plato Choi",
                None,
                None,
                None,
                None,
                None,
                "1. Test step",
                "bake",
                "submitted",
                None,
                None,
                None,
                None,
            ),
        )
        assert False, "Expected recipe insert without yield to fail schema check"
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()


def test_garbage_collect_test_tmp_only_targets_stale_test_directories(tmp_path):
    stale_run = tmp_path / "run-old"
    stale_debug = tmp_path / "debug-old"
    new_run = tmp_path / "run-new"
    unrelated = tmp_path / "keep-me"
    for path in (stale_run, stale_debug, new_run, unrelated):
        path.mkdir()
        (path / "database").mkdir()

    old_timestamp = time.time() - (48 * 60 * 60)
    for path in (stale_run, stale_debug):
        os.utime(path, (old_timestamp, old_timestamp))

    dry_run = garbage_collect_test_tmp(
        test_tmp_dir=tmp_path,
        min_age_hours=24,
        dry_run=True,
    )

    assert dry_run["scanned"] == 4
    assert dry_run["eligible"] == 2
    assert dry_run["deleted"] == 0
    assert stale_run.exists()
    assert stale_debug.exists()

    applied = garbage_collect_test_tmp(
        test_tmp_dir=tmp_path,
        min_age_hours=24,
        dry_run=False,
    )

    assert applied["eligible"] == 2
    assert applied["deleted"] == 2
    assert not stale_run.exists()
    assert not stale_debug.exists()
    assert new_run.exists()
    assert unrelated.exists()
