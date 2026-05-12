from difflib import SequenceMatcher

from config.menu_builder import DAY_OF_WEEK_OPTIONS, MEAL_PERIOD_OPTIONS
from db import get_connection


MIN_FORECAST_FUZZY_RATIO = 0.62


def _label_lookup(options: list[dict[str, str]]) -> dict[str, str]:
    return {option["value"]: option["label"] for option in options}


def _normalize_search_term(search_term: str) -> str:
    return " ".join(str(search_term or "").split())


def _matches_recipe_search(recipe_name: str, normalized_term: str) -> bool:
    if not normalized_term:
        return True

    recipe_lower = recipe_name.lower()
    term_lower = normalized_term.lower()
    if term_lower in recipe_lower:
        return True

    compact_recipe = recipe_lower.replace(" ", "")
    compact_term = term_lower.replace(" ", "")
    ratios = [
        SequenceMatcher(None, term_lower, recipe_lower).ratio(),
        SequenceMatcher(None, compact_term, compact_recipe).ratio(),
    ]
    for token in term_lower.split():
        ratios.extend(
            SequenceMatcher(None, token, candidate).ratio()
            for candidate in recipe_lower.split()
        )

    return max(ratios) >= MIN_FORECAST_FUZZY_RATIO


def _normalize_sort(sort_by: str, sort_order: str) -> tuple[str, str]:
    normalized_sort_by = sort_by if sort_by in {"menu_order", "meal_period", "concept"} else "menu_order"
    normalized_sort_order = sort_order if sort_order in {"asc", "desc"} else "asc"
    return normalized_sort_by, normalized_sort_order


def get_menu_forecast_page(
    menu_id: int,
    *,
    week_number: int,
    day_of_week: str,
    search_term: str = "",
    meal_period: str = "",
    concept: str = "",
    sort_by: str = "menu_order",
    sort_order: str = "asc",
) -> dict | None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                menu_id,
                menu_name,
                author_user_id,
                author_display_name,
                service_days_json,
                meal_periods_json,
                concepts_json,
                menu_length_weeks,
                status
            FROM menu
            WHERE menu_id = ?
            """,
            (menu_id,),
        )
        menu_row = cursor.fetchone()
        if menu_row is None:
            return None

        import json

        service_days = json.loads(menu_row[4])
        meal_periods = json.loads(menu_row[5])
        concepts = json.loads(menu_row[6])
        menu_length_weeks = int(menu_row[7])

        normalized_week = week_number if 1 <= week_number <= menu_length_weeks else 1
        normalized_day = day_of_week if day_of_week in service_days else service_days[0]
        normalized_meal_period = meal_period if meal_period in meal_periods else ""
        normalized_concept = concept if concept in concepts else ""
        normalized_search = _normalize_search_term(search_term)
        normalized_sort_by, normalized_sort_order = _normalize_sort(sort_by, sort_order)

        cursor.execute(
            """
            SELECT
                ms.menu_slot_id,
                ms.meal_period,
                ms.concept_name,
                msi.menu_slot_item_id,
                msi.item_sequence,
                i.item_id,
                i.item_name,
                i.yield_quantity,
                i.yield_unit,
                mf.menu_forecast_id,
                mf.forecast_yield_quantity,
                mf.forecast_yield_unit,
                mf.updated_at
            FROM menu_slot ms
            JOIN menu_slot_item msi
              ON msi.menu_slot_id = ms.menu_slot_id
            JOIN item i
              ON i.item_id = msi.item_id
            LEFT JOIN menu_forecast mf
              ON mf.menu_slot_item_id = msi.menu_slot_item_id
            WHERE ms.menu_id = ?
              AND ms.week_number = ?
              AND ms.day_of_week = ?
              AND i.item_type = 'recipe'
              AND i.status = 'live'
            """,
            (menu_id, normalized_week, normalized_day),
        )
        recipe_rows = cursor.fetchall()

    day_labels = _label_lookup(DAY_OF_WEEK_OPTIONS)
    meal_labels = _label_lookup(MEAL_PERIOD_OPTIONS)
    meal_index = {value: index for index, value in enumerate(meal_periods)}
    concept_index = {value: index for index, value in enumerate(concepts)}

    rows = []
    for row in recipe_rows:
        meal_value = row[1]
        concept_value = row[2]
        item_name = row[6]
        if normalized_meal_period and meal_value != normalized_meal_period:
            continue
        if normalized_concept and concept_value != normalized_concept:
            continue
        if not _matches_recipe_search(item_name, normalized_search):
            continue

        rows.append(
            {
                "menu_slot_id": row[0],
                "meal_period": meal_value,
                "meal_period_label": meal_labels.get(meal_value, meal_value.replace("_", " ").title()),
                "concept": concept_value,
                "concept_label": concept_value.replace("_", " ").title(),
                "menu_slot_item_id": row[3],
                "item_sequence": row[4],
                "item_id": row[5],
                "recipe_name": item_name,
                "yield_quantity": row[7],
                "yield_unit": row[8] or "",
                "menu_forecast_id": row[9],
                "forecast_quantity": f"{row[10]:g}" if row[10] is not None else "0",
                "forecast_unit": row[11] or row[8] or "",
                "forecast_updated_at": row[12],
                "menu_order": (
                    meal_index.get(meal_value, 999),
                    concept_index.get(concept_value, 999),
                    row[4],
                    item_name.lower(),
                    row[5],
                ),
            }
        )

    if normalized_sort_by == "meal_period":
        rows.sort(key=lambda item: (meal_index.get(item["meal_period"], 999), item["concept_label"], item["recipe_name"].lower()))
    elif normalized_sort_by == "concept":
        rows.sort(key=lambda item: (concept_index.get(item["concept"], 999), item["meal_period_label"], item["recipe_name"].lower()))
    else:
        rows.sort(key=lambda item: item["menu_order"])

    if normalized_sort_order == "desc":
        rows.reverse()

    week_numbers = list(range(1, menu_length_weeks + 1))
    cycle_start = ((normalized_week - 1) // 4) * 4 + 1
    cycle_weeks = [week for week in range(cycle_start, min(cycle_start + 4, menu_length_weeks + 1))]

    return {
        "menu": {
            "menu_id": menu_row[0],
            "menu_name": menu_row[1],
            "author_user_id": menu_row[2],
            "author_display_name": menu_row[3],
            "service_days": service_days,
            "meal_periods": meal_periods,
            "concepts": concepts,
            "menu_length_weeks": menu_length_weeks,
            "status": menu_row[8],
        },
        "selected_week_number": normalized_week,
        "selected_day": normalized_day,
        "selected_day_label": day_labels.get(normalized_day, normalized_day.title()),
        "week_numbers": week_numbers,
        "cycle_start": cycle_start,
        "cycle_weeks": cycle_weeks,
        "previous_cycle_week": cycle_start - 4 if cycle_start > 1 else None,
        "next_cycle_week": cycle_start + 4 if cycle_start + 4 <= menu_length_weeks else None,
        "rows": rows,
        "search_term": normalized_search,
        "selected_meal_period": normalized_meal_period,
        "selected_concept": normalized_concept,
        "selected_sort": normalized_sort_by,
        "selected_order": normalized_sort_order,
    }
