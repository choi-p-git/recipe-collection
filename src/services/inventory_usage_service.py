from __future__ import annotations

import json
import re
from datetime import date

from config.item_categories import ITEM_CATEGORY_LABELS
from db import get_connection
from services.inventory_service import _format_location_line_display, _format_quantity
from services.menu_calendar_service import build_week_day_dates
from services.recipe_flattening_service import build_flattened_recipe_view
from services.unit_conversion_service import convert_unit_value, convert_with_item_mass_volume_bridge, normalize_unit_symbol
from services.unit_label_service import format_unit_label


MAX_DASHBOARD_USAGE_ROWS = 5
EACH_ONLY_COUNT_TYPE = "counted_by_each_only"


def _format_optional_quantity(value) -> str:
    if value is None:
        return ""
    return _format_quantity(value)


def _service_date_lookup(menu_rows: list[tuple]) -> dict[int, dict]:
    lookup = {}
    for menu_id, start_date, end_date, menu_length_weeks, service_days_json in menu_rows:
        try:
            service_days = json.loads(service_days_json or "[]")
        except json.JSONDecodeError:
            service_days = []
        lookup[int(menu_id)] = build_week_day_dates(
            menu_start_date=start_date or "",
            menu_end_date=end_date or "",
            week_numbers=list(range(1, int(menu_length_weeks or 1) + 1)),
            service_days=service_days,
        )
    return lookup


