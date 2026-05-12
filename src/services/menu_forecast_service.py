from config.units import APPROVED_UNITS
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


def save_menu_forecast_yield(
    *,
    menu_id: int,
    menu_slot_item_id: int,
    actor_user_id: str,
    forecast_yield_quantity,
    forecast_yield_unit,
) -> dict:
    normalized_quantity = _normalize_forecast_quantity(forecast_yield_quantity)
    normalized_unit = _normalize_forecast_unit(forecast_yield_unit)

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
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(menu_slot_item_id) DO UPDATE SET
                forecast_yield_quantity = excluded.forecast_yield_quantity,
                forecast_yield_unit = excluded.forecast_yield_unit,
                updated_at = datetime('now')
            """,
            (menu_slot_item_id, normalized_quantity, normalized_unit),
        )
        cursor.execute(
            """
            SELECT
                menu_forecast_id,
                forecast_yield_quantity,
                forecast_yield_unit,
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
        "updated_at": forecast_row[3],
    }
