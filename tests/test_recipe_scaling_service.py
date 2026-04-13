from services.recipe_scaling_service import build_recipe_scaling_foundation, build_scaled_recipe_view
from services.unit_conversion_service import (
    convert_unit_value,
    convert_with_mass_volume_bridge,
    describe_unit_conversion,
    get_unit_measurement_profile,
)


def test_get_unit_measurement_profile_returns_mass_volume_and_count_units():
    assert get_unit_measurement_profile("g")["measurement_type"] == "mass"
    assert get_unit_measurement_profile("cup")["measurement_type"] == "volume"
    assert get_unit_measurement_profile("each")["measurement_type"] == "count"


def test_describe_unit_conversion_identifies_direct_ratio_and_same_family_conversion():
    assert describe_unit_conversion("cup", "cup")["status"] == "direct_ratio"
    assert describe_unit_conversion("qt", "cup")["status"] == "same_family_conversion"
    assert describe_unit_conversion("lb", "qt")["status"] == "incompatible"


def test_convert_unit_value_supports_same_family_conversions():
    cup_to_qt = convert_unit_value(4, "cup", "qt")
    lb_to_oz = convert_unit_value(1, "lb", "oz")

    assert cup_to_qt["ok"] is True
    assert round(cup_to_qt["quantity"], 3) == 1.0
    assert cup_to_qt["status"] == "same_family_conversion"
    assert lb_to_oz["ok"] is True
    assert round(lb_to_oz["quantity"], 3) == 16.0


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