def _load_menu_date_lookup(menu_ids: set[int]) -> dict[int, dict]:
    if not menu_ids:
        return {}
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT menu_id, menu_start_date, menu_end_date, menu_length_weeks, service_days_json
            FROM menu
            WHERE menu_id IN ({})
            """.format(", ".join("?" for _ in menu_ids)),
            sorted(menu_ids),
        )
        return _service_date_lookup(cursor.fetchall())


def _format_service_date(menu_date_lookup: dict, *, menu_id: int, week_number: int, day_of_week: str) -> dict:
    service_date = (
        menu_date_lookup
        .get(menu_id, {})
        .get(week_number, {})
        .get(day_of_week, {})
    )
    return {
        "date": service_date.get("date", ""),
        "display": service_date.get("display") or f"Week {week_number} {day_of_week.title()}",
    }


def _usage_payload(row, menu_date_lookup: dict, today_iso: str) -> dict:
    (
        menu_id,
        menu_name,
        week_number,
        day_of_week,
        meal_period,
        concept_name,
        menu_slot_item_id,
        menu_item_id,
        menu_item_name,
        menu_item_type,
        menu_item_yield_quantity,
        menu_item_yield_unit,
        menu_item_mass_quantity,
        menu_item_mass_unit,
        menu_item_volume_quantity,
        menu_item_volume_unit,
        production_record_id,
        production_record_line_id,
        production_status,
        forecast_quantity,
        forecast_unit,
        actual_quantity,
        actual_unit,
        variance_quantity,
        variance_unit,
        implied_demand_quantity,
        implied_demand_unit,
        forecast_error_percent,
        reason_code,
    ) = row
    menu_id = int(menu_id)
    week_number = int(week_number)
    service_date = _format_service_date(
        menu_date_lookup,
        menu_id=menu_id,
        week_number=week_number,
        day_of_week=day_of_week,
    )
    is_past = bool(service_date["date"] and service_date["date"] < today_iso)
    return {
        "menu_id": menu_id,
        "menu_name": menu_name,
        "week_number": week_number,
        "day_of_week": day_of_week,
        "day_label": str(day_of_week).title(),
        "meal_period": meal_period,
        "meal_period_label": str(meal_period).replace("_", " ").title(),
        "concept_name": concept_name,
        "concept_label": str(concept_name).replace("_", " ").title(),
        "menu_slot_item_id": int(menu_slot_item_id),
        "menu_item_id": int(menu_item_id),
        "menu_item_name": menu_item_name,
        "menu_item_type": menu_item_type,
        "menu_item_yield_quantity": float(menu_item_yield_quantity) if menu_item_yield_quantity is not None else None,
        "menu_item_yield_unit": menu_item_yield_unit or "",
        "menu_item_mass_quantity": float(menu_item_mass_quantity) if menu_item_mass_quantity is not None else None,
        "menu_item_mass_unit": menu_item_mass_unit or "",
        "menu_item_volume_quantity": float(menu_item_volume_quantity) if menu_item_volume_quantity is not None else None,
        "menu_item_volume_unit": menu_item_volume_unit or "",
        "production_record_id": int(production_record_id) if production_record_id is not None else None,
        "production_record_line_id": int(production_record_line_id) if production_record_line_id is not None else None,
        "production_status": production_status or "",
        "production_status_label": str(production_status or "").title(),
        "service_date": service_date["date"],
        "service_date_display": service_date["display"],
        "forecast_quantity": float(forecast_quantity) if forecast_quantity is not None else None,
        "forecast_quantity_display": _format_optional_quantity(forecast_quantity),
        "forecast_unit": forecast_unit or "",
        "forecast_unit_label": format_unit_label(forecast_unit) if forecast_unit else "",
        "actual_quantity_display": _format_optional_quantity(actual_quantity),
        "actual_unit": actual_unit or forecast_unit or "",
        "actual_unit_label": format_unit_label(actual_unit or forecast_unit) if (actual_unit or forecast_unit) else "",
        "variance_quantity_display": _format_optional_quantity(variance_quantity),
        "variance_unit": variance_unit or forecast_unit or "",
        "variance_unit_label": format_unit_label(variance_unit or forecast_unit) if (variance_unit or forecast_unit) else "",
        "implied_demand_quantity_display": _format_optional_quantity(implied_demand_quantity),
        "implied_demand_unit": implied_demand_unit or forecast_unit or "",
        "implied_demand_unit_label": format_unit_label(implied_demand_unit or forecast_unit) if (implied_demand_unit or forecast_unit) else "",
        "forecast_error_percent_display": _format_optional_quantity(forecast_error_percent),
        "reason_label": str(reason_code or "").replace("_", " ").title(),
        "is_past": is_past,
    }


def _scaled_forecast_factor(usage: dict) -> float | None:
    forecast_quantity = usage.get("forecast_quantity")
    forecast_unit = usage.get("forecast_unit")
    yield_quantity = usage.get("menu_item_yield_quantity")
    yield_unit = usage.get("menu_item_yield_unit")
    if forecast_quantity is None or not forecast_unit or not yield_quantity or not yield_unit:
        return None
    if forecast_unit == yield_unit:
        forecast_in_yield_unit = float(forecast_quantity)
    else:
        conversion = convert_unit_value(float(forecast_quantity), forecast_unit, yield_unit)
        if not conversion["ok"]:
            conversion = convert_with_item_mass_volume_bridge(
                float(forecast_quantity),
                forecast_unit,
                yield_unit,
                item_type=usage.get("menu_item_type") or "",
                mass_quantity=usage.get("menu_item_mass_quantity"),
                mass_unit=usage.get("menu_item_mass_unit"),
                volume_quantity=usage.get("menu_item_volume_quantity"),
                volume_unit=usage.get("menu_item_volume_unit"),
            )
        if not conversion["ok"]:
            return None
        forecast_in_yield_unit = float(conversion["quantity"])
    return forecast_in_yield_unit / float(yield_quantity)


def _needed_parts_for_usage(item_id: int, usage: dict) -> list[dict]:
    forecast_quantity = usage.get("forecast_quantity")
    forecast_unit = usage.get("forecast_unit")
    if int(usage["menu_item_id"]) == int(item_id) and forecast_quantity is not None and forecast_unit:
        return [{"quantity": float(forecast_quantity), "unit": forecast_unit}]
    if usage.get("menu_item_type") != "recipe":
        return []

    scale_factor = _scaled_forecast_factor(usage)
    if scale_factor is None:
        return []
    flattened_view = build_flattened_recipe_view(int(usage["menu_item_id"]), scale_factor=scale_factor)
    totals_by_unit: dict[str, float] = {}
    for row in flattened_view.get("rows", []):
        if int(row.get("component_item_id") or 0) != int(item_id):
            continue
        unit = row.get("component_unit") or ""
        if not unit:
            continue
        totals_by_unit[unit] = totals_by_unit.get(unit, 0.0) + float(row.get("total_quantity") or 0)
    return [
        {"quantity": quantity, "unit": unit}
        for unit, quantity in totals_by_unit.items()
        if quantity > 0
    ]


def _parse_pack_size_text(pack_size_text: str | None) -> tuple[float, str] | None:
    match = re.match(r"^\s*(\d+(?:\.\d+)?)\s+([A-Za-z][A-Za-z0-9_ ]*)\s*$", str(pack_size_text or ""))
    if not match:
        return None
    unit = normalize_unit_symbol(match.group(2).strip().lower())
    if not unit:
        return None
    return float(match.group(1)), unit


def _load_inventory_needed_profile(item_id: int) -> dict | None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                ili.unit_of_measurement,
                ili.count_type,
                ili.pack_quantity,
                ili.pack_size_text,
                i.yield_quantity,
                i.yield_unit,
                i.item_type,
                i.mass_quantity,
                i.mass_unit,
                i.volume_quantity,
                i.volume_unit
            FROM inventory_location_item ili
            JOIN inventory_location il
              ON il.inventory_location_id = ili.inventory_location_id
            JOIN item i
              ON i.item_id = ili.item_id
            WHERE ili.item_id = ?
              AND il.status = 'active'
            ORDER BY
                CASE
                    WHEN ili.unit_of_measurement = 'Case' AND ili.count_type != ? THEN 0
                    WHEN ili.count_type = ? OR ili.unit_of_measurement = 'Each' THEN 1
                    ELSE 2
                END,
                ili.updated_at DESC
            LIMIT 1
            """,
            (item_id, EACH_ONLY_COUNT_TYPE, EACH_ONLY_COUNT_TYPE),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    return {
        "unit_of_measurement": row[0] or "",
        "count_type": row[1] or "",
        "pack_quantity": float(row[2]) if row[2] is not None else None,
        "pack_size_text": row[3] or "",
        "yield_quantity": float(row[4]) if row[4] is not None else None,
        "yield_unit": row[5] or "",
        "item_type": row[6] or "",
        "mass_quantity": float(row[7]) if row[7] is not None else None,
        "mass_unit": row[8] or "",
        "volume_quantity": float(row[9]) if row[9] is not None else None,
        "volume_unit": row[10] or "",
    }


