from db import get_connection
from queries.item_search import search_items_page


def get_menu_slot_detail(menu_id: int, menu_slot_id: int, *, search_term: str = "", item_type: str = "") -> dict | None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                m.menu_id,
                m.menu_name,
                ms.menu_slot_id,
                ms.week_number,
                ms.day_of_week,
                ms.meal_period,
                ms.concept_name
            FROM menu_slot ms
            JOIN menu m
              ON m.menu_id = ms.menu_id
            WHERE ms.menu_slot_id = ?
              AND m.menu_id = ?
            """,
            (menu_slot_id, menu_id),
        )
        slot_row = cursor.fetchone()
        if slot_row is None:
            return None

        cursor.execute(
            """
            SELECT
                msi.menu_slot_item_id,
                msi.item_sequence,
                i.item_id,
                i.item_name,
                i.item_type
            FROM menu_slot_item msi
            JOIN item i
              ON i.item_id = msi.item_id
            WHERE msi.menu_slot_id = ?
            ORDER BY msi.item_sequence ASC, msi.menu_slot_item_id ASC
            """,
            (menu_slot_id,),
        )
        assigned_rows = cursor.fetchall()

    return {
        "menu_id": slot_row[0],
        "menu_name": slot_row[1],
        "menu_slot_id": slot_row[2],
        "week_number": slot_row[3],
        "day_of_week": slot_row[4],
        "meal_period": slot_row[5],
        "concept_name": slot_row[6],
        "assigned_items": [
            {
                "menu_slot_item_id": row[0],
                "item_sequence": row[1],
                "item_id": row[2],
                "item_name": row[3],
                "item_type": row[4],
            }
            for row in assigned_rows
        ],
        "search_results": search_items_page(
            search_term=search_term,
            item_type=item_type,
        ) if search_term else {"items": [], "has_more": False, "next_offset": 0, "limit": 15},
    }
