import json

from db import get_connection, initialize_database

DAY_OF_WEEK_ORDER = {
    "sunday": 0,
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
}
MEAL_PERIOD_ORDER = {
    "breakfast": 0,
    "lunch": 1,
    "dinner": 2,
}


class InvalidMenuPayloadError(ValueError):
    """Raised when the menu create payload is invalid."""


class InvalidMenuSlotAssignmentError(ValueError):
    """Raised when slot assignment payload is invalid."""


class InvalidMenuDeleteError(ValueError):
    """Raised when a menu delete request is invalid."""


class InvalidMenuSlotActionError(ValueError):
    """Raised when a slot clear/copy/paste request is invalid."""


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


def _validate_menu_payload(
    *,
    menu_name: str,
    service_days: list[str],
    meal_periods: list[str],
    concepts: list[str],
    menu_length_weeks,
    allowed_service_days: list[str],
    allowed_meal_periods: list[str],
    allowed_concepts: list[str],
) -> tuple[str, list[str], list[str], list[str], int]:
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

    return (
        normalized_name,
        normalized_service_days,
        normalized_meal_periods,
        normalized_concepts,
        normalized_menu_length_weeks,
    )


def _get_menu_slot_context(cursor, menu_slot_id: int) -> tuple[int, str]:
    cursor.execute(
        """
        SELECT ms.menu_id, m.author_user_id
        FROM menu_slot ms
        JOIN menu m
          ON m.menu_id = ms.menu_id
        WHERE ms.menu_slot_id = ?
        """,
        (menu_slot_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise InvalidMenuSlotActionError("Menu slot not found.")
    return int(row[0]), str(row[1])


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

    (
        normalized_name,
        normalized_service_days,
        normalized_meal_periods,
        normalized_concepts,
        normalized_menu_length_weeks,
    ) = _validate_menu_payload(
        menu_name=menu_name,
        service_days=service_days,
        meal_periods=meal_periods,
        concepts=concepts,
        menu_length_weeks=menu_length_weeks,
        allowed_service_days=allowed_service_days,
        allowed_meal_periods=allowed_meal_periods,
        allowed_concepts=allowed_concepts,
    )

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


def update_menu_config(
    *,
    menu_id: int,
    actor_user_id: str,
    menu_name: str,
    service_days: list[str],
    meal_periods: list[str],
    concepts: list[str],
    menu_length_weeks,
    allowed_service_days: list[str],
    allowed_meal_periods: list[str],
    allowed_concepts: list[str],
) -> None:
    initialize_database()

    (
        normalized_name,
        normalized_service_days,
        normalized_meal_periods,
        normalized_concepts,
        normalized_menu_length_weeks,
    ) = _validate_menu_payload(
        menu_name=menu_name,
        service_days=service_days,
        meal_periods=meal_periods,
        concepts=concepts,
        menu_length_weeks=menu_length_weeks,
        allowed_service_days=allowed_service_days,
        allowed_meal_periods=allowed_meal_periods,
        allowed_concepts=allowed_concepts,
    )

    desired_slot_keys = {
        (week_number, day_of_week, meal_period, concept_name)
        for week_number in range(1, normalized_menu_length_weeks + 1)
        for day_of_week in normalized_service_days
        for meal_period in normalized_meal_periods
        for concept_name in normalized_concepts
    }

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT author_user_id
            FROM menu
            WHERE menu_id = ?
            """,
            (menu_id,),
        )
        menu_row = cursor.fetchone()
        if menu_row is None:
            raise InvalidMenuPayloadError("Menu not found.")
        if menu_row[0] != actor_user_id:
            raise InvalidMenuPayloadError("You can only edit menus you created.")

        cursor.execute(
            """
            SELECT menu_slot_id, week_number, day_of_week, meal_period, concept_name
            FROM menu_slot
            WHERE menu_id = ?
            """,
            (menu_id,),
        )
        existing_slots = cursor.fetchall()
        existing_slot_lookup = {
            (row[1], row[2], row[3], row[4]): row[0]
            for row in existing_slots
        }

        slot_ids_to_delete = [
            row[0]
            for row in existing_slots
            if (row[1], row[2], row[3], row[4]) not in desired_slot_keys
        ]
        if slot_ids_to_delete:
            cursor.execute(
                "DELETE FROM menu_slot WHERE menu_slot_id IN ({})".format(
                    ", ".join("?" for _ in slot_ids_to_delete)
                ),
                slot_ids_to_delete,
            )

        missing_slot_keys = sorted(desired_slot_keys - set(existing_slot_lookup.keys()))
        for week_number, day_of_week, meal_period, concept_name in missing_slot_keys:
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

        cursor.execute(
            """
            UPDATE menu
            SET menu_name = ?,
                service_days_json = ?,
                meal_periods_json = ?,
                concepts_json = ?,
                menu_length_weeks = ?,
                updated_at = datetime('now')
            WHERE menu_id = ?
            """,
            (
                normalized_name,
                json.dumps(normalized_service_days),
                json.dumps(normalized_meal_periods),
                json.dumps(normalized_concepts),
                normalized_menu_length_weeks,
                menu_id,
            ),
        )
        conn.commit()


def replace_menu_slot_items(
    *,
    menu_slot_id: int,
    selected_item_ids: list[str | int],
    actor_user_id: str,
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
        _, owner_user_id = _get_menu_slot_context(cursor, menu_slot_id)
        if owner_user_id != actor_user_id:
            raise InvalidMenuSlotAssignmentError("You can only edit menu slots for menus you created.")

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

        _sync_slot_items(cursor, menu_slot_id, normalized_item_ids)
        conn.commit()


def get_menu_slot_assignment_ids(*, menu_slot_id: int, actor_user_id: str) -> list[int]:
    initialize_database()

    with get_connection() as conn:
        cursor = conn.cursor()
        _, owner_user_id = _get_menu_slot_context(cursor, menu_slot_id)
        if owner_user_id != actor_user_id:
            raise InvalidMenuSlotActionError("You can only copy menu slots for menus you created.")

        cursor.execute(
            """
            SELECT item_id
            FROM menu_slot_item
            WHERE menu_slot_id = ?
            ORDER BY item_sequence ASC, menu_slot_item_id ASC
            """,
            (menu_slot_id,),
        )
        return [int(row[0]) for row in cursor.fetchall()]


def clear_menu_slot(*, menu_slot_id: int, actor_user_id: str) -> None:
    initialize_database()

    with get_connection() as conn:
        cursor = conn.cursor()
        _, owner_user_id = _get_menu_slot_context(cursor, menu_slot_id)
        if owner_user_id != actor_user_id:
            raise InvalidMenuSlotActionError("You can only clear menu slots for menus you created.")

        cursor.execute(
            "DELETE FROM menu_slot_item WHERE menu_slot_id = ?",
            (menu_slot_id,),
        )
        cursor.execute(
            "UPDATE menu_slot SET updated_at = datetime('now') WHERE menu_slot_id = ?",
            (menu_slot_id,),
        )
        conn.commit()


def paste_menu_slot_assignment_ids(
    *,
    menu_slot_id: int,
    actor_user_id: str,
    copied_item_ids: list[str | int],
) -> None:
    if not copied_item_ids:
        raise InvalidMenuSlotActionError("No copied slot items are available to paste.")

    try:
        replace_menu_slot_items(
            menu_slot_id=menu_slot_id,
            selected_item_ids=copied_item_ids,
            actor_user_id=actor_user_id,
        )
    except InvalidMenuSlotAssignmentError as exc:
        raise InvalidMenuSlotActionError(str(exc))


def _load_menu_slots(cursor, *, menu_id: int, actor_user_id: str) -> list[dict]:
    cursor.execute(
        """
        SELECT
            ms.menu_slot_id,
            ms.menu_id,
            ms.week_number,
            ms.day_of_week,
            ms.meal_period,
            ms.concept_name,
            m.author_user_id
        FROM menu_slot ms
        JOIN menu m
          ON m.menu_id = ms.menu_id
        WHERE ms.menu_id = ?
        """,
        (menu_id,),
    )
    rows = cursor.fetchall()
    if not rows:
        raise InvalidMenuSlotActionError("Menu not found.")
    if rows[0][6] != actor_user_id:
        raise InvalidMenuSlotActionError("You can only edit menu slots for menus you created.")
    return [
        {
            "menu_slot_id": int(row[0]),
            "menu_id": int(row[1]),
            "week_number": int(row[2]),
            "day_of_week": row[3],
            "meal_period": row[4],
            "concept_name": row[5],
        }
        for row in rows
    ]


def _normalize_slot_ids(selected_slot_ids: list[str | int]) -> list[int]:
    normalized_slot_ids: list[int] = []
    seen: set[int] = set()
    for slot_id in selected_slot_ids:
        try:
            normalized_slot_id = int(slot_id)
        except (TypeError, ValueError):
            raise InvalidMenuSlotActionError("Each selected slot must be valid.")
        if normalized_slot_id not in seen:
            normalized_slot_ids.append(normalized_slot_id)
            seen.add(normalized_slot_id)
    if not normalized_slot_ids:
        raise InvalidMenuSlotActionError("Select at least one slot.")
    return normalized_slot_ids


def _get_selected_slots(slots: list[dict], selected_slot_ids: list[str | int]) -> list[dict]:
    normalized_slot_ids = set(_normalize_slot_ids(selected_slot_ids))
    selected_slots = [slot for slot in slots if slot["menu_slot_id"] in normalized_slot_ids]
    if len(selected_slots) != len(normalized_slot_ids):
        raise InvalidMenuSlotActionError("One or more selected slots were not found.")
    return selected_slots


def _sort_slots(slots: list[dict]) -> list[dict]:
    return sorted(
        slots,
        key=lambda slot: (
            slot["week_number"],
            DAY_OF_WEEK_ORDER.get(slot["day_of_week"], 99),
            MEAL_PERIOD_ORDER.get(slot["meal_period"], 99),
            slot["concept_name"],
            slot["menu_slot_id"],
        ),
    )


def _load_slot_item_ids(cursor, menu_slot_ids: list[int]) -> dict[int, list[int]]:
    if not menu_slot_ids:
        return {}
    cursor.execute(
        """
        SELECT menu_slot_id, item_id
        FROM menu_slot_item
        WHERE menu_slot_id IN ({})
        ORDER BY menu_slot_id ASC, item_sequence ASC, menu_slot_item_id ASC
        """.format(", ".join("?" for _ in menu_slot_ids)),
        menu_slot_ids,
    )
    lookup: dict[int, list[int]] = {}
    for row in cursor.fetchall():
        lookup.setdefault(int(row[0]), []).append(int(row[1]))
    return lookup


def _expand_slot_scope(slots: list[dict], selected_slots: list[dict], scope: str) -> list[int]:
    selected_slot_ids: set[int] = set()
    if scope == "cell":
        selected_slot_ids = {slot["menu_slot_id"] for slot in selected_slots}
    elif scope == "concept":
        concept_keys = {
            (slot["week_number"], slot["meal_period"], slot["concept_name"])
            for slot in selected_slots
        }
        selected_slot_ids = {
            slot["menu_slot_id"]
            for slot in slots
            if (slot["week_number"], slot["meal_period"], slot["concept_name"]) in concept_keys
        }
    elif scope == "day":
        day_keys = {
            (slot["week_number"], slot["day_of_week"])
            for slot in selected_slots
        }
        selected_slot_ids = {
            slot["menu_slot_id"]
            for slot in slots
            if (slot["week_number"], slot["day_of_week"]) in day_keys
        }
    elif scope == "week":
        week_keys = {slot["week_number"] for slot in selected_slots}
        selected_slot_ids = {
            slot["menu_slot_id"]
            for slot in slots
            if slot["week_number"] in week_keys
        }
    else:
        raise InvalidMenuSlotActionError("Unsupported clear scope.")

    return sorted(selected_slot_ids)


def _build_target_concept_groups(slots: list[dict], selected_slots: list[dict]) -> list[dict]:
    groups: list[dict] = []
    seen: set[tuple[int, str, str]] = set()
    for slot in _sort_slots(selected_slots):
        group_key = (slot["week_number"], slot["meal_period"], slot["concept_name"])
        if group_key in seen:
            continue
        seen.add(group_key)
        groups.append(
            {
                "group_key": group_key,
                "slots": _sort_slots(
                    [
                        candidate
                        for candidate in slots
                        if candidate["week_number"] == slot["week_number"]
                        and candidate["meal_period"] == slot["meal_period"]
                        and candidate["concept_name"] == slot["concept_name"]
                    ]
                ),
            }
        )
    return groups


def _validate_live_menu_items(cursor, item_ids: list[int]) -> None:
    if not item_ids:
        return
    cursor.execute(
        "SELECT item_id, item_type, status FROM item WHERE item_id IN ({})".format(
            ", ".join("?" for _ in item_ids)
        ),
        item_ids,
    )
    rows = cursor.fetchall()
    row_lookup = {int(row[0]): row for row in rows}
    for item_id in item_ids:
        row = row_lookup.get(item_id)
        if row is None:
            raise InvalidMenuSlotActionError("One or more copied items were not found.")
        if row[1] not in {"recipe", "base_food"}:
            raise InvalidMenuSlotActionError("Copied item type is not supported in Menu Builder.")
        if row[2] != "live":
            raise InvalidMenuSlotActionError("Only live items can be pasted into a menu slot.")


def _sync_slot_items(cursor, menu_slot_id: int, item_ids: list[int]) -> None:
    cursor.execute(
        """
        SELECT menu_slot_item_id, item_id
        FROM menu_slot_item
        WHERE menu_slot_id = ?
        ORDER BY item_sequence ASC, menu_slot_item_id ASC
        """,
        (menu_slot_id,),
    )
    existing_rows = [(int(row[0]), int(row[1])) for row in cursor.fetchall()]
    existing_by_item_id: dict[int, int] = {}
    duplicate_slot_item_ids: set[int] = set()
    for slot_item_id, item_id in existing_rows:
        if item_id in existing_by_item_id:
            duplicate_slot_item_ids.add(slot_item_id)
        else:
            existing_by_item_id[item_id] = slot_item_id

    desired_item_ids = set(item_ids)
    slot_item_ids_to_delete = [
        slot_item_id
        for slot_item_id, item_id in existing_rows
        if item_id not in desired_item_ids or slot_item_id in duplicate_slot_item_ids
    ]
    if slot_item_ids_to_delete:
        cursor.execute(
            "DELETE FROM menu_slot_item WHERE menu_slot_item_id IN ({})".format(
                ", ".join("?" for _ in slot_item_ids_to_delete)
            ),
            slot_item_ids_to_delete,
        )

    preserved_slot_item_ids = [
        existing_by_item_id[item_id]
        for item_id in item_ids
        if item_id in existing_by_item_id
    ]
    for slot_item_id in preserved_slot_item_ids:
        cursor.execute(
            """
            UPDATE menu_slot_item
            SET item_sequence = ?,
                updated_at = datetime('now')
            WHERE menu_slot_item_id = ?
            """,
            (1_000_000 + slot_item_id, slot_item_id),
        )

    for index, item_id in enumerate(item_ids, start=1):
        existing_slot_item_id = existing_by_item_id.get(item_id)
        if existing_slot_item_id is not None:
            cursor.execute(
                """
                UPDATE menu_slot_item
                SET item_sequence = ?,
                    updated_at = datetime('now')
                WHERE menu_slot_item_id = ?
                """,
                (index, existing_slot_item_id),
            )
        else:
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


def _replace_slot_items(cursor, menu_slot_id: int, item_ids: list[int]) -> None:
    _sync_slot_items(cursor, menu_slot_id, item_ids)


def delete_menu(*, menu_id: int, actor_user_id: str) -> None:
    initialize_database()

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT author_user_id FROM menu WHERE menu_id = ?",
            (menu_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise InvalidMenuDeleteError("Menu not found.")
        if row[0] != actor_user_id:
            raise InvalidMenuDeleteError("You can only delete menus you created.")

        cursor.execute("DELETE FROM menu WHERE menu_id = ?", (menu_id,))
        conn.commit()


def copy_menu_slots(
    *,
    menu_id: int,
    actor_user_id: str,
    selected_slot_ids: list[str | int],
    scope: str,
) -> dict:
    initialize_database()

    with get_connection() as conn:
        cursor = conn.cursor()
        slots = _load_menu_slots(cursor, menu_id=menu_id, actor_user_id=actor_user_id)
        selected_slots = _get_selected_slots(slots, selected_slot_ids)
        slot_item_lookup = _load_slot_item_ids(cursor, [slot["menu_slot_id"] for slot in slots])

        if scope == "cell":
            entries = [
                {
                    "slot_signature": {
                        "week_number": slot["week_number"],
                        "day_of_week": slot["day_of_week"],
                        "meal_period": slot["meal_period"],
                        "concept_name": slot["concept_name"],
                    },
                    "item_ids": slot_item_lookup.get(slot["menu_slot_id"], []),
                }
                for slot in _sort_slots(selected_slots)
            ]
        elif scope == "concept":
            entries = []
            seen_groups: set[tuple[int, str, str]] = set()
            for slot in _sort_slots(selected_slots):
                group_key = (slot["week_number"], slot["meal_period"], slot["concept_name"])
                if group_key in seen_groups:
                    continue
                seen_groups.add(group_key)
                group_slots = _sort_slots(
                    [
                        candidate
                        for candidate in slots
                        if candidate["week_number"] == slot["week_number"]
                        and candidate["meal_period"] == slot["meal_period"]
                        and candidate["concept_name"] == slot["concept_name"]
                    ]
                )
                entries.append(
                    {
                        "group_signature": {
                            "week_number": slot["week_number"],
                            "meal_period": slot["meal_period"],
                            "concept_name": slot["concept_name"],
                        },
                        "days": {
                            group_slot["day_of_week"]: slot_item_lookup.get(group_slot["menu_slot_id"], [])
                            for group_slot in group_slots
                        },
                    }
                )
        elif scope == "day":
            entries = []
            seen_days: set[tuple[int, str]] = set()
            for slot in _sort_slots(selected_slots):
                day_key = (slot["week_number"], slot["day_of_week"])
                if day_key in seen_days:
                    continue
                seen_days.add(day_key)
                day_slots = _sort_slots(
                    [
                        candidate
                        for candidate in slots
                        if candidate["week_number"] == slot["week_number"]
                        and candidate["day_of_week"] == slot["day_of_week"]
                    ]
                )
                entries.append(
                    {
                        "day_signature": {
                            "week_number": slot["week_number"],
                            "day_of_week": slot["day_of_week"],
                        },
                        "slots": [
                            {
                                "meal_period": day_slot["meal_period"],
                                "concept_name": day_slot["concept_name"],
                                "item_ids": slot_item_lookup.get(day_slot["menu_slot_id"], []),
                            }
                            for day_slot in day_slots
                        ],
                    }
                )
        elif scope == "week":
            entries = []
            seen_weeks: set[int] = set()
            for slot in _sort_slots(selected_slots):
                week_number = slot["week_number"]
                if week_number in seen_weeks:
                    continue
                seen_weeks.add(week_number)
                week_slots = _sort_slots(
                    [candidate for candidate in slots if candidate["week_number"] == week_number]
                )
                entries.append(
                    {
                        "week_signature": {
                            "week_number": week_number,
                        },
                        "slots": [
                            {
                                "day_of_week": week_slot["day_of_week"],
                                "meal_period": week_slot["meal_period"],
                                "concept_name": week_slot["concept_name"],
                                "item_ids": slot_item_lookup.get(week_slot["menu_slot_id"], []),
                            }
                            for week_slot in week_slots
                        ],
                    }
                )
        else:
            raise InvalidMenuSlotActionError("Unsupported copy scope.")

    return {
        "mode": scope,
        "entries": entries,
        "copied_count": len(entries),
    }


def clear_menu_slots(
    *,
    menu_id: int,
    actor_user_id: str,
    selected_slot_ids: list[str | int],
    scope: str,
) -> int:
    initialize_database()

    with get_connection() as conn:
        cursor = conn.cursor()
        slots = _load_menu_slots(cursor, menu_id=menu_id, actor_user_id=actor_user_id)
        selected_slots = _get_selected_slots(slots, selected_slot_ids)
        slot_ids_to_clear = _expand_slot_scope(slots, selected_slots, scope)

        cursor.execute(
            "DELETE FROM menu_slot_item WHERE menu_slot_id IN ({})".format(
                ", ".join("?" for _ in slot_ids_to_clear)
            ),
            slot_ids_to_clear,
        )
        cursor.execute(
            "UPDATE menu_slot SET updated_at = datetime('now') WHERE menu_slot_id IN ({})".format(
                ", ".join("?" for _ in slot_ids_to_clear)
            ),
            slot_ids_to_clear,
        )
        conn.commit()

    return len(slot_ids_to_clear)


def paste_menu_slots(
    *,
    menu_id: int,
    actor_user_id: str,
    selected_slot_ids: list[str | int],
    clipboard: dict | None,
) -> int:
    initialize_database()

    if not clipboard or not clipboard.get("entries"):
        raise InvalidMenuSlotActionError("No copied slot items are available to paste.")

    with get_connection() as conn:
        cursor = conn.cursor()
        slots = _load_menu_slots(cursor, menu_id=menu_id, actor_user_id=actor_user_id)
        selected_slots = _get_selected_slots(slots, selected_slot_ids)

        if clipboard.get("mode") == "cell":
            target_slots = _sort_slots(selected_slots)
            entries = clipboard["entries"]
            if len(entries) == 1:
                target_payloads = [(slot["menu_slot_id"], entries[0]["item_ids"]) for slot in target_slots]
            elif len(entries) == len(target_slots):
                target_payloads = [
                    (slot["menu_slot_id"], entry["item_ids"])
                    for slot, entry in zip(target_slots, entries)
                ]
            else:
                raise InvalidMenuSlotActionError("Select the same number of target cells as copied cells, or copy a single cell.")
        elif clipboard.get("mode") == "concept":
            target_groups = _build_target_concept_groups(slots, selected_slots)
            entries = clipboard["entries"]
            if len(entries) == 1:
                source_entries = entries * len(target_groups)
            elif len(entries) == len(target_groups):
                source_entries = entries
            else:
                raise InvalidMenuSlotActionError("Select the same number of target concepts as copied concepts, or copy a single concept.")

            target_payloads = []
            for target_group, source_entry in zip(target_groups, source_entries):
                for group_slot in target_group["slots"]:
                    target_payloads.append(
                        (
                            group_slot["menu_slot_id"],
                            source_entry["days"].get(group_slot["day_of_week"], []),
                        )
                    )
        elif clipboard.get("mode") == "day":
            target_days: list[dict] = []
            seen_days: set[tuple[int, str]] = set()
            for slot in _sort_slots(selected_slots):
                day_key = (slot["week_number"], slot["day_of_week"])
                if day_key in seen_days:
                    continue
                seen_days.add(day_key)
                target_days.append(
                    {
                        "week_number": slot["week_number"],
                        "day_of_week": slot["day_of_week"],
                        "slots": _sort_slots(
                            [
                                candidate
                                for candidate in slots
                                if candidate["week_number"] == slot["week_number"]
                                and candidate["day_of_week"] == slot["day_of_week"]
                            ]
                        ),
                    }
                )

            entries = clipboard["entries"]
            if len(entries) == 1:
                source_entries = entries * len(target_days)
            elif len(entries) == len(target_days):
                source_entries = entries
            else:
                raise InvalidMenuSlotActionError("Select the same number of target days as copied days, or copy a single day.")

            target_payloads = []
            for target_day, source_entry in zip(target_days, source_entries):
                source_lookup = {
                    (slot_entry["meal_period"], slot_entry["concept_name"]): slot_entry["item_ids"]
                    for slot_entry in source_entry["slots"]
                }
                for day_slot in target_day["slots"]:
                    target_payloads.append(
                        (
                            day_slot["menu_slot_id"],
                            source_lookup.get((day_slot["meal_period"], day_slot["concept_name"]), []),
                        )
                    )
        else:
            raise InvalidMenuSlotActionError("No copied slot items are available to paste.")

        unique_item_ids = sorted(
            {
                item_id
                for _, item_ids in target_payloads
                for item_id in item_ids
            }
        )
        _validate_live_menu_items(cursor, unique_item_ids)

        for menu_slot_id, item_ids in target_payloads:
            _replace_slot_items(cursor, menu_slot_id, item_ids)

        conn.commit()

    return len(target_payloads)


def paste_menu_weeks(
    *,
    menu_id: int,
    actor_user_id: str,
    selected_week_numbers: list[str | int],
    clipboard: dict | None,
) -> int:
    initialize_database()

    if not clipboard or clipboard.get("mode") != "week" or not clipboard.get("entries"):
        raise InvalidMenuSlotActionError("No copied week is available to paste.")

    normalized_weeks: list[int] = []
    seen_weeks: set[int] = set()
    for week_number in selected_week_numbers:
        try:
            normalized_week_number = int(week_number)
        except (TypeError, ValueError):
            raise InvalidMenuSlotActionError("Select valid destination weeks.")
        if normalized_week_number not in seen_weeks:
            normalized_weeks.append(normalized_week_number)
            seen_weeks.add(normalized_week_number)

    if not normalized_weeks:
        raise InvalidMenuSlotActionError("Select at least one destination week.")

    with get_connection() as conn:
        cursor = conn.cursor()
        slots = _load_menu_slots(cursor, menu_id=menu_id, actor_user_id=actor_user_id)
        available_weeks = {slot["week_number"] for slot in slots}
        invalid_weeks = [week_number for week_number in normalized_weeks if week_number not in available_weeks]
        if invalid_weeks:
            raise InvalidMenuSlotActionError("One or more destination weeks are not available in this menu.")

        entries = clipboard["entries"]
        if len(entries) == 1:
            source_entries = entries * len(normalized_weeks)
        elif len(entries) == len(normalized_weeks):
            source_entries = entries
        else:
            raise InvalidMenuSlotActionError("Select the same number of target weeks as copied weeks, or copy a single week.")

        target_payloads = []
        for target_week_number, source_entry in zip(normalized_weeks, source_entries):
            source_lookup = {
                (slot_entry["day_of_week"], slot_entry["meal_period"], slot_entry["concept_name"]): slot_entry["item_ids"]
                for slot_entry in source_entry["slots"]
            }
            target_week_slots = _sort_slots(
                [slot for slot in slots if slot["week_number"] == target_week_number]
            )
            for week_slot in target_week_slots:
                target_payloads.append(
                    (
                        week_slot["menu_slot_id"],
                        source_lookup.get(
                            (week_slot["day_of_week"], week_slot["meal_period"], week_slot["concept_name"]),
                            [],
                        ),
                    )
                )

        unique_item_ids = sorted(
            {
                item_id
                for _, item_ids in target_payloads
                for item_id in item_ids
            }
        )
        _validate_live_menu_items(cursor, unique_item_ids)

        for menu_slot_id, item_ids in target_payloads:
            _replace_slot_items(cursor, menu_slot_id, item_ids)

        conn.commit()

    return len(normalized_weeks)