def _temporary_each_bridge_from_input(temporary_each_bridge: dict | None) -> dict:
    if not temporary_each_bridge:
        return {}
    try:
        quantity = float(temporary_each_bridge.get("quantity") or 0)
    except (TypeError, ValueError):
        return {
            "ok": False,
            "message": "Temporary each conversion quantity must be a valid number.",
        }
    unit = normalize_unit_symbol(temporary_each_bridge.get("unit"))
    if quantity <= 0 or not unit:
        return {}
    return {
        "ok": True,
        "quantity": quantity,
        "unit": unit,
        "source": "temporary",
        "label": f"Temporary each conversion: 1 each = {_format_quantity(quantity)} {format_unit_label(unit)}",
    }


def _official_each_bridge(profile: dict) -> dict:
    yield_quantity = float(profile.get("yield_quantity") or 0)
    if yield_quantity <= 0 or normalize_unit_symbol(profile.get("yield_unit")) != "each":
        return {}
    if profile.get("mass_quantity") and profile.get("mass_unit"):
        quantity = float(profile["mass_quantity"]) / yield_quantity
        return {
            "ok": True,
            "quantity": quantity,
            "unit": profile["mass_unit"],
            "source": "official",
            "label": f"Official item conversion: 1 each = {_format_quantity(quantity)} {format_unit_label(profile['mass_unit'])}",
        }
    if profile.get("volume_quantity") and profile.get("volume_unit"):
        quantity = float(profile["volume_quantity"]) / yield_quantity
        return {
            "ok": True,
            "quantity": quantity,
            "unit": profile["volume_unit"],
            "source": "official",
            "label": f"Official item conversion: 1 each = {_format_quantity(quantity)} {format_unit_label(profile['volume_unit'])}",
        }
    return {}


def _each_bridge(profile: dict, temporary_each_bridge: dict | None) -> dict:
    temporary_bridge = _temporary_each_bridge_from_input(temporary_each_bridge)
    if temporary_bridge.get("ok"):
        return temporary_bridge
    official_bridge = _official_each_bridge(profile)
    if official_bridge.get("ok"):
        return official_bridge
    return temporary_bridge or {}


def _convert_each_part_with_bridge(part: dict, target_unit: str, profile: dict, each_bridge: dict) -> float | None:
    if normalize_unit_symbol(part.get("unit")) != "each" or not each_bridge.get("ok"):
        return None
    bridged_quantity = float(part["quantity"]) * float(each_bridge["quantity"])
    conversion = convert_unit_value(bridged_quantity, each_bridge["unit"], target_unit)
    if not conversion["ok"]:
        conversion = convert_with_item_mass_volume_bridge(
            bridged_quantity,
            each_bridge["unit"],
            target_unit,
            item_type=profile.get("item_type") or "",
            mass_quantity=profile.get("mass_quantity"),
            mass_unit=profile.get("mass_unit"),
            volume_quantity=profile.get("volume_quantity"),
            volume_unit=profile.get("volume_unit"),
        )
    if not conversion["ok"]:
        return None
    return float(conversion["quantity"])


