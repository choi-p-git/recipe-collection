from datetime import date, timedelta


PYTHON_WEEKDAY_BY_DAY = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def parse_iso_date(value: str | None) -> date | None:
    cleaned = str(value or "").strip()
    if not cleaned:
        return None

    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        return None


def format_service_date(value: date | None) -> str:
    if value is None:
        return ""
    return f"{value:%b} {value.day}"


def build_week_day_dates(
    *,
    menu_start_date: str,
    menu_end_date: str,
    week_numbers: list[int],
    service_days: list[str],
) -> dict[int, dict[str, dict]]:
    start_date = parse_iso_date(menu_start_date)
    end_date = parse_iso_date(menu_end_date)
    if start_date is None:
        return {}

    week_day_dates: dict[int, dict[str, dict]] = {}
    for week_number in week_numbers:
        day_dates: dict[str, dict] = {}
        for day_of_week in service_days:
            target_weekday = PYTHON_WEEKDAY_BY_DAY.get(day_of_week)
            if target_weekday is None:
                continue
            service_date = start_date + timedelta(days=((week_number - 1) * 7) + target_weekday - start_date.weekday())
            is_in_range = service_date >= start_date and (end_date is None or service_date <= end_date)
            day_dates[day_of_week] = {
                "date": service_date.isoformat(),
                "display": format_service_date(service_date),
                "is_in_range": is_in_range,
            }
        week_day_dates[week_number] = day_dates

    return week_day_dates
