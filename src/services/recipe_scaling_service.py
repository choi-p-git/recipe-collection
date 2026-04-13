from db import get_connection
from services.unit_conversion_service import (
    convert_unit_value,
    describe_unit_conversion,
    get_unit_measurement_profile,
)
from services.recipe_flattening_service import build_flattened_recipe_view


ACCORDING_TO_TASTE_THRESHOLD = 0.001


def _format_scaled_quantity(quantity: float) -> str:
    rounded_quantity = round(quantity, 3)
    if rounded_quantity < ACCORDING_TO_TASTE_THRESHOLD:
        return "according to taste"
    return f"{rounded_quantity:g}"


def build_scaled_recipe_view(
    recipe_item_id: int,
    target_quantity,
    target_unit: str | None,
    ingredient_view: str = "hierarchical",
) -> dict | None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                item_id,
                item_name,
                item_type,
                status,
                yield_quantity,
                yield_unit
            FROM item
            WHERE item_id = ?
            """,
            (recipe_item_id,),
        )
        recipe_row = cursor.fetchone()

        if recipe_row is None or recipe_row[2] != "recipe" or recipe_row[3] != "live":
            return None

        cursor.execute(
            """
            SELECT
                rc.component_item_id,
                i.item_name,
                i.item_type,
                rc.component_quantity,
                rc.component_unit,
                rc.component_sequence
            FROM recipe_component rc
            JOIN item i
              ON i.item_id = rc.component_item_id
            WHERE rc.parent_recipe_item_id = ?
            ORDER BY rc.component_sequence ASC, rc.recipe_component_id ASC
            """,
            (recipe_item_id,),
        )
        component_rows = cursor.fetchall()

    try:
        normalized_target_quantity = float(target_quantity)
    except (TypeError, ValueError):
        return {
            "available": True,
            "is_scaled": False,
            "warnings": ["Scale quantity must be a valid number."],
            "rows": [],
        }

    normalized_target_unit = str(target_unit or "").strip()
    if normalized_target_quantity <= 0:
        return {
            "available": True,
            "is_scaled": False,
            "warnings": ["Scale quantity must be greater than 0."],
            "rows": [],
        }

    if not normalized_target_unit:
        return {
            "available": True,
            "is_scaled": False,
            "warnings": ["Scale unit is required."],
            "rows": [],
        }

    conversion_result = convert_unit_value(
        quantity=normalized_target_quantity,
        from_unit=normalized_target_unit,
        to_unit=recipe_row[5],
    )
    if not conversion_result["ok"]:
        return {
            "available": True,
            "is_scaled": False,
            "warnings": [
                f"Scale target unit '{normalized_target_unit}' is not convertible to recipe yield unit '{recipe_row[5]}'."
            ],
            "rows": [],
        }

    scale_factor = float(conversion_result["quantity"]) / float(recipe_row[4])

    if ingredient_view == "flattened":
        flattened_view = build_flattened_recipe_view(recipe_item_id, scale_factor=scale_factor)
        return {
            "available": True,
            "is_scaled": True,
            "scale_factor": scale_factor,
            "target_quantity": normalized_target_quantity,
            "target_unit": normalized_target_unit,
            "recipe_yield_quantity": recipe_row[4],
            "recipe_yield_unit": recipe_row[5],
            "warnings": flattened_view["warnings"],
            "rows": flattened_view["rows"],
            "row_mode": "flattened",
        }

    return {
        "available": True,
        "is_scaled": True,
        "scale_factor": scale_factor,
        "target_quantity": normalized_target_quantity,
        "target_unit": normalized_target_unit,
        "recipe_yield_quantity": recipe_row[4],
        "recipe_yield_unit": recipe_row[5],
        "warnings": [],
        "row_mode": "hierarchical",
        "rows": [
            {
                "component_item_id": row[0],
                "component_item_name": row[1],
                "component_item_type": row[2],
                "component_quantity": float(row[3]) * scale_factor,
                "component_unit": row[4],
                "quantity_display": _format_scaled_quantity(float(row[3]) * scale_factor),
                "component_sequence": row[5],
            }
            for row in component_rows
        ],
    }


def build_recipe_scaling_foundation(recipe_item_id: int) -> dict | None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                item_id,
                item_name,
                item_type,
                yield_quantity,
                yield_unit,
                serving_size_quantity,
                serving_size_unit,
                serving_count,
                status
            FROM item
            WHERE item_id = ?
            """,
            (recipe_item_id,),
        )
        recipe_row = cursor.fetchone()

        if recipe_row is None or recipe_row[2] != "recipe":
            return None

        cursor.execute(
            """
            SELECT
                rc.component_item_id,
                i.item_name,
                i.item_type,
                rc.component_quantity,
                rc.component_unit,
                i.yield_quantity,
                i.yield_unit,
                i.status
            FROM recipe_component rc
            JOIN item i
              ON i.item_id = rc.component_item_id
            WHERE rc.parent_recipe_item_id = ?
            ORDER BY rc.component_sequence ASC, rc.recipe_component_id ASC
            """,
            (recipe_item_id,),
        )
        component_rows = cursor.fetchall()

    recipe_yield_profile = get_unit_measurement_profile(recipe_row[4])
    serving_size_profile = get_unit_measurement_profile(recipe_row[6])

    sub_recipe_rows = []
    relationship_counts = {
        "direct_ratio": 0,
        "same_family_conversion": 0,
        "incompatible": 0,
        "unknown": 0,
        "missing": 0,
    }

    for component_row in component_rows:
        if component_row[2] != "recipe":
            continue

        relationship = describe_unit_conversion(component_row[4], component_row[6])
        relationship_counts[relationship["status"]] += 1
        sub_recipe_rows.append(
            {
                "component_item_id": component_row[0],
                "component_item_name": component_row[1],
                "component_quantity": component_row[3],
                "component_unit": component_row[4],
                "child_yield_quantity": component_row[5],
                "child_yield_unit": component_row[6],
                "child_status": component_row[7],
                "relationship_status": relationship["status"],
                "relationship_label": relationship["label"],
            }
        )

    return {
        "recipe_item_id": recipe_row[0],
        "recipe_item_name": recipe_row[1],
        "recipe_status": recipe_row[8],
        "yield_quantity": recipe_row[3],
        "yield_unit": recipe_row[4],
        "yield_profile": recipe_yield_profile,
        "serving_size_quantity": recipe_row[5],
        "serving_size_unit": recipe_row[6],
        "serving_count": recipe_row[7],
        "serving_size_profile": serving_size_profile,
        "sub_recipe_rows": sub_recipe_rows,
        "relationship_counts": relationship_counts,
        "future_notes": [
            "Direct same-unit scaling is ready for ratio math.",
            "Same-family unit conversion is now modeled through the shared unit conversion service.",
            "Cross-type scaling such as mass-to-volume will require richer measurement metadata and likely density-aware base foods.",
        ],
    }
