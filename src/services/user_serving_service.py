from services.unit_conversion_service import convert_unit_value, get_unit_measurement_profile
from services.unit_display_service import format_display_quantity


def _coerce_positive_quantity(value) -> tuple[float | None, str | None]:
    try:
        quantity = float(value)
    except (TypeError, ValueError):
        return None, "User serving size quantity must be a valid number."

    if quantity <= 0:
        return None, "User serving size quantity must be greater than 0."

    return quantity, None


def build_user_serving_preview(
    *,
    recipe_measurements: dict,
    serving_quantity,
    serving_unit: str | None,
) -> dict | None:
    if serving_quantity in (None, "") and not serving_unit:
        return None

    normalized_serving_quantity, quantity_error = _coerce_positive_quantity(serving_quantity)
    normalized_serving_unit = str(serving_unit or "").strip()

    if quantity_error:
        return {"available": False, "warning": quantity_error}
    if not normalized_serving_unit:
        return {"available": False, "warning": "User serving size unit is required."}

    serving_profile = get_unit_measurement_profile(normalized_serving_unit)
    if serving_profile is None or not serving_profile["conversion_ready"]:
        return {
            "available": False,
            "warning": f"User serving size unit '{normalized_serving_unit}' is not supported.",
        }

    measurement_type = serving_profile["measurement_type"]
    if measurement_type == "count":
        source_quantity = recipe_measurements.get("yield_quantity")
        source_unit = recipe_measurements.get("yield_unit")
    else:
        source_quantity = recipe_measurements.get(f"{measurement_type}_quantity")
        source_unit = recipe_measurements.get(f"{measurement_type}_unit")
        if not source_quantity or not source_unit:
            source_quantity = recipe_measurements.get("yield_quantity")
            source_unit = recipe_measurements.get("yield_unit")

    if not source_quantity or not source_unit:
        return {
            "available": False,
            "warning": f"Recipe does not have a {measurement_type} basis for user serving calculation.",
        }

    conversion = convert_unit_value(
        quantity=float(source_quantity),
        from_unit=source_unit,
        to_unit=normalized_serving_unit,
    )
    if not conversion["ok"]:
        return {
            "available": False,
            "warning": (
                f"Recipe {measurement_type} basis '{source_unit}' cannot be converted to "
                f"user serving unit '{normalized_serving_unit}'."
            ),
        }

    portions = float(conversion["quantity"]) / normalized_serving_quantity
    return {
        "available": True,
        "serving_quantity": normalized_serving_quantity,
        "serving_quantity_display": format_display_quantity(normalized_serving_quantity),
        "serving_unit": normalized_serving_unit,
        "portion_count": portions,
        "portion_count_display": format_display_quantity(portions),
        "basis_quantity": float(source_quantity),
        "basis_unit": source_unit,
    }


def build_desired_portions_yield_target(
    *,
    recipe_measurements: dict,
    desired_portions,
    serving_quantity,
    serving_unit: str | None,
    target_unit: str | None = None,
) -> dict | None:
    if desired_portions in (None, ""):
        return None

    normalized_desired_portions, portions_error = _coerce_positive_quantity(desired_portions)
    if portions_error:
        return {"available": False, "warning": portions_error.replace("User serving size", "Desired portions")}

    serving_preview = build_user_serving_preview(
        recipe_measurements=recipe_measurements,
        serving_quantity=serving_quantity,
        serving_unit=serving_unit,
    )
    if not serving_preview:
        return {"available": False, "warning": "A portion size is required before scaling by desired portions."}
    if not serving_preview["available"]:
        return serving_preview

    portion_count = float(serving_preview["portion_count"])
    if portion_count <= 0:
        return {"available": False, "warning": "Portion count basis must be greater than 0."}

    scale_factor = normalized_desired_portions / portion_count
    recipe_yield_quantity = recipe_measurements.get("yield_quantity")
    recipe_yield_unit = recipe_measurements.get("yield_unit")
    if not recipe_yield_quantity or not recipe_yield_unit:
        return {"available": False, "warning": "Recipe yield is required before scaling by desired portions."}

    scaled_yield_quantity = float(recipe_yield_quantity) * scale_factor
    normalized_target_unit = str(target_unit or recipe_yield_unit or "").strip()
    if normalized_target_unit:
        conversion = convert_unit_value(
            quantity=scaled_yield_quantity,
            from_unit=recipe_yield_unit,
            to_unit=normalized_target_unit,
        )
        if conversion["ok"]:
            scaled_yield_quantity = float(conversion["quantity"])
        else:
            normalized_target_unit = recipe_yield_unit
    else:
        normalized_target_unit = recipe_yield_unit

    return {
        "available": True,
        "desired_portions": normalized_desired_portions,
        "desired_portions_display": format_display_quantity(normalized_desired_portions),
        "target_quantity": scaled_yield_quantity,
        "target_quantity_display": format_display_quantity(scaled_yield_quantity),
        "target_unit": normalized_target_unit,
        "scale_factor": scale_factor,
        "serving_quantity": serving_preview["serving_quantity"],
        "serving_unit": serving_preview["serving_unit"],
    }
