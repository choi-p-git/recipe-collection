from services.recipe_scaling_service import (
    build_bottom_up_scaled_recipe_view,
    build_recipe_scaling_foundation,
    build_scaled_recipe_view,
)
from services.unit_conversion_service import (
    convert_unit_value,
    convert_with_item_mass_volume_bridge,
    convert_with_mass_volume_bridge,
    describe_unit_conversion,
    get_unit_measurement_profile,
)
from services.unit_display_service import build_display_measurement
from services.unit_label_service import format_unit_label


def test_get_unit_measurement_profile_returns_mass_volume_and_count_units():
    assert get_unit_measurement_profile("g")["measurement_type"] == "mass"
    assert get_unit_measurement_profile("cup")["measurement_type"] == "volume"
    assert get_unit_measurement_profile("l")["unit"] == "L"
    assert get_unit_measurement_profile("L")["measurement_type"] == "volume"
    assert get_unit_measurement_profile("each")["measurement_type"] == "count"


def test_describe_unit_conversion_identifies_direct_ratio_and_same_family_conversion():
    assert describe_unit_conversion("cup", "cup")["status"] == "direct_ratio"
    assert describe_unit_conversion("qt", "cup")["status"] == "same_family_conversion"
    assert describe_unit_conversion("lb", "qt")["status"] == "incompatible"


def test_convert_unit_value_supports_same_family_conversions():
    cup_to_qt = convert_unit_value(4, "cup", "qt")
    lb_to_oz = convert_unit_value(1, "lb", "oz")
    lowercase_liter_to_ml = convert_unit_value(1, "l", "ml")
    full_pan_to_qt = convert_unit_value(1, "pan_full_4", "qt")

    assert cup_to_qt["ok"] is True
    assert round(cup_to_qt["quantity"], 3) == 1.0
    assert cup_to_qt["status"] == "same_family_conversion"
    assert lb_to_oz["ok"] is True
    assert round(lb_to_oz["quantity"], 3) == 16.0
    assert lowercase_liter_to_ml["ok"] is True
    assert round(lowercase_liter_to_ml["quantity"], 3) == 1000.0
    assert full_pan_to_qt["ok"] is True
    assert round(full_pan_to_qt["quantity"], 1) == 11.2
    assert format_unit_label("pan_full_4") == 'Full pan, 4"'


def test_convert_unit_value_rejects_cross_family_conversion():
    result = convert_unit_value(1, "lb", "cup")

    assert result["ok"] is False
    assert result["status"] == "incompatible"


def test_convert_with_mass_volume_bridge_supports_recipe_level_cross_family_conversion():
    mass_to_volume = convert_with_mass_volume_bridge(
        500,
        "g",
        "cup",
        mass_quantity=1000,
        mass_unit="g",
        volume_quantity=1,
        volume_unit="qt",
    )
    volume_to_mass = convert_with_mass_volume_bridge(
        1,
        "cup",
        "g",
        mass_quantity=1000,
        mass_unit="g",
        volume_quantity=1,
        volume_unit="qt",
    )

    assert mass_to_volume["ok"] is True
    assert mass_to_volume["status"] == "recipe_bridge_conversion"
    assert round(mass_to_volume["quantity"], 3) == 2.0
    assert volume_to_mass["ok"] is True
    assert volume_to_mass["status"] == "recipe_bridge_conversion"
    assert round(volume_to_mass["quantity"], 3) == 250.0


def test_convert_with_item_mass_volume_bridge_supports_base_food_cross_family_conversion():
    volume_to_mass = convert_with_item_mass_volume_bridge(
        1,
        "cup",
        "g",
        item_type="base_food",
        mass_quantity=216,
        mass_unit="g",
        volume_quantity=1,
        volume_unit="cup",
    )
    mass_to_volume = convert_with_item_mass_volume_bridge(
        13.5,
        "g",
        "tbs",
        item_type="base_food",
        mass_quantity=216,
        mass_unit="g",
        volume_quantity=1,
        volume_unit="cup",
    )

    assert volume_to_mass["ok"] is True
    assert volume_to_mass["status"] == "base_food_bridge_conversion"
    assert round(volume_to_mass["quantity"], 3) == 216.0
    assert mass_to_volume["ok"] is True
    assert mass_to_volume["status"] == "base_food_bridge_conversion"
    assert round(mass_to_volume["quantity"], 3) == 1.0


def test_build_display_measurement_cascades_to_smaller_imperial_volume_unit():
    display = build_display_measurement(
        quantity=0.5,
        source_unit="cup",
        item_type="base_food",
        display_mode="volume",
        unit_system="imperial",
        mass_quantity=216,
        mass_unit="g",
        volume_quantity=1,
        volume_unit="cup",
    )

    assert display["quantity_display"] == "8"
    assert display["unit"] == "tbs"


