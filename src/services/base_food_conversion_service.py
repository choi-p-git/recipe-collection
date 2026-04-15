from services.unit_conversion_service import convert_unit_value, convert_with_item_mass_volume_bridge


def build_base_food_conversion_preview(
    item: dict,
    target_quantity,
    target_unit: str | None,
) -> dict | None:
    if item.get("item_type") != "base_food":
        return None

    try:
        normalized_target_quantity = float(target_quantity)
    except (TypeError, ValueError):
        return {
            "available": True,
            "is_converted": False,
            "warnings": ["Conversion quantity must be a valid number."],
        }

    normalized_target_unit = str(target_unit or "").strip()
    if normalized_target_quantity <= 0:
        return {
            "available": True,
            "is_converted": False,
            "warnings": ["Conversion quantity must be greater than 0."],
        }

    if not normalized_target_unit:
        return {
            "available": True,
            "is_converted": False,
            "warnings": ["Conversion unit is required."],
        }

    if item.get("mass_quantity") and item.get("mass_unit"):
        source_quantity = item["mass_quantity"]
        source_unit = item["mass_unit"]
        source_basis_label = "official mass"
    elif item.get("volume_quantity") and item.get("volume_unit"):
        source_quantity = item["volume_quantity"]
        source_unit = item["volume_unit"]
        source_basis_label = "official volume"
    else:
        return {
            "available": True,
            "is_converted": False,
            "warnings": ["Base food is missing official mass/volume data for conversion preview."],
        }

    conversion_result = convert_unit_value(
        quantity=normalized_target_quantity,
        from_unit=normalized_target_unit,
        to_unit=source_unit,
    )
    if not conversion_result["ok"]:
        conversion_result = convert_with_item_mass_volume_bridge(
            quantity=normalized_target_quantity,
            from_unit=normalized_target_unit,
            to_unit=source_unit,
            item_type="base_food",
            mass_quantity=item.get("mass_quantity"),
            mass_unit=item.get("mass_unit"),
            volume_quantity=item.get("volume_quantity"),
            volume_unit=item.get("volume_unit"),
        )

    if not conversion_result["ok"]:
        return {
            "available": True,
            "is_converted": False,
            "warnings": [
                f"Target unit '{normalized_target_unit}' is not convertible to base-food reference unit '{source_unit}'."
            ],
        }

    return {
        "available": True,
        "is_converted": True,
        "target_quantity": normalized_target_quantity,
        "target_unit": normalized_target_unit,
        "reference_quantity": source_quantity,
        "reference_unit": source_unit,
        "source_basis_label": source_basis_label,
        "conversion_status": conversion_result["status"],
        "reference_equivalent_quantity": conversion_result["quantity"],
        "warnings": [],
    }
