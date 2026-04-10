from config.cooking_methods import COOKING_METHOD_LABELS
from config.item_types import ITEM_TYPE_LABELS
from config.statuses import APPROVED_STATUSES, STATUS_LABELS
from db import get_connection
from services.workflow_service import (
    build_status_summary,
    get_available_workflow_portals,
    get_status_filter_options,
    get_workflow_actions_for_item,
)


SORT_OPTIONS = {
    "updated_desc": "i.updated_at DESC, i.item_id DESC",
    "updated_asc": "i.updated_at ASC, i.item_id ASC",
    "name_asc": "i.item_name ASC, i.item_id ASC",
    "status_asc": "i.status ASC, i.updated_at DESC, i.item_id DESC",
}


def get_workflow_portal_items(
    role: str,
    portal_name: str,
    selected_status: str = "",
    selected_item_type: str = "",
    sort: str = "updated_desc",
) -> dict:
    allowed_statuses = get_status_filter_options(portal_name)
    normalized_status = selected_status if selected_status in APPROVED_STATUSES else ""
    normalized_item_type = selected_item_type if selected_item_type in {"recipe", "base_food"} else ""
    normalized_sort = sort if sort in SORT_OPTIONS else "updated_desc"

    query = """
        SELECT
            i.item_id,
            i.item_name,
            i.item_type,
            i.status,
            i.author_user_id,
            i.author_display_name,
            i.requires_resubmission,
            i.updated_at,
            i.created_at,
            i.primary_cooking_method_code
        FROM item i
        WHERE 1 = 1
    """
    params: list[str] = []

    if portal_name != "admin":
        placeholders = ", ".join("?" for _ in allowed_statuses)
        query += f" AND i.status IN ({placeholders})"
        params.extend(allowed_statuses)

    if normalized_status:
        query += " AND i.status = ?"
        params.append(normalized_status)

    if normalized_item_type:
        query += " AND i.item_type = ?"
        params.append(normalized_item_type)

    query += f" ORDER BY {SORT_OPTIONS[normalized_sort]}"

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()

    items = [
        {
            "item_id": row[0],
            "item_name": row[1],
            "item_type": row[2],
            "item_type_label": ITEM_TYPE_LABELS.get(row[2], row[2]),
            "display_title": f"{ITEM_TYPE_LABELS.get(row[2], row[2])} {row[1]}",
            "status": row[3],
            "status_label": STATUS_LABELS.get(row[3], row[3]),
            "author_display_name": row[5],
            "requires_resubmission": bool(row[6]),
            "updated_at": row[7],
            "created_at": row[8],
            "primary_cooking_method_code": row[9],
            "primary_cooking_method_label": (
                COOKING_METHOD_LABELS.get(row[9], row[9]) if row[9] else None
            ),
            "actions": get_workflow_actions_for_item(
                role,
                portal_name,
                {
                    "item_id": row[0],
                    "item_type": row[2],
                    "author_user_id": row[4],
                    "author_display_name": row[5],
                    "status": row[3],
                    "requires_resubmission": bool(row[6]),
                },
            ),
        }
        for row in rows
    ]

    return {
        "items": items,
        "selected_status": normalized_status,
        "selected_item_type": normalized_item_type,
        "selected_sort": normalized_sort,
        "available_statuses": [
            {"value": status_code, "label": STATUS_LABELS[status_code]}
            for status_code in (allowed_statuses if portal_name != "admin" else APPROVED_STATUSES)
        ],
        "available_item_types": [
            {"value": "recipe", "label": "Recipe"},
            {"value": "base_food", "label": "Base Food"},
        ],
        "available_sorts": [
            {"value": "updated_desc", "label": "Recently Updated"},
            {"value": "updated_asc", "label": "Oldest Updated"},
            {"value": "name_asc", "label": "Name A-Z"},
            {"value": "status_asc", "label": "Status"},
        ],
        "status_counts": build_status_summary(items),
        "available_portals": get_available_workflow_portals(role),
    }