def test_build_display_measurement_keeps_each_in_mass_mode():
    display = build_display_measurement(
        quantity=1.25,
        source_unit="each",
        item_type="base_food",
        display_mode="mass",
        unit_system="metric",
        mass_quantity=120,
        mass_unit="g",
        volume_quantity=1,
        volume_unit="cup",
    )

    assert display["quantity_display"] == "1.25"
    assert display["unit"] == "each"
    assert display["status"] == "original"


def test_build_recipe_scaling_foundation_uses_same_family_relationship_label(isolated_db):
    import sqlite3

    from services.item_service import create_base_food
    from services.recipe_service import create_recipe

    base_food_id = create_base_food(item_name="Scaling Foundation Oil")
    child_recipe_id = create_recipe(
        {
            "item_name": "Scaling Foundation Child",
            "yield_quantity": 2,
            "yield_unit": "qt",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "oz",
                }
            ],
        }
    )
    recipe_id = create_recipe(
        {
            "item_name": "Scaling Foundation Parent",
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

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE item SET status = 'live' WHERE item_id IN (?, ?, ?)",
        (base_food_id, child_recipe_id, recipe_id),
    )
    conn.commit()
    conn.close()

    foundation = build_recipe_scaling_foundation(recipe_id)

    assert foundation is not None
    assert foundation["relationship_counts"]["same_family_conversion"] == 1
    assert foundation["sub_recipe_rows"][0]["relationship_label"] == "Same-family conversion ready"


def test_build_scaled_recipe_view_returns_scaled_hierarchical_rows(isolated_db):
    import sqlite3

    from services.item_service import create_base_food
    from services.recipe_service import create_recipe

    oil_id = create_base_food(item_name="Scaled Hierarchy Oil")
    spice_id = create_base_food(item_name="Scaled Hierarchy Spice")
    recipe_id = create_recipe(
        {
            "item_name": "Scaled Hierarchy Recipe",
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
                {"component_item_id": spice_id, "component_quantity": 0.0008, "component_unit": "tsp"},
            ],
        }
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?, ?)", (oil_id, spice_id, recipe_id))
    conn.commit()
    conn.close()

    scaled_view = build_scaled_recipe_view(recipe_id, 1, "qt", ingredient_view="hierarchical")

    assert scaled_view is not None
    assert scaled_view["is_scaled"] is True
    assert scaled_view["row_mode"] == "hierarchical"
    assert scaled_view["rows"][0]["quantity_display"] == "4"
    assert scaled_view["rows"][1]["quantity_display"] == "according to taste"


def test_build_bottom_up_scaled_recipe_view_uses_hierarchical_ingredient_target(isolated_db):
    import sqlite3

    from services.item_service import create_base_food
    from services.recipe_service import create_recipe

    oil_id = create_base_food(item_name="Bottom Up Oil")
    spice_id = create_base_food(item_name="Bottom Up Spice")
    recipe_id = create_recipe(
        {
            "item_name": "Bottom Up Recipe",
            "yield_quantity": 2,
            "yield_unit": "qt",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {"component_item_id": oil_id, "component_quantity": 8, "component_unit": "oz"},
                {"component_item_id": spice_id, "component_quantity": 2, "component_unit": "tsp"},
            ],
        }
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?, ?)", (oil_id, spice_id, recipe_id))
    cursor.execute(
        """
        SELECT recipe_component_id
        FROM recipe_component
        WHERE parent_recipe_item_id = ?
          AND component_item_id = ?
        """,
        (recipe_id, oil_id),
    )
    oil_component_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()

    scaled_view = build_bottom_up_scaled_recipe_view(
        recipe_id,
        ingredient_view="hierarchical",
        target_row_key=str(oil_component_id),
        target_quantity=16,
        target_unit="oz",
    )

    assert scaled_view is not None
    assert scaled_view["is_scaled"] is True
    assert scaled_view["scale_mode"] == "ingredient"
    assert scaled_view["forecast_yield_quantity"] == 4
    assert scaled_view["forecast_yield_unit"] == "qt"
    assert scaled_view["rows"][0]["quantity_display"] == "16"
    assert scaled_view["rows"][1]["quantity_display"] == "4"


