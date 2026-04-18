import json

from config.menu_builder import MENU_STATUS_LABELS
from db import get_connection


def get_menu_detail(menu_id: int) -> dict | None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                menu_id,
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
            FROM menu
            WHERE menu_id = ?
            """,
            (menu_id,),
        )
        menu_row = cursor.fetchone()
        if menu_row is None:
            return None

        cursor.execute(
            """
            SELECT
                menu_slot_id,
                week_number,
                day_of_week,
                meal_period,
                concept_name
            FROM menu_slot
            WHERE menu_id = ?
            ORDER BY week_number ASC, day_of_week ASC, meal_period ASC, concept_name ASC
            """,
            (menu_id,),
        )
        slot_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT
                msi.menu_slot_id,
                msi.menu_slot_item_id,
                msi.item_sequence,
                i.item_id,
                i.item_name,
                i.item_type
            FROM menu_slot_item msi
            JOIN item i
              ON i.item_id = msi.item_id
            JOIN menu_slot ms
              ON ms.menu_slot_id = msi.menu_slot_id
            WHERE ms.menu_id = ?
            ORDER BY msi.menu_slot_id ASC, msi.item_sequence ASC, msi.menu_slot_item_id ASC
            """,
            (menu_id,),
        )
        slot_item_rows = cursor.fetchall()

    slot_items_by_slot_id: dict[int, list[dict]] = {}
    for row in slot_item_rows:
        slot_items_by_slot_id.setdefault(row[0], []).append(
            {
                "menu_slot_item_id": row[1],
                "item_sequence": row[2],
                "item_id": row[3],
                "item_name": row[4],
                "item_type": row[5],
            }
        )

    return {
        "menu_id": menu_row[0],
        "menu_name": menu_row[1],
        "author_user_id": menu_row[2],
        "author_display_name": menu_row[3],
        "service_days": json.loads(menu_row[4]),
        "meal_periods": json.loads(menu_row[5]),
        "concepts": json.loads(menu_row[6]),
        "menu_length_weeks": menu_row[7],
        "status": menu_row[8],
        "status_label": MENU_STATUS_LABELS.get(menu_row[8], menu_row[8]),
        "created_at": menu_row[9],
        "updated_at": menu_row[10],
        "slots": [
            {
                "menu_slot_id": row[0],
                "week_number": row[1],
                "day_of_week": row[2],
                "meal_period": row[3],
                "concept_name": row[4],
                "assigned_items": slot_items_by_slot_id.get(row[0], []),
            }
            for row in slot_rows
        ],
    }
