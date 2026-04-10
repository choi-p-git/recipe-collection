from db import get_connection


def search_items(search_term: str, limit: int = 10) -> list[dict]:
    """
    Search items by item_name or item_id prefix/substring for MVP.
    Returns lightweight dictionaries for frontend selection.
    """
    normalized_term = search_term.strip()

    if not normalized_term:
        return []

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                item_id,
                item_name,
                item_type,
                status
            FROM item
            WHERE item_name LIKE ? COLLATE NOCASE
               OR CAST(item_id AS TEXT) LIKE ?
            ORDER BY item_name ASC
            LIMIT ?
            """,
            (
                f"%{normalized_term}%",
                f"{normalized_term}%",
                limit,
            ),
        )

        rows = cursor.fetchall()

    return [
        {
            "item_id": row[0],
            "item_name": row[1],
            "item_type": row[2],
            "status": row[3],
        }
        for row in rows
    ]