def _convert_needed_part_to_unit(part: dict, target_unit: str, profile: dict, each_bridge: dict) -> float | None:
    conversion = convert_unit_value(float(part["quantity"]), part["unit"], target_unit)
    if not conversion["ok"]:
        conversion = convert_with_item_mass_volume_bridge(
            float(part["quantity"]),
            part["unit"],
            target_unit,
            item_type=profile.get("item_type") or "",
            mass_quantity=profile.get("mass_quantity"),
            mass_unit=profile.get("mass_unit"),
            volume_quantity=profile.get("volume_quantity"),
            volume_unit=profile.get("volume_unit"),
        )
    if not conversion["ok"]:
        return _convert_each_part_with_bridge(part, target_unit, profile, each_bridge)
    return float(conversion["quantity"])


def _sum_needed_parts_in_unit(needed_parts: list[dict], target_unit: str, profile: dict, each_bridge: dict) -> float | None:
    total = 0.0
    for part in needed_parts:
        converted_quantity = _convert_needed_part_to_unit(part, target_unit, profile, each_bridge)
        if converted_quantity is None:
            return None
        total += converted_quantity
    return total


def _needed_conversion_issue(needed_parts: list[dict], target_unit: str, each_bridge: dict) -> dict:
    if each_bridge.get("ok") is False and each_bridge.get("message"):
        return {
            "code": "invalid_temporary_each_bridge",
            "message": each_bridge["message"],
        }
    needs_each_bridge = any(normalize_unit_symbol(part.get("unit")) == "each" for part in needed_parts)
    if needs_each_bridge and not each_bridge.get("ok"):
        return {
            "code": "missing_each_bridge",
            "message": (
                f"Cannot convert recipe eaches into {format_unit_label(target_unit)} because this item "
                "does not have an official each-to-mass/volume conversion."
            ),
        }
    return {
        "code": "conversion_unavailable",
        "message": f"Cannot convert recipe need into {format_unit_label(target_unit)} with the current item metadata.",
    }


def _inventory_needed_measure(
    needed_parts: list[dict],
    profile: dict | None,
    temporary_each_bridge: dict | None = None,
) -> dict:
    empty_measure = {
        "display": "",
        "quantity": None,
        "unit": "",
        "unit_label": "",
        "conversion_note": "",
        "conversion_issue": None,
    }
    if not profile:
        return empty_measure

    unit_of_measurement = profile.get("unit_of_measurement")
    count_type = profile.get("count_type")
    pack_size = _parse_pack_size_text(profile.get("pack_size_text"))
    each_bridge = _each_bridge(profile, temporary_each_bridge)

    if unit_of_measurement == "Case" and count_type != EACH_ONLY_COUNT_TYPE:
        pack_quantity = float(profile.get("pack_quantity") or 0)
        if not pack_size or pack_quantity <= 0:
            return empty_measure
        pack_size_quantity, pack_size_unit = pack_size
        needed_in_pack_unit = _sum_needed_parts_in_unit(needed_parts, pack_size_unit, profile, each_bridge)
        if needed_in_pack_unit is None or pack_size_quantity <= 0:
            return {
                **empty_measure,
                "conversion_issue": _needed_conversion_issue(needed_parts, pack_size_unit, each_bridge),
            }
        quantity = needed_in_pack_unit / (pack_quantity * pack_size_quantity)
        return {
            "display": f"{_format_quantity(quantity)} case",
            "quantity": quantity,
            "unit": "case",
            "unit_label": "case",
            "conversion_note": each_bridge.get("label", ""),
            "conversion_issue": None,
        }

    if unit_of_measurement in {"Kg", "Lb"}:
        target_unit = "kg" if unit_of_measurement == "Kg" else "lb"
        needed_in_unit = _sum_needed_parts_in_unit(needed_parts, target_unit, profile, each_bridge)
        if needed_in_unit is not None:
            return {
                "display": f"{_format_quantity(needed_in_unit)} {format_unit_label(target_unit)}",
                "quantity": needed_in_unit,
                "unit": target_unit,
                "unit_label": format_unit_label(target_unit),
                "conversion_note": each_bridge.get("label", ""),
                "conversion_issue": None,
            }
        return {
            **empty_measure,
            "conversion_issue": _needed_conversion_issue(needed_parts, target_unit, each_bridge),
        }

    if unit_of_measurement == "Each" or count_type == EACH_ONLY_COUNT_TYPE:
        if pack_size:
            pack_size_quantity, pack_size_unit = pack_size
            needed_in_pack_unit = _sum_needed_parts_in_unit(needed_parts, pack_size_unit, profile, each_bridge)
            if needed_in_pack_unit is not None and pack_size_quantity > 0:
                quantity = needed_in_pack_unit / pack_size_quantity
                return {
                    "display": f"{_format_quantity(quantity)} each",
                    "quantity": quantity,
                    "unit": "each",
                    "unit_label": format_unit_label("each"),
                    "conversion_note": each_bridge.get("label", ""),
                    "conversion_issue": None,
                }
        needed_each = _sum_needed_parts_in_unit(needed_parts, "each", profile, each_bridge)
        if needed_each is not None:
            return {
                "display": f"{_format_quantity(needed_each)} {format_unit_label('each')}",
                "quantity": needed_each,
                "unit": "each",
                "unit_label": format_unit_label("each"),
                "conversion_note": "",
                "conversion_issue": None,
            }
        return {
            **empty_measure,
            "conversion_issue": _needed_conversion_issue(needed_parts, "each", each_bridge),
        }
    return empty_measure


