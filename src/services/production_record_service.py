import json
import ast
import operator
import re

from db import get_connection, initialize_database
from services.menu_forecast_service import build_forecast_display_unit_options
from services.unit_conversion_service import convert_with_item_mass_volume_bridge, normalize_unit_symbol
from services.unit_label_service import format_unit_label


FORMULA_ALLOWED_PATTERN = re.compile(r"^[0-9+\-*/().\s]+$")
FORMULA_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


PRODUCTION_RECORD_REASON_OPTIONS = [
    {"value": "extra_guests", "label": "Extra Guests"},
    {"value": "unexpected_low_attendance", "label": "Unexpected Low Attendance"},
    {"value": "field_trip", "label": "Field Trip"},
    {"value": "menu_mix", "label": "Menu Mix"},
    {"value": "sports_team_away", "label": "Sports Team Away"},
    {"value": "weather", "label": "Weather"},
    {"value": "other", "label": "Other"},
    {"value": "as_expected", "label": "As Expected"},
    {"value": "par_item", "label": "Par Item"},
]
PRODUCTION_RECORD_REASON_VALUES = {
    option["value"]
    for option in PRODUCTION_RECORD_REASON_OPTIONS
}
PRODUCTION_RECORD_REASON_LABELS = {
    option["value"]: option["label"]
    for option in PRODUCTION_RECORD_REASON_OPTIONS
}
PRODUCTION_RECORD_STATUS_LABELS = {
    "draft": "Draft",
    "posted": "Posted",
}
PRODUCTION_RECORD_HISTORY_CYCLE_WEEKS = 4
PRODUCTION_RECORD_HISTORY_FILTER_DEFAULTS = {
    "view": "records",
    "status": "",
    "accuracy": "",
    "reason_code": "",
    "item_query": "",
    "week": "",
    "day": "",
    "date_from": "",
    "date_to": "",
    "reason_sort": "lines",
    "reason_dir": "desc",
    "variance_sort": "total",
    "variance_dir": "desc",
}


class InvalidProductionRecordError(ValueError):
    """Raised when production record data is invalid."""


