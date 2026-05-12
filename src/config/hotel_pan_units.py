LIQUID_OUNCE_TO_ML = 29.5735

HOTEL_PAN_SIZE_OPTIONS = [
    {"value": "full", "label": "Full pan"},
    {"value": "half", "label": "Half pan"},
    {"value": "half_long", "label": "Torpedo / half long pan"},
    {"value": "two_thirds", "label": "Two-thirds pan"},
    {"value": "third", "label": "Third pan"},
    {"value": "quarter", "label": "Fourth pan"},
    {"value": "sixth", "label": "Sixth pan"},
    {"value": "ninth", "label": "Ninth pan"},
]

HOTEL_PAN_DEPTH_OPTIONS = [
    {"value": "2_5", "label": '2.5"'},
    {"value": "4", "label": '4"'},
    {"value": "6", "label": '6"'},
]

HOTEL_PAN_CAPACITIES_FL_OZ = {
    ("full", "2_5"): 212.5,
    ("full", "4"): 358.4,
    ("full", "6"): 537.6,
    ("two_thirds", "2_5"): 143.4,
    ("two_thirds", "4"): 238.1,
    ("two_thirds", "6"): 358.4,
    ("half", "2_5"): 110.1,
    ("half", "4"): 171.5,
    ("half", "6"): 256.0,
    ("half_long", "2_5"): 97.3,
    ("half_long", "4"): 153.6,
    ("half_long", "6"): 222.7,
    ("third", "2_5"): 66.6,
    ("third", "4"): 105.0,
    ("third", "6"): 156.2,
    ("quarter", "2_5"): 46.1,
    ("quarter", "4"): 76.8,
    ("quarter", "6"): 115.2,
    ("sixth", "2_5"): 30.7,
    ("sixth", "4"): 46.1,
    ("sixth", "6"): 69.1,
    ("ninth", "4"): 28.2,
}

_SIZE_LABELS = {option["value"]: option["label"] for option in HOTEL_PAN_SIZE_OPTIONS}
_DEPTH_LABELS = {option["value"]: option["label"] for option in HOTEL_PAN_DEPTH_OPTIONS}


def build_hotel_pan_unit_code(size: str, depth: str) -> str:
    return f"pan_{size}_{depth}"


HOTEL_PAN_UNITS = [
    {
        "value": build_hotel_pan_unit_code(size, depth),
        "label": f"{_SIZE_LABELS[size]}, {_DEPTH_LABELS[depth]}",
        "size": size,
        "depth": depth,
        "capacity_fl_oz": capacity,
        "capacity_ml": capacity * LIQUID_OUNCE_TO_ML,
    }
    for (size, depth), capacity in HOTEL_PAN_CAPACITIES_FL_OZ.items()
]

HOTEL_PAN_UNIT_DEFINITIONS = {
    unit["value"]: {
        "measurement_type": "volume",
        "canonical_unit": "ml",
        "canonical_factor": unit["capacity_ml"],
    }
    for unit in HOTEL_PAN_UNITS
}

HOTEL_PAN_UNIT_LABELS = {
    unit["value"]: unit["label"]
    for unit in HOTEL_PAN_UNITS
}

