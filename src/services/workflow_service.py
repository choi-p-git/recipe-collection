from config.roles import ROLE_LABELS
from config.statuses import APPROVED_STATUSES, STATUS_LABELS
from db import get_connection
from services.item_event_service import build_transition_summary, record_item_event
from services.notification_service import create_workflow_action_notifications
from services.policy_service import can_edit_items


PORTAL_DEFINITIONS = {
    "reviewer": {
        "label": "Reviewer Portal",
        "allowed_roles": {"reviewer", "admin", "super_user"},
        "default_statuses": ["submitted", "reviewed", "analyzed"],
    },
    "dietitian": {
        "label": "Dietitian Portal",
        "allowed_roles": {"dietitian", "admin", "super_user"},
        "default_statuses": ["approved"],
    },
    "admin": {
        "label": "Admin Workflow Portal",
        "allowed_roles": {"admin", "super_user"},
        "default_statuses": ["submitted", "reviewed", "approved", "analyzed", "live", "rejected"],
    },
}

WORKFLOW_ACTIONS = {
    "reviewer": {
        "submitted": [
            {
                "action_code": "advance_reviewed",
                "target_status": "reviewed",
                "label": "Advance To Reviewed",
                "tone": "primary",
            },
            {
                "action_code": "return_to_submitter",
                "target_status": "submitted",
                "label": "Return To Submitter",
                "tone": "secondary",
                "item_types": {"recipe"},
                "set_requires_resubmission": True,
                "requires_reason": True,
                "reason_label": "Revision request",
            },
            {
                "action_code": "reject_submitted",
                "target_status": "rejected",
                "label": "Reject",
                "tone": "danger",
                "requires_reason": True,
                "reason_label": "Rejection reason",
            },
        ],
        "reviewed": [
            {
                "action_code": "send_back_submitted",
                "target_status": "submitted",
                "label": "Send Back To Submitted",
                "tone": "secondary",
                "requires_reason": True,
                "reason_label": "Send-back reason",
            },
            {
                "action_code": "approve_for_dietitian",
                "target_status": "approved",
                "label": "Approve For Dietitian",
                "tone": "primary",
            },
            {
                "action_code": "reject_reviewed",
                "target_status": "rejected",
                "label": "Reject",
                "tone": "danger",
                "requires_reason": True,
                "reason_label": "Rejection reason",
            },
        ],
        "analyzed": [
            {"action_code": "go_live", "target_status": "live", "label": "Go Live", "tone": "primary"},
            {
                "action_code": "reject_analyzed",
                "target_status": "rejected",
                "label": "Reject",
                "tone": "danger",
                "requires_reason": True,
                "reason_label": "Rejection reason",
            },
        ],
    },
    "dietitian": {
        "approved": [
            {
                "action_code": "send_back_review",
                "target_status": "reviewed",
                "label": "Send Back To Review",
                "tone": "secondary",
                "requires_reason": True,
                "reason_label": "Send-back reason",
            },
            {
                "action_code": "mark_analyzed",
                "target_status": "analyzed",
                "label": "Mark As Analyzed",
                "tone": "primary",
            },
            {
                "action_code": "reject_approved",
                "target_status": "rejected",
                "label": "Reject",
                "tone": "danger",
                "requires_reason": True,
                "reason_label": "Rejection reason",
            },
        ],
    },
    "admin": {
        "submitted": [
            {
                "action_code": "advance_reviewed",
                "target_status": "reviewed",
                "label": "Advance To Reviewed",
                "tone": "primary",
            },
            {
                "action_code": "return_to_submitter",
                "target_status": "submitted",
                "label": "Return To Submitter",
                "tone": "secondary",
                "item_types": {"recipe"},
                "set_requires_resubmission": True,
                "requires_reason": True,
                "reason_label": "Revision request",
            },
            {
                "action_code": "reject_submitted",
                "target_status": "rejected",
                "label": "Reject",
                "tone": "danger",
                "requires_reason": True,
                "reason_label": "Rejection reason",
            },
        ],
        "reviewed": [
            {
                "action_code": "send_back_submitted",
                "target_status": "submitted",
                "label": "Send Back To Submitted",
                "tone": "secondary",
                "requires_reason": True,
                "reason_label": "Send-back reason",
            },
            {
                "action_code": "approve_for_dietitian",
                "target_status": "approved",
                "label": "Approve For Dietitian",
                "tone": "primary",
            },
            {
                "action_code": "reject_reviewed",
                "target_status": "rejected",
                "label": "Reject",
                "tone": "danger",
                "requires_reason": True,
                "reason_label": "Rejection reason",
            },
        ],
        "approved": [
            {
                "action_code": "send_back_review",
                "target_status": "reviewed",
                "label": "Send Back To Review",
                "tone": "secondary",
                "requires_reason": True,
                "reason_label": "Send-back reason",
            },
            {
                "action_code": "mark_analyzed",
                "target_status": "analyzed",
                "label": "Mark As Analyzed",
                "tone": "primary",
            },
            {
                "action_code": "reject_approved",
                "target_status": "rejected",
                "label": "Reject",
                "tone": "danger",
                "requires_reason": True,
                "reason_label": "Rejection reason",
            },
        ],
        "analyzed": [
            {"action_code": "go_live", "target_status": "live", "label": "Go Live", "tone": "primary"},
            {
                "action_code": "reject_analyzed",
                "target_status": "rejected",
                "label": "Reject",
                "tone": "danger",
                "requires_reason": True,
                "reason_label": "Rejection reason",
            },
        ],
    },
}


