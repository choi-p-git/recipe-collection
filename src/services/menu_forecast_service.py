from config.units import APPROVED_UNITS, STANDARD_UNITS
from db import get_connection
from services.recipe_scaling_service import build_bottom_up_scaled_recipe_view
from services.unit_conversion_service import (
    convert_with_item_mass_volume_bridge,
    get_unit_measurement_profile,
    normalize_unit_symbol,
)
from services.unit_display_service import format_display_quantity


class InvalidMenuForecastError(ValueError):
    """Raised when a menu forecast save request is invalid."""


class InvalidMenuForecastBatchError(ValueError):
    """Raised when menu forecast batch split data is invalid."""


MAX_BATCH_SPLITS = 12
BATCH_PERCENT_TOLERANCE = 0.05
CASE_FORECAST_UNIT = "case"
CASE_PACK_MATCH_TOLERANCE = 0.000001


def _normalize_forecast_quantity(value) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        raise InvalidMenuForecastError("Forecast quantity must be a valid number.")

    if normalized < 0:
        raise InvalidMenuForecastError("Forecast quantity cannot be negative.")

    return normalized


def _normalize_batch_percent(value) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        raise InvalidMenuForecastBatchError("Batch percent must be a valid number.")

    if normalized <= 0 or normalized > 100:
        raise InvalidMenuForecastBatchError("Batch percent must be greater than 0 and no more than 100.")

    return normalized


def _normalize_batch_quantity(value) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        raise InvalidMenuForecastBatchError("Batch quantity must be a valid number.")

    if normalized <= 0:
        raise InvalidMenuForecastBatchError("Batch quantity must be greater than 0.")

    return normalized


def _normalize_optional_planned_time(value) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _get_forecast_assignment_context(cursor, *, menu_id: int, menu_slot_item_id: int) -> dict:
    cursor.execute(
        """
        SELECT
            m.author_user_id,
            i.item_id,
            i.item_type,
            i.status
        FROM menu_slot_item msi
        JOIN menu_slot ms
          ON ms.menu_slot_id = msi.menu_slot_id
        JOIN menu m
          ON m.menu_id = ms.menu_id
        JOIN item i
          ON i.item_id = msi.item_id
        WHERE m.menu_id = ?
          AND msi.menu_slot_item_id = ?
        """,
        (menu_id, menu_slot_item_id),
    )
    row = cursor.fetchone()
    if row is None:
        raise InvalidMenuForecastError("Forecast recipe assignment was not found.")
    return {
        "author_user_id": row[0],
        "item_id": row[1],
        "item_type": row[2],
        "status": row[3],
    }