def _attach_needed_display(
    item_id: int,
    usage: dict,
    inventory_needed_profile: dict | None,
    temporary_each_bridge: dict | None = None,
) -> dict:
    needed_parts = _needed_parts_for_usage(item_id, usage)
    if not needed_parts:
        return {
            **usage,
            "needed_parts": [],
            "needed_display": "",
            "needed_quantity": None,
            "needed_unit": "",
            "needed_unit_label": "",
            "recipe_needed_display": "",
            "needed_quantity_display": "",
            "recipe_needed_unit_label": "",
            "needed_conversion_note": "",
            "needed_conversion_issue": None,
        }
    display_parts = [
        f"{_format_quantity(part['quantity'])} {format_unit_label(part['unit'])}"
        for part in needed_parts
    ]
    first_part = needed_parts[0]
    recipe_needed_display = " + ".join(display_parts)
    inventory_needed = _inventory_needed_measure(needed_parts, inventory_needed_profile, temporary_each_bridge)
    return {
        **usage,
        "needed_parts": needed_parts,
        "needed_display": inventory_needed["display"] or recipe_needed_display,
        "needed_quantity": inventory_needed["quantity"],
        "needed_unit": inventory_needed["unit"],
        "needed_unit_label": inventory_needed["unit_label"],
        "recipe_needed_display": recipe_needed_display,
        "needed_quantity_display": _format_quantity(first_part["quantity"]),
        "recipe_needed_unit_label": format_unit_label(first_part["unit"]),
        "needed_conversion_note": inventory_needed["conversion_note"],
        "needed_conversion_issue": inventory_needed["conversion_issue"],
    }


