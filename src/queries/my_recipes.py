from config.statuses import APPROVED_STATUSES, STATUS_LABELS
from db import get_connection


SORT_OPTIONS = {
    "updated_desc": "i.updated_at DESC, i.item_id DESC",
    "updated_asc": "i.updated_at ASC, i.item_id ASC",
    "name_asc": "i.item_name ASC, i.item_id ASC",
    "name_desc": "i.item_name DESC, i.item_id DESC",
    "status_asc": "i.status ASC, i.updated_at DESC, i.item_id DESC",
}


def get_my_recipes(
    author_user_id: str,
    status: str | None = None,
    sort: str = "updated_desc",
) -> dict:
    """
    Return recipe rows for a single author with optional status filtering and sorting.
    """
    normalized_status = status.strip() if status else ""
    if normalized_status not in APPROVED_STATUSES:
        normalized_status = ""

    normalized_sort = sort if sort in SORT_OPTIONS else "updated_desc"

    query = """
        SELECT
            i.item_id,
            i.item_name,
            i.status,
            i.updated_at,
            i.created_at,
            i.primary_cooking_method_code
        FROM item i
        WHERE i.item_type = 'recipe'
          AND i.author_user_id = ?
    """
    params: list[str] = [author_user_id]

    if normalized_status:
        query += " AND i.status = ?"
        params.append(normalized_status)

    query += f" ORDER BY {SORT_OPTIONS[normalized_sort]}"

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()

    recipes = [
        {
            "item_id": row[0],
            "item_name": row[1],
            "status": row[2],
            "status_label": STATUS_LABELS.get(row[2], row[2]),
            "updated_at": row[3],
            "created_at": row[4],
            "primary_cooking_method_code": row[5],
        }
        for row in rows
    ]

    counts = {status_code: 0 for status_code in APPROVED_STATUSES}
    for recipe in recipes:
        counts[recipe["status"]] += 1

    return {
        "recipes": recipes,
        "selected_status": normalized_status,
        "selected_sort": normalized_sort,
        "available_statuses": [
            {"value": status_code, "label": STATUS_LABELS[status_code]}
            for status_code in APPROVED_STATUSES
        ],
        "available_sorts": [
            {"value": "updated_desc", "label": "Recently Updated"},
            {"value": "updated_asc", "label": "Oldest Updated"},
            {"value": "name_asc", "label": "Name A-Z"},
            {"value": "name_desc", "label": "Name Z-A"},
            {"value": "status_asc", "label": "Status"},
        ],
        "counts": counts,
    }