def _get_item_context(cursor, item_id: int) -> dict:
    cursor.execute(
        """
        SELECT item_id, item_type, status
        FROM item
        WHERE item_id = ?
        """,
        (item_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise InvalidMenuForecastError("Case ingredient was not found.")
    return {
        "item_id": int(row[0]),
        "item_type": row[1],
        "status": row[2],
    }


def _ensure_forecast_assignment_can_update(context: dict, actor_user_id: str) -> None:
    if context["author_user_id"] != actor_user_id:
        raise InvalidMenuForecastError("You can only update forecasts for menus you created.")
    if context["item_type"] not in {"recipe", "base_food"} or context["status"] != "live":
        raise InvalidMenuForecastError("Only live menu item assignments can be forecasted.")


def _ensure_live_case_pack_item(context: dict) -> None:
    if context["item_type"] not in {"recipe", "base_food"} or context["status"] != "live":
        raise InvalidMenuForecastError("Case sizes can only be saved for live recipe or base food items.")


def _normalize_forecast_unit(value) -> str:
    normalized = normalize_unit_symbol(value)
    if normalized == CASE_FORECAST_UNIT:
        return normalized
    if normalized not in APPROVED_UNITS:
        raise InvalidMenuForecastError("Select an approved forecast unit.")
    return normalized


def _normalize_positive_case_value(value, label: str) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        raise InvalidMenuForecastError(f"{label} must be a valid number.")

    if normalized <= 0:
        raise InvalidMenuForecastError(f"{label} must be greater than zero.")

    return normalized


def _format_case_pack_quantity(quantity: float) -> str:
    return format_display_quantity(float(quantity))


def _build_case_pack_payload(row) -> dict:
    return {
        "item_case_pack_id": int(row[0]),
        "item_id": int(row[1]),
        "pack_quantity": float(row[2]),
        "pack_quantity_display": _format_case_pack_quantity(row[2]),
        "subunit_quantity": float(row[3]),
        "subunit_quantity_display": _format_case_pack_quantity(row[3]),
        "subunit_unit": normalize_unit_symbol(row[4]),
    }


def _dedupe_case_pack_payloads(rows) -> list[dict]:
    case_packs: list[dict] = []
    seen: set[tuple[int, float, float, str]] = set()
    for row in rows:
        payload = _build_case_pack_payload(row)
        key = (
            payload["item_id"],
            round(payload["pack_quantity"], 6),
            round(payload["subunit_quantity"], 6),
            payload["subunit_unit"],
        )
        if key in seen:
            continue
        seen.add(key)
        case_packs.append(payload)
    return case_packs


def _normalize_case_quantity(value) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        raise InvalidMenuForecastError("Case quantity must be a valid number.")

    if normalized < 0:
        raise InvalidMenuForecastError("Case quantity cannot be negative.")

    return normalized


def _normalize_case_fields(
    *,
    forecast_unit: str,
    forecast_yield_quantity,
    case_pack_quantity,
    case_subunit_quantity,
    case_subunit_unit,
) -> dict:
    if forecast_unit != CASE_FORECAST_UNIT:
        return {
            "case_quantity": None,
            "case_pack_quantity": None,
            "case_subunit_quantity": None,
            "case_subunit_unit": None,
            "calculated_quantity": _normalize_forecast_quantity(forecast_yield_quantity),
            "calculated_unit": forecast_unit,
        }

    case_quantity = _normalize_case_quantity(forecast_yield_quantity)
    normalized_pack_quantity = _normalize_positive_case_value(case_pack_quantity, "Pack quantity")
    normalized_subunit_quantity = _normalize_positive_case_value(case_subunit_quantity, "Subunit size")
    normalized_subunit_unit = normalize_unit_symbol(case_subunit_unit)
    if normalized_subunit_unit not in STANDARD_UNITS:
        raise InvalidMenuForecastError("Select an approved case subunit.")

    return {
        "case_quantity": case_quantity,
        "case_pack_quantity": normalized_pack_quantity,
        "case_subunit_quantity": normalized_subunit_quantity,
        "case_subunit_unit": normalized_subunit_unit,
        "calculated_quantity": case_quantity * normalized_pack_quantity * normalized_subunit_quantity,
        "calculated_unit": normalized_subunit_unit,
    }


def _normalize_case_basis_fields(
    cursor,
    *,
    context: dict,
    forecast_unit: str,
    case_basis_component_item_id=None,
    case_basis_component_name=None,
    case_basis_view_mode=None,
    case_basis_row_key=None,
) -> dict:
    if forecast_unit != CASE_FORECAST_UNIT:
        return {
            "case_basis_component_item_id": None,
            "case_basis_component_name": None,
            "case_basis_view_mode": None,
            "case_basis_row_key": None,
        }

    if case_basis_component_item_id in (None, ""):
        return {
            "case_basis_component_item_id": None,
            "case_basis_component_name": None,
            "case_basis_view_mode": None,
            "case_basis_row_key": None,
        }

    try:
        component_item_id = int(case_basis_component_item_id)
    except (TypeError, ValueError):
        raise InvalidMenuForecastError("Select a valid case ingredient.")

    view_mode = str(case_basis_view_mode or "hierarchical").strip()
    if view_mode not in {"hierarchical", "flattened", "base"}:
        view_mode = "hierarchical"
    row_key = str(case_basis_row_key or "").strip()

    if context["item_type"] == "base_food":
        if component_item_id != int(context["item_id"]):
            raise InvalidMenuForecastError("Selected case ingredient does not belong to this item.")
        row_key = row_key or str(component_item_id)
    else:
        if not row_key:
            raise InvalidMenuForecastError("Select a valid case ingredient.")
        cursor.execute(
            """
            WITH RECURSIVE component_tree(component_item_id, component_item_type, path) AS (
                SELECT
                    rc.component_item_id,
                    i.item_type,
                    printf('%d', rc.component_item_id)
                FROM recipe_component rc
                JOIN item i
                  ON i.item_id = rc.component_item_id
                WHERE rc.parent_recipe_item_id = ?
                UNION ALL
                SELECT
                    rc.component_item_id,
                    i.item_type,
                    component_tree.path || ',' || rc.component_item_id
                FROM component_tree
                JOIN recipe_component rc
                  ON rc.parent_recipe_item_id = component_tree.component_item_id
                JOIN item i
                  ON i.item_id = rc.component_item_id
                WHERE component_tree.component_item_type = 'recipe'
                  AND instr(',' || component_tree.path || ',', ',' || rc.component_item_id || ',') = 0
            )
            SELECT 1
            FROM component_tree
            WHERE component_item_id = ?
            LIMIT 1
            """,
            (context["item_id"], component_item_id),
        )
        if cursor.fetchone() is None:
            raise InvalidMenuForecastError("Selected case ingredient does not belong to this recipe.")

    cursor.execute(
        """
        SELECT item_name
        FROM item
        WHERE item_id = ?
        """,
        (component_item_id,),
    )
    item_row = cursor.fetchone()
    if item_row is None:
        raise InvalidMenuForecastError("Selected case ingredient was not found.")

    component_name = str(case_basis_component_name or item_row[0]).strip() or item_row[0]
    return {
        "case_basis_component_item_id": component_item_id,
        "case_basis_component_name": component_name,
        "case_basis_view_mode": view_mode,
        "case_basis_row_key": row_key,
    }


def _normalize_optional_serving_quantity(value) -> float | None:
    if value in (None, ""):
        return None

    try:
        normalized = float(value)
    except (TypeError, ValueError):
        raise InvalidMenuForecastError("User serving size quantity must be a valid number.")

    if normalized <= 0:
        raise InvalidMenuForecastError("User serving size quantity must be greater than zero.")

    return normalized


def _normalize_optional_serving_unit(value, quantity: float | None) -> str | None:
    if quantity is None:
        return None

    normalized = normalize_unit_symbol(value)
    if normalized not in STANDARD_UNITS:
        raise InvalidMenuForecastError("Select an approved user serving size unit.")
    return normalized


def _normalize_optional_desired_portions(value) -> float | None:
    if value in (None, ""):
        return None

    try:
        normalized = float(value)
    except (TypeError, ValueError):
        raise InvalidMenuForecastError("Desired portions must be a valid number.")

    if normalized <= 0:
        raise InvalidMenuForecastError("Desired portions must be greater than zero.")

    return normalized


def _get_existing_serving_fields(cursor, menu_slot_item_id: int) -> dict | None:
    cursor.execute(
        """
        SELECT
            user_serving_size_quantity,
            user_serving_size_unit,
            desired_portions
        FROM menu_forecast
        WHERE menu_slot_item_id = ?
        """,
        (menu_slot_item_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return {
        "user_serving_size_quantity": row[0],
        "user_serving_size_unit": row[1],
        "desired_portions": row[2],
    }


def calculate_advanced_case_effective_yield(
    *,
    recipe_item_id: int,
    case_quantity: float,
    case_pack_quantity: float,
    case_subunit_quantity: float,
    case_subunit_unit: str,
    case_basis_view_mode: str,
    case_basis_row_key: str,
) -> dict:
    target_quantity = float(case_quantity) * float(case_pack_quantity) * float(case_subunit_quantity)
    scaled_view = build_bottom_up_scaled_recipe_view(
        recipe_item_id,
        ingredient_view=case_basis_view_mode,
        target_row_key=case_basis_row_key,
        target_quantity=target_quantity,
        target_unit=case_subunit_unit,
    )
    if scaled_view is None or not scaled_view.get("is_scaled"):
        warnings = scaled_view.get("warnings") if isinstance(scaled_view, dict) else None
        message = warnings[0] if warnings else "Advanced case basis could not calculate recipe yield."
        raise InvalidMenuForecastError(message)

    return {
        "calculated_quantity": float(scaled_view["forecast_yield_quantity"]),
        "calculated_unit": scaled_view["forecast_yield_unit"],
    }


def _apply_advanced_case_basis(
    *,
    context: dict,
    case_fields: dict,
    case_basis_fields: dict,
) -> dict:
    if (
        context["item_type"] != "recipe"
        or not case_basis_fields["case_basis_component_item_id"]
        or case_fields["case_quantity"] == 0
    ):
        return case_fields

    calculated = calculate_advanced_case_effective_yield(
        recipe_item_id=context["item_id"],
        case_quantity=case_fields["case_quantity"],
        case_pack_quantity=case_fields["case_pack_quantity"],
        case_subunit_quantity=case_fields["case_subunit_quantity"],
        case_subunit_unit=case_fields["case_subunit_unit"],
        case_basis_view_mode=case_basis_fields["case_basis_view_mode"],
        case_basis_row_key=case_basis_fields["case_basis_row_key"],
    )

    return {
        **case_fields,
        "calculated_quantity": calculated["calculated_quantity"],
        "calculated_unit": calculated["calculated_unit"],
    }


def list_item_case_packs(item_id: int) -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                item_case_pack_id,
                item_id,
                pack_quantity,
                subunit_quantity,
                subunit_unit
            FROM item_case_pack
            WHERE item_id = ?
            ORDER BY updated_at DESC, item_case_pack_id DESC
            """,
            (item_id,),
        )
        return _dedupe_case_pack_payloads(cursor.fetchall())


def list_item_case_packs_for_items(item_ids: list[int]) -> dict[int, list[dict]]:
    normalized_item_ids = sorted({int(item_id) for item_id in item_ids if item_id})
    if not normalized_item_ids:
        return {}

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                item_case_pack_id,
                item_id,
                pack_quantity,
                subunit_quantity,
                subunit_unit
            FROM item_case_pack
            WHERE item_id IN ({})
            ORDER BY item_id ASC, updated_at DESC, item_case_pack_id DESC
            """.format(", ".join("?" for _ in normalized_item_ids)),
            normalized_item_ids,
        )
        case_packs_by_item_id: dict[int, list[dict]] = {}
        for case_pack in _dedupe_case_pack_payloads(cursor.fetchall()):
            case_packs_by_item_id.setdefault(case_pack["item_id"], []).append(case_pack)
        return case_packs_by_item_id


def save_item_case_pack(
    *,
    menu_id: int,
    menu_slot_item_id: int,
    actor_user_id: str,
    item_id,
    pack_quantity,
    subunit_quantity,
    subunit_unit,
) -> dict:
    try:
        normalized_item_id = int(item_id)
    except (TypeError, ValueError):
        raise InvalidMenuForecastError("Select a valid case ingredient.")
    case_fields = _normalize_case_fields(
        forecast_unit=CASE_FORECAST_UNIT,
        forecast_yield_quantity=1,
        case_pack_quantity=pack_quantity,
        case_subunit_quantity=subunit_quantity,
        case_subunit_unit=subunit_unit,
    )

    with get_connection() as conn:
        cursor = conn.cursor()
        assignment_context = _get_forecast_assignment_context(
            cursor,
            menu_id=menu_id,
            menu_slot_item_id=menu_slot_item_id,
        )
        _ensure_forecast_assignment_can_update(assignment_context, actor_user_id)
        item_context = _get_item_context(cursor, normalized_item_id)
        _ensure_live_case_pack_item(item_context)

        cursor.execute(
            """
            SELECT
                item_case_pack_id,
                item_id,
                pack_quantity,
                subunit_quantity,
                subunit_unit
            FROM item_case_pack
            WHERE item_id = ?
              AND ABS(pack_quantity - ?) <= ?
              AND ABS(subunit_quantity - ?) <= ?
              AND subunit_unit = ?
            ORDER BY item_case_pack_id ASC
            LIMIT 1
            """,
            (
                normalized_item_id,
                case_fields["case_pack_quantity"],
                CASE_PACK_MATCH_TOLERANCE,
                case_fields["case_subunit_quantity"],
                CASE_PACK_MATCH_TOLERANCE,
                case_fields["case_subunit_unit"],
            ),
        )
        if cursor.fetchone() is not None:
            raise InvalidMenuForecastError("This case size is already saved for that item.")

        cursor.execute(
            """
            INSERT INTO item_case_pack (
                item_id,
                pack_quantity,
                subunit_quantity,
                subunit_unit,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                normalized_item_id,
                case_fields["case_pack_quantity"],
                case_fields["case_subunit_quantity"],
                case_fields["case_subunit_unit"],
            ),
        )
        item_case_pack_id = int(cursor.lastrowid)
        cursor.execute(
            """
            SELECT
                item_case_pack_id,
                item_id,
                pack_quantity,
                subunit_quantity,
                subunit_unit
            FROM item_case_pack
            WHERE item_case_pack_id = ?
            """,
            (item_case_pack_id,),
        )
        row = cursor.fetchone()
        conn.commit()

    return _build_case_pack_payload(row)


def save_menu_forecast_yield(
    *,
    menu_id: int,
    menu_slot_item_id: int,
    actor_user_id: str,
    forecast_yield_quantity,
    forecast_yield_unit,
    user_serving_size_quantity=None,
    user_serving_size_unit=None,
    desired_portions=None,
    case_pack_quantity=None,
    case_subunit_quantity=None,
    case_subunit_unit=None,
    case_basis_component_item_id=None,
    case_basis_component_name=None,
    case_basis_view_mode=None,
    case_basis_row_key=None,
) -> dict:
    normalized_unit = _normalize_forecast_unit(forecast_yield_unit)
    case_fields = _normalize_case_fields(
        forecast_unit=normalized_unit,
        forecast_yield_quantity=forecast_yield_quantity,
        case_pack_quantity=case_pack_quantity,
        case_subunit_quantity=case_subunit_quantity,
        case_subunit_unit=case_subunit_unit,
    )
    normalized_quantity = (
        case_fields["case_quantity"]
        if normalized_unit == CASE_FORECAST_UNIT
        else case_fields["calculated_quantity"]
    )

    with get_connection() as conn:
        cursor = conn.cursor()
        context = _get_forecast_assignment_context(
            cursor,
            menu_id=menu_id,
            menu_slot_item_id=menu_slot_item_id,
        )
        _ensure_forecast_assignment_can_update(context, actor_user_id)
        case_basis_fields = _normalize_case_basis_fields(
            cursor,
            context=context,
            forecast_unit=normalized_unit,
            case_basis_component_item_id=case_basis_component_item_id,
            case_basis_component_name=case_basis_component_name,
            case_basis_view_mode=case_basis_view_mode,
            case_basis_row_key=case_basis_row_key,
        )
        case_fields = _apply_advanced_case_basis(
            context=context,
            case_fields=case_fields,
            case_basis_fields=case_basis_fields,
        )
        is_advanced_case = (
            normalized_unit == CASE_FORECAST_UNIT
            and context["item_type"] == "recipe"
            and case_basis_fields["case_basis_component_item_id"] is not None
        )
        if normalized_unit == CASE_FORECAST_UNIT and not is_advanced_case:
            normalized_serving_quantity = None
            normalized_serving_unit = None
            normalized_desired_portions = None
        else:
            existing_serving = _get_existing_serving_fields(cursor, menu_slot_item_id) or {}
            if user_serving_size_quantity in (None, "") and existing_serving.get("user_serving_size_quantity") is not None:
                user_serving_size_quantity = existing_serving["user_serving_size_quantity"]
            if user_serving_size_unit in (None, "") and existing_serving.get("user_serving_size_unit"):
                user_serving_size_unit = existing_serving["user_serving_size_unit"]
            if desired_portions in (None, "") and existing_serving.get("desired_portions") is not None:
                desired_portions = existing_serving["desired_portions"]
            normalized_serving_quantity = _normalize_optional_serving_quantity(user_serving_size_quantity)
            normalized_serving_unit = _normalize_optional_serving_unit(
                user_serving_size_unit,
                normalized_serving_quantity,
            )
            normalized_desired_portions = _normalize_optional_desired_portions(desired_portions)
        item_case_pack_id = None

        cursor.execute(
            """
            INSERT INTO menu_forecast (
                menu_slot_item_id,
                forecast_yield_quantity,
                forecast_yield_unit,
                user_serving_size_quantity,
                user_serving_size_unit,
                desired_portions,
                forecast_display_unit,
                case_quantity,
                case_pack_quantity,
                case_subunit_quantity,
                case_subunit_unit,
                calculated_forecast_quantity,
                calculated_forecast_unit,
                item_case_pack_id,
                case_basis_component_item_id,
                case_basis_component_name,
                case_basis_view_mode,
                case_basis_row_key,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(menu_slot_item_id) DO UPDATE SET
                forecast_yield_quantity = excluded.forecast_yield_quantity,
                forecast_yield_unit = excluded.forecast_yield_unit,
                user_serving_size_quantity = excluded.user_serving_size_quantity,
                user_serving_size_unit = excluded.user_serving_size_unit,
                desired_portions = excluded.desired_portions,
                forecast_display_unit = excluded.forecast_display_unit,
                case_quantity = excluded.case_quantity,
                case_pack_quantity = excluded.case_pack_quantity,
                case_subunit_quantity = excluded.case_subunit_quantity,
                case_subunit_unit = excluded.case_subunit_unit,
                calculated_forecast_quantity = excluded.calculated_forecast_quantity,
                calculated_forecast_unit = excluded.calculated_forecast_unit,
                item_case_pack_id = excluded.item_case_pack_id,
                case_basis_component_item_id = excluded.case_basis_component_item_id,
                case_basis_component_name = excluded.case_basis_component_name,
                case_basis_view_mode = excluded.case_basis_view_mode,
                case_basis_row_key = excluded.case_basis_row_key,
                updated_at = datetime('now')
            """,
            (
                menu_slot_item_id,
                normalized_quantity,
                normalized_unit,
                normalized_serving_quantity,
                normalized_serving_unit,
                normalized_desired_portions,
                normalized_unit,
                case_fields["case_quantity"],
                case_fields["case_pack_quantity"],
                case_fields["case_subunit_quantity"],
                case_fields["case_subunit_unit"],
                case_fields["calculated_quantity"],
                case_fields["calculated_unit"],
                item_case_pack_id,
                case_basis_fields["case_basis_component_item_id"],
                case_basis_fields["case_basis_component_name"],
                case_basis_fields["case_basis_view_mode"],
                case_basis_fields["case_basis_row_key"],
            ),
        )
        cursor.execute(
            """
            SELECT
                menu_forecast_id,
                forecast_yield_quantity,
                forecast_yield_unit,
                user_serving_size_quantity,
                user_serving_size_unit,
                desired_portions,
                forecast_display_unit,
                case_quantity,
                case_pack_quantity,
                case_subunit_quantity,
                case_subunit_unit,
                calculated_forecast_quantity,
                calculated_forecast_unit,
                item_case_pack_id,
                case_basis_component_item_id,
                case_basis_component_name,
                case_basis_view_mode,
                case_basis_row_key,
                updated_at
            FROM menu_forecast
            WHERE menu_slot_item_id = ?
            """,
            (menu_slot_item_id,),
        )
        forecast_row = cursor.fetchone()
        conn.commit()

    return {
        "menu_forecast_id": forecast_row[0],
        "menu_slot_item_id": menu_slot_item_id,
        "forecast_yield_quantity": forecast_row[1],
        "forecast_yield_unit": forecast_row[2],
        "user_serving_size_quantity": forecast_row[3],
        "user_serving_size_unit": forecast_row[4],
        "desired_portions": forecast_row[5],
        "forecast_display_unit": forecast_row[6],
        "case_quantity": forecast_row[7],
        "case_pack_quantity": forecast_row[8],
        "case_subunit_quantity": forecast_row[9],
        "case_subunit_unit": forecast_row[10],
        "calculated_forecast_quantity": forecast_row[11],
        "calculated_forecast_unit": forecast_row[12],
        "item_case_pack_id": forecast_row[13],
        "case_basis_component_item_id": forecast_row[14],
        "case_basis_component_name": forecast_row[15],
        "case_basis_view_mode": forecast_row[16],
        "case_basis_row_key": forecast_row[17],
        "updated_at": forecast_row[18],
    }


def get_menu_forecast_by_slot_item(menu_slot_item_id: int, menu_id: int | None = None) -> dict | None:
    with get_connection() as conn:
        cursor = conn.cursor()
        menu_filter = ""
        params: list[int] = [menu_slot_item_id]
        if menu_id is not None:
            menu_filter = "AND ms.menu_id = ?"
            params.append(menu_id)
        cursor.execute(
            f"""
            SELECT
                mf.menu_forecast_id,
                mf.menu_slot_item_id,
                mf.forecast_yield_quantity,
                mf.forecast_yield_unit,
                mf.user_serving_size_quantity,
                mf.user_serving_size_unit,
                mf.desired_portions,
                mf.forecast_display_unit,
                mf.case_quantity,
                mf.case_pack_quantity,
                mf.case_subunit_quantity,
                mf.case_subunit_unit,
                mf.calculated_forecast_quantity,
                mf.calculated_forecast_unit,
                mf.item_case_pack_id,
                mf.case_basis_component_item_id,
                mf.case_basis_component_name,
                mf.case_basis_view_mode,
                mf.case_basis_row_key,
                mf.updated_at
            FROM menu_forecast mf
            JOIN menu_slot_item msi
              ON msi.menu_slot_item_id = mf.menu_slot_item_id
            JOIN menu_slot ms
              ON ms.menu_slot_id = msi.menu_slot_id
            WHERE mf.menu_slot_item_id = ?
              {menu_filter}
            """,
            params,
        )
        row = cursor.fetchone()

    if row is None:
        return None

    return {
        "menu_forecast_id": row[0],
        "menu_slot_item_id": row[1],
        "forecast_yield_quantity": row[2],
        "forecast_yield_unit": row[3],
        "user_serving_size_quantity": row[4],
        "user_serving_size_unit": row[5],
        "desired_portions": row[6],
        "forecast_display_unit": row[7],
        "case_quantity": row[8],
        "case_pack_quantity": row[9],
        "case_subunit_quantity": row[10],
        "case_subunit_unit": row[11],
        "calculated_forecast_quantity": row[12],
        "calculated_forecast_unit": row[13],
        "item_case_pack_id": row[14],
        "case_basis_component_item_id": row[15],
        "case_basis_component_name": row[16],
        "case_basis_view_mode": row[17],
        "case_basis_row_key": row[18],
        "updated_at": row[19],
    }


def _normalize_batch_splits(batch_splits: list[dict], forecast_quantity: float) -> list[dict]:
    if not isinstance(batch_splits, list):
        raise InvalidMenuForecastBatchError("Batch splits must be a list.")
    if not batch_splits:
        return []
    if len(batch_splits) > MAX_BATCH_SPLITS:
        raise InvalidMenuForecastBatchError(f"Batch splits cannot exceed {MAX_BATCH_SPLITS} rows.")
    if forecast_quantity <= 0:
        raise InvalidMenuForecastBatchError("Set a forecast quantity before saving batch splits.")

    normalized_splits: list[dict] = []
    for index, split in enumerate(batch_splits, start=1):
        if not isinstance(split, dict):
            raise InvalidMenuForecastBatchError("Each batch split must be an object.")

        percent_value = split.get("batch_percent")
        quantity_value = split.get("batch_quantity")
        if percent_value not in (None, ""):
            batch_percent = _normalize_batch_percent(percent_value)
        elif quantity_value not in (None, ""):
            batch_quantity = _normalize_batch_quantity(quantity_value)
            batch_percent = batch_quantity / forecast_quantity * 100
            if batch_percent > 100:
                raise InvalidMenuForecastBatchError("Batch quantity cannot exceed the forecast quantity.")
        else:
            raise InvalidMenuForecastBatchError("Each batch split requires a percent or quantity.")

        normalized_splits.append(
            {
                "batch_sequence": index,
                "batch_percent": batch_percent,
                "planned_time": _normalize_optional_planned_time(split.get("planned_time")),
            }
        )

    percent_total = sum(split["batch_percent"] for split in normalized_splits)
    if abs(percent_total - 100) > BATCH_PERCENT_TOLERANCE:
        raise InvalidMenuForecastBatchError("Batch split percentages must total 100%.")

    return normalized_splits


def save_menu_forecast_batch_splits(
    *,
    menu_id: int,
    menu_slot_item_id: int,
    actor_user_id: str,
    batch_splits: list[dict],
) -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            context = _get_forecast_assignment_context(
                cursor,
                menu_id=menu_id,
                menu_slot_item_id=menu_slot_item_id,
            )
            _ensure_forecast_assignment_can_update(context, actor_user_id)
        except InvalidMenuForecastError as exc:
            raise InvalidMenuForecastBatchError(str(exc))

        cursor.execute(
            """
            SELECT
                forecast_yield_quantity,
                forecast_yield_unit,
                COALESCE(calculated_forecast_quantity, forecast_yield_quantity),
                COALESCE(calculated_forecast_unit, forecast_yield_unit)
            FROM menu_forecast
            WHERE menu_slot_item_id = ?
            """,
            (menu_slot_item_id,),
        )
        forecast_row = cursor.fetchone()
        if forecast_row is None:
            raise InvalidMenuForecastBatchError("Set a forecast yield before saving batch splits.")

        display_forecast_quantity = float(forecast_row[0])
        display_forecast_unit = forecast_row[1]
        effective_forecast_quantity = float(forecast_row[2])
        effective_forecast_unit = forecast_row[3]
        normalized_splits = _normalize_batch_splits(batch_splits, display_forecast_quantity)

        cursor.execute(
            "DELETE FROM menu_forecast_batch_split WHERE menu_slot_item_id = ?",
            (menu_slot_item_id,),
        )
        for split in normalized_splits:
            cursor.execute(
                """
                INSERT INTO menu_forecast_batch_split (
                    menu_slot_item_id,
                    batch_sequence,
                    batch_percent,
                    planned_time,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))
                """,
                (
                    menu_slot_item_id,
                    split["batch_sequence"],
                    split["batch_percent"],
                    split["planned_time"],
                ),
            )
        conn.commit()

    return {
        "menu_slot_item_id": menu_slot_item_id,
        "forecast_yield_quantity": display_forecast_quantity,
        "forecast_yield_unit": display_forecast_unit,
        "effective_forecast_quantity": effective_forecast_quantity,
        "effective_forecast_unit": effective_forecast_unit,
        "batch_splits": decorate_batch_splits(
            normalized_splits,
            forecast_quantity=effective_forecast_quantity,
            forecast_unit=effective_forecast_unit,
            display_forecast_quantity=display_forecast_quantity,
            display_forecast_unit=display_forecast_unit,
        ),
    }


def decorate_batch_splits(
    batch_splits: list[dict],
    *,
    forecast_quantity: float | None,
    forecast_unit: str | None,
    display_forecast_quantity: float | None = None,
    display_forecast_unit: str | None = None,
) -> list[dict]:
    decorated: list[dict] = []
    for split in batch_splits:
        batch_percent = float(split["batch_percent"])
        batch_quantity = (
            float(forecast_quantity) * batch_percent / 100
            if forecast_quantity is not None
            else 0
        )
        display_batch_quantity = (
            float(display_forecast_quantity) * batch_percent / 100
            if display_forecast_quantity is not None
            else batch_quantity
        )
        display_batch_unit = normalize_unit_symbol(display_forecast_unit or forecast_unit)
        decorated.append(
            {
                "batch_sequence": int(split["batch_sequence"]),
                "batch_percent": batch_percent,
                "batch_percent_display": _format_rollup_quantity(batch_percent),
                "batch_quantity": display_batch_quantity,
                "batch_quantity_display": _format_rollup_quantity(display_batch_quantity),
                "batch_unit": display_batch_unit,
                "effective_batch_quantity": batch_quantity,
                "effective_batch_unit": normalize_unit_symbol(forecast_unit),
                "planned_time": split.get("planned_time") or "",
            }
        )
    return decorated


def _coerce_optional_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_rollup_quantity(quantity: float) -> str:
    if quantity == 0:
        return "0"
    return format_display_quantity(quantity)


def _build_slot_label(row: dict) -> str:
    return " / ".join(
        part
        for part in [
            row.get("meal_period_label"),
            row.get("concept_label"),
        ]
        if part
    )


def _has_mass_volume_bridge(row: dict) -> bool:
    mass_profile = get_unit_measurement_profile(row.get("mass_unit"))
    volume_profile = get_unit_measurement_profile(row.get("volume_unit"))
    return bool(
        _coerce_optional_float(row.get("mass_quantity"))
        and _coerce_optional_float(row.get("volume_quantity"))
        and mass_profile
        and volume_profile
        and mass_profile["measurement_type"] == "mass"
        and volume_profile["measurement_type"] == "volume"
    )


def build_forecast_display_unit_options(*, base_unit: str, row: dict) -> list[str]:
    base_profile = get_unit_measurement_profile(base_unit)
    if not base_profile:
        return [base_unit] if base_unit else []

    allowed_measurement_types = {base_profile["measurement_type"]}
    if base_profile["measurement_type"] in {"mass", "volume"} and _has_mass_volume_bridge(row):
        allowed_measurement_types.update({"mass", "volume"})

    options = [
        unit
        for unit in APPROVED_UNITS
        if (profile := get_unit_measurement_profile(unit))
        and profile["conversion_ready"]
        and profile["measurement_type"] in allowed_measurement_types
    ]
    if base_unit and base_unit not in options:
        options.insert(0, base_unit)
    return options


def build_menu_forecast_production_summary(rows: list[dict]) -> dict:
    """
    Roll forecast rows up by recipe for production planning.

    The editable forecast grid is slot-oriented. Production planning needs the
    inverse view: one row per recipe with total target yield and batch count.
    """
    rollups: dict[int, dict] = {}
    warnings: list[str] = []

    for row in rows:
        item_id = int(row["item_id"])
        recipe_yield_quantity = _coerce_optional_float(row.get("yield_quantity"))
        recipe_yield_unit = normalize_unit_symbol(row.get("yield_unit"))
        forecast_quantity = _coerce_optional_float(row.get("effective_forecast_quantity"))
        if forecast_quantity is None:
            forecast_quantity = _coerce_optional_float(row.get("forecast_quantity"))
        forecast_unit = normalize_unit_symbol(row.get("effective_forecast_unit") or row.get("forecast_unit"))

        rollup = rollups.setdefault(
            item_id,
            {
                "item_id": item_id,
                "recipe_name": row["recipe_name"],
                "item_type": row.get("item_type", "recipe"),
                "assignment_count": 0,
                "slot_labels": [],
                "sort_order": row.get("menu_order") or (999, 999, 999, row["recipe_name"].lower(), item_id),
                "yield_quantity": recipe_yield_quantity,
                "yield_quantity_display": (
                    _format_rollup_quantity(recipe_yield_quantity)
                    if recipe_yield_quantity is not None
                    else ""
                ),
                "yield_unit": recipe_yield_unit,
                "mass_quantity": _coerce_optional_float(row.get("mass_quantity")),
                "mass_unit": row.get("mass_unit") or "",
                "volume_quantity": _coerce_optional_float(row.get("volume_quantity")),
                "volume_unit": row.get("volume_unit") or "",
                "total_forecast_quantity": 0.0,
                "total_forecast_quantity_display": "0",
                "total_forecast_unit": recipe_yield_unit,
                "batch_count": 0.0,
                "batch_count_display": "0",
                "desired_portions_total": 0.0,
                "desired_portions_display": "",
                "batch_totals": {},
                "batch_summary": [],
                "warnings": [],
                "display_unit_options": [],
            },
        )
        rollup["assignment_count"] += 1
        slot_label = _build_slot_label(row)
        if slot_label and slot_label not in rollup["slot_labels"]:
            rollup["slot_labels"].append(slot_label)

        if not forecast_quantity or forecast_quantity <= 0 or not forecast_unit:
            warning = f"{row['recipe_name']} has an assignment without a forecast yield."
            rollup["warnings"].append(warning)
            warnings.append(warning)
            continue
        if row.get("item_type") == "base_food" and not recipe_yield_unit:
            recipe_yield_unit = forecast_unit
            rollup["yield_unit"] = recipe_yield_unit
            rollup["total_forecast_unit"] = recipe_yield_unit
        if not recipe_yield_quantity or recipe_yield_quantity <= 0 or not recipe_yield_unit:
            if row.get("item_type") == "base_food":
                recipe_yield_quantity = forecast_quantity
                rollup["yield_quantity"] = recipe_yield_quantity
                rollup["yield_quantity_display"] = _format_rollup_quantity(recipe_yield_quantity)
            else:
                warning = f"{row['recipe_name']} is missing recipe yield data for batch calculation."
                rollup["warnings"].append(warning)
                warnings.append(warning)
                continue

        if not recipe_yield_quantity or recipe_yield_quantity <= 0 or not recipe_yield_unit:
            warning = f"{row['recipe_name']} is missing recipe yield data for batch calculation."
            rollup["warnings"].append(warning)
            warnings.append(warning)
            continue

        rollup["display_unit_options"] = build_forecast_display_unit_options(
            base_unit=recipe_yield_unit,
            row=rollup,
        )

        conversion = convert_with_item_mass_volume_bridge(
            quantity=forecast_quantity,
            from_unit=forecast_unit,
            to_unit=recipe_yield_unit,
            item_type="recipe",
            mass_quantity=_coerce_optional_float(row.get("mass_quantity")),
            mass_unit=row.get("mass_unit"),
            volume_quantity=_coerce_optional_float(row.get("volume_quantity")),
            volume_unit=row.get("volume_unit"),
        )
        if not conversion["ok"]:
            warning = (
                f"{row['recipe_name']} forecast unit '{forecast_unit}' cannot roll up "
                f"to recipe yield unit '{recipe_yield_unit}'."
            )
            rollup["warnings"].append(warning)
            warnings.append(warning)
            continue

        converted_quantity = float(conversion["quantity"])
        rollup["total_forecast_quantity"] += converted_quantity
        rollup["batch_count"] += converted_quantity / recipe_yield_quantity

        desired_portions = _coerce_optional_float(row.get("desired_portions"))
        if desired_portions:
            rollup["desired_portions_total"] += desired_portions

        for split in row.get("batch_splits", []):
            batch_quantity = _coerce_optional_float(split.get("effective_batch_quantity"))
            if batch_quantity is None:
                batch_quantity = _coerce_optional_float(split.get("batch_quantity"))
            batch_unit = normalize_unit_symbol(split.get("effective_batch_unit") or split.get("batch_unit"))
            if not batch_quantity or not batch_unit:
                continue
            batch_conversion = convert_with_item_mass_volume_bridge(
                quantity=batch_quantity,
                from_unit=batch_unit,
                to_unit=recipe_yield_unit,
                item_type="recipe",
                mass_quantity=_coerce_optional_float(row.get("mass_quantity")),
                mass_unit=row.get("mass_unit"),
                volume_quantity=_coerce_optional_float(row.get("volume_quantity")),
                volume_unit=row.get("volume_unit"),
            )
            if not batch_conversion["ok"]:
                warning = (
                    f"{row['recipe_name']} batch {split['batch_sequence']} cannot roll up "
                    f"from '{batch_unit}' to '{recipe_yield_unit}'."
                )
                rollup["warnings"].append(warning)
                warnings.append(warning)
                continue
            batch_total = rollup["batch_totals"].setdefault(
                int(split["batch_sequence"]),
                {
                    "batch_sequence": int(split["batch_sequence"]),
                    "total_quantity": 0.0,
                    "unit": recipe_yield_unit,
                    "planned_times": [],
                    "concept_splits": [],
                },
            )
            batch_total["total_quantity"] += float(batch_conversion["quantity"])
            if split.get("planned_time") and split["planned_time"] not in batch_total["planned_times"]:
                batch_total["planned_times"].append(split["planned_time"])
            batch_total["concept_splits"].append(
                {
                    "label": _build_slot_label(row),
                    "percent_display": split.get("batch_percent_display"),
                    "quantity_display": split.get("batch_quantity_display"),
                    "unit": batch_unit,
                }
            )

    summary_rows = []
    for rollup in rollups.values():
        rollup["total_forecast_quantity_display"] = _format_rollup_quantity(
            rollup["total_forecast_quantity"]
        )
        rollup["batch_count_display"] = _format_rollup_quantity(rollup["batch_count"])
        if rollup["desired_portions_total"] > 0:
            rollup["desired_portions_display"] = _format_rollup_quantity(
                rollup["desired_portions_total"]
            )
        batch_summary = []
        for batch_total in sorted(rollup["batch_totals"].values(), key=lambda item: item["batch_sequence"]):
            batch_percent = (
                batch_total["total_quantity"] / rollup["total_forecast_quantity"] * 100
                if rollup["total_forecast_quantity"] > 0
                else 0
            )
            batch_summary.append(
                {
                    "batch_sequence": batch_total["batch_sequence"],
                    "total_quantity": batch_total["total_quantity"],
                    "total_quantity_display": _format_rollup_quantity(batch_total["total_quantity"]),
                    "unit": batch_total["unit"],
                    "combined_percent": batch_percent,
                    "combined_percent_display": _format_rollup_quantity(batch_percent),
                    "planned_times": batch_total["planned_times"],
                    "concept_splits": batch_total["concept_splits"],
                }
            )
        rollup["batch_summary"] = batch_summary
        summary_rows.append(rollup)

    summary_rows.sort(key=lambda item: item["sort_order"])
    return {
        "rows": summary_rows,
        "warnings": list(dict.fromkeys(warnings)),
    }
