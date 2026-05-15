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
                volume_unit,
                serving_count
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
                rc.recipe_component_id,
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
    scaled_snapshot = {
        "yield_quantity": normalized_target_quantity,
        "yield_unit": normalized_target_unit,
        "mass_quantity": float(recipe_row[6]) * scale_factor if recipe_row[6] and recipe_row[7] else None,
        "mass_unit": recipe_row[7],
        "volume_quantity": float(recipe_row[8]) * scale_factor if recipe_row[8] and recipe_row[9] else None,
        "volume_unit": recipe_row[9],
        "serving_count": float(recipe_row[10]) * scale_factor if recipe_row[10] else None,
    }

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
            "scaled_snapshot": scaled_snapshot,
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
        "scaled_snapshot": scaled_snapshot,
        "warnings": [],
        "row_mode": "hierarchical",
        "rows": [
            {
                "component_item_id": row[0],
                "recipe_component_id": row[1],
                "component_item_name": row[2],
                "component_item_type": row[3],
                "mass_quantity": row[4],
                "mass_unit": row[5],
                "volume_quantity": row[6],
                "volume_unit": row[7],
                "component_quantity": float(row[8]) * scale_factor,
                "component_unit": row[9],
                "quantity_display": _format_scaled_quantity(float(row[8]) * scale_factor),
                "component_sequence": row[10],
                "measurement_equivalent": _build_measurement_equivalent(
                    quantity=float(row[8]) * scale_factor,
                    source_unit=row[9],
                    item_type=row[3],
                    target_measurement_type=preferred_measurement_type,
                    mass_quantity=row[4],
                    mass_unit=row[5],
                    volume_quantity=row[6],
                    volume_unit=row[7],
                ),
            }
            for row in component_rows
        ],
    }


def _convert_ingredient_target_to_base_quantity(
    *,
    target_quantity: float,
    target_unit: str,
    base_unit: str,
    item_type: str,
    mass_quantity: float | None,
    mass_unit: str | None,
    volume_quantity: float | None,
    volume_unit: str | None,
) -> dict:
    result = convert_unit_value(
        quantity=target_quantity,
        from_unit=target_unit,
        to_unit=base_unit,
    )
    if result["ok"]:
        return result

    source_profile = get_unit_measurement_profile(target_unit)
    target_profile = get_unit_measurement_profile(base_unit)
    if source_profile and target_profile and target_profile["measurement_type"] == "count":
        if source_profile["measurement_type"] == "mass" and mass_quantity and mass_unit:
            mass_result = convert_unit_value(
                quantity=target_quantity,
                from_unit=target_unit,
                to_unit=mass_unit,
            )
            if mass_result["ok"] and float(mass_quantity) > 0:
                return {
                    **mass_result,
                    "quantity": float(mass_result["quantity"]) / float(mass_quantity),
                    "unit": base_unit,
                    "status": "base_food_mass_count_bridge",
                    "label": "Base food mass-count bridge conversion ready",
                }

        if source_profile["measurement_type"] == "volume" and volume_quantity and volume_unit:
            volume_result = convert_unit_value(
                quantity=target_quantity,
                from_unit=target_unit,
                to_unit=volume_unit,
            )
            if volume_result["ok"] and float(volume_quantity) > 0:
                return {
                    **volume_result,
                    "quantity": float(volume_result["quantity"]) / float(volume_quantity),
                    "unit": base_unit,
                    "status": "base_food_volume_count_bridge",
                    "label": "Base food volume-count bridge conversion ready",
                }

    return convert_with_item_mass_volume_bridge(
        quantity=target_quantity,
        from_unit=target_unit,
        to_unit=base_unit,
        item_type=item_type,
        mass_quantity=mass_quantity,
        mass_unit=mass_unit,
        volume_quantity=volume_quantity,
        volume_unit=volume_unit,
    )


def _load_live_recipe_basis(recipe_item_id: int) -> tuple | None:
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
    return recipe_row


def _build_forecast_yield_target_from_scale(
    *,
    recipe_row: tuple,
    scale_factor: float,
    preferred_unit: str,
) -> tuple[float, str]:
    preferred_profile = get_unit_measurement_profile(preferred_unit)
    if preferred_profile and preferred_profile["measurement_type"] == "mass" and recipe_row[6] and recipe_row[7]:
        scaled_mass_quantity = float(recipe_row[6]) * scale_factor
        mass_result = convert_unit_value(
            quantity=scaled_mass_quantity,
            from_unit=recipe_row[7],
            to_unit=preferred_unit,
        )
        if mass_result["ok"]:
            return float(mass_result["quantity"]), preferred_unit

    if preferred_profile and preferred_profile["measurement_type"] == "volume" and recipe_row[8] and recipe_row[9]:
        scaled_volume_quantity = float(recipe_row[8]) * scale_factor
        volume_result = convert_unit_value(
            quantity=scaled_volume_quantity,
            from_unit=recipe_row[9],
            to_unit=preferred_unit,
        )
        if volume_result["ok"]:
            return float(volume_result["quantity"]), preferred_unit

    return float(recipe_row[4]) * scale_factor, recipe_row[5]


