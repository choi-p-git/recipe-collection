import sqlite3


def test_initialize_database_seeds_catalog_when_enabled(isolated_db):
    import db

    did_seed = db.load_seed_catalog_if_needed()

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM item WHERE item_type = 'base_food'")
    base_food_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM item WHERE item_type = 'recipe'")
    recipe_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM item WHERE status = 'live'")
    live_count = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM recipe_component rc
        JOIN item parent ON parent.item_id = rc.parent_recipe_item_id
        JOIN item child ON child.item_id = rc.component_item_id
        WHERE parent.item_name = 'Deli Chicken Salad Meal Prep'
          AND child.item_name = 'Chicken Salad'
        """
    )
    nested_component_count = cursor.fetchone()[0]

    cursor.execute(
        """
        SELECT item_name
        FROM item
        WHERE item_name IN (
            'Frozen French Fries',
            'Ground Beef',
            'Breaded Chicken Tender',
            'Truffle Oil',
            'Lobster Meat'
        )
        """
    )
    commercial_kitchen_items = {row[0] for row in cursor.fetchall()}

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM item
        WHERE lower(item_name) LIKE '%infant%'
           OR lower(item_name) LIKE '%formula%'
        """
    )
    non_kitchen_item_count = cursor.fetchone()[0]

    conn.close()

    assert did_seed is True
    assert base_food_count == 500
    assert recipe_count == 200
    assert live_count == 700
    assert nested_component_count == 1
    assert commercial_kitchen_items == {
        "Frozen French Fries",
        "Ground Beef",
        "Breaded Chicken Tender",
        "Truffle Oil",
        "Lobster Meat",
    }
    assert non_kitchen_item_count == 0


def test_initialize_database_does_not_duplicate_seed_catalog(isolated_db):
    import db

    first_seed = db.load_seed_catalog_if_needed()
    second_seed = db.load_seed_catalog_if_needed()

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM item")
    item_count = cursor.fetchone()[0]
    conn.close()

    assert first_seed is True
    assert second_seed is False
    assert item_count == 700
