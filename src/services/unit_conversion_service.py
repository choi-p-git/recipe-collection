from config.unit_measurements import MEASUREMENT_TYPE_LABELS, UNIT_MEASUREMENT_DEFINITIONS


def get_unit_measurement_profile(unit: str | None) -> dict | None:
    normalized_unit = str(unit or "").strip()
    if not normalized_unit:
        return None

    definition = UNIT_MEASUREMENT_DEFINITIONS.get(normalized_unit)
    if definition is None:
        return {
            "unit": normalized_unit,
            "measurement_type": "unknown",
            "measurement_type_label": "Unknown",
            "canonical_unit": None,
            "canonical_factor": None,
            "conversion_ready": False,
        }

    return {
        "unit": normalized_unit,
        "measurement_type": definition["measurement_type"],
        "measurement_type_label": MEASUREMENT_TYPE_LABELS[definition["measurement_type"]],
        "canonical_unit": definition["canonical_unit"],
        "canonical_factor": definition["canonical_factor"],
        "conversion_ready": True,
    }


def describe_unit_conversion(source_unit: str | None, target_unit: str | None) -> dict:
    source_profile = get_unit_measurement_profile(source_unit)
    target_profile = get_unit_measurement_profile(target_unit)

    if source_profile is None or target_profile is None:
        return {
            "status": "missing",
            "label": "Missing unit metadata",
            "source_profile": source_profile,
            "target_profile": target_profile,
        }

    if source_profile["unit"] == target_profile["unit"]:
        return {
            "status": "direct_ratio",
            "label": "Direct ratio ready",
            "source_profile": source_profile,
            "target_profile": target_profile,
        }

    if (
        source_profile["conversion_ready"]
        and target_profile["conversion_ready"]
        and source_profile["measurement_type"] == target_profile["measurement_type"]
        and source_profile["canonical_unit"] == target_profile["canonical_unit"]
    ):
        return {
            "status": "same_family_conversion",
            "label": "Same-family conversion ready",
            "source_profile": source_profile,
            "target_profile": target_profile,
        }

    if (
        source_profile["measurement_type"] != "unknown"
        and target_profile["measurement_type"] != "unknown"
    ):
        return {
            "status": "incompatible",
            "label": "Different measurement types",
            "source_profile": source_profile,
            "target_profile": target_profile,
        }

    return {
        "status": "unknown",
        "label": "Unit relationship not yet modeled",
        "source_profile": source_profile,
        "target_profile": target_profile,
    }


def convert_unit_value(quantity: float, from_unit: str, to_unit: str) -> dict:
    relationship = describe_unit_conversion(from_unit, to_unit)

    if relationship["status"] not in {"direct_ratio", "same_family_conversion"}:
        return {
            "ok": False,
            "status": relationship["status"],
            "label": relationship["label"],
            "quantity": None,
            "unit": to_unit,
            "source_profile": relationship["source_profile"],
            "target_profile": relationship["target_profile"],
        }

    if relationship["status"] == "direct_ratio":
        converted_quantity = float(quantity)
    else:
        source_factor = float(relationship["source_profile"]["canonical_factor"])
        target_factor = float(relationship["target_profile"]["canonical_factor"])
        converted_quantity = float(quantity) * source_factor / target_factor

    return {
        "ok": True,
        "status": relationship["status"],
        "label": relationship["label"],
        "quantity": converted_quantity,
        "unit": to_unit,
        "source_profile": relationship["source_profile"],
        "target_profile": relationship["target_profile"],
    }
