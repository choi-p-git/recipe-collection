WORKFLOW_STAFF_ROLES = {"reviewer", "dietitian", "admin", "super_user"}
REVIEWER_DOMAIN_ROLES = {"reviewer", "admin", "super_user"}
DIETITIAN_DOMAIN_ROLES = {"dietitian", "admin", "super_user"}
ITEM_EDITOR_ROLES = {"reviewer", "dietitian", "admin", "super_user"}
ADVANCED_WORKFLOW_VIEW_ROLES = {"reviewer", "dietitian", "admin", "super_user"}
OFFICIAL_MEASUREMENT_ROLES = {"dietitian", "admin", "super_user"}


def is_workflow_staff(role: str) -> bool:
    return role in WORKFLOW_STAFF_ROLES


def is_reviewer_domain_role(role: str) -> bool:
    return role in REVIEWER_DOMAIN_ROLES


def is_dietitian_domain_role(role: str) -> bool:
    return role in DIETITIAN_DOMAIN_ROLES


def can_edit_items(role: str) -> bool:
    return role in ITEM_EDITOR_ROLES


def can_view_advanced_workflow(role: str) -> bool:
    return role in ADVANCED_WORKFLOW_VIEW_ROLES


def can_manage_official_measurements(role: str) -> bool:
    return role in OFFICIAL_MEASUREMENT_ROLES


def can_edit_item(current_user: dict, item: dict) -> bool:
    if can_edit_items(current_user["role"]):
        return True

    return (
        current_user["user_id"] == item["author_user_id"]
        and item["item_type"] == "recipe"
        and item["status"] == "submitted"
        and bool(item.get("requires_resubmission"))
    )
