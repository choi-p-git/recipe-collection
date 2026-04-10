from config.item_types import ITEM_TYPE_LABELS
from config.statuses import STATUS_LABELS
from db import get_connection


def record_item_event(
    *,
    item_id: int,
    event_type: str,
    actor_user_id: str,
    actor_display_name: str,
    actor_role: str,
    event_summary: str,
    action_code: str | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    reason_text: str | None = None,
    conn=None,
) -> int:
    normalized_reason = " ".join(reason_text.split()) if reason_text else None

    should_commit = conn is None
    active_conn = conn or get_connection()
    try:
        cursor = active_conn.cursor()
        cursor.execute(
            """
            INSERT INTO item_event (
                item_id,
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
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                item_id,
                event_type,
                actor_user_id,
                actor_display_name,
                actor_role,
                event_summary,
                action_code,
                from_status,
                to_status,
                normalized_reason,
            ),
        )
        event_id = int(cursor.lastrowid)
        if should_commit:
            active_conn.commit()
        return event_id
    finally:
        if should_commit:
            active_conn.close()


def build_creation_summary(item_type: str) -> str:
    return f"{ITEM_TYPE_LABELS.get(item_type, item_type)} created."


def build_update_summary(item_type: str) -> str:
    return f"{ITEM_TYPE_LABELS.get(item_type, item_type)} updated."


def build_resubmission_summary() -> str:
    return "Recipe resubmitted after revision request."


def build_note_summary(recipient_label: str) -> str:
    return f"Workflow note posted to {recipient_label}."


def build_transition_summary(action: dict, from_status: str, to_status: str) -> str:
    if action["action_code"] == "return_to_submitter":
        return "Recipe returned to submitter."

    if action["action_code"] in {"send_back_submitted", "send_back_review"}:
        return f"Item sent back from {STATUS_LABELS.get(from_status, from_status)} to {STATUS_LABELS.get(to_status, to_status)}."

    if action["action_code"].startswith("reject_"):
        return f"Item moved from {STATUS_LABELS.get(from_status, from_status)} to Rejected."

    return (
        f"Status moved from {STATUS_LABELS.get(from_status, from_status)} "
        f"to {STATUS_LABELS.get(to_status, to_status)}."
    )
