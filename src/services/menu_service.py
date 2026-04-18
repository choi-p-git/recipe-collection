import json

from db import get_connection, initialize_database


class InvalidMenuPayloadError(ValueError):
    """Raised when the menu create payload is invalid."""


class InvalidMenuSlotAssignmentError(ValueError):
    """Raised when slot assignment payload is invalid."""


def _normalize_name(value: str) -> str:
    return " ".join(str(value or "").split())


def _normalize_unique_values(values: list[str], allowed_values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    allowed = set(allowed_values)

    for value in values:
        cleaned = str(value or "").strip().lower()
        if cleaned in allowed and cleaned not in seen:
            normalized.append(cleaned)
            seen.add(cleaned)

    return normalized


def _normalize_unique_concepts(values: list[str], allowed_values: list[str]) -> list[str]:
    return _normalize_unique_values(values, allowed_values)


def create_menu(
    *,
    menu_name: str,
    author_user_id: str,
    author_display_name: str,
    service_days: list[str],
    meal_periods: list[str],
    concepts: list[str],
    menu_length_weeks,
    allowed_service_days: list[str],
    allowed_meal_periods: list[str],
    allowed_concepts: list[str],
) -> int:
    initialize_database()

    normalized_name = _normalize_name(menu_name)
    if not normalized_name:
        raise InvalidMenuPayloadError("Menu name is required.")

    normalized_service_days = _normalize_unique_values(service_days, allowed_service_days)
    if not normalized_service_days:
        raise InvalidMenuPayloadError("Select at least one service day.")

    normalized_meal_periods = _normalize_unique_values(meal_periods, allowed_meal_periods)
    if not normalized_meal_periods:
        raise InvalidMenuPayloadError("Select at least one meal period.")

    normalized_concepts = _normalize_unique_concepts(concepts, allowed_concepts)
    if not normalized_concepts:
        raise InvalidMenuPayloadError("Select at least one concept.")

    try:
        normalized_menu_length_weeks = int(menu_length_weeks)
    except (TypeError, ValueError):
        raise InvalidMenuPayloadError("Menu length in weeks must be a whole number.")

    if normalized_menu_length_weeks <= 0:
        raise InvalidMenuPayloadError("Menu length in weeks must be greater than 0.")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO menu (
                menu_name,
                author_user_id,
                author_display_name,
                service_days_json,
                meal_periods_json,
                concepts_json,
                menu_length_weeks,
                status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', datetime('now'), datetime('now'))
            """,
            (
                normalized_name,
                author_user_id,
                author_display_name,
                json.dumps(normalized_service_days),
                json.dumps(normalized_meal_periods),
                json.dumps(normalized_concepts),
                normalized_menu_length_weeks,
            ),
        )
        menu_id = int(cursor.lastrowid)

        for week_number in range(1, normalized_menu_length_weeks + 1):
            for day_of_week in normalized_service_days:
                for meal_period in normalized_meal_periods:
                    for concept_name in normalized_concepts:
                        cursor.execute(
                            """
                            INSERT INTO menu_slot (
                                menu_id,
                                week_number,
                                day_of_week,
                                meal_period,
                                concept_name,
                                created_at,
                                updated_at
                            )
                            VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                            """,
                            (
                                menu_id,
                                week_number,
                                day_of_week,
                                meal_period,
                                concept_name,
                            ),
                        )

        conn.commit()
        return menu_id


def replace_menu_slot_items(
    *,
    menu_slot_id: int,
    selected_item_ids: list[str | int],
) -> None:
    initialize_database()

    normalized_item_ids: list[int] = []
    seen: set[int] = set()
    for item_id in selected_item_ids:
        try:
            normalized_item_id = int(item_id)
        except (TypeError, ValueError):
            raise InvalidMenuSlotAssignmentError("Each selected item must be valid.")

        if normalized_item_id not in seen:
            normalized_item_ids.append(normalized_item_id)
            seen.add(normalized_item_id)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT menu_slot_id FROM menu_slot WHERE menu_slot_id = ?",
            (menu_slot_id,),
        )
        if cursor.fetchone() is None:
            raise InvalidMenuSlotAssignmentError("Menu slot not found.")

        if normalized_item_ids:
            cursor.execute(
                "SELECT item_id, item_type, status FROM item WHERE item_id IN ({})".format(
                    ", ".join("?" for _ in normalized_item_ids)
                ),
                normalized_item_ids,
            )
            rows = cursor.fetchall()
            row_lookup = {row[0]: row for row in rows}

            for item_id in normalized_item_ids:
                row = row_lookup.get(item_id)
                if row is None:
                    raise InvalidMenuSlotAssignmentError("One or more selected items were not found.")
                if row[1] not in {"recipe", "base_food"}:
                    raise InvalidMenuSlotAssignmentError("Selected item type is not supported in Menu Builder.")
                if row[2] != "live":
                    raise InvalidMenuSlotAssignmentError("Only live items can be assigned to a menu slot.")

        cursor.execute(
            "DELETE FROM menu_slot_item WHERE menu_slot_id = ?",
            (menu_slot_id,),
        )

        for index, item_id in enumerate(normalized_item_ids, start=1):
            cursor.execute(
                """
                INSERT INTO menu_slot_item (
                    menu_slot_id,
                    item_id,
                    item_sequence,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, datetime('now'), datetime('now'))
                """,
                (menu_slot_id, item_id, index),
            )

        cursor.execute(
            "UPDATE menu_slot SET updated_at = datetime('now') WHERE menu_slot_id = ?",
            (menu_slot_id,),
        )
        conn.commit()
