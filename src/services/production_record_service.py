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
        totals = {
            "total_records": len(record_rows),
            "draft": 0,
            "posted": 0,
            "total_lines": 0,
            "recorded": 0,
            "unrecorded": 0,
            "accurate": 0,
            "review": 0,
            "miss": 0,
        }
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
            summary = _build_record_summary(lines)
            status = record_row[3]
            if status in {"draft", "posted"}:
                totals[status] += 1
            for key in ("total", "recorded", "unrecorded", "accurate", "review", "miss"):
                totals["total_lines" if key == "total" else key] += summary[key]

            records.append(
                {
                    "production_record_id": production_record_id,
                    "week_number": int(record_row[1]),
                    "day_of_week": record_row[2],
                    "day_label": str(record_row[2]).title(),
                    "status": status,
                    "status_label": PRODUCTION_RECORD_STATUS_LABELS.get(status, str(status).title()),
                    "is_posted": status == "posted",
                    "created_at": record_row[4],
                    "updated_at": record_row[5],
                    "summary": summary,
                },
            )

    return {
        "records": records,
        "totals": totals,
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
