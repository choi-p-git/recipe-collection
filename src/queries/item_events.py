from db import get_connection


def get_item_events(item_id: int) -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                item_event_id,
                event_type,
                actor_user_id,
                actor_display_name,
                actor_role,
                event_summary,
                action_code,
                from_status,
                to_status,
                reason_text,
                created_at
            FROM item_event
            WHERE item_id = ?
            ORDER BY item_event_id DESC
            """,
            (item_id,),
        )
        rows = cursor.fetchall()

    return [
        {
            "item_event_id": row[0],
            "event_type": row[1],
            "actor_user_id": row[2],
            "actor_display_name": row[3],
            "actor_role": row[4],
            "event_summary": row[5],
            "action_code": row[6],
            "from_status": row[7],
            "to_status": row[8],
            "reason_text": row[9],
            "created_at": row[10],
        }
        for row in rows
    ]
