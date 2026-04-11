from difflib import SequenceMatcher

from db import get_connection


MIN_SEARCH_LENGTH = 2
DEFAULT_SEARCH_LIMIT = 15
DIRECT_MATCH_FETCH_LIMIT = 250
FUZZY_CANDIDATE_FETCH_LIMIT = 250
MIN_FUZZY_RATIO = 0.62
MIN_SHORT_FUZZY_RATIO = 0.8
RELAXED_MIN_SHORT_FUZZY_RATIO = 0.74


def _normalize_search_limit(limit: int) -> int:
    try:
        requested_limit = int(limit)
    except (TypeError, ValueError):
        requested_limit = DEFAULT_SEARCH_LIMIT
    return max(1, min(requested_limit, DEFAULT_SEARCH_LIMIT))


def _normalize_search_offset(offset: int) -> int:
    try:
        requested_offset = int(offset)
    except (TypeError, ValueError):
        requested_offset = 0
    return max(0, requested_offset)


def _normalize_search_term(search_term: str) -> str:
    return " ".join(search_term.split())


def _normalize_relaxed_short_query(relaxed_short_query) -> bool:
    if isinstance(relaxed_short_query, bool):
        return relaxed_short_query
    return str(relaxed_short_query).strip().lower() in {"1", "true", "yes", "on"}


def _map_item_row(row) -> dict:
    return {
        "item_id": row[0],
        "item_name": row[1],
        "item_type": row[2],
        "status": row[3],
        "updated_at": row[4],
        "created_at": row[5],
        "primary_cooking_method_code": row[6],
    }


def _fetch_direct_match_rows(
    normalized_term: str,
    normalized_item_type: str,
) -> list[tuple]:
    tokens = [token for token in normalized_term.lower().split(" ") if token]
    token_prefix_score_sql = " + ".join(
        [
            "CASE WHEN lower(item_name) LIKE ? THEN 1 ELSE 0 END"
            for _ in tokens
        ]
    ) or "0"

    query = f"""
        SELECT
            item_id,
            item_name,
            item_type,
            status,
            updated_at,
            created_at,
            primary_cooking_method_code,
            (
                CASE
                    WHEN CAST(item_id AS TEXT) = ? THEN 600
                    WHEN lower(item_name) = ? THEN 500
                    WHEN CAST(item_id AS TEXT) LIKE ? THEN 400
                    WHEN lower(item_name) LIKE ? THEN 300
                    ELSE 0
                END
                + ({token_prefix_score_sql}) * 25
                + CASE WHEN lower(item_name) LIKE ? THEN 50 ELSE 0 END
            ) AS relevance_score
        FROM item
        WHERE (
                lower(item_name) LIKE ?
                OR CAST(item_id AS TEXT) LIKE ?
              )
          AND status = 'live'
    """
    params: list[str | int] = [
        normalized_term,
        normalized_term.lower(),
        f"{normalized_term}%",
        f"{normalized_term.lower()}%",
        *[f"{token}%" for token in tokens],
        f"%{normalized_term.lower()}%",
        f"%{normalized_term.lower()}%",
        f"{normalized_term}%",
    ]

    if normalized_item_type in {"recipe", "base_food"}:
        query += " AND item_type = ?"
        params.append(normalized_item_type)

    query += """
        ORDER BY relevance_score DESC, item_name ASC, item_id ASC
        LIMIT ?
    """
    params.append(DIRECT_MATCH_FETCH_LIMIT)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()


def _fetch_fuzzy_candidate_rows(normalized_item_type: str) -> list[tuple]:
    query = """
        SELECT
            item_id,
            item_name,
            item_type,
            status,
            updated_at,
            created_at,
            primary_cooking_method_code
        FROM item
        WHERE status = 'live'
    """
    params: list[str | int] = []

    if normalized_item_type in {"recipe", "base_food"}:
        query += " AND item_type = ?"
        params.append(normalized_item_type)

    query += """
        ORDER BY updated_at DESC, item_id DESC
        LIMIT ?
    """
    params.append(FUZZY_CANDIDATE_FETCH_LIMIT)

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()


