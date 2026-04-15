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


def convert_with_item_mass_volume_bridge(
    quantity: float,
    from_unit: str,
    to_unit: str,
    *,
    item_type: str,
    mass_quantity: float | None,
    mass_unit: str | None,
    volume_quantity: float | None,
    volume_unit: str | None,
) -> dict:
    direct_result = convert_unit_value(quantity, from_unit, to_unit)
    if direct_result["ok"]:
        return direct_result

    source_profile = get_unit_measurement_profile(from_unit)
    target_profile = get_unit_measurement_profile(to_unit)
    mass_profile = get_unit_measurement_profile(mass_unit)
    volume_profile = get_unit_measurement_profile(volume_unit)

    if source_profile is None or target_profile is None:
        return {
            "ok": False,
            "status": "missing",
            "label": "Missing unit metadata",
            "quantity": None,
            "unit": to_unit,
            "source_profile": source_profile,
            "target_profile": target_profile,
        }

    if source_profile["measurement_type"] not in {"mass", "volume"}:
        return {
            "ok": False,
            "status": "incompatible",
            "label": "Bridge conversion requires mass or volume units",
            "quantity": None,
            "unit": to_unit,
            "source_profile": source_profile,
            "target_profile": target_profile,
        }

    if target_profile["measurement_type"] not in {"mass", "volume"}:
        return {
            "ok": False,
            "status": "incompatible",
            "label": "Bridge conversion requires mass or volume units",
            "quantity": None,
            "unit": to_unit,
            "source_profile": source_profile,
            "target_profile": target_profile,
        }

    if not mass_quantity or not mass_profile or mass_profile["measurement_type"] != "mass":
        return {
            "ok": False,
            "status": "missing_bridge_metadata",
            "label": "Mass bridge metadata is missing",
            "quantity": None,
            "unit": to_unit,
            "source_profile": source_profile,
            "target_profile": target_profile,
        }

    if not volume_quantity or not volume_profile or volume_profile["measurement_type"] != "volume":
        return {
            "ok": False,
            "status": "missing_bridge_metadata",
            "label": "Volume bridge metadata is missing",
            "quantity": None,
            "unit": to_unit,
            "source_profile": source_profile,
            "target_profile": target_profile,
        }

    canonical_mass_quantity = float(mass_quantity) * float(mass_profile["canonical_factor"])
    canonical_volume_quantity = float(volume_quantity) * float(volume_profile["canonical_factor"])
    source_canonical_quantity = float(quantity) * float(source_profile["canonical_factor"])

    if canonical_mass_quantity <= 0 or canonical_volume_quantity <= 0:
        return {
            "ok": False,
            "status": "missing_bridge_metadata",
            "label": "Bridge metadata must be greater than 0",
            "quantity": None,
            "unit": to_unit,
            "source_profile": source_profile,
            "target_profile": target_profile,
        }

    if source_profile["measurement_type"] == "mass" and target_profile["measurement_type"] == "volume":
        bridged_canonical_quantity = source_canonical_quantity * canonical_volume_quantity / canonical_mass_quantity
    elif source_profile["measurement_type"] == "volume" and target_profile["measurement_type"] == "mass":
        bridged_canonical_quantity = source_canonical_quantity * canonical_mass_quantity / canonical_volume_quantity
    else:
        return {
            "ok": False,
            "status": direct_result["status"],
            "label": direct_result["label"],
            "quantity": None,
            "unit": to_unit,
            "source_profile": source_profile,
            "target_profile": target_profile,
        }

    converted_quantity = bridged_canonical_quantity / float(target_profile["canonical_factor"])
    item_type_label = "Recipe" if item_type == "recipe" else "Base food"
    status_code = (
        "recipe_bridge_conversion"
        if item_type == "recipe"
        else "base_food_bridge_conversion"
    )
    return {
        "ok": True,
        "status": status_code,
        "label": f"{item_type_label} mass-volume bridge conversion ready",
        "quantity": converted_quantity,
        "unit": to_unit,
        "source_profile": source_profile,
        "target_profile": target_profile,
    }


def convert_with_mass_volume_bridge(
    quantity: float,
    from_unit: str,
    to_unit: str,
    *,
    mass_quantity: float | None,
    mass_unit: str | None,
    volume_quantity: float | None,
    volume_unit: str | None,
) -> dict:
    return convert_with_item_mass_volume_bridge(
        quantity=quantity,
        from_unit=from_unit,
        to_unit=to_unit,
        item_type="recipe",
        mass_quantity=mass_quantity,
        mass_unit=mass_unit,
        volume_quantity=volume_quantity,
        volume_unit=volume_unit,
    )
