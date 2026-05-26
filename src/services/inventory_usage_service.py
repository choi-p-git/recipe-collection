from __future__ import annotations

import json
from datetime import date

from config.item_categories import ITEM_CATEGORY_LABELS
from db import get_connection
from services.inventory_service import _format_location_line_display, _format_quantity
from services.menu_calendar_service import build_week_day_dates
from services.recipe_flattening_service import build_flattened_recipe_view
from services.unit_conversion_service import convert_unit_value, convert_with_item_mass_volume_bridge
from services.unit_label_service import format_unit_label


MAX_DASHBOARD_USAGE_ROWS = 5


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


def _attach_needed_display(item_id: int, usage: dict) -> dict:
    needed_parts = _needed_parts_for_usage(item_id, usage)
    if not needed_parts:
        return {
            **usage,
            "needed_parts": [],
            "needed_display": "",
            "needed_quantity_display": "",
            "needed_unit_label": "",
        }
    display_parts = [
        f"{_format_quantity(part['quantity'])} {format_unit_label(part['unit'])}"
        for part in needed_parts
    ]
    first_part = needed_parts[0]
    return {
        **usage,
        "needed_parts": needed_parts,
        "needed_display": " + ".join(display_parts),
        "needed_quantity_display": _format_quantity(first_part["quantity"]),
        "needed_unit_label": format_unit_label(first_part["unit"]),
    }


def get_inventory_item_usage(item_id: int, *, today: date | None = None, limit: int | None = None) -> dict:
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
    upcoming = []
    past = []
    for row in raw_rows:
        payload = _attach_needed_display(item_id, _usage_payload(row, menu_date_lookup, today_iso))
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
            payloads.append(payload)
        return payloads


def get_inventory_item_detail(item_id: int) -> dict | None:
    usage = get_inventory_item_usage(item_id)
    if not usage["item"]["item_name"]:
        return None
    return {
        **usage,
        "count_rolldown": get_inventory_item_count_rolldown(item_id),
    }