def _calculate_fuzzy_ratio(normalized_term: str, candidate_name: str) -> float:
    term_lower = normalized_term.lower()
    candidate_lower = candidate_name.lower()
    term_compact = term_lower.replace(" ", "")
    candidate_compact = candidate_lower.replace(" ", "")

    ratios = [
        SequenceMatcher(None, term_lower, candidate_lower).ratio(),
        SequenceMatcher(None, term_compact, candidate_compact).ratio(),
    ]

    search_tokens = [token for token in term_lower.split(" ") if token]
    candidate_tokens = [token for token in candidate_lower.split(" ") if token]
    for search_token in search_tokens:
        for candidate_token in candidate_tokens:
            ratios.append(SequenceMatcher(None, search_token, candidate_token).ratio())

    return max(ratios)


def _build_fuzzy_rows(
    normalized_term: str,
    normalized_item_type: str,
    excluded_item_ids: set[int],
    relaxed_short_query: bool = False,
) -> list[tuple[int, float, dict]]:
    if normalized_term.isdigit():
        return []

    minimum_ratio = (
        (
            RELAXED_MIN_SHORT_FUZZY_RATIO
            if relaxed_short_query
            else MIN_SHORT_FUZZY_RATIO
        )
        if len(normalized_term.replace(" ", "")) <= 4
        else MIN_FUZZY_RATIO
    )

    fuzzy_rows: list[tuple[int, float, dict]] = []
    for row in _fetch_fuzzy_candidate_rows(normalized_item_type):
        item_id = row[0]
        if item_id in excluded_item_ids:
            continue

        fuzzy_ratio = _calculate_fuzzy_ratio(normalized_term, row[1])
        if fuzzy_ratio < minimum_ratio:
            continue

        fuzzy_rows.append((1, fuzzy_ratio, _map_item_row(row)))

    fuzzy_rows.sort(key=lambda entry: (-entry[1], entry[2]["item_name"].lower(), entry[2]["item_id"]))
    return fuzzy_rows


def search_live_items_page(
    search_term: str,
    limit: int = DEFAULT_SEARCH_LIMIT,
    offset: int = 0,
    item_type: str = "",
    relaxed_short_query: bool = False,
) -> dict:
    """
    Search live items for interactive selection UIs and collection browsing.

    Ranking preference:
    1. exact item_id match
    2. exact item_name match
    3. item_id prefix
    4. item_name prefix
    5. token prefix matches
    6. general substring matches
    7. fuzzy name/token similarity matches
    """
    normalized_term = _normalize_search_term(search_term)
    normalized_item_type = item_type.strip()
    normalized_limit = _normalize_search_limit(limit)
    normalized_offset = _normalize_search_offset(offset)
    normalized_relaxed_short_query = _normalize_relaxed_short_query(relaxed_short_query)

    if len(normalized_term) < MIN_SEARCH_LENGTH and not normalized_term.isdigit():
        return {
            "items": [],
            "has_more": False,
            "next_offset": normalized_offset,
            "limit": normalized_limit,
        }

    direct_rows = _fetch_direct_match_rows(normalized_term, normalized_item_type)
    combined_rows: list[tuple[int, float | int, dict]] = [
        (0, row[7], _map_item_row(row))
        for row in direct_rows
    ]

    direct_item_ids = {row[0] for row in direct_rows}
    combined_rows.extend(
        _build_fuzzy_rows(
            normalized_term,
            normalized_item_type,
            direct_item_ids,
            relaxed_short_query=normalized_relaxed_short_query,
        )
    )

    paged_rows = combined_rows[normalized_offset : normalized_offset + normalized_limit + 1]
    has_more = len(paged_rows) > normalized_limit
    visible_rows = paged_rows[:normalized_limit]
    items = [row[2] for row in visible_rows]

    return {
        "items": items,
        "has_more": has_more,
        "next_offset": normalized_offset + len(items),
        "limit": normalized_limit,
    }


def search_items(
    search_term: str,
    limit: int = DEFAULT_SEARCH_LIMIT,
    item_type: str = "",
    relaxed_short_query: bool = False,
) -> list[dict]:
    return search_items_page(
        search_term=search_term,
        limit=limit,
        offset=0,
        item_type=item_type,
        relaxed_short_query=relaxed_short_query,
    )["items"]


def search_items_page(
    search_term: str,
    limit: int = DEFAULT_SEARCH_LIMIT,
    offset: int = 0,
    item_type: str = "",
    relaxed_short_query: bool = False,
) -> dict:
    return search_live_items_page(
        search_term=search_term,
        limit=limit,
        offset=offset,
        item_type=item_type,
        relaxed_short_query=relaxed_short_query,
    )
