from services.recipe_scaling_service import build_recipe_scaling_foundation
from services.unit_conversion_service import (
    convert_unit_value,
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