class WorkflowPermissionError(ValueError):
    """Raised when the current role cannot access a portal or transition."""


def get_available_workflow_portals(role: str) -> list[dict[str, str]]:
    portals = []
    for portal_name, definition in PORTAL_DEFINITIONS.items():
        if role in definition["allowed_roles"]:
            portals.append({"name": portal_name, "label": definition["label"]})
    return portals


def ensure_portal_access(role: str, portal_name: str) -> dict:
    definition = PORTAL_DEFINITIONS.get(portal_name)
    if definition is None:
        raise WorkflowPermissionError("Workflow portal not found.")

    if role not in definition["allowed_roles"]:
        raise WorkflowPermissionError(
            f"{ROLE_LABELS.get(role, role)} does not have access to the {definition['label']}."
        )

    return definition


def get_workflow_actions_for_item(role: str, portal_name: str, item: dict) -> list[dict[str, str]]:
    ensure_portal_access(role, portal_name)
    actions = []
    for action in WORKFLOW_ACTIONS.get(portal_name, {}).get(item["status"], []):
        allowed_item_types = action.get("item_types")
        if allowed_item_types and item["item_type"] not in allowed_item_types:
            continue
        actions.append(dict(action))
    return actions


def transition_item_status(
    item_id: int,
    current_user: dict,
    portal_name: str,
    action_code: str,
    target_status: str,
    reason_text: str = "",
) -> str:
    if target_status not in APPROVED_STATUSES:
        raise WorkflowPermissionError("Target workflow status is invalid.")

    item = _get_item_workflow_context(item_id)
    allowed_actions = get_workflow_actions_for_item(current_user["role"], portal_name, item)
    matching_action = next(
        (
            action
            for action in allowed_actions
            if action["action_code"] == action_code and action["target_status"] == target_status
        ),
        None,
    )

    if matching_action is None:
        raise WorkflowPermissionError("This workflow transition is not allowed from the current portal.")

    normalized_reason = " ".join(reason_text.split())
    if matching_action.get("requires_reason") and not normalized_reason:
        raise WorkflowPermissionError(f"{matching_action['reason_label']} is required.")

    if action_code == "go_live" and item["item_type"] == "recipe":
        if not item["mass_quantity"] or not item["mass_unit"] or not item["volume_quantity"] or not item["volume_unit"]:
            raise WorkflowPermissionError(
                "Recipes must have both mass and volume yield data before they can go live."
            )

    from_status = item["status"]
    requires_resubmission = 1 if matching_action.get("set_requires_resubmission") else 0
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE item
            SET status = ?,
                requires_resubmission = ?,
                updated_at = datetime('now')
            WHERE item_id = ?
            """,
            (target_status, requires_resubmission, item_id),
        )

        if cursor.rowcount == 0:
            raise WorkflowPermissionError("Workflow item was not found.")

        record_item_event(
            item_id=item_id,
            event_type="status_transition",
            actor_user_id=current_user["user_id"],
            actor_display_name=current_user["display_name"],
            actor_role=current_user["role"],
            event_summary=build_transition_summary(matching_action, from_status, target_status),
            action_code=action_code,
            from_status=from_status,
            to_status=target_status,
            reason_text=normalized_reason or None,
            conn=conn,
        )
        create_workflow_action_notifications(
            item=item,
            action_code=action_code,
            actor_user_id=current_user["user_id"],
            actor_display_name=current_user["display_name"],
            actor_role=current_user["role"],
            message_text=build_transition_summary(matching_action, from_status, target_status),
            conn=conn,
        )

        conn.commit()

    return target_status


def _get_item_workflow_context(item_id: int) -> dict:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT item_id, item_type, author_user_id, author_display_name, status, requires_resubmission
                 , mass_quantity, mass_unit, volume_quantity, volume_unit
            FROM item
            WHERE item_id = ?
            """,
            (item_id,),
        )
        row = cursor.fetchone()

    if row is None:
        raise WorkflowPermissionError("Workflow item was not found.")

    return {
        "item_id": row[0],
        "item_type": row[1],
        "author_user_id": row[2],
        "author_display_name": row[3],
        "status": row[4],
        "requires_resubmission": bool(row[5]),
        "mass_quantity": row[6],
        "mass_unit": row[7],
        "volume_quantity": row[8],
        "volume_unit": row[9],
    }


def get_status_filter_options(portal_name: str) -> list[str]:
    return PORTAL_DEFINITIONS[portal_name]["default_statuses"]


def build_status_summary(rows: list[dict]) -> dict[str, int]:
    counts = {status_code: 0 for status_code in APPROVED_STATUSES}
    for row in rows:
        counts[row["status"]] += 1
    return counts


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)
