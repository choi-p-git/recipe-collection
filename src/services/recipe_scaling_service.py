from db import get_connection
from services.unit_conversion_service import (
    convert_unit_value,
    convert_with_item_mass_volume_bridge,
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


def _build_measurement_equivalent(
    *,
    quantity: float,
    source_unit: str,
    item_type: str,
    target_measurement_type: str | None,
    mass_quantity: float | None,
    mass_unit: str | None,
    volume_quantity: float | None,
    volume_unit: str | None,
) -> dict | None:
    if target_measurement_type == "mass" and mass_unit:
        result = convert_unit_value(quantity=quantity, from_unit=source_unit, to_unit=mass_unit)
        if not result["ok"]:
            result = convert_with_item_mass_volume_bridge(
                quantity=quantity,
                from_unit=source_unit,
                to_unit=mass_unit,
                item_type=item_type,
                mass_quantity=mass_quantity,
                mass_unit=mass_unit,
                volume_quantity=volume_quantity,
                volume_unit=volume_unit,
            )
        if result["ok"]:
            return {
                "quantity": float(result["quantity"]),
                "quantity_display": _format_scaled_quantity(float(result["quantity"])),
                "unit": mass_unit,
                "label": "Official mass equivalent",
                "status": result["status"],
            }

    if target_measurement_type == "volume" and volume_unit:
        result = convert_unit_value(quantity=quantity, from_unit=source_unit, to_unit=volume_unit)
        if not result["ok"]:
            result = convert_with_item_mass_volume_bridge(
                quantity=quantity,
                from_unit=source_unit,
                to_unit=volume_unit,
                item_type=item_type,
                mass_quantity=mass_quantity,
                mass_unit=mass_unit,
                volume_quantity=volume_quantity,
                volume_unit=volume_unit,
            )
        if result["ok"]:
            return {
                "quantity": float(result["quantity"]),
                "quantity_display": _format_scaled_quantity(float(result["quantity"])),
                "unit": volume_unit,
                "label": "Official volume equivalent",
                "status": result["status"],
            }

    return None


def _convert_target_to_recipe_scale_basis(
    *,
    target_quantity: float,
    target_unit: str,
    recipe_yield_quantity: float,
    recipe_yield_unit: str,
    recipe_mass_quantity: float | None,
    recipe_mass_unit: str | None,
    recipe_volume_quantity: float | None,
    recipe_volume_unit: str | None,
) -> dict:
    target_profile = get_unit_measurement_profile(target_unit)
    recipe_yield_profile = get_unit_measurement_profile(recipe_yield_unit)

    direct_result = convert_unit_value(
        quantity=target_quantity,
        from_unit=target_unit,
        to_unit=recipe_yield_unit,
    )
    if direct_result["ok"]:
        return {
            "ok": True,
            "status": direct_result["status"],
            "scale_factor": float(direct_result["quantity"]) / float(recipe_yield_quantity),
            "basis_quantity": recipe_yield_quantity,
            "basis_unit": recipe_yield_unit,
        }

    if target_profile and recipe_yield_profile:
        if recipe_yield_profile["measurement_type"] == "count" and target_profile["measurement_type"] == "mass":
            mass_result = convert_unit_value(
                quantity=target_quantity,
                from_unit=target_unit,
                to_unit=recipe_mass_unit,
            )
            if mass_result["ok"] and recipe_mass_quantity:
                return {
                    "ok": True,
                    "status": "recipe_batch_mass_basis",
                    "scale_factor": float(mass_result["quantity"]) / float(recipe_mass_quantity),
                    "basis_quantity": recipe_mass_quantity,
                    "basis_unit": recipe_mass_unit,
                }

        if target_profile and recipe_yield_profile["measurement_type"] == "count" and target_profile["measurement_type"] == "volume":
            volume_result = convert_unit_value(
                quantity=target_quantity,
                from_unit=target_unit,
                to_unit=recipe_volume_unit,
            )
            if volume_result["ok"] and recipe_volume_quantity:
                return {
                    "ok": True,
                    "status": "recipe_batch_volume_basis",
                    "scale_factor": float(volume_result["quantity"]) / float(recipe_volume_quantity),
                    "basis_quantity": recipe_volume_quantity,
                    "basis_unit": recipe_volume_unit,
                }

    bridge_result = convert_with_item_mass_volume_bridge(
        quantity=target_quantity,
        from_unit=target_unit,
        to_unit=recipe_yield_unit,
        item_type="recipe",
        mass_quantity=recipe_mass_quantity,
        mass_unit=recipe_mass_unit,
        volume_quantity=recipe_volume_quantity,
        volume_unit=recipe_volume_unit,
    )
    if bridge_result["ok"]:
        return {
            "ok": True,
            "status": bridge_result["status"],
            "scale_factor": float(bridge_result["quantity"]) / float(recipe_yield_quantity),
            "basis_quantity": recipe_yield_quantity,
            "basis_unit": recipe_yield_unit,
        }

    return {
        "ok": False,
        "status": bridge_result["status"],
    }


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
                yield_unit,
                mass_quantity,
                mass_unit,
                volume_quantity,
                volume_unit
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
                i.mass_quantity,
                i.mass_unit,
                i.volume_quantity,
                i.volume_unit,
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

    scale_basis_result = _convert_target_to_recipe_scale_basis(
        target_quantity=normalized_target_quantity,
        target_unit=normalized_target_unit,
        recipe_yield_quantity=recipe_row[4],
        recipe_yield_unit=recipe_row[5],
        recipe_mass_quantity=recipe_row[6],
        recipe_mass_unit=recipe_row[7],
        recipe_volume_quantity=recipe_row[8],
        recipe_volume_unit=recipe_row[9],
    )
    if not scale_basis_result["ok"]:
        return {
            "available": True,
            "is_scaled": False,
            "warnings": [
                f"Scale target unit '{normalized_target_unit}' is not convertible to recipe yield unit '{recipe_row[5]}'."
            ],
            "rows": [],
        }

    scale_factor = float(scale_basis_result["scale_factor"])
    target_profile = get_unit_measurement_profile(normalized_target_unit)
    preferred_measurement_type = (
        target_profile["measurement_type"]
        if target_profile and target_profile["measurement_type"] in {"mass", "volume"}
        else None
    )

    if ingredient_view == "flattened":
        flattened_view = build_flattened_recipe_view(
            recipe_item_id,
            scale_factor=scale_factor,
            preferred_measurement_type=preferred_measurement_type,
        )
        return {
            "available": True,
            "is_scaled": True,
            "scale_factor": scale_factor,
            "target_quantity": normalized_target_quantity,
            "target_unit": normalized_target_unit,
            "recipe_yield_quantity": recipe_row[4],
            "recipe_yield_unit": recipe_row[5],
            "conversion_status": scale_basis_result["status"],
            "scale_basis_quantity": scale_basis_result["basis_quantity"],
            "scale_basis_unit": scale_basis_result["basis_unit"],
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
        "conversion_status": scale_basis_result["status"],
        "scale_basis_quantity": scale_basis_result["basis_quantity"],
        "scale_basis_unit": scale_basis_result["basis_unit"],
        "warnings": [],
        "row_mode": "hierarchical",
        "rows": [
            {
                "component_item_id": row[0],
                "component_item_name": row[1],
                "component_item_type": row[2],
                "mass_quantity": row[3],
                "mass_unit": row[4],
                "volume_quantity": row[5],
                "volume_unit": row[6],
                "component_quantity": float(row[7]) * scale_factor,
                "component_unit": row[8],
                "quantity_display": _format_scaled_quantity(float(row[7]) * scale_factor),
                "component_sequence": row[9],
                "measurement_equivalent": _build_measurement_equivalent(
                    quantity=float(row[7]) * scale_factor,
                    source_unit=row[8],
                    item_type=row[2],
                    target_measurement_type=preferred_measurement_type,
                    mass_quantity=row[3],
                    mass_unit=row[4],
                    volume_quantity=row[5],
                    volume_unit=row[6],
                ),
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
            "Recipe-level mass-to-volume scaling can use authoritative recipe measurement fields during live scaling.",
            "Base-food mass-to-volume bridge conversion is now defined in the shared conversion layer for future module reuse.",
            "Broader density-aware and richer cross-type scaling remains a later step.",
        ],
    }
