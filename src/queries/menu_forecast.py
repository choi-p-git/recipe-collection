from difflib import SequenceMatcher

from config.menu_builder import DAY_OF_WEEK_OPTIONS, MEAL_PERIOD_OPTIONS
from db import get_connection
from services.menu_forecast_service import (
    InvalidMenuForecastError,
    build_menu_forecast_production_summary,
    calculate_advanced_case_effective_yield,
    decorate_batch_splits,
)
from services.recipe_flattening_service import build_flattened_recipe_view


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


def _get_case_basis_candidates(cursor, *, item_id: int, item_type: str, item_name: str) -> dict:
    if item_type == "base_food":
        candidate = {
            "component_item_id": item_id,
            "component_item_name": item_name,
            "source": "This item",
            "depth": 0,
            "row_key": str(item_id),
        }
        return {"hierarchical": [candidate], "flattened": [candidate]}

    cursor.execute(
        """
        SELECT
            rc.component_item_id,
            rc.recipe_component_id,
            i.item_name,
            rc.component_quantity,
            rc.component_unit
        FROM recipe_component rc
        JOIN item i
          ON i.item_id = rc.component_item_id
        WHERE rc.parent_recipe_item_id = ?
        ORDER BY rc.component_sequence ASC, rc.recipe_component_id ASC
        """,
        (item_id,),
    )
    hierarchical = [
        {
            "component_item_id": row[0],
            "row_key": str(row[1]),
            "component_item_name": row[2],
            "quantity_display": f"{row[3]:g}",
            "unit": row[4],
            "source": "Direct ingredient",
            "depth": 0,
        }
        for row in cursor.fetchall()
    ]

    flattened_view = build_flattened_recipe_view(item_id)
    flattened = [
        {
            "component_item_id": row["component_item_id"],
            "row_key": str(index),
            "component_item_name": row["component_item_name"],
            "quantity_display": row["quantity_display"],
            "unit": row["component_unit"],
            "source": row.get("source_recipe_name") or "Flattened ingredient",
            "depth": int(row.get("depth") or 0),
        }
        for index, row in enumerate(flattened_view["rows"])
    ]
    return {"hierarchical": hierarchical, "flattened": flattened}


