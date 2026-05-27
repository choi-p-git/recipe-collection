import json
from datetime import date, datetime, time, timedelta

from config.item_categories import ITEM_CATEGORY_LABELS, ITEM_CATEGORY_VALUES
from db import get_connection, initialize_database


DAY_OPTIONS = (
    ("monday", "Monday"),
    ("tuesday", "Tuesday"),
    ("wednesday", "Wednesday"),
    ("thursday", "Thursday"),
    ("friday", "Friday"),
    ("saturday", "Saturday"),
    ("sunday", "Sunday"),
)
DAY_INDEX = {day: index for index, (day, _label) in enumerate(DAY_OPTIONS)}
ORDERING_FREQUENCY_OPTIONS = (
    ("daily", "Daily"),
    ("as_needed", "As needed"),
    ("custom", "Custom"),
)
DEFAULT_PLANNING_HORIZON_DAYS = 7


class InvalidInventoryOrderingPreferenceError(ValueError):
    """Raised when inventory ordering preference data is invalid."""


def _normalize_user_id(value) -> str:
    normalized = " ".join(str(value or "").split())
    if not normalized:
        raise InvalidInventoryOrderingPreferenceError("User is required.")
    return normalized


def _normalize_text(value, label: str) -> str:
    normalized = " ".join(str(value or "").split())
    if not normalized:
        raise InvalidInventoryOrderingPreferenceError(f"{label} is required.")
    return normalized


def _normalize_item_category(value) -> str:
    normalized = str(value or "").strip()
    if normalized not in ITEM_CATEGORY_VALUES:
        raise InvalidInventoryOrderingPreferenceError("Select a valid item category.")
    return normalized


def _normalize_frequency(value) -> str:
    normalized = str(value or "as_needed").strip()
    allowed = {option[0] for option in ORDERING_FREQUENCY_OPTIONS}
    if normalized not in allowed:
        raise InvalidInventoryOrderingPreferenceError("Select a valid ordering frequency.")
    return normalized


def _normalize_item_categories(values) -> list[str]:
    if values is None:
        raw_values = []
    elif isinstance(values, str):
        raw_values = [values]
    else:
        raw_values = list(values)
    categories = []
    for value in raw_values:
        category = _normalize_item_category(value)
        if category not in categories:
            categories.append(category)
    if not categories:
        raise InvalidInventoryOrderingPreferenceError("Select at least one item category.")
    return categories


def _normalize_days(values, *, require_one: bool = True) -> list[str]:
    if values is None:
        raw_values = []
    elif isinstance(values, str):
        raw_values = [values]
    else:
        raw_values = list(values)
    days = []
    for value in raw_values:
        day = str(value or "").strip()
        if not day:
            continue
        if day not in DAY_INDEX:
            raise InvalidInventoryOrderingPreferenceError("Select valid delivery days.")
        if day not in days:
            days.append(day)
    if require_one and not days:
        raise InvalidInventoryOrderingPreferenceError("Select at least one delivery day.")
    return days


def _normalize_cutoff_day(value) -> str:
    normalized = str(value or "").strip()
    if normalized not in DAY_INDEX:
        raise InvalidInventoryOrderingPreferenceError("Select a valid cutoff day.")
    return normalized


def _normalize_cutoff_time(value) -> str:
    normalized = str(value or "").strip()
    try:
        parsed = time.fromisoformat(normalized)
    except ValueError:
        raise InvalidInventoryOrderingPreferenceError("Cutoff time must be a valid time.")
    return parsed.strftime("%H:%M")


def _normalize_lead_days(value) -> int:
    try:
        lead_days = int(value)
    except (TypeError, ValueError):
        raise InvalidInventoryOrderingPreferenceError("Preferred lead time must be a whole number of days.")
    if lead_days < 0 or lead_days > 14:
        raise InvalidInventoryOrderingPreferenceError("Preferred lead time must be between 0 and 14 days.")
    return lead_days