def get_inventory_item_usage(
    item_id: int,
    *,
    today: date | None = None,
    limit: int | None = None,
    temporary_each_bridge: dict | None = None,
) -> dict:
    today_iso = (today or date.today()).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            WITH RECURSIVE recipe_uses(parent_recipe_item_id, path) AS (
                SELECT
                    rc.parent_recipe_item_id,
                    printf('%d', rc.parent_recipe_item_id)
                FROM recipe_component rc
                JOIN item parent
                  ON parent.item_id = rc.parent_recipe_item_id
                WHERE rc.component_item_id = ?
                  AND parent.status = 'live'
                UNION
                SELECT
                    rc.parent_recipe_item_id,
                    recipe_uses.path || ',' || rc.parent_recipe_item_id
                FROM recipe_component rc
                JOIN item parent
                  ON parent.item_id = rc.parent_recipe_item_id
                JOIN recipe_uses
                  ON recipe_uses.parent_recipe_item_id = rc.component_item_id
                WHERE parent.status = 'live'
                  AND instr(',' || recipe_uses.path || ',', ',' || rc.parent_recipe_item_id || ',') = 0
            ),
            menu_items AS (
                SELECT ? AS item_id
                UNION
                SELECT parent_recipe_item_id FROM recipe_uses
            )
            SELECT
                ms.menu_id,
                m.menu_name,
                ms.week_number,
                ms.day_of_week,
                ms.meal_period,
                ms.concept_name,
                msi.menu_slot_item_id,
                i.item_id,
                i.item_name,
                i.item_type,
                i.yield_quantity,
                i.yield_unit,
                i.mass_quantity,
                i.mass_unit,
                i.volume_quantity,
                i.volume_unit,
                pr.production_record_id,
                prl.production_record_line_id,
                pr.status,
                COALESCE(mf.calculated_forecast_quantity, mf.forecast_yield_quantity),
                COALESCE(mf.calculated_forecast_unit, mf.forecast_yield_unit),
                prl.actual_quantity,
                prl.actual_unit,
                prl.end_service_variance_quantity,
                prl.end_service_variance_unit,
                prl.implied_demand_quantity,
                prl.implied_demand_unit,
                prl.forecast_error_percent,
                prl.reason_code
            FROM menu_slot_item msi
            JOIN menu_slot ms
              ON ms.menu_slot_id = msi.menu_slot_id
            JOIN menu m
              ON m.menu_id = ms.menu_id
            JOIN item i
              ON i.item_id = msi.item_id
            JOIN menu_items mi
              ON mi.item_id = msi.item_id
            LEFT JOIN menu_forecast mf
              ON mf.menu_slot_item_id = msi.menu_slot_item_id
            LEFT JOIN production_record pr
              ON pr.menu_id = ms.menu_id
             AND pr.week_number = ms.week_number
             AND pr.day_of_week = ms.day_of_week
            LEFT JOIN production_record_line prl
              ON prl.production_record_id = pr.production_record_id
             AND prl.item_id = msi.item_id
            ORDER BY ms.menu_id ASC, ms.week_number ASC, ms.day_of_week ASC, ms.meal_period ASC, ms.concept_name ASC
            """,
            (item_id, item_id),
        )
        raw_rows = cursor.fetchall()
        cursor.execute(
            """
            SELECT item_id, item_name, item_category
            FROM item
            WHERE item_id = ?
            """,
            (item_id,),
        )
        item_row = cursor.fetchone()

    menu_ids = {int(row[0]) for row in raw_rows}
    menu_date_lookup = _load_menu_date_lookup(menu_ids)
    inventory_needed_profile = _load_inventory_needed_profile(item_id)
    upcoming = []
    past = []
    for row in raw_rows:
        payload = _attach_needed_display(
            item_id,
            _usage_payload(row, menu_date_lookup, today_iso),
            inventory_needed_profile,
            temporary_each_bridge,
        )
        if payload["is_past"]:
            past.append(payload)
        else:
            upcoming.append(payload)

    upcoming.sort(key=lambda item: (item["service_date"] or "9999-99-99", item["menu_id"], item["week_number"]))
    past.sort(key=lambda item: (item["service_date"] or "", item["menu_id"], item["week_number"]), reverse=True)
    if limit is not None:
        upcoming = upcoming[:limit]
        past = past[:limit]

    return {
        "item": {
            "item_id": int(item_row[0]) if item_row else int(item_id),
            "item_name": item_row[1] if item_row else "",
            "item_category": item_row[2] if item_row else "",
            "item_category_label": ITEM_CATEGORY_LABELS.get(item_row[2], str(item_row[2]).title()) if item_row else "",
        },
        "upcoming": upcoming,
        "past": past,
        "upcoming_count": len(upcoming),
        "past_count": len(past),
    }


def _format_entered_count_display(row: dict) -> str:
    unit_of_measurement = row.get("unit_of_measurement")
    count_type = row.get("count_type")
    each_quantity = float(row.get("count_each_quantity") or 0)
    case_quantity = float(row.get("count_case_quantity") or 0)
    if unit_of_measurement == "Case":
        parts = []
        if count_type in {"counted_by_case_only", "counted_by_each_and_case"} and case_quantity > 0:
            parts.append(f"{_format_quantity(case_quantity)} case")
        if count_type in {EACH_ONLY_COUNT_TYPE, "counted_by_each_and_case"} and each_quantity > 0:
            parts.append(f"{_format_quantity(each_quantity)} {format_unit_label('each')}")
        return " + ".join(parts) or "0"
    return f"{_format_quantity(each_quantity)} {format_unit_label(row.get('unit') or '')}".strip()


def _format_count_pack_display(row: dict) -> str:
    pack_quantity = row.get("pack_quantity_display")
    pack_size_text = row.get("pack_size_text")
    if pack_quantity and pack_size_text:
        return f"{pack_quantity} packs x {pack_size_text}"
    return pack_size_text or "--"


def get_inventory_item_count_rolldown(item_id: int) -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                ili.inventory_location_item_id,
                ili.inventory_location_id,
                root.location_name,
                child.location_name,
                ili.count_each_quantity,
                ili.count_case_quantity,
                ili.pack_quantity,
                ili.pack_size_text,
                ili.unit_of_measurement,
                ili.count_type,
                ili.quantity,
                ili.unit,
                ili.updated_at
            FROM inventory_location_item ili
            JOIN inventory_location child
              ON child.inventory_location_id = ili.inventory_location_id
            LEFT JOIN inventory_location root
              ON root.inventory_location_id = child.parent_inventory_location_id
            WHERE ili.item_id = ?
              AND child.status = 'active'
            ORDER BY COALESCE(root.location_name, child.location_name), child.location_name, ili.display_sequence
            """,
            (item_id,),
        )
        payloads = []
        for row in cursor.fetchall():
            payload = {
                "inventory_location_item_id": int(row[0]),
                "inventory_location_id": int(row[1]),
                "root_location_name": row[2] or row[3],
                "location_name": row[3],
                "location_label": f"{row[2]} / {row[3]}" if row[2] else row[3],
                "count_each_quantity": float(row[4] or 0),
                "count_each_quantity_display": _format_quantity(row[4]),
                "count_case_quantity": float(row[5] or 0),
                "count_case_quantity_display": _format_quantity(row[5]),
                "pack_quantity": row[6],
                "pack_quantity_display": _format_quantity(row[6]) if row[6] is not None else "",
                "pack_size_text": row[7] or "",
                "unit_of_measurement": row[8],
                "count_type": row[9],
                "count_type_label": str(row[9]).replace("_", " ").title(),
                "quantity": float(row[10] or 0),
                "quantity_display": _format_quantity(row[10]),
                "unit": row[11],
                "unit_label": format_unit_label(row[11]),
                "updated_at": row[12],
            }
            payload.update(_format_location_line_display(payload))
            payload["entered_count_display"] = _format_entered_count_display(payload)
            payload["pack_display"] = _format_count_pack_display(payload)
            payloads.append(payload)
        return payloads


