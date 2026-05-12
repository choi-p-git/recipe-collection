from services.unit_conversion_service import (
    convert_unit_value,
    convert_with_item_mass_volume_bridge,
    get_unit_measurement_profile,
    normalize_unit_symbol,
)


DISPLAY_MODE_DEFAULT = "default"
DISPLAY_MODE_MASS = "mass"
DISPLAY_MODE_VOLUME = "volume"
DISPLAY_MODE_OPTIONS = {DISPLAY_MODE_DEFAULT, DISPLAY_MODE_MASS, DISPLAY_MODE_VOLUME}

UNIT_SYSTEM_IMPERIAL = "imperial"
UNIT_SYSTEM_METRIC = "metric"
UNIT_SYSTEM_OPTIONS = {UNIT_SYSTEM_IMPERIAL, UNIT_SYSTEM_METRIC}

DISPLAY_UNIT_CASCADES = {
    UNIT_SYSTEM_IMPERIAL: {
        "mass": ["lb", "oz"],
        "volume": ["gal", "qt", "pt", "cup", "tbs", "tsp"],
    },
    UNIT_SYSTEM_METRIC: {
        "mass": ["kg", "g"],
        "volume": ["L", "ml"],
    },
}

ACCORDING_TO_TASTE_THRESHOLD = 0.001


def normalize_display_mode(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in DISPLAY_MODE_OPTIONS:
        return normalized
    return DISPLAY_MODE_DEFAULT


def normalize_unit_system(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in UNIT_SYSTEM_OPTIONS:
        return normalized
    return UNIT_SYSTEM_IMPERIAL


def format_display_quantity(quantity: float) -> str:
    rounded_quantity = round(quantity, 3)
    if rounded_quantity < ACCORDING_TO_TASTE_THRESHOLD:
        return "according to taste"
    return f"{rounded_quantity:g}"


def _convert_for_display(
    *,
    quantity: float,
    source_unit: str,
    target_unit: str,
    item_type: str,
    mass_quantity: float | None,
    mass_unit: str | None,
    volume_quantity: float | None,
    volume_unit: str | None,
) -> dict:
    direct_result = convert_unit_value(quantity=quantity, from_unit=source_unit, to_unit=target_unit)
    if direct_result["ok"]:
        return direct_result

    return convert_with_item_mass_volume_bridge(
        quantity=quantity,
        from_unit=source_unit,
        to_unit=target_unit,
        item_type=item_type,
        mass_quantity=mass_quantity,
        mass_unit=mass_unit,
        volume_quantity=volume_quantity,
        volume_unit=volume_unit,
    )


def build_display_measurement(
    *,
    quantity: float,
    source_unit: str,
    item_type: str,
    display_mode: str,
    unit_system: str,
    mass_quantity: float | None,
    mass_unit: str | None,
    volume_quantity: float | None,
    volume_unit: str | None,
) -> dict:
    normalized_display_mode = normalize_display_mode(display_mode)
    normalized_unit_system = normalize_unit_system(unit_system)
    source_profile = get_unit_measurement_profile(source_unit)

    if (
        normalized_display_mode == DISPLAY_MODE_DEFAULT
        or source_profile is None
        or source_profile["measurement_type"] == "count"
    ):
        return {
            "quantity": float(quantity),
            "quantity_display": format_display_quantity(float(quantity)),
            "unit": normalize_unit_symbol(source_unit),
            "status": "original",
            "is_converted": False,
        }

    target_measurement_type = normalized_display_mode
    candidate_units = DISPLAY_UNIT_CASCADES[normalized_unit_system][target_measurement_type]
    viable_candidates: list[tuple[str, dict]] = []

    for candidate_unit in candidate_units:
        conversion_result = _convert_for_display(
            quantity=float(quantity),
            source_unit=source_unit,
            target_unit=candidate_unit,
            item_type=item_type,
            mass_quantity=mass_quantity,
            mass_unit=mass_unit,
            volume_quantity=volume_quantity,
            volume_unit=volume_unit,
        )
        if conversion_result["ok"]:
            viable_candidates.append((candidate_unit, conversion_result))

    if not viable_candidates:
        return {
            "quantity": float(quantity),
            "quantity_display": format_display_quantity(float(quantity)),
            "unit": normalize_unit_symbol(source_unit),
            "status": "fallback_original",
            "warning": (
                f"{target_measurement_type.title()} display unavailable for item in unit '{source_unit}'. "
                "Original unit kept."
            ),
            "is_converted": False,
        }

    selected_unit, selected_result = viable_candidates[-1]
    for candidate_unit, candidate_result in viable_candidates:
        if float(candidate_result["quantity"]) >= 1:
            selected_unit, selected_result = candidate_unit, candidate_result
            break

    return {
        "quantity": float(selected_result["quantity"]),
        "quantity_display": format_display_quantity(float(selected_result["quantity"])),
        "unit": selected_unit,
        "status": selected_result["status"],
        "is_converted": selected_result["status"] != "direct_ratio"
        or selected_unit != source_unit,
    }


def apply_display_preferences_to_rows(
    *,
    rows: list[dict],
    row_mode: str,
    display_mode: str,
    unit_system: str,
) -> dict:
    warnings: list[str] = []
    display_rows: list[dict] = []

    for row in rows:
        display_row = dict(row)
        item_type = row.get("component_item_type")
        if item_type is None:
            item_type = "recipe" if row.get("row_type") == "sub_recipe" else "base_food"

        source_quantity = row.get("component_quantity")
        if source_quantity is None:
            source_quantity = row.get("total_quantity")

        source_unit = row.get("component_unit")

        display_measurement = build_display_measurement(
            quantity=float(source_quantity),
            source_unit=source_unit,
            item_type=item_type,
            display_mode=display_mode,
            unit_system=unit_system,
            mass_quantity=row.get("mass_quantity"),
            mass_unit=row.get("mass_unit"),
            volume_quantity=row.get("volume_quantity"),
            volume_unit=row.get("volume_unit"),
        )
        display_row["display_quantity"] = display_measurement["quantity"]
        display_row["display_quantity_display"] = display_measurement["quantity_display"]
        display_row["display_unit"] = display_measurement["unit"]
        display_row["display_status"] = display_measurement["status"]

        if display_measurement.get("warning") and display_measurement["warning"] not in warnings:
            warnings.append(display_measurement["warning"])

        display_rows.append(display_row)

    return {
        "rows": display_rows,
        "warnings": warnings,
    }