def _find_hierarchical_scale_target(recipe_item_id: int, row_key: str) -> dict | None:
    try:
        recipe_component_id = int(row_key)
    except (TypeError, ValueError):
        return None

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                rc.recipe_component_id,
                rc.component_item_id,
                i.item_name,
                i.item_type,
                i.mass_quantity,
                i.mass_unit,
                i.volume_quantity,
                i.volume_unit,
                rc.component_quantity,
                rc.component_unit
            FROM recipe_component rc
            JOIN item i
              ON i.item_id = rc.component_item_id
            WHERE rc.parent_recipe_item_id = ?
              AND rc.recipe_component_id = ?
            """,
            (recipe_item_id, recipe_component_id),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    return {
        "row_key": str(row[0]),
        "component_item_id": row[1],
        "component_item_name": row[2],
        "component_item_type": row[3],
        "mass_quantity": row[4],
        "mass_unit": row[5],
        "volume_quantity": row[6],
        "volume_unit": row[7],
        "base_quantity": float(row[8]),
        "base_unit": row[9],
    }


def _find_flattened_scale_target(recipe_item_id: int, row_key: str) -> dict | None:
    try:
        row_index = int(row_key)
    except (TypeError, ValueError):
        return None

    flattened_view = build_flattened_recipe_view(recipe_item_id)
    if row_index < 0 or row_index >= len(flattened_view["rows"]):
        return None

    row = flattened_view["rows"][row_index]
    return {
        "row_key": str(row_index),
        "component_item_id": row["component_item_id"],
        "component_item_name": row["component_item_name"],
        "component_item_type": row["component_item_type"],
        "mass_quantity": row.get("mass_quantity"),
        "mass_unit": row.get("mass_unit"),
        "volume_quantity": row.get("volume_quantity"),
        "volume_unit": row.get("volume_unit"),
        "base_quantity": float(row["total_quantity"]),
        "base_unit": row["component_unit"],
    }


def build_bottom_up_scaled_recipe_view(
    recipe_item_id: int,
    *,
    ingredient_view: str,
    target_row_key: str,
    target_quantity,
    target_unit: str | None,
) -> dict | None:
    recipe_row = _load_live_recipe_basis(recipe_item_id)
    if recipe_row is None:
        return None

    try:
        normalized_target_quantity = float(target_quantity)
    except (TypeError, ValueError):
        return {
            "available": True,
            "is_scaled": False,
            "warnings": ["Ingredient target quantity must be a valid number."],
            "rows": [],
        }

    normalized_target_unit = str(target_unit or "").strip()
    if normalized_target_quantity <= 0:
        return {
            "available": True,
            "is_scaled": False,
            "warnings": ["Ingredient target quantity must be greater than 0."],
            "rows": [],
        }
    if not normalized_target_unit:
        return {
            "available": True,
            "is_scaled": False,
            "warnings": ["Ingredient target unit is required."],
            "rows": [],
        }

    target = (
        _find_flattened_scale_target(recipe_item_id, target_row_key)
        if ingredient_view == "flattened"
        else _find_hierarchical_scale_target(recipe_item_id, target_row_key)
    )
    if target is None:
        return {
            "available": True,
            "is_scaled": False,
            "warnings": ["Select a valid ingredient to scale from."],
            "rows": [],
        }

    conversion = _convert_ingredient_target_to_base_quantity(
        target_quantity=normalized_target_quantity,
        target_unit=normalized_target_unit,
        base_unit=target["base_unit"],
        item_type=target["component_item_type"],
        mass_quantity=target["mass_quantity"],
        mass_unit=target["mass_unit"],
        volume_quantity=target["volume_quantity"],
        volume_unit=target["volume_unit"],
    )
    if not conversion["ok"]:
        return {
            "available": True,
            "is_scaled": False,
            "warnings": [
                f"Ingredient target unit '{normalized_target_unit}' is not convertible to "
                f"'{target['base_unit']}' for {target['component_item_name']}."
            ],
            "rows": [],
            "target_ingredient": target,
        }

    scale_factor = float(conversion["quantity"]) / target["base_quantity"]
    forecast_yield_quantity = float(recipe_row[4]) * scale_factor
    forecast_save_quantity, forecast_save_unit = _build_forecast_yield_target_from_scale(
        recipe_row=recipe_row,
        scale_factor=scale_factor,
        preferred_unit=normalized_target_unit,
    )
    scaled_view = build_scaled_recipe_view(
        recipe_item_id,
        target_quantity=forecast_yield_quantity,
        target_unit=recipe_row[5],
        ingredient_view=ingredient_view,
    )
    if scaled_view is None:
        return None

    scaled_view["scale_mode"] = "ingredient"
    scaled_view["target_ingredient"] = target
    scaled_view["ingredient_target_quantity"] = normalized_target_quantity
    scaled_view["ingredient_target_unit"] = normalized_target_unit
    scaled_view["forecast_yield_quantity"] = forecast_yield_quantity
    scaled_view["forecast_yield_unit"] = recipe_row[5]
    scaled_view["forecast_save_quantity"] = forecast_save_quantity
    scaled_view["forecast_save_unit"] = forecast_save_unit
    scaled_view["ingredient_conversion_status"] = conversion["status"]
    return scaled_view


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