def _build_inventory_item_summary(*, usage: dict, count_rolldown: list[dict]) -> dict:
    quantities_by_unit: dict[str, float] = {}
    quantity_labels_by_unit: dict[str, str] = {}
    coverage_quantities_by_unit: dict[str, float] = {}
    for row in count_rolldown:
        unit = row.get("display_unit") or row.get("unit") or ""
        unit_label = row.get("display_unit_label") or row.get("unit_label") or unit
        if not unit:
            continue
        quantities_by_unit[unit] = quantities_by_unit.get(unit, 0.0) + float(row.get("display_quantity") or 0)
        quantity_labels_by_unit[unit] = unit_label

        if row.get("unit_of_measurement") == "Case" and row.get("pack_quantity"):
            pack_quantity = float(row.get("pack_quantity") or 0)
            if pack_quantity > 0:
                count_each_quantity = float(row.get("count_each_quantity") or 0)
                count_case_quantity = float(row.get("count_case_quantity") or 0)
                equivalent_case_quantity = count_case_quantity + (count_each_quantity / pack_quantity)
                equivalent_each_quantity = (count_case_quantity * pack_quantity) + count_each_quantity
                coverage_quantities_by_unit["case"] = coverage_quantities_by_unit.get("case", 0.0) + equivalent_case_quantity
                coverage_quantities_by_unit["each"] = coverage_quantities_by_unit.get("each", 0.0) + equivalent_each_quantity
                continue
        coverage_quantities_by_unit[unit] = coverage_quantities_by_unit.get(unit, 0.0) + float(
            row.get("display_quantity") or 0
        )

    current_on_hand_display = " / ".join(
        f"{_format_quantity(quantity)} {quantity_labels_by_unit.get(unit, unit)}"
        for unit, quantity in sorted(quantities_by_unit.items())
    ) or "0"
    last_counted_at = max((row.get("updated_at") or "" for row in count_rolldown), default="")
    next_usage = usage["upcoming"][0] if usage["upcoming"] else None
    conversion_note = ""
    for usage_row in [*usage["upcoming"], *usage["past"]]:
        if usage_row.get("needed_conversion_note"):
            conversion_note = usage_row["needed_conversion_note"]
            break
    coverage_display = "No upcoming need"
    coverage_status = "none"
    if next_usage and next_usage.get("needed_quantity") is not None and next_usage.get("needed_unit"):
        needed_quantity = float(next_usage["needed_quantity"])
        needed_unit = next_usage["needed_unit"]
        needed_unit_label = next_usage.get("needed_unit_label") or needed_unit
        on_hand_quantity = coverage_quantities_by_unit.get(needed_unit)
        if on_hand_quantity is None:
            coverage_display = "Unit mismatch"
            coverage_status = "unknown"
        else:
            delta = on_hand_quantity - needed_quantity
            if delta >= 0:
                coverage_display = f"Can cover, {_format_quantity(delta)} {needed_unit_label} remaining"
                coverage_status = "ok"
            else:
                coverage_display = f"Short by {_format_quantity(abs(delta))} {needed_unit_label}"
                coverage_status = "short"
    return {
        "current_on_hand_display": current_on_hand_display,
        "count_location_count": len(count_rolldown),
        "last_counted_at": last_counted_at,
        "next_usage_display": next_usage["service_date_display"] if next_usage else "",
        "next_needed_display": next_usage.get("needed_display", "") if next_usage else "",
        "conversion_note": conversion_note,
        "coverage_display": coverage_display,
        "coverage_status": coverage_status,
        "upcoming_count": usage["upcoming_count"],
        "past_count": usage["past_count"],
        "total_usage_count": usage["upcoming_count"] + usage["past_count"],
    }


