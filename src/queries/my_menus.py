from db import get_connection


def get_my_menus(author_user_id: str) -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                m.menu_id,
                m.menu_name,
                m.author_display_name,
                m.menu_length_weeks,
                m.status,
                m.created_at,
                m.updated_at,
                COUNT(DISTINCT ms.menu_slot_id) AS slot_count,
                COUNT(DISTINCT msi.menu_slot_item_id) AS assigned_item_count
            FROM menu m
            LEFT JOIN menu_slot ms
              ON ms.menu_id = m.menu_id
            LEFT JOIN menu_slot_item msi
              ON msi.menu_slot_id = ms.menu_slot_id
            WHERE m.author_user_id = ?
            GROUP BY
                m.menu_id,
                m.menu_name,
                m.author_display_name,
                m.menu_length_weeks,
                m.status,
                m.created_at,
                m.updated_at
            ORDER BY m.updated_at DESC, m.menu_id DESC
            """,
            (author_user_id,),
        )
        rows = cursor.fetchall()

    return {
        "menus": [
            {
                "menu_id": row[0],
                "menu_name": row[1],
                "author_display_name": row[2],
                "menu_length_weeks": row[3],
                "status": row[4],
                "created_at": row[5],
                "updated_at": row[6],
                "slot_count": row[7],
                "assigned_item_count": row[8],
            }
            for row in rows
        ]
    }
