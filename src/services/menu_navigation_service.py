from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def current_service_date() -> date:
    try:
        return datetime.now(ZoneInfo("America/Chicago")).date()
    except ZoneInfoNotFoundError:
        return datetime.now().date()


def current_day_of_week(service_date: date | None = None) -> str:
    return (service_date or current_service_date()).strftime("%A").lower()


def default_menu_week_number(menu: dict | None, current_date: date | None = None) -> int:
    if not menu:
        return 1

    menu_length_weeks = int(menu.get("menu_length_weeks") or 1)
    start_date_value = str(menu.get("menu_start_date") or "").strip()
    if not start_date_value:
        return 1

    try:
        start_date = date.fromisoformat(start_date_value)
    except ValueError:
        return 1

    service_date = current_date or current_service_date()
    if service_date <= start_date:
        return 1

    week_number = ((service_date - start_date).days // 7) + 1
    return max(1, min(week_number, menu_length_weeks))