def _coerce_optional_float(value, label: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        raise InvalidProductionRecordError(f"{label} must be a valid number.")
    return normalized


def _is_recordable_summary_row(row: dict) -> bool:
    return bool(str(row.get("total_forecast_unit") or "").strip())


def _evaluate_formula_node(node):
    if isinstance(node, ast.Expression):
        return _evaluate_formula_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in FORMULA_OPERATORS:
        left = _evaluate_formula_node(node.left)
        right = _evaluate_formula_node(node.right)
        if isinstance(node.op, ast.Div) and right == 0:
            raise InvalidProductionRecordError("Quantity formula cannot divide by zero.")
        return FORMULA_OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in FORMULA_OPERATORS:
        return FORMULA_OPERATORS[type(node.op)](_evaluate_formula_node(node.operand))
    raise InvalidProductionRecordError("Quantity formula can only use numbers and + - * / ().")


def _is_incomplete_formula(value: str) -> bool:
    stripped = value.rstrip()
    if stripped in {"-", "+", "."}:
        return True
    if stripped.endswith(("+", "-", "*", "/", ".")):
        return True
    return stripped.count("(") > stripped.count(")")


def _normalize_quantity_input(value, label: str) -> tuple[float | None, str | None]:
    cleaned = str(value or "").strip()
    if not cleaned:
        return None, None
    if not FORMULA_ALLOWED_PATTERN.fullmatch(cleaned):
        raise InvalidProductionRecordError(f"{label} formula can only use numbers and + - * / ().")
    if _is_incomplete_formula(cleaned):
        return None, cleaned

    try:
        return float(cleaned), None
    except ValueError:
        pass

    try:
        expression = ast.parse(cleaned, mode="eval")
        result = float(_evaluate_formula_node(expression))
    except InvalidProductionRecordError:
        raise
    except SyntaxError:
        if _is_incomplete_formula(cleaned):
            return None, cleaned
        raise InvalidProductionRecordError(f"{label} formula is incomplete or invalid.")
    except Exception:
        raise InvalidProductionRecordError(f"{label} formula is incomplete or invalid.")

    return result, cleaned


def _format_quantity(value: float | None) -> str:
    if value is None:
        return ""
    rounded_quantity = round(float(value), 3)
    if rounded_quantity == 0:
        return "0"
    return f"{rounded_quantity:g}"


def _get_menu_owner(cursor, menu_id: int) -> str:
    cursor.execute(
        """
        SELECT author_user_id
        FROM menu
        WHERE menu_id = ?
        """,
        (menu_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise InvalidProductionRecordError("Menu not found.")
    return str(row[0])


def _ensure_menu_can_update(cursor, *, menu_id: int, actor_user_id: str) -> None:
    if _get_menu_owner(cursor, menu_id) != actor_user_id:
        raise InvalidProductionRecordError("You can only update production records for menus you created.")


def _forecast_accuracy_level(forecast_error_percent: float | None) -> str | None:
    if forecast_error_percent is None:
        return None
    absolute_percent = abs(float(forecast_error_percent))
    if absolute_percent < 5:
        return "accurate"
    if absolute_percent < 15:
        return "review"
    return "miss"


def _normalize_reason_code(value) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    if normalized not in PRODUCTION_RECORD_REASON_VALUES:
        raise InvalidProductionRecordError("Select a valid production record reason.")
    return normalized


def _build_line_payload(row) -> dict:
    slot_labels = json.loads(row[5] or "[]")
    forecast_quantity = float(row[6] or 0)
    actual_quantity = row[8]
    end_service_variance_quantity = row[14]
    implied_demand_quantity = row[16]
    forecast_error_quantity = row[18]
    forecast_error_percent = row[20]
    return {
        "production_record_line_id": int(row[0]),
        "item_id": int(row[2]),
        "recipe_name": row[3],
        "assignment_count": int(row[4] or 0),
        "slot_labels": slot_labels,
        "forecast_quantity": forecast_quantity,
        "forecast_quantity_display": _format_quantity(forecast_quantity),
        "forecast_unit": row[7],
        "actual_quantity": actual_quantity,
        "actual_quantity_display": _format_quantity(actual_quantity),
        "actual_quantity_formula": row[25] or "",
        "actual_unit": row[9] or row[7],
        "end_service_variance_quantity": end_service_variance_quantity,
        "end_service_variance_quantity_display": _format_quantity(end_service_variance_quantity),
        "end_service_variance_quantity_formula": row[26] or "",
        "end_service_variance_unit": row[15] or row[7],
        "implied_demand_quantity": implied_demand_quantity,
        "implied_demand_quantity_display": _format_quantity(implied_demand_quantity),
        "implied_demand_unit": row[17] or row[7],
        "implied_demand_unit_label": format_unit_label(row[17] or row[7]),
        "forecast_error_quantity": forecast_error_quantity,
        "forecast_error_quantity_display": _format_quantity(forecast_error_quantity),
        "forecast_error_unit": row[19] or row[7],
        "forecast_error_unit_label": format_unit_label(row[19] or row[7]),
        "forecast_error_percent": forecast_error_percent,
        "forecast_error_percent_display": _format_quantity(forecast_error_percent),
        "forecast_accuracy_level": row[21] or "",
        "reason_code": row[22] or "",
        "reason_label": PRODUCTION_RECORD_REASON_LABELS.get(row[22], ""),
        "reason_note": row[23] or "",
        "notes": row[24] or "",
    }


def _build_record_summary(lines: list[dict]) -> dict:
    summary = {
        "total": len(lines),
        "recorded": 0,
        "unrecorded": 0,
        "accurate": 0,
        "review": 0,
        "miss": 0,
    }
    for line in lines:
        is_recorded = (
            line.get("actual_quantity") is not None
            and line.get("end_service_variance_quantity") is not None
        )
        if not is_recorded:
            summary["unrecorded"] += 1
            continue

        summary["recorded"] += 1
        accuracy_level = line.get("forecast_accuracy_level")
        if accuracy_level in {"accurate", "review", "miss"}:
            summary[accuracy_level] += 1

    return summary


def _is_recorded_line(line: dict) -> bool:
    return (
        line.get("actual_quantity") is not None
        and line.get("end_service_variance_quantity") is not None
    )


def _normalize_history_filters(filters: dict | None) -> dict:
    normalized = dict(PRODUCTION_RECORD_HISTORY_FILTER_DEFAULTS)
    for key in normalized:
        normalized[key] = str((filters or {}).get(key, "") or "").strip()

    if normalized["view"] not in {"records", "items"}:
        normalized["view"] = "records"
    if normalized["status"] not in {"", "draft", "posted"}:
        normalized["status"] = ""
    if normalized["accuracy"] not in {"", "accurate", "review", "miss", "unrecorded"}:
        normalized["accuracy"] = ""
    if normalized["reason_code"] not in {"", *PRODUCTION_RECORD_REASON_VALUES}:
        normalized["reason_code"] = ""
    if normalized["reason_sort"] not in {"lines"}:
        normalized["reason_sort"] = "lines"
    if normalized["reason_dir"] not in {"asc", "desc"}:
        normalized["reason_dir"] = "desc"
    if normalized["variance_sort"] not in {"total", "leftover", "shortage"}:
        normalized["variance_sort"] = "total"
    if normalized["variance_dir"] not in {"asc", "desc"}:
        normalized["variance_dir"] = "desc"
    if normalized["day"] not in {"", "sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"}:
        normalized["day"] = ""
    try:
        if normalized["week"]:
            normalized["week"] = str(max(1, int(normalized["week"])))
    except ValueError:
        normalized["week"] = ""

    return normalized


def _apply_item_trend_default_dates(
    filters: dict,
    *,
    default_date_from: str = "",
    default_date_to: str = "",
) -> dict:
    normalized = dict(filters)
    if not normalized["date_from"] and default_date_from:
        normalized["date_from"] = str(default_date_from)
    if not normalized["date_to"] and default_date_to:
        normalized["date_to"] = str(default_date_to)
    return normalized


def _line_matches_history_filters(line: dict, filters: dict) -> bool:
    if filters["accuracy"]:
        is_recorded = (
            line.get("actual_quantity") is not None
            and line.get("end_service_variance_quantity") is not None
        )
        if filters["accuracy"] == "unrecorded":
            if is_recorded:
                return False
        elif line.get("forecast_accuracy_level") != filters["accuracy"]:
            return False

    if filters["reason_code"] and line.get("reason_code") != filters["reason_code"]:
        return False

    if filters["item_query"]:
        item_query = filters["item_query"].casefold()
        if item_query not in str(line.get("recipe_name") or "").casefold():
            return False

    return True


def _record_matches_history_filters(record: dict, filters: dict) -> bool:
    if filters["status"] and record["status"] != filters["status"]:
        return False
    if filters["week"] and str(record["week_number"]) != filters["week"]:
        return False
    if filters["day"] and record["day_of_week"] != filters["day"]:
        return False

    service_date = record.get("service_date", {}).get("date", "")
    if filters["date_from"] and service_date and service_date < filters["date_from"]:
        return False
    if filters["date_to"] and service_date and service_date > filters["date_to"]:
        return False

    return True


def _build_history_totals(records: list[dict]) -> dict:
    totals = {
        "total_records": len(records),
        "draft": 0,
        "posted": 0,
        "total_lines": 0,
        "recorded": 0,
        "unrecorded": 0,
        "accurate": 0,
        "review": 0,
        "miss": 0,
    }
    for record in records:
        if record["status"] in {"draft", "posted"}:
            totals[record["status"]] += 1
        for key in ("total", "recorded", "unrecorded", "accurate", "review", "miss"):
            totals["total_lines" if key == "total" else key] += record["summary"][key]
    return totals


def _build_item_trend_totals(groups: list[dict]) -> dict:
    totals = {
        "group_count": len(groups),
        "occurrence_count": 0,
        "recorded": 0,
        "unrecorded": 0,
        "accurate": 0,
        "review": 0,
        "miss": 0,
    }
    for group in groups:
        totals["occurrence_count"] += group["occurrence_count"]
        totals["recorded"] += group["recorded"]
        totals["unrecorded"] += group["unrecorded"]
        totals["accurate"] += group["accurate"]
        totals["review"] += group["review"]
        totals["miss"] += group["miss"]
    return totals


def _history_cycle_day_sort(day_of_week: str) -> int:
    return {
        "sunday": 0,
        "monday": 1,
        "tuesday": 2,
        "wednesday": 3,
        "thursday": 4,
        "friday": 5,
        "saturday": 6,
    }.get(day_of_week, 7)


def _build_cycle_day_groups(rows: list[dict]) -> list[dict]:
    groups_by_cycle_day: dict[tuple[int, str], dict] = {}
    for row in rows:
        cycle_week = ((int(row["week_number"]) - 1) % PRODUCTION_RECORD_HISTORY_CYCLE_WEEKS) + 1
        cycle_day_key = (cycle_week, row["day_of_week"])
        group = groups_by_cycle_day.setdefault(
            cycle_day_key,
            {
                "cycle_week": cycle_week,
                "day_of_week": row["day_of_week"],
                "day_label": row["day_label"],
                "label": f"Cycle Week {cycle_week} {row['day_label']}",
                "rows": [],
            },
        )
        group["rows"].append(row)

    return sorted(
        groups_by_cycle_day.values(),
        key=lambda group: (
            group["cycle_week"],
            _history_cycle_day_sort(group["day_of_week"]),
        ),
    )


def _finalize_item_trend_groups(groups_by_item: dict[int, dict]) -> list[dict]:
    groups = []
    for group in groups_by_item.values():
        error_values = group.pop("_forecast_error_values")
        group["occurrence_count"] = len(group["rows"])
        group["average_forecast_error_percent"] = (
            sum(error_values) / len(error_values)
            if error_values
            else None
        )
        group["average_forecast_error_percent_display"] = _format_quantity(
            group["average_forecast_error_percent"]
        )
        group["cycle_day_groups"] = _build_cycle_day_groups(group["rows"])
        groups.append(group)

    return sorted(groups, key=lambda row: (row["recipe_name"].casefold(), row["item_id"]))


def _build_history_report(records: list[dict], filters: dict | None = None) -> dict:
    normalized_filters = filters or dict(PRODUCTION_RECORD_HISTORY_FILTER_DEFAULTS)
    reason_counts: dict[str, dict] = {}
    variance_by_item: dict[tuple[int, str], dict] = {}
    for record in records:
        for line in record.get("lines", []):
            if line.get("reason_code"):
                reason = reason_counts.setdefault(
                    line["reason_code"],
                    {
                        "reason_code": line["reason_code"],
                        "reason_label": line["reason_label"],
                        "count": 0,
                    },
                )
                reason["count"] += 1

            variance_quantity = line.get("end_service_variance_quantity")
            if variance_quantity is None:
                continue
            variance_unit = line.get("end_service_variance_unit") or line.get("forecast_unit")
            variance_key = (line["item_id"], variance_unit)
            item_total = variance_by_item.setdefault(
                variance_key,
                {
                    "item_id": line["item_id"],
                    "recipe_name": line["recipe_name"],
                    "unit": variance_unit,
                    "leftover_quantity": 0.0,
                    "shortage_quantity": 0.0,
                    "leftover_occurrences": [],
                    "shortage_occurrences": [],
                },
            )
            signed_variance_quantity = float(variance_quantity)
            occurrence = {
                "production_record_id": record["production_record_id"],
                "week_number": record["week_number"],
                "day_of_week": record["day_of_week"],
                "day_label": record["day_label"],
                "status_label": record["status_label"],
                "service_date_display": record.get("service_date_display") or f"Week {record['week_number']} {record['day_label']}",
                "quantity": abs(signed_variance_quantity),
                "quantity_display": _format_quantity(abs(signed_variance_quantity)),
                "unit": variance_unit,
                "forecast_quantity_display": line.get("forecast_quantity_display", ""),
                "forecast_unit": line.get("forecast_unit", ""),
                "actual_quantity_display": line.get("actual_quantity_display", ""),
                "actual_unit": line.get("actual_unit", ""),
                "forecast_accuracy_level": line.get("forecast_accuracy_level", ""),
                "forecast_error_percent_display": line.get("forecast_error_percent_display", ""),
                "reason_label": line.get("reason_label", ""),
                "has_notes": bool(line.get("reason_note") or line.get("notes")),
            }
            if signed_variance_quantity >= 0:
                item_total["leftover_quantity"] += signed_variance_quantity
                item_total["leftover_occurrences"].append(occurrence)
            else:
                item_total["shortage_quantity"] += abs(signed_variance_quantity)
                item_total["shortage_occurrences"].append(occurrence)

    reason_reverse = normalized_filters["reason_dir"] == "desc"
    reason_rows = sorted(
        reason_counts.values(),
        key=lambda row: (
            -row["count"] if reason_reverse else row["count"],
            row["reason_label"],
        ),
    )

    variance_sort = normalized_filters["variance_sort"]
    variance_reverse = normalized_filters["variance_dir"] == "desc"

    def variance_sort_value(row: dict) -> float:
        if variance_sort == "leftover":
            return float(row["leftover_quantity"])
        if variance_sort == "shortage":
            return float(row["shortage_quantity"])
        return float(row["leftover_quantity"]) + float(row["shortage_quantity"])

    variance_rows = sorted(
        variance_by_item.values(),
        key=lambda row: (
            -variance_sort_value(row) if variance_reverse else variance_sort_value(row),
            row["recipe_name"],
            row["unit"],
        ),
    )
    for row in variance_rows:
        row["leftover_quantity_display"] = _format_quantity(row["leftover_quantity"])
        row["shortage_quantity_display"] = _format_quantity(row["shortage_quantity"])
        row["leftover_occurrence_count"] = len(row["leftover_occurrences"])
        row["shortage_occurrence_count"] = len(row["shortage_occurrences"])

    return {
        "top_reason_codes": reason_rows,
        "variance_by_item": variance_rows,
    }


def _build_posted_production_fact(*, record: dict, line: dict) -> dict:
    variance_quantity = line.get("end_service_variance_quantity")
    leftover_quantity = None
    shortage_quantity = None
    if variance_quantity is not None:
        if float(variance_quantity) >= 0:
            leftover_quantity = float(variance_quantity)
            shortage_quantity = 0.0
        else:
            leftover_quantity = 0.0
            shortage_quantity = abs(float(variance_quantity))

    return {
        "source": "production_record_line",
        "source_status": "posted",
        "production_record_id": record["production_record_id"],
        "production_record_line_id": line["production_record_line_id"],
        "menu_id": record["menu_id"],
        "service_date": record.get("service_date", {}).get("date", ""),
        "service_date_display": record.get("service_date", {}).get("display", ""),
        "week_number": record["week_number"],
        "day_of_week": record["day_of_week"],
        "item_id": line["item_id"],
        "item_name": line["recipe_name"],
        "assignment_count": line["assignment_count"],
        "slot_labels": line["slot_labels"],
        "forecast_quantity": line["forecast_quantity"],
        "forecast_unit": line["forecast_unit"],
        "actual_production_quantity": line["actual_quantity"],
        "actual_production_unit": line["actual_unit"],
        "end_service_variance_quantity": variance_quantity,
        "end_service_variance_unit": line["end_service_variance_unit"],
        "leftover_quantity": leftover_quantity,
        "leftover_unit": line["end_service_variance_unit"],
        "shortage_quantity": shortage_quantity,
        "shortage_unit": line["end_service_variance_unit"],
        "implied_demand_quantity": line["implied_demand_quantity"],
        "implied_demand_unit": line["implied_demand_unit"],
        "forecast_error_quantity": line["forecast_error_quantity"],
        "forecast_error_unit": line["forecast_error_unit"],
        "forecast_error_percent": line["forecast_error_percent"],
        "forecast_accuracy_level": line["forecast_accuracy_level"],
        "reason_code": line["reason_code"],
        "reason_label": line["reason_label"],
        "has_reason_note": bool(line["reason_note"]),
        "has_line_notes": bool(line["notes"]),
        "record_updated_at": record["updated_at"],
    }


def get_posted_production_facts_for_menu(
    *,
    menu_id: int,
    actor_user_id: str,
    service_date_lookup: dict | None = None,
) -> dict:
    history = list_production_records_for_menu(
        menu_id=menu_id,
        actor_user_id=actor_user_id,
        service_date_lookup=service_date_lookup,
        filters={"status": "posted"},
    )
    facts = []
    for record in history["records"]:
        record_with_menu = {**record, "menu_id": menu_id}
        for line in record["lines"]:
            facts.append(_build_posted_production_fact(record=record_with_menu, line=line))

    return {
        "contract_version": "production_record.posted_facts.v1",
        "source": "posted_production_records",
        "menu_id": menu_id,
        "facts": facts,
        "summary": {
            "record_count": history["totals"]["posted"],
            "line_count": len(facts),
            "accurate": history["totals"]["accurate"],
            "review": history["totals"]["review"],
            "miss": history["totals"]["miss"],
        },
    }


def ensure_production_record(
    *,
    menu_id: int,
    week_number: int,
    day_of_week: str,
    production_summary: dict,
    actor_user_id: str,
) -> dict:
    initialize_database()

    with get_connection() as conn:
        cursor = conn.cursor()
        _ensure_menu_can_update(cursor, menu_id=menu_id, actor_user_id=actor_user_id)
        cursor.execute(
            """
            INSERT INTO production_record (
                menu_id,
                week_number,
                day_of_week,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, 'draft', datetime('now'), datetime('now'))
            ON CONFLICT(menu_id, week_number, day_of_week) DO UPDATE SET
                updated_at = production_record.updated_at
            """,
            (menu_id, week_number, day_of_week),
        )
        cursor.execute(
            """
            SELECT production_record_id, status, created_at, updated_at
            FROM production_record
            WHERE menu_id = ?
              AND week_number = ?
              AND day_of_week = ?
            """,
            (menu_id, week_number, day_of_week),
        )
        record_row = cursor.fetchone()
        production_record_id = int(record_row[0])

        recordable_summary_rows = [
            summary_row
            for summary_row in production_summary.get("rows", [])
            if _is_recordable_summary_row(summary_row)
        ]
        for summary_row in recordable_summary_rows:
            cursor.execute(
                """
                INSERT INTO production_record_line (
                    production_record_id,
                    item_id,
                    recipe_name,
                    assignment_count,
                    slot_labels_json,
                    forecast_quantity,
                    forecast_unit,
                    variance_unit,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(production_record_id, item_id) DO UPDATE SET
                    recipe_name = excluded.recipe_name,
                    assignment_count = excluded.assignment_count,
                    slot_labels_json = excluded.slot_labels_json,
                    forecast_quantity = excluded.forecast_quantity,
                    forecast_unit = excluded.forecast_unit,
                    variance_unit = excluded.variance_unit,
                    updated_at = datetime('now')
                """,
                (
                    production_record_id,
                    summary_row["item_id"],
                    summary_row["recipe_name"],
                    summary_row["assignment_count"],
                    json.dumps(summary_row.get("slot_labels", [])),
                    summary_row["total_forecast_quantity"],
                    summary_row["total_forecast_unit"],
                    summary_row["total_forecast_unit"],
                ),
            )

        summary_item_ids = [int(row["item_id"]) for row in recordable_summary_rows]
        if summary_item_ids:
            cursor.execute(
                """
                DELETE FROM production_record_line
                WHERE production_record_id = ?
                  AND item_id NOT IN ({})
                """.format(", ".join("?" for _ in summary_item_ids)),
                [production_record_id, *summary_item_ids],
            )
        else:
            cursor.execute(
                "DELETE FROM production_record_line WHERE production_record_id = ?",
                (production_record_id,),
            )

        cursor.execute(
            """
            SELECT
                production_record_line_id,
                production_record_id,
                item_id,
                recipe_name,
                assignment_count,
                slot_labels_json,
                forecast_quantity,
                forecast_unit,
                actual_quantity,
                actual_unit,
                variance_quantity,
                variance_unit,
                variance_percent,
                variance_level,
                end_service_variance_quantity,
                end_service_variance_unit,
                implied_demand_quantity,
                implied_demand_unit,
                forecast_error_quantity,
                forecast_error_unit,
                forecast_error_percent,
                forecast_accuracy_level,
                reason_code,
                reason_note,
                notes,
                actual_quantity_formula,
                end_service_variance_quantity_formula
            FROM production_record_line
            WHERE production_record_id = ?
            ORDER BY production_record_line_id ASC
            """,
            (production_record_id,),
        )
        lines = [_build_line_payload(row) for row in cursor.fetchall()]
        conn.commit()

        return {
            "production_record_id": production_record_id,
            "status": record_row[1],
            "status_label": PRODUCTION_RECORD_STATUS_LABELS.get(record_row[1], str(record_row[1]).title()),
            "is_posted": record_row[1] == "posted",
            "created_at": record_row[2],
            "updated_at": record_row[3],
            "summary": _build_record_summary(lines),
            "lines": lines,
        }


def save_production_record_line(
    *,
    menu_id: int,
    production_record_line_id: int,
    actor_user_id: str,
    actual_quantity,
    actual_unit,
    end_service_variance_quantity=None,
    end_service_variance_unit=None,
    reason_code=None,
    reason_note=None,
    notes=None,
) -> dict:
    initialize_database()

    with get_connection() as conn:
        cursor = conn.cursor()
        _ensure_menu_can_update(cursor, menu_id=menu_id, actor_user_id=actor_user_id)
        cursor.execute(
            """
            SELECT
                prl.production_record_line_id,
                prl.production_record_id,
                prl.item_id,
                prl.recipe_name,
                prl.assignment_count,
                prl.slot_labels_json,
                prl.forecast_quantity,
                prl.forecast_unit,
                prl.actual_quantity,
                prl.actual_unit,
                prl.variance_quantity,
                prl.variance_unit,
                prl.variance_percent,
                prl.variance_level,
                prl.end_service_variance_quantity,
                prl.end_service_variance_unit,
                prl.implied_demand_quantity,
                prl.implied_demand_unit,
                prl.forecast_error_quantity,
                prl.forecast_error_unit,
                prl.forecast_error_percent,
                prl.forecast_accuracy_level,
                prl.reason_code,
                prl.reason_note,
                prl.notes,
                i.item_type,
                i.mass_quantity,
                i.mass_unit,
                i.volume_quantity,
                i.volume_unit,
                pr.status,
                prl.actual_quantity_formula,
                prl.end_service_variance_quantity_formula
            FROM production_record_line prl
            JOIN production_record pr
              ON pr.production_record_id = prl.production_record_id
            JOIN item i
              ON i.item_id = prl.item_id
            WHERE pr.menu_id = ?
              AND prl.production_record_line_id = ?
            """,
            (menu_id, production_record_line_id),
        )
        row = cursor.fetchone()
        if row is None:
            raise InvalidProductionRecordError("Production record line not found.")
        if row[30] == "posted":
            raise InvalidProductionRecordError("Posted production records cannot be edited.")

        normalized_actual_quantity, normalized_actual_formula = _normalize_quantity_input(actual_quantity, "Actual production")
        if normalized_actual_quantity is not None and normalized_actual_quantity < 0:
            raise InvalidProductionRecordError("Actual production cannot be negative.")
        normalized_actual_unit = normalize_unit_symbol(actual_unit or row[7])
        if normalized_actual_quantity is not None and not normalized_actual_unit:
            raise InvalidProductionRecordError("Select an actual production unit.")

        normalized_end_service_variance_quantity, normalized_variance_formula = _normalize_quantity_input(
            end_service_variance_quantity,
            "End of service variance",
        )
        normalized_end_service_variance_unit = normalize_unit_symbol(end_service_variance_unit or row[7])
        if normalized_end_service_variance_quantity is not None and not normalized_end_service_variance_unit:
            raise InvalidProductionRecordError("Select an end of service variance unit.")

        normalized_reason_code = _normalize_reason_code(reason_code)
        normalized_reason_note = str(reason_note or "").strip() if normalized_reason_code == "other" else None
        normalized_notes = row[24] if notes is None else str(notes or "").strip() or None

        implied_demand_quantity = None
        forecast_error_quantity = None
        forecast_error_percent = None
        forecast_accuracy_level = None
        calculation_unit = row[7]
        if normalized_actual_quantity is not None:
            actual_conversion = convert_with_item_mass_volume_bridge(
                quantity=normalized_actual_quantity,
                from_unit=normalized_actual_unit,
                to_unit=row[7],
                item_type=row[25],
                mass_quantity=row[26],
                mass_unit=row[27],
                volume_quantity=row[28],
                volume_unit=row[29],
            )
            if not actual_conversion["ok"]:
                raise InvalidProductionRecordError("Actual production unit cannot convert to the forecast unit.")
            actual_in_forecast_unit = float(actual_conversion["quantity"])
            variance_in_forecast_unit = 0.0
            if normalized_end_service_variance_quantity is not None:
                variance_conversion = convert_with_item_mass_volume_bridge(
                    quantity=normalized_end_service_variance_quantity,
                    from_unit=normalized_end_service_variance_unit,
                    to_unit=row[7],
                    item_type=row[25],
                    mass_quantity=row[26],
                    mass_unit=row[27],
                    volume_quantity=row[28],
                    volume_unit=row[29],
                )
                if not variance_conversion["ok"]:
                    raise InvalidProductionRecordError("End of service variance unit cannot convert to the forecast unit.")
                variance_in_forecast_unit = float(variance_conversion["quantity"])

            implied_demand_quantity = actual_in_forecast_unit - variance_in_forecast_unit
            forecast_error_quantity = float(row[6]) - implied_demand_quantity
            forecast_error_percent = (
                forecast_error_quantity / float(row[6]) * 100
                if float(row[6]) > 0
                else None
            )
            forecast_accuracy_level = _forecast_accuracy_level(forecast_error_percent)

        cursor.execute(
            """
            UPDATE production_record_line
            SET actual_quantity = ?,
                actual_quantity_formula = ?,
                actual_unit = ?,
                end_service_variance_quantity = ?,
                end_service_variance_quantity_formula = ?,
                end_service_variance_unit = ?,
                implied_demand_quantity = ?,
                implied_demand_unit = ?,
                forecast_error_quantity = ?,
                forecast_error_unit = ?,
                forecast_error_percent = ?,
                forecast_accuracy_level = ?,
                reason_code = ?,
                reason_note = ?,
                notes = ?,
                updated_at = datetime('now')
            WHERE production_record_line_id = ?
            """,
            (
                normalized_actual_quantity,
                normalized_actual_formula,
                normalized_actual_unit if normalized_actual_quantity is not None else None,
                normalized_end_service_variance_quantity,
                normalized_variance_formula,
                normalized_end_service_variance_unit if normalized_end_service_variance_quantity is not None else None,
                implied_demand_quantity,
                calculation_unit if implied_demand_quantity is not None else None,
                forecast_error_quantity,
                calculation_unit if forecast_error_quantity is not None else None,
                forecast_error_percent,
                forecast_accuracy_level,
                normalized_reason_code,
                normalized_reason_note,
                normalized_notes,
                production_record_line_id,
            ),
        )
        cursor.execute(
            """
            SELECT
                production_record_line_id,
                production_record_id,
                item_id,
                recipe_name,
                assignment_count,
                slot_labels_json,
                forecast_quantity,
                forecast_unit,
                actual_quantity,
                actual_unit,
                variance_quantity,
                variance_unit,
                variance_percent,
                variance_level,
                end_service_variance_quantity,
                end_service_variance_unit,
                implied_demand_quantity,
                implied_demand_unit,
                forecast_error_quantity,
                forecast_error_unit,
                forecast_error_percent,
                forecast_accuracy_level,
                reason_code,
                reason_note,
                notes,
                actual_quantity_formula,
                end_service_variance_quantity_formula
            FROM production_record_line
            WHERE production_record_line_id = ?
            """,
            (production_record_line_id,),
        )
        updated_row = cursor.fetchone()
        conn.commit()

    return _build_line_payload(updated_row)


def post_production_record(
    *,
    menu_id: int,
    production_record_id: int,
    actor_user_id: str,
) -> dict:
    initialize_database()

    with get_connection() as conn:
        cursor = conn.cursor()
        _ensure_menu_can_update(cursor, menu_id=menu_id, actor_user_id=actor_user_id)
        cursor.execute(
            """
            SELECT production_record_id, status
            FROM production_record
            WHERE menu_id = ?
              AND production_record_id = ?
            """,
            (menu_id, production_record_id),
        )
        record_row = cursor.fetchone()
        if record_row is None:
            raise InvalidProductionRecordError("Production record not found.")
        if record_row[1] == "posted":
            raise InvalidProductionRecordError("Production record is already posted.")

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM production_record_line
            WHERE production_record_id = ?
              AND (
                actual_quantity IS NULL
                OR end_service_variance_quantity IS NULL
              )
            """,
            (production_record_id,),
        )
        unrecorded_count = int(cursor.fetchone()[0])
        if unrecorded_count:
            raise InvalidProductionRecordError("Record every production line before posting.")

        cursor.execute(
            """
            UPDATE production_record
            SET status = 'posted',
                updated_at = datetime('now')
            WHERE production_record_id = ?
            """,
            (production_record_id,),
        )
        conn.commit()

    return {
        "production_record_id": production_record_id,
        "status": "posted",
        "status_label": PRODUCTION_RECORD_STATUS_LABELS["posted"],
        "is_posted": True,
    }


def get_production_record_review(
    *,
    menu_id: int,
    production_record_id: int,
    actor_user_id: str,
) -> dict:
    initialize_database()

    with get_connection() as conn:
        cursor = conn.cursor()
        _ensure_menu_can_update(cursor, menu_id=menu_id, actor_user_id=actor_user_id)
        cursor.execute(
            """
            SELECT
                production_record_id,
                week_number,
                day_of_week,
                status,
                created_at,
                updated_at
            FROM production_record
            WHERE menu_id = ?
              AND production_record_id = ?
            """,
            (menu_id, production_record_id),
        )
        record_row = cursor.fetchone()
        if record_row is None:
            raise InvalidProductionRecordError("Production record not found.")

        cursor.execute(
            """
            SELECT
                production_record_line_id,
                production_record_id,
                item_id,
                recipe_name,
                assignment_count,
                slot_labels_json,
                forecast_quantity,
                forecast_unit,
                actual_quantity,
                actual_unit,
                variance_quantity,
                variance_unit,
                variance_percent,
                variance_level,
                end_service_variance_quantity,
                end_service_variance_unit,
                implied_demand_quantity,
                implied_demand_unit,
                forecast_error_quantity,
                forecast_error_unit,
                forecast_error_percent,
                forecast_accuracy_level,
                reason_code,
                reason_note,
                notes,
                actual_quantity_formula,
                end_service_variance_quantity_formula
            FROM production_record_line
            WHERE production_record_id = ?
            ORDER BY production_record_line_id ASC
            """,
            (production_record_id,),
        )
        lines = [_build_line_payload(row) for row in cursor.fetchall()]

    return {
        "production_record_id": int(record_row[0]),
        "week_number": int(record_row[1]),
        "day_of_week": record_row[2],
        "status": record_row[3],
        "status_label": PRODUCTION_RECORD_STATUS_LABELS.get(record_row[3], str(record_row[3]).title()),
        "is_posted": record_row[3] == "posted",
        "created_at": record_row[4],
        "updated_at": record_row[5],
        "summary": _build_record_summary(lines),
        "lines": lines,
    }


def get_production_record_for_service_day(
    *,
    menu_id: int,
    week_number: int,
    day_of_week: str,
    actor_user_id: str,
) -> dict | None:
    initialize_database()

    with get_connection() as conn:
        cursor = conn.cursor()
        _ensure_menu_can_update(cursor, menu_id=menu_id, actor_user_id=actor_user_id)
        cursor.execute(
            """
            SELECT production_record_id
            FROM production_record
            WHERE menu_id = ?
              AND week_number = ?
              AND day_of_week = ?
            """,
            (menu_id, week_number, day_of_week),
        )
        record_row = cursor.fetchone()
        if record_row is None:
            return None

    return get_production_record_review(
        menu_id=menu_id,
        production_record_id=int(record_row[0]),
        actor_user_id=actor_user_id,
    )


def list_production_records_for_menu(
    *,
    menu_id: int,
    actor_user_id: str,
    service_date_lookup: dict | None = None,
    filters: dict | None = None,
) -> dict:
    initialize_database()
    normalized_filters = _normalize_history_filters(filters)

    with get_connection() as conn:
        cursor = conn.cursor()
        _ensure_menu_can_update(cursor, menu_id=menu_id, actor_user_id=actor_user_id)
        cursor.execute(
            """
            SELECT
                production_record_id,
                week_number,
                day_of_week,
                status,
                created_at,
                updated_at
            FROM production_record
            WHERE menu_id = ?
            ORDER BY week_number ASC,
                     CASE day_of_week
                        WHEN 'sunday' THEN 0
                        WHEN 'monday' THEN 1
                        WHEN 'tuesday' THEN 2
                        WHEN 'wednesday' THEN 3
                        WHEN 'thursday' THEN 4
                        WHEN 'friday' THEN 5
                        WHEN 'saturday' THEN 6
                        ELSE 7
                     END ASC
            """,
            (menu_id,),
        )
        record_rows = cursor.fetchall()

        records = []
        for record_row in record_rows:
            production_record_id = int(record_row[0])
            cursor.execute(
                """
                SELECT
                    production_record_line_id,
                    production_record_id,
                    item_id,
                    recipe_name,
                    assignment_count,
                    slot_labels_json,
                    forecast_quantity,
                    forecast_unit,
                    actual_quantity,
                    actual_unit,
                    variance_quantity,
                    variance_unit,
                    variance_percent,
                    variance_level,
                    end_service_variance_quantity,
                    end_service_variance_unit,
                    implied_demand_quantity,
                    implied_demand_unit,
                    forecast_error_quantity,
                    forecast_error_unit,
                    forecast_error_percent,
                    forecast_accuracy_level,
                    reason_code,
                    reason_note,
                    notes,
                    actual_quantity_formula,
                    end_service_variance_quantity_formula
                FROM production_record_line
                WHERE production_record_id = ?
                ORDER BY production_record_line_id ASC
                """,
                (production_record_id,),
            )
            lines = [_build_line_payload(line_row) for line_row in cursor.fetchall()]
            record_week = int(record_row[1])
            record_day = record_row[2]
            service_date = (service_date_lookup or {}).get(record_week, {}).get(record_day, {})
            record = {
                "production_record_id": production_record_id,
                "week_number": record_week,
                "day_of_week": record_day,
                "day_label": str(record_day).title(),
                "status": record_row[3],
                "status_label": PRODUCTION_RECORD_STATUS_LABELS.get(record_row[3], str(record_row[3]).title()),
                "is_posted": record_row[3] == "posted",
                "created_at": record_row[4],
                "updated_at": record_row[5],
                "service_date": service_date,
                "service_date_display": service_date.get("display", ""),
                "lines": lines,
            }
            if not _record_matches_history_filters(record, normalized_filters):
                continue

            filtered_lines = [
                line
                for line in lines
                if _line_matches_history_filters(line, normalized_filters)
            ]
            has_line_filters = bool(
                normalized_filters["accuracy"]
                or normalized_filters["reason_code"]
                or normalized_filters["item_query"]
            )
            if has_line_filters and not filtered_lines:
                continue

            record["lines"] = filtered_lines
            record["summary"] = _build_record_summary(filtered_lines)
            status = record_row[3]
            record["status_label"] = PRODUCTION_RECORD_STATUS_LABELS.get(status, str(status).title())
            records.append(record)

    return {
        "records": records,
        "totals": _build_history_totals(records),
        "report": _build_history_report(records, normalized_filters),
        "filters": normalized_filters,
    }


def list_production_record_item_trends_for_menu(
    *,
    menu_id: int,
    actor_user_id: str,
    service_date_lookup: dict | None = None,
    filters: dict | None = None,
    default_date_from: str = "",
    default_date_to: str = "",
) -> dict:
    initialize_database()
    normalized_filters = _apply_item_trend_default_dates(
        _normalize_history_filters(filters),
        default_date_from=default_date_from,
        default_date_to=default_date_to,
    )
    normalized_filters["view"] = "items"

    where_clauses = ["pr.menu_id = ?"]
    query_params: list = [menu_id]
    if normalized_filters["status"]:
        where_clauses.append("pr.status = ?")
        query_params.append(normalized_filters["status"])
    if normalized_filters["week"]:
        where_clauses.append("pr.week_number = ?")
        query_params.append(int(normalized_filters["week"]))
    if normalized_filters["day"]:
        where_clauses.append("pr.day_of_week = ?")
        query_params.append(normalized_filters["day"])

    with get_connection() as conn:
        cursor = conn.cursor()
        _ensure_menu_can_update(cursor, menu_id=menu_id, actor_user_id=actor_user_id)
        cursor.execute(
            f"""
            SELECT
                pr.production_record_id,
                pr.week_number,
                pr.day_of_week,
                pr.status,
                pr.updated_at,
                prl.production_record_line_id,
                prl.production_record_id,
                prl.item_id,
                prl.recipe_name,
                prl.assignment_count,
                prl.slot_labels_json,
                prl.forecast_quantity,
                prl.forecast_unit,
                prl.actual_quantity,
                prl.actual_unit,
                prl.variance_quantity,
                prl.variance_unit,
                prl.variance_percent,
                prl.variance_level,
                prl.end_service_variance_quantity,
                prl.end_service_variance_unit,
                prl.implied_demand_quantity,
                prl.implied_demand_unit,
                prl.forecast_error_quantity,
                prl.forecast_error_unit,
                prl.forecast_error_percent,
                prl.forecast_accuracy_level,
                prl.reason_code,
                prl.reason_note,
                prl.notes,
                prl.actual_quantity_formula,
                prl.end_service_variance_quantity_formula
            FROM production_record pr
            JOIN production_record_line prl
              ON pr.production_record_id = prl.production_record_id
            WHERE {" AND ".join(where_clauses)}
            ORDER BY pr.week_number ASC,
                     CASE pr.day_of_week
                        WHEN 'sunday' THEN 0
                        WHEN 'monday' THEN 1
                        WHEN 'tuesday' THEN 2
                        WHEN 'wednesday' THEN 3
                        WHEN 'thursday' THEN 4
                        WHEN 'friday' THEN 5
                        WHEN 'saturday' THEN 6
                        ELSE 7
                     END ASC,
                     prl.recipe_name ASC,
                     prl.item_id ASC
            """,
            tuple(query_params),
        )
        rows = cursor.fetchall()

    groups_by_item: dict[int, dict] = {}
    for row in rows:
        record_week = int(row[1])
        record_day = row[2]
        service_date = (service_date_lookup or {}).get(record_week, {}).get(record_day, {})
        record = {
            "week_number": record_week,
            "day_of_week": record_day,
            "status": row[3],
            "service_date": service_date,
        }
        if not _record_matches_history_filters(record, normalized_filters):
            continue

        line = _build_line_payload(row[5:])
        if not _line_matches_history_filters(line, normalized_filters):
            continue

        item_id = line["item_id"]
        group = groups_by_item.setdefault(
            item_id,
            {
                "item_id": item_id,
                "recipe_name": line["recipe_name"],
                "rows": [],
                "occurrence_count": 0,
                "recorded": 0,
                "unrecorded": 0,
                "accurate": 0,
                "review": 0,
                "miss": 0,
                "_forecast_error_values": [],
            },
        )
        recorded = _is_recorded_line(line)
        accuracy_level = line.get("forecast_accuracy_level")
        if recorded:
            group["recorded"] += 1
            if accuracy_level in {"accurate", "review", "miss"}:
                group[accuracy_level] += 1
        else:
            group["unrecorded"] += 1

        if line.get("forecast_error_percent") is not None:
            group["_forecast_error_values"].append(float(line["forecast_error_percent"]))

        group["rows"].append(
            {
                "production_record_id": int(row[0]),
                "production_record_line_id": line["production_record_line_id"],
                "week_number": record_week,
                "day_of_week": record_day,
                "day_label": str(record_day).title(),
                "status": row[3],
                "status_label": PRODUCTION_RECORD_STATUS_LABELS.get(row[3], str(row[3]).title()),
                "is_posted": row[3] == "posted",
                "updated_at": row[4],
                "service_date": service_date.get("date", ""),
                "service_date_display": service_date.get("display") or f"Week {record_week} {str(record_day).title()}",
                "forecast_quantity_display": line["forecast_quantity_display"],
                "forecast_unit": line["forecast_unit"],
                "actual_quantity_display": line["actual_quantity_display"],
                "actual_unit": line["actual_unit"],
                "implied_demand_quantity_display": line["implied_demand_quantity_display"],
                "implied_demand_unit": line["implied_demand_unit"],
                "forecast_error_quantity_display": line["forecast_error_quantity_display"],
                "forecast_error_unit": line["forecast_error_unit"],
                "forecast_error_percent_display": line["forecast_error_percent_display"],
                "forecast_accuracy_level": accuracy_level or "",
                "reason_label": line.get("reason_label", ""),
                "reason_note": line.get("reason_note", ""),
                "notes": line.get("notes", ""),
                "has_notes": bool(line.get("reason_note", "") or line.get("notes", "")),
                "recorded": recorded,
            }
        )

    groups = _finalize_item_trend_groups(groups_by_item)
    return {
        "groups": groups,
        "totals": _build_item_trend_totals(groups),
        "filters": normalized_filters,
    }


def build_production_record_unit_options(summary_row: dict) -> list[str]:
    return build_forecast_display_unit_options(
        base_unit=summary_row["total_forecast_unit"],
        row={
            "mass_quantity": summary_row.get("mass_quantity"),
            "mass_unit": summary_row.get("mass_unit"),
            "volume_quantity": summary_row.get("volume_quantity"),
            "volume_unit": summary_row.get("volume_unit"),
        },
    )
