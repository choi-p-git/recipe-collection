from config.hotel_pan_units import HOTEL_PAN_UNIT_DEFINITIONS


UNIT_MEASUREMENT_DEFINITIONS = {
    "g": {
        "measurement_type": "mass",
        "canonical_unit": "g",
        "canonical_factor": 1.0,
    },
    "kg": {
        "measurement_type": "mass",
        "canonical_unit": "g",
        "canonical_factor": 1000.0,
    },
    "oz": {
        "measurement_type": "mass",
        "canonical_unit": "g",
        "canonical_factor": 28.3495,
    },
    "lb": {
        "measurement_type": "mass",
        "canonical_unit": "g",
        "canonical_factor": 453.592,
    },
    "ml": {
        "measurement_type": "volume",
        "canonical_unit": "ml",
        "canonical_factor": 1.0,
    },
    "L": {
        "measurement_type": "volume",
        "canonical_unit": "ml",
        "canonical_factor": 1000.0,
    },
    "tsp": {
        "measurement_type": "volume",
        "canonical_unit": "ml",
        "canonical_factor": 4.92892,
    },
    "tbs": {
        "measurement_type": "volume",
        "canonical_unit": "ml",
        "canonical_factor": 14.7868,
    },
    "cup": {
        "measurement_type": "volume",
        "canonical_unit": "ml",
        "canonical_factor": 236.588,
    },
    "pt": {
        "measurement_type": "volume",
        "canonical_unit": "ml",
        "canonical_factor": 473.176,
    },
    "qt": {
        "measurement_type": "volume",
        "canonical_unit": "ml",
        "canonical_factor": 946.353,
    },
    "gal": {
        "measurement_type": "volume",
        "canonical_unit": "ml",
        "canonical_factor": 3785.41,
    },
    "each": {
        "measurement_type": "count",
        "canonical_unit": "each",
        "canonical_factor": 1.0,
    },
    **HOTEL_PAN_UNIT_DEFINITIONS,
}

MEASUREMENT_TYPE_LABELS = {
    "mass": "Mass",
    "volume": "Volume",
    "count": "Count",
}