def get_inventory_item_detail(item_id: int, *, temporary_each_bridge: dict | None = None) -> dict | None:
    usage = get_inventory_item_usage(item_id, temporary_each_bridge=temporary_each_bridge)
    if not usage["item"]["item_name"]:
        return None
    count_rolldown = get_inventory_item_count_rolldown(item_id)
    return {
        **usage,
        "count_rolldown": count_rolldown,
        "summary": _build_inventory_item_summary(usage=usage, count_rolldown=count_rolldown),
    }


def _inventory_planning_item_ids() -> list[int]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT ili.item_id
            FROM inventory_location_item ili
            JOIN inventory_location il
              ON il.inventory_location_id = ili.inventory_location_id
            JOIN item i
              ON i.item_id = ili.item_id
            WHERE il.status = 'active'
              AND i.status = 'live'
              AND i.item_type = 'base_food'
            ORDER BY i.item_name ASC, i.item_id ASC
            """
        )
        return [int(row[0]) for row in cursor.fetchall()]


def get_inventory_reorder_plan(*, today: date | None = None, limit: int | None = None) -> dict:
    """
    Build first-pass shortage/reorder facts from counted inventory and upcoming menu need.

    This intentionally returns calculated need/coverage only. Rounded purchasing
    suggestions belong to a later inventory purchasing slice.
    """
    rows = []
    status_sort = {"short": 0, "unknown": 1, "ok": 2, "none": 3}
    for item_id in _inventory_planning_item_ids():
        usage = get_inventory_item_usage(item_id, today=today)
        if not usage["upcoming"]:
            continue
        count_rolldown = get_inventory_item_count_rolldown(item_id)
        summary = _build_inventory_item_summary(usage=usage, count_rolldown=count_rolldown)
        next_usage = usage["upcoming"][0]
        rows.append(
            {
                "item_id": item_id,
                "item_name": usage["item"]["item_name"],
                "item_category_label": usage["item"]["item_category_label"],
                "current_on_hand_display": summary["current_on_hand_display"],
                "next_service_date": next_usage.get("service_date", ""),
                "next_usage_display": summary["next_usage_display"],
                "next_needed_display": summary["next_needed_display"],
                "coverage_display": summary["coverage_display"],
                "coverage_status": summary["coverage_status"],
                "upcoming_count": usage["upcoming_count"],
                "next_menu_name": next_usage.get("menu_name", ""),
                "next_menu_item_name": next_usage.get("menu_item_name", ""),
                "needed_conversion_issue": next_usage.get("needed_conversion_issue"),
                "service_context": {
                    "menu_id": next_usage["menu_id"],
                    "week_number": next_usage["week_number"],
                    "day_of_week": next_usage["day_of_week"],
                },
            }
        )

    rows.sort(
        key=lambda row: (
            status_sort.get(row["coverage_status"], 99),
            row["next_service_date"] or "9999-99-99",
            row["item_name"].lower(),
        )
    )
    totals = {
        "planning_item_count": len(rows),
        "short_count": len([row for row in rows if row["coverage_status"] == "short"]),
        "unknown_count": len([row for row in rows if row["coverage_status"] == "unknown"]),
        "ok_count": len([row for row in rows if row["coverage_status"] == "ok"]),
    }
    if limit is not None:
        rows = rows[:limit]
    return {
        "rows": rows,
        "totals": totals,
        "contract_version": "inventory.reorder_plan.v1",
    }
