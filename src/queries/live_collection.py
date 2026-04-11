from config.item_types import ITEM_TYPE_LABELS
from db import get_connection
from queries.item_search import (
    DEFAULT_SEARCH_LIMIT,
    MIN_SEARCH_LENGTH,
    _normalize_search_limit,
    _normalize_search_offset,
    search_live_items_page,
)


SORT_OPTIONS = {
    "updated_desc": "i.updated_at DESC, i.item_id DESC",
    "updated_asc": "i.updated_at ASC, i.item_id ASC",
    "name_asc": "i.item_name ASC, i.item_id ASC",
    "name_desc": "i.item_name DESC, i.item_id DESC",
    "type_asc": "i.item_type ASC, i.item_name ASC, i.item_id ASC",
}


def get_live_collection_page(
    search_term: str | None = None,
    item_type: str | None = None,
    sort: str = "updated_desc",
    offset: int = 0,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> dict:
    normalized_search_term = " ".join((search_term or "").split())
    normalized_item_type = (item_type or "").strip()
    normalized_sort = sort if sort in SORT_OPTIONS else "updated_desc"
    normalized_offset = _normalize_search_offset(offset)
    normalized_limit = _normalize_search_limit(limit)
    minimum_query_met = (
        not normalized_search_term
        or len(normalized_search_term) >= MIN_SEARCH_LENGTH
        or normalized_search_term.isdigit()
    )

    query = """
        SELECT
            i.item_id,
            i.item_name,
            i.item_type,
            i.status,
            i.updated_at,
            i.created_at,
            i.primary_cooking_method_code
        FROM item i
        WHERE i.status = 'live'
    """
    params: list[str | int] = []

    if normalized_item_type in ITEM_TYPE_LABELS:
        query += " AND i.item_type = ?"
        params.append(normalized_item_type)
    else:
        normalized_item_type = ""

    if normalized_search_term and minimum_query_met:
        search_page = search_live_items_page(
            search_term=normalized_search_term,
            item_type=normalized_item_type,
            offset=normalized_offset,
            limit=normalized_limit,
        )
        items = [
            {
                **item,
                "item_type_label": ITEM_TYPE_LABELS.get(item["item_type"], item["item_type"]),
            }
            for item in search_page["items"]
        ]
        has_more = search_page["has_more"]
        next_offset = search_page["next_offset"]
    else:
        query += f"""
            ORDER BY {SORT_OPTIONS[normalized_sort]}
            LIMIT ?
            OFFSET ?
        """
        params.extend([normalized_limit + 1, normalized_offset])

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

        has_more = len(rows) > normalized_limit
        visible_rows = rows[:normalized_limit]
        items = [
            {
                "item_id": row[0],
                "item_name": row[1],
                "item_type": row[2],
                "item_type_label": ITEM_TYPE_LABELS.get(row[2], row[2]),
                "status": row[3],
                "updated_at": row[4],
                "created_at": row[5],
                "primary_cooking_method_code": row[6],
            }
            for row in visible_rows
        ]
        next_offset = normalized_offset + len(items)

    previous_offset = max(0, normalized_offset - normalized_limit)

    return {
        "items": items,
        "search_term": normalized_search_term,
        "selected_item_type": normalized_item_type,
        "selected_sort": normalized_sort,
        "minimum_query_met": minimum_query_met,
        "minimum_query_length": MIN_SEARCH_LENGTH,
        "limit": normalized_limit,
        "offset": normalized_offset,
        "previous_offset": previous_offset,
        "next_offset": next_offset,
        "has_previous": normalized_offset > 0,
        "has_more": has_more,
        "available_item_types": [
            {"value": item_type_code, "label": item_type_label}
            for item_type_code, item_type_label in ITEM_TYPE_LABELS.items()
        ],
        "available_sorts": [
            {"value": "updated_desc", "label": "Recently Updated"},
            {"value": "updated_asc", "label": "Oldest Updated"},
            {"value": "name_asc", "label": "Name A-Z"},
            {"value": "name_desc", "label": "Name Z-A"},
            {"value": "type_asc", "label": "Item Type"},
        ],
    }