def test_build_scaled_recipe_view_returns_scaled_flattened_rows(isolated_db):
    import sqlite3

    from services.item_service import create_base_food
    from services.recipe_service import create_recipe

    oil_id = create_base_food(item_name="Scaled Flat Oil")
    sauce_id = create_recipe(
        {
            "item_name": "Scaled Flat Sauce",
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
            "item_name": "Scaled Flat Parent",
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

    scaled_view = build_scaled_recipe_view(recipe_id, 2, "each", ingredient_view="flattened")

    assert scaled_view is not None
    assert scaled_view["is_scaled"] is True
    assert scaled_view["row_mode"] == "flattened"
    assert scaled_view["rows"][0]["row_type"] == "sub_recipe"
    assert scaled_view["rows"][1]["quantity_display"] == "4"


def test_build_scaled_recipe_view_warns_when_target_unit_is_not_convertible(isolated_db):
    import sqlite3

    from services.item_service import create_base_food
    from services.recipe_service import create_recipe

    oil_id = create_base_food(item_name="Scaled Warning Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Scaled Warning Recipe",
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

    scaled_view = build_scaled_recipe_view(recipe_id, 1, "each", ingredient_view="hierarchical")

    assert scaled_view is not None
    assert scaled_view["is_scaled"] is False
    assert "not convertible" in scaled_view["warnings"][0]


def test_build_scaled_recipe_view_supports_recipe_mass_volume_bridge(isolated_db):
    import sqlite3

    from services.item_service import create_base_food
    from services.recipe_service import create_recipe

    oil_id = create_base_food(item_name="Scaled Bridge Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Scaled Bridge Recipe",
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

    scaled_view = build_scaled_recipe_view(recipe_id, 1, "kg", ingredient_view="hierarchical")

    assert scaled_view is not None
    assert scaled_view["is_scaled"] is True
    assert scaled_view["conversion_status"] == "recipe_bridge_conversion"
    assert scaled_view["rows"][0]["quantity_display"] == "4"


def test_build_scaled_recipe_view_supports_each_recipe_scaled_by_mass_basis(isolated_db):
    import sqlite3

    from services.item_service import create_base_food
    from services.recipe_service import create_recipe

    oil_id = create_base_food(item_name="Scaled Each Mass Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Scaled Each Mass Recipe",
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

    scaled_view = build_scaled_recipe_view(recipe_id, 500, "g", ingredient_view="hierarchical")

    assert scaled_view is not None
    assert scaled_view["is_scaled"] is True
    assert scaled_view["conversion_status"] == "recipe_batch_mass_basis"
    assert scaled_view["scale_basis_quantity"] == 1000
    assert scaled_view["scale_basis_unit"] == "g"
    assert scaled_view["rows"][0]["quantity_display"] == "2.5"


def test_build_scaled_recipe_view_supports_each_recipe_scaled_by_volume_basis(isolated_db):
    import sqlite3

    from services.item_service import create_base_food
    from services.recipe_service import create_recipe

    oil_id = create_base_food(item_name="Scaled Each Volume Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Scaled Each Volume Recipe",
            "yield_quantity": 10,
            "yield_unit": "each",
            "mass_quantity": 1000,
            "mass_unit": "g",
            "volume_quantity": 1,
            "volume_unit": "qt",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Mix"],
            "ingredients": [
                {"component_item_id": oil_id, "component_quantity": 2, "component_unit": "cup"},
            ],
        }
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id IN (?, ?)", (oil_id, recipe_id))
    conn.commit()
    conn.close()

    scaled_view = build_scaled_recipe_view(recipe_id, 2, "cup", ingredient_view="hierarchical")

    assert scaled_view is not None
    assert scaled_view["is_scaled"] is True
    assert scaled_view["conversion_status"] == "recipe_batch_volume_basis"
    assert scaled_view["scale_basis_quantity"] == 1
    assert scaled_view["scale_basis_unit"] == "qt"
    assert scaled_view["rows"][0]["quantity_display"] == "1"


def test_build_scaled_recipe_view_adds_base_food_mass_equivalent_for_hierarchical_rows(isolated_db):
    import sqlite3

    from services.item_service import create_base_food
    from services.recipe_service import create_recipe

    oil_id = create_base_food(item_name="Scaled Equivalent Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Scaled Equivalent Recipe",
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
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (recipe_id,))
    conn.commit()
    conn.close()

    scaled_view = build_scaled_recipe_view(recipe_id, 1, "kg", ingredient_view="hierarchical")

    assert scaled_view is not None
    equivalent = scaled_view["rows"][0]["measurement_equivalent"]
    assert equivalent is not None
    assert equivalent["label"] == "Official mass equivalent"
    assert equivalent["quantity_display"] == "54"
    assert equivalent["unit"] == "g"


def test_build_scaled_recipe_view_adds_base_food_volume_equivalent_for_flattened_rows(isolated_db):
    import sqlite3

    from services.item_service import create_base_food
    from services.recipe_service import create_recipe

    oil_id = create_base_food(item_name="Scaled Flat Equivalent Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Scaled Flat Equivalent Recipe",
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
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (recipe_id,))
    conn.commit()
    conn.close()

    scaled_view = build_scaled_recipe_view(recipe_id, 1, "qt", ingredient_view="flattened")

    assert scaled_view is not None
    base_food_row = next(row for row in scaled_view["rows"] if row["row_type"] == "base_food")
    equivalent = base_food_row["measurement_equivalent"]
    assert equivalent is not None
    assert equivalent["label"] == "Official volume equivalent"
    assert equivalent["quantity_display"] == "0.25"
    assert equivalent["unit"] == "cup"