def _normalize_cutoff_rules(cutoff_rules) -> list[dict]:
    if not isinstance(cutoff_rules, list):
        raise InvalidInventoryOrderingPreferenceError("Delivery cutoff rules are required.")

    normalized_rules = []
    seen_delivery_days = set()
    for rule in cutoff_rules:
        if not isinstance(rule, dict):
            continue
        delivery_day = str(rule.get("delivery_day") or "").strip()
        if not delivery_day:
            continue
        if delivery_day not in DAY_INDEX:
            raise InvalidInventoryOrderingPreferenceError("Select valid delivery days.")
        if delivery_day in seen_delivery_days:
            continue
        seen_delivery_days.add(delivery_day)
        normalized_rules.append(
            {
                "delivery_day": delivery_day,
                "cutoff_day": _normalize_cutoff_day(rule.get("cutoff_day")),
                "cutoff_time": _normalize_cutoff_time(rule.get("cutoff_time")),
            }
        )

    if not normalized_rules:
        raise InvalidInventoryOrderingPreferenceError("Select at least one delivery day.")
    return sorted(normalized_rules, key=lambda rule: DAY_INDEX[rule["delivery_day"]])


def _preference_payload(row) -> dict:
    cutoff_rules = json.loads(row[5] or "[]")
    day_labels = dict(DAY_OPTIONS)
    delivery_days = [rule["delivery_day"] for rule in cutoff_rules]
    return {
        "inventory_ordering_preference_id": int(row[0]),
        "user_id": row[1],
        "item_category": row[2],
        "item_category_label": ITEM_CATEGORY_LABELS.get(row[2], row[2].title()),
        "vendor_name": row[3],
        "ordering_frequency": row[4],
        "ordering_frequency_label": dict(ORDERING_FREQUENCY_OPTIONS).get(row[4], row[4].title()),
        "delivery_days": delivery_days,
        "delivery_days_display": ", ".join(day_labels.get(day, day.title()) for day in delivery_days),
        "cutoff_rules": [
            {
                **rule,
                "delivery_day_label": day_labels.get(rule["delivery_day"], rule["delivery_day"].title()),
                "cutoff_day_label": day_labels.get(rule["cutoff_day"], rule["cutoff_day"].title()),
                "display": (
                    f"{day_labels.get(rule['delivery_day'], rule['delivery_day'].title())}: "
                    f"{day_labels.get(rule['cutoff_day'], rule['cutoff_day'].title())} {rule['cutoff_time']}"
                ),
            }
            for rule in cutoff_rules
        ],
        "cutoff_rules_display": "; ".join(
            f"{day_labels.get(rule['delivery_day'], rule['delivery_day'].title())}: "
            f"{day_labels.get(rule['cutoff_day'], rule['cutoff_day'].title())} {rule['cutoff_time']}"
            for rule in cutoff_rules
        ),
        "preferred_lead_days": int(row[6] or 0),
        "status": row[7],
        "created_at": row[8],
        "updated_at": row[9],
    }


def list_inventory_ordering_preferences(user_id: str) -> list[dict]:
    initialize_database()
    normalized_user_id = _normalize_user_id(user_id)
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                inventory_ordering_preference_id,
                user_id,
                item_category,
                vendor_name,
                ordering_frequency,
                cutoff_rules_json,
                preferred_lead_days,
                status,
                created_at,
                updated_at
            FROM inventory_ordering_preference
            WHERE user_id = ?
              AND status = 'active'
            ORDER BY item_category ASC
            """,
            (normalized_user_id,),
        )
        return [_preference_payload(row) for row in cursor.fetchall()]


def get_inventory_ordering_preference_map(user_id: str) -> dict[str, dict]:
    return {
        preference["item_category"]: preference
        for preference in list_inventory_ordering_preferences(user_id)
    }


def upsert_inventory_ordering_preference(
    *,
    user_id: str,
    item_category,
    vendor_name,
    ordering_frequency="as_needed",
    cutoff_rules=None,
    preferred_lead_days=0,
) -> dict:
    initialize_database()
    normalized_user_id = _normalize_user_id(user_id)
    normalized_category = _normalize_item_category(item_category)
    normalized_vendor = _normalize_text(vendor_name, "Vendor name")
    normalized_frequency = _normalize_frequency(ordering_frequency)
    normalized_cutoff_rules = _normalize_cutoff_rules(cutoff_rules)
    normalized_lead_days = _normalize_lead_days(preferred_lead_days)
    cutoff_rules_json = json.dumps(normalized_cutoff_rules)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO inventory_ordering_preference (
                user_id,
                item_category,
                vendor_name,
                ordering_frequency,
                cutoff_rules_json,
                preferred_lead_days,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 'active', datetime('now'), datetime('now'))
            ON CONFLICT(user_id, item_category) DO UPDATE SET
                vendor_name = excluded.vendor_name,
                ordering_frequency = excluded.ordering_frequency,
                cutoff_rules_json = excluded.cutoff_rules_json,
                preferred_lead_days = excluded.preferred_lead_days,
                status = 'active',
                updated_at = datetime('now')
            """,
            (
                normalized_user_id,
                normalized_category,
                normalized_vendor,
                normalized_frequency,
                cutoff_rules_json,
                normalized_lead_days,
            ),
        )
        conn.commit()

    return get_inventory_ordering_preference_map(normalized_user_id)[normalized_category]


