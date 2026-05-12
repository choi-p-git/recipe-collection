from config.hotel_pan_units import HOTEL_PAN_UNIT_LABELS


def format_unit_label(unit: str | None) -> str:
    normalized_unit = str(unit or "").strip()
    return HOTEL_PAN_UNIT_LABELS.get(normalized_unit, normalized_unit)

