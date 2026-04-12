from db import get_connection
from services.unit_conversion_service import (
    describe_unit_conversion,
    get_unit_measurement_profile,
)


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