def upsert_inventory_ordering_preferences_for_categories(
    *,
    user_id: str,
    item_categories,
    vendor_name,
    ordering_frequency="as_needed",
    cutoff_rules=None,
    preferred_lead_days=0,
) -> list[dict]:
    normalized_categories = _normalize_item_categories(item_categories)
    return [
        upsert_inventory_ordering_preference(
            user_id=user_id,
            item_category=category,
            vendor_name=vendor_name,
            ordering_frequency=ordering_frequency,
            cutoff_rules=cutoff_rules,
            preferred_lead_days=preferred_lead_days,
        )
        for category in normalized_categories
    ]


def delete_inventory_ordering_preference(*, user_id: str, item_category) -> None:
    initialize_database()
    normalized_user_id = _normalize_user_id(user_id)
    normalized_category = _normalize_item_category(item_category)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE inventory_ordering_preference
            SET status = 'inactive',
                updated_at = datetime('now')
            WHERE user_id = ?
              AND item_category = ?
              AND status = 'active'
            """,
            (normalized_user_id, normalized_category),
        )
        if cursor.rowcount == 0:
            raise InvalidInventoryOrderingPreferenceError("Inventory planning preference not found.")
        conn.commit()


def _parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        return None


def _format_date(value: date) -> str:
    return f"{value.strftime('%b')} {value.day}"


def _format_datetime(value: datetime) -> str:
    hour = value.strftime("%I").lstrip("0") or "0"
    return f"{value.strftime('%b')} {value.day} {hour}:{value.strftime('%M')} {value.strftime('%p').lower()}"


def _previous_or_same_weekday(anchor: date, day_name: str) -> date:
    delta_days = (anchor.weekday() - DAY_INDEX[day_name]) % 7
    return anchor - timedelta(days=delta_days)


def _cutoff_rule_by_delivery_day(preference: dict) -> dict[str, dict]:
    return {
        rule["delivery_day"]: rule
        for rule in preference.get("cutoff_rules", [])
    }


def _delivery_candidates_before(
    usage_date: date,
    cutoff_rules: list[dict],
    *,
    earliest_date: date,
) -> list[date]:
    delivery_days = [rule["delivery_day"] for rule in cutoff_rules]
    candidates = []
    lookback_days = max((usage_date - earliest_date).days, 0)
    for offset in range(0, lookback_days + 1):
        candidate = usage_date - timedelta(days=offset)
        if candidate >= earliest_date and any(candidate.weekday() == DAY_INDEX[day] for day in delivery_days):
            candidates.append(candidate)
    return sorted(candidates)


def _cutoff_for_delivery(delivery_date: date, cutoff_rule: dict) -> datetime:
    cutoff_date = _previous_or_same_weekday(delivery_date, cutoff_rule["cutoff_day"])
    cutoff_clock = time.fromisoformat(cutoff_rule["cutoff_time"])
    return datetime.combine(cutoff_date, cutoff_clock)


def build_ordering_window_for_usage(
    *,
    usage_date: str,
    item_category: str,
    preference: dict | None,
    today: date | None = None,
) -> dict:
    normalized_today = today or date.today()
    parsed_usage_date = _parse_iso_date(usage_date)
    if parsed_usage_date is None:
        return {
            "preference_source": "unknown_date",
            "planning_review_message": "Usage date is unavailable for ordering-window calculation.",
            "include_in_current_window": False,
        }

    if not preference:
        horizon_end = normalized_today + timedelta(days=DEFAULT_PLANNING_HORIZON_DAYS)
        return {
            "preference_source": "default",
            "vendor_name": "Default planning",
            "preferred_in_house_date": parsed_usage_date.isoformat(),
            "preferred_in_house_display": _format_date(parsed_usage_date),
            "planned_delivery_date": "",
            "planned_delivery_display": "",
            "order_cutoff_deadline": "",
            "order_cutoff_display": "",
            "planning_window_end": horizon_end.isoformat(),
            "planning_window_label": f"Next {DEFAULT_PLANNING_HORIZON_DAYS} days",
            "include_in_current_window": parsed_usage_date <= horizon_end,
            "planning_review_message": "Using default 7-day planning window.",
        }

    preferred_in_house_date = parsed_usage_date - timedelta(days=int(preference["preferred_lead_days"]))
    cutoff_rules_by_delivery_day = _cutoff_rule_by_delivery_day(preference)
    candidates = _delivery_candidates_before(
        parsed_usage_date,
        preference["cutoff_rules"],
        earliest_date=normalized_today,
    )
    satisfying_candidates = [candidate for candidate in candidates if candidate <= preferred_in_house_date]
    planning_review_message = ""
    if satisfying_candidates:
        planned_delivery_date = satisfying_candidates[-1]
    elif candidates:
        planned_delivery_date = candidates[-1]
        planning_review_message = "Preferred lead time cannot be met by configured delivery days."
    else:
        return {
            "preference_source": "configured",
            "vendor_name": preference["vendor_name"],
            "planning_review_message": "No valid delivery day found before usage date.",
            "include_in_current_window": False,
        }

    delivery_day = DAY_OPTIONS[planned_delivery_date.weekday()][0]
    cutoff_rule = cutoff_rules_by_delivery_day[delivery_day]
    cutoff_deadline = _cutoff_for_delivery(planned_delivery_date, cutoff_rule)
    next_cutoff = cutoff_deadline if cutoff_deadline.date() >= normalized_today else None
    include_in_current_window = bool(next_cutoff and cutoff_deadline.date() == next_cutoff.date())

    return {
        "preference_source": "configured",
        "vendor_name": preference["vendor_name"],
        "preferred_in_house_date": preferred_in_house_date.isoformat(),
        "preferred_in_house_display": _format_date(preferred_in_house_date),
        "planned_delivery_date": planned_delivery_date.isoformat(),
        "planned_delivery_display": _format_date(planned_delivery_date),
        "planned_delivery_day": cutoff_rule["delivery_day"],
        "planned_delivery_day_label": dict(DAY_OPTIONS).get(cutoff_rule["delivery_day"], cutoff_rule["delivery_day"].title()),
        "cutoff_day": cutoff_rule["cutoff_day"],
        "cutoff_day_label": dict(DAY_OPTIONS).get(cutoff_rule["cutoff_day"], cutoff_rule["cutoff_day"].title()),
        "cutoff_time": cutoff_rule["cutoff_time"],
        "order_cutoff_deadline": cutoff_deadline.isoformat(timespec="minutes"),
        "order_cutoff_display": _format_datetime(cutoff_deadline),
        "planning_window_end": planned_delivery_date.isoformat(),
        "planning_window_label": f"{preference['vendor_name']} cutoff {_format_datetime(cutoff_deadline)}",
        "include_in_current_window": include_in_current_window,
        "planning_review_message": planning_review_message,
        "item_category": item_category,
        "item_category_label": ITEM_CATEGORY_LABELS.get(item_category, item_category.title()),
    }
