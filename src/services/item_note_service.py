from db import get_connection
from services.item_event_service import build_note_summary, record_item_event
from services.policy_service import is_dietitian_domain_role, is_reviewer_domain_role


class ItemNoteError(ValueError):
    """Raised when item note actions are invalid."""


def resolve_note_recipient(item: dict, current_user: dict) -> dict | None:
    """
    Infer the recipient based on the item's workflow state and the current user's role.
    """
    item_status = item["status"]
    item_type = item.get("item_type")
    current_role = current_user["role"]
    current_user_id = current_user["user_id"]

    if item_status == "submitted" and item_type == "recipe":
        if is_reviewer_domain_role(current_role):
            return {
                "recipient_user_id": item["author_user_id"],
                "recipient_role": None,
                "recipient_label": item["author_display_name"],
            }

        if current_user_id == item["author_user_id"]:
            return {
                "recipient_user_id": None,
                "recipient_role": "reviewer",
                "recipient_label": "Reviewer",
            }

    if item_status == "reviewed":
        if is_reviewer_domain_role(current_role):
            return {
                "recipient_user_id": item["author_user_id"],
                "recipient_role": None,
                "recipient_label": item["author_display_name"],
            }

        if current_user_id == item["author_user_id"]:
            return {
                "recipient_user_id": None,
                "recipient_role": "reviewer",
                "recipient_label": "Reviewer",
            }

    if item_status == "approved":
        if is_dietitian_domain_role(current_role) and not is_reviewer_domain_role(current_role):
            return {
                "recipient_user_id": None,
                "recipient_role": "reviewer",
                "recipient_label": "Reviewer",
            }

        if is_reviewer_domain_role(current_role):
            return {
                "recipient_user_id": None,
                "recipient_role": "dietitian",
                "recipient_label": "Dietitian",
            }

    if item_status == "analyzed" and is_reviewer_domain_role(current_role):
        return {
            "recipient_user_id": item["author_user_id"],
            "recipient_role": None,
            "recipient_label": item["author_display_name"],
        }

    return None


def acknowledge_item_notes_for_viewer(item_id: int, current_user: dict) -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE item_note
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
        acknowledged_count = cursor.rowcount
        conn.commit()
        return acknowledged_count


def post_item_note(item: dict, current_user: dict, note_text: str) -> int:
    normalized_text = " ".join(note_text.split())
    if not normalized_text:
        raise ItemNoteError("Note text cannot be empty.")

    recipient = resolve_note_recipient(item, current_user)
    if recipient is None:
        raise ItemNoteError("No note recipient is available for the current item state and role.")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE item_note
            SET is_acknowledged = 1
            WHERE item_id = ?
              AND is_acknowledged = 0
              AND (
                    recipient_user_id = ?
                    OR recipient_role = ?
                  )
            """,
            (
                item["item_id"],
                current_user["user_id"],
                current_user["role"],
            ),
        )

        cursor.execute(
            """
            INSERT INTO item_note (
                item_id,
                author_user_id,
                author_display_name,
                author_role,
                note_text,
                recipient_user_id,
                recipient_role,
                is_acknowledged,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, datetime('now'))
            """,
            (
                item["item_id"],
                current_user["user_id"],
                current_user["display_name"],
                current_user["role"],
                normalized_text,
                recipient["recipient_user_id"],
                recipient["recipient_role"],
            ),
        )
        note_id = int(cursor.lastrowid)
        record_item_event(
            item_id=item["item_id"],
            event_type="note_posted",
            actor_user_id=current_user["user_id"],
            actor_display_name=current_user["display_name"],
            actor_role=current_user["role"],
            event_summary=build_note_summary(recipient["recipient_label"]),
            conn=conn,
        )
        conn.commit()
        return note_id


def get_item_notes(item_id: int) -> list[dict]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                item_note_id,
                author_user_id,
                author_display_name,
                author_role,
                note_text,
                recipient_user_id,
                recipient_role,
                is_acknowledged,
                created_at
            FROM item_note
            WHERE item_id = ?
            ORDER BY item_note_id ASC
            """,
            (item_id,),
        )
        rows = cursor.fetchall()

    return [
        {
            "item_note_id": row[0],
            "author_user_id": row[1],
            "author_display_name": row[2],
            "author_role": row[3],
            "note_text": row[4],
            "recipient_user_id": row[5],
            "recipient_role": row[6],
            "is_acknowledged": bool(row[7]),
            "created_at": row[8],
        }
        for row in rows
    ]
