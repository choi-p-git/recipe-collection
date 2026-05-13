from config.units import APPROVED_UNITS, STANDARD_UNITS
from db import get_connection
from services.unit_conversion_service import normalize_unit_symbol


class InvalidMenuForecastError(ValueError):
    """Raised when a menu forecast save request is invalid."""


def _normalize_forecast_quantity(value) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        raise InvalidMenuForecastError("Forecast quantity must be a valid number.")

    if normalized < 0:
        raise InvalidMenuForecastError("Forecast quantity cannot be negative.")

    return normalized


def _normalize_forecast_unit(value) -> str:
    normalized = normalize_unit_symbol(value)
    if normalized not in APPROVED_UNITS:
        raise InvalidMenuForecastError("Select an approved forecast unit.")
    return normalized


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
) -> dict:
    normalized_quantity = _normalize_forecast_quantity(forecast_yield_quantity)
    normalized_unit = _normalize_forecast_unit(forecast_yield_unit)
    normalized_serving_quantity = _normalize_optional_serving_quantity(user_serving_size_quantity)
    normalized_serving_unit = _normalize_optional_serving_unit(
        user_serving_size_unit,
        normalized_serving_quantity,
    )
    normalized_desired_portions = _normalize_optional_desired_portions(desired_portions)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                m.author_user_id,
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
        if row[0] != actor_user_id:
            raise InvalidMenuForecastError("You can only update forecasts for menus you created.")
        if row[1] != "recipe" or row[2] != "live":
            raise InvalidMenuForecastError("Only live recipe assignments can be forecasted.")

        cursor.execute(
            """
            INSERT INTO menu_forecast (
                menu_slot_item_id,
                forecast_yield_quantity,
                forecast_yield_unit,
                user_serving_size_quantity,
                user_serving_size_unit,
                desired_portions,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(menu_slot_item_id) DO UPDATE SET
                forecast_yield_quantity = excluded.forecast_yield_quantity,
                forecast_yield_unit = excluded.forecast_yield_unit,
                user_serving_size_quantity = excluded.user_serving_size_quantity,
                user_serving_size_unit = excluded.user_serving_size_unit,
                desired_portions = excluded.desired_portions,
                updated_at = datetime('now')
            """,
            (
                menu_slot_item_id,
                normalized_quantity,
                normalized_unit,
                normalized_serving_quantity,
                normalized_serving_unit,
                normalized_desired_portions,
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
        "updated_at": forecast_row[6],
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
        "updated_at": row[7],
    }
