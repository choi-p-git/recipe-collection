from config.hotel_pan_units import HOTEL_PAN_UNITS


STANDARD_UNITS = [
    "g",
    "kg",
    "ml",
    "L",
    "oz",
    "lb",
    "tsp",
    "tbs",
    "cup",
    "pt",
    "qt",
    "gal",
    "each",
]

ADVANCED_SCALING_UNITS = [
    *[unit["value"] for unit in HOTEL_PAN_UNITS],
]

APPROVED_UNITS = [
    *STANDARD_UNITS,
    *ADVANCED_SCALING_UNITS,
]
