from db import get_connection


def create_notification(
    *,
    item_id: int,
    notification_type: str,
    actor_user_id: str,
    actor_display_name: str,
    actor_role: str,
    message_text: str,
    recipient_user_id: str | None = None,
    recipient_role: str | None = None,
    conn=None,
) -> int | None:
    if not recipient_user_id and not recipient_role:
        return None

    if recipient_user_id == actor_user_id:
        return None

    if recipient_role == actor_role and recipient_user_id is None:
        return None

    should_commit = conn is None
    active_conn = conn or get_connection()
    try:
        cursor = active_conn.cursor()
        cursor.execute(
            """
            INSERT INTO item_notification (
                item_id,
                notification_type,
                actor_user_id,
                actor_display_name,
                actor_role,
                message_text,
                recipient_user_id,
                recipient_role,
                is_acknowledged,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, datetime('now'))
            """,
            (
                item_id,
                notification_type,
                actor_user_id,
                actor_display_name,
                actor_role,
                message_text,
                recipient_user_id,
                recipient_role,
            ),
        )
        notification_id = int(cursor.lastrowid)
        if should_commit:
            active_conn.commit()
        return notification_id
    finally:
        if should_commit:
            active_conn.close()


def create_workflow_action_notifications(
    *,
    item: dict,
    action_code: str,
    actor_user_id: str,
    actor_display_name: str,
    actor_role: str,
    message_text: str,
    conn=None,
) -> None:
    recipients: list[dict[str, str | None]] = []

    if action_code in {"advance_reviewed", "return_to_submitter", "send_back_submitted", "go_live"}:
        recipients.append({"recipient_user_id": item["author_user_id"], "recipient_role": None})
    elif action_code == "approve_for_dietitian":
        recipients.append({"recipient_user_id": None, "recipient_role": "dietitian"})
    elif action_code == "send_back_review":
        recipients.append({"recipient_user_id": None, "recipient_role": "reviewer"})
    elif action_code == "mark_analyzed":
        recipients.append({"recipient_user_id": None, "recipient_role": "reviewer"})
    elif action_code in {"reject_submitted", "reject_reviewed", "reject_analyzed"}:
        recipients.append({"recipient_user_id": item["author_user_id"], "recipient_role": None})
    elif action_code == "reject_approved":
        recipients.append({"recipient_user_id": item["author_user_id"], "recipient_role": None})
        recipients.append({"recipient_user_id": None, "recipient_role": "reviewer"})

    for recipient in recipients:
        create_notification(
            item_id=item["item_id"],
            notification_type="workflow_action",
            actor_user_id=actor_user_id,
            actor_display_name=actor_display_name,
            actor_role=actor_role,
            message_text=message_text,
            recipient_user_id=recipient["recipient_user_id"],
            recipient_role=recipient["recipient_role"],
            conn=conn,
        )


def create_post_live_edit_notifications(
    *,
    item: dict,
    actor_user_id: str,
    actor_display_name: str,
    actor_role: str,
    message_text: str,
    conn=None,
) -> None:
    recipients: list[dict[str, str | None]] = [
        {"recipient_user_id": None, "recipient_role": "reviewer"},
        {"recipient_user_id": None, "recipient_role": "dietitian"},
    ]

    if item.get("author_user_id") and item["author_user_id"] != "system_base_food":
        recipients.append({"recipient_user_id": item["author_user_id"], "recipient_role": None})

    for recipient in recipients:
        create_notification(
            item_id=item["item_id"],
            notification_type="post_live_edit",
            actor_user_id=actor_user_id,
            actor_display_name=actor_display_name,
            actor_role=actor_role,
            message_text=message_text,
            recipient_user_id=recipient["recipient_user_id"],
            recipient_role=recipient["recipient_role"],
            conn=conn,
        )


def acknowledge_item_notifications_for_viewer(item_id: int, current_user: dict) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE item_notification
            SET is_acknowledged = 1
            WHERE item_id = ?
              AND is_acknowledged = 0
              AND (
                    recipient_user_id = ?
                    OR recipient_role = ?
                  )
            """,
            (
                item_id,
                current_user["user_id"],
                current_user["role"],
            ),
        )
        count = cursor.rowcount
        conn.commit()
        return count


def get_notification_rows(current_user: dict) -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                notification_type,
                notification_id,
                item_id,
                item_name,
                item_type,
                actor_display_name,
                actor_role,
                message_text,
                created_at
            FROM (
                SELECT
                    'workflow_action' AS notification_type,
                    n.item_notification_id AS notification_id,
                    n.item_id,
                    i.item_name,
                    i.item_type,
                    n.actor_display_name,
                    n.actor_role,
                    n.message_text,
                    n.created_at
                FROM item_notification n
                JOIN item i
                  ON i.item_id = n.item_id
                WHERE n.is_acknowledged = 0
                  AND (
                        n.recipient_user_id = ?
                        OR n.recipient_role = ?
                      )

                UNION ALL

                SELECT
                    'workflow_note' AS notification_type,
                    note.item_note_id AS notification_id,
                    note.item_id,
                    i.item_name,
                    i.item_type,
                    note.author_display_name,
                    note.author_role,
                    note.note_text AS message_text,
                    note.created_at
                FROM item_note note
                JOIN item i
                  ON i.item_id = note.item_id
                WHERE note.is_acknowledged = 0
                  AND (
                        note.recipient_user_id = ?
                        OR note.recipient_role = ?
                      )
            )
            ORDER BY created_at DESC, notification_id DESC
            """,
            (
                current_user["user_id"],
                current_user["role"],
                current_user["user_id"],
                current_user["role"],
            ),
        )
        rows = cursor.fetchall()

    return [
        {
            "notification_type": row[0],
            "notification_id": row[1],
            "item_id": row[2],
            "item_name": row[3],
            "item_type": row[4],
            "actor_display_name": row[5],
            "actor_role": row[6],
            "message_text": row[7],
            "created_at": row[8],
        }
        for row in rows
    ]


def get_notification_count(current_user: dict) -> int:
    return len(get_notification_rows(current_user))