def _resolve_case_basis_row_key(candidates: dict, *, component_item_id: int | None, view_mode: str) -> str:
    if component_item_id is None:
        return ""
    candidate_view = "flattened" if view_mode == "flattened" else "hierarchical"
    for candidate in candidates.get(candidate_view, []):
        if int(candidate["component_item_id"]) == int(component_item_id):
            return str(candidate.get("row_key") or "")
    return ""


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
                i.item_type,
                i.yield_quantity,
                i.yield_unit,
                i.mass_quantity,
                i.mass_unit,
                i.volume_quantity,
                i.volume_unit,
                i.serving_size_quantity,
                i.serving_size_unit,
                mf.menu_forecast_id,
                mf.forecast_yield_quantity,
                mf.forecast_yield_unit,
                mf.user_serving_size_quantity,
                mf.user_serving_size_unit,
                mf.desired_portions,
                mf.forecast_display_unit,
                mf.case_quantity,
                mf.case_pack_quantity,
                mf.case_subunit_quantity,
                mf.case_subunit_unit,
                mf.calculated_forecast_quantity,
                mf.calculated_forecast_unit,
                mf.case_basis_component_item_id,
                mf.case_basis_component_name,
                mf.case_basis_view_mode,
                mf.case_basis_row_key,
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
              AND i.item_type IN ('recipe', 'base_food')
              AND i.status = 'live'
            """,
            (menu_id, normalized_week, normalized_day),
        )
        recipe_rows = cursor.fetchall()
        menu_slot_item_ids = [row[3] for row in recipe_rows]
        batch_split_lookup: dict[int, list[dict]] = {}
        if menu_slot_item_ids:
            cursor.execute(
                """
                SELECT
                    menu_slot_item_id,
                    batch_sequence,
                    batch_percent,
                    planned_time
                FROM menu_forecast_batch_split
                WHERE menu_slot_item_id IN ({})
                ORDER BY menu_slot_item_id ASC, batch_sequence ASC
                """.format(", ".join("?" for _ in menu_slot_item_ids)),
                menu_slot_item_ids,
            )
            for split_row in cursor.fetchall():
                batch_split_lookup.setdefault(split_row[0], []).append(
                    {
                        "batch_sequence": split_row[1],
                        "batch_percent": split_row[2],
                        "planned_time": split_row[3],
                    }
                )

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

        forecast_quantity = row[17] if row[17] is not None else 0
        forecast_unit = row[22] or row[18] or row[9] or "each"
        effective_forecast_quantity = row[27] if row[27] is not None else forecast_quantity
        effective_forecast_unit = row[28] or (row[18] if forecast_unit != "case" else "") or row[9] or "each"
        case_basis_candidates = _get_case_basis_candidates(
            cursor,
            item_id=row[5],
            item_type=row[7],
            item_name=item_name,
        )
        case_basis_view_mode = row[31] or "hierarchical"
        case_basis_row_key = row[32] or _resolve_case_basis_row_key(
            case_basis_candidates,
            component_item_id=row[29],
            view_mode=case_basis_view_mode,
        )
        if (
            forecast_unit == "case"
            and row[7] == "recipe"
            and row[29] is not None
            and case_basis_row_key
            and forecast_quantity is not None
            and row[24] is not None
            and row[25] is not None
            and row[26]
        ):
            try:
                calculated_case = calculate_advanced_case_effective_yield(
                    recipe_item_id=row[5],
                    case_quantity=forecast_quantity,
                    case_pack_quantity=row[24],
                    case_subunit_quantity=row[25],
                    case_subunit_unit=row[26],
                    case_basis_view_mode=case_basis_view_mode,
                    case_basis_row_key=case_basis_row_key,
                )
                effective_forecast_quantity = calculated_case["calculated_quantity"]
                effective_forecast_unit = calculated_case["calculated_unit"]
            except InvalidMenuForecastError:
                pass
        batch_splits = decorate_batch_splits(
            batch_split_lookup.get(row[3], []),
            forecast_quantity=effective_forecast_quantity,
            forecast_unit=effective_forecast_unit,
            display_forecast_quantity=forecast_quantity,
            display_forecast_unit=forecast_unit,
        )
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
                "item_type": row[7],
                "yield_quantity": row[8],
                "yield_unit": row[9] or "",
                "mass_quantity": row[10],
                "mass_unit": row[11] or "",
                "volume_quantity": row[12],
                "volume_unit": row[13] or "",
                "serving_size_quantity": f"{row[14]:g}" if row[14] is not None else "",
                "serving_size_unit": row[15] or "",
                "menu_forecast_id": row[16],
                "forecast_quantity": f"{forecast_quantity:g}",
                "forecast_unit": forecast_unit,
                "user_serving_size_quantity": f"{row[19]:g}" if row[19] is not None else "",
                "user_serving_size_unit": row[20] or "",
                "desired_portions": f"{row[21]:g}" if row[21] is not None else "",
                "case_pack_quantity": f"{row[24]:g}" if row[24] is not None else "",
                "case_subunit_quantity": f"{row[25]:g}" if row[25] is not None else "",
                "case_subunit_unit": row[26] or "",
                "effective_forecast_quantity": effective_forecast_quantity,
                "effective_forecast_quantity_display": f"{effective_forecast_quantity:g}" if effective_forecast_quantity is not None else "",
                "effective_forecast_unit": effective_forecast_unit,
                "is_case_forecast": forecast_unit == "case",
                "case_basis_component_item_id": row[29],
                "case_basis_component_name": row[30] or "",
                "case_basis_view_mode": case_basis_view_mode,
                "case_basis_row_key": case_basis_row_key,
                "case_basis_candidates": case_basis_candidates,
                "forecast_updated_at": row[33],
                "batch_splits": batch_splits,
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
        "production_summary": build_menu_forecast_production_summary(rows),
        "search_term": normalized_search,
        "selected_meal_period": normalized_meal_period,
        "selected_concept": normalized_concept,
        "selected_sort": normalized_sort_by,
        "selected_order": normalized_sort_order,
    }
