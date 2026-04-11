import sqlite3

from queries.item_detail import get_item_detail
from queries.item_search import DEFAULT_SEARCH_LIMIT, search_items, search_items_page
from services.item_service import create_base_food
from services.recipe_service import create_recipe


def test_search_items_returns_matches_for_name_and_id(isolated_db):
    base_food_id = create_base_food(item_name="Granulated Garlic")
    create_base_food(item_name="Spinach")
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (base_food_id,))
    conn.commit()
    conn.close()

    name_results = search_items("garlic")
    id_results = search_items(str(base_food_id))

    assert any(result["item_name"] == "Granulated Garlic" for result in name_results)
    assert any(result["item_id"] == base_food_id for result in id_results)


def test_search_items_enforces_minimum_length(isolated_db):
    create_base_food(item_name="Salt")

    assert search_items("s") == []


def test_search_items_ranks_exact_name_and_prefix_matches_first(isolated_db):
    first_id = create_base_food(item_name="Chicken Salad")
    second_id = create_base_food(item_name="Roasted Chicken Salad")
    third_id = create_base_food(item_name="Salad Chicken Mix")
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE item SET status = 'live' WHERE item_id IN (?, ?, ?)",
        (first_id, second_id, third_id),
    )
    conn.commit()
    conn.close()

    results = search_items("Chicken Salad")

    assert results[0]["item_name"] == "Chicken Salad"


def test_search_items_honors_limit_and_optional_filters(isolated_db):
    created_ids = []
    for index in range(20):
        created_ids.append(create_base_food(item_name=f"Filter Item {index:02d}"))

    recipe_component_id = create_base_food(item_name="Filter Recipe Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Filter Recipe Match",
            "yield_quantity": 1,
            "yield_unit": "each",
            "primary_cooking_method_code": "bake",
            "instruction_steps": ["Mix", "Bake"],
            "ingredients": [
                {
                    "component_item_id": recipe_component_id,
                    "component_quantity": 1,
                    "component_unit": "oz",
                }
            ],
        }
    )
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE item SET status = 'live' WHERE item_id IN ({})".format(
            ", ".join("?" for _ in [*created_ids, recipe_component_id, recipe_id])
        ),
        [*created_ids, recipe_component_id, recipe_id],
    )
    conn.commit()
    conn.close()

    filtered_results = search_items("Filter", item_type="recipe")
    capped_results = search_items("Filter")

    assert all(result["item_type"] == "recipe" for result in filtered_results)
    assert len(capped_results) == DEFAULT_SEARCH_LIMIT


def test_search_items_excludes_non_live_items(isolated_db):
    live_id = create_base_food(item_name="Live Celery")
    submitted_id = create_base_food(item_name="Submitted Celery")
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (live_id,))
    cursor.execute("UPDATE item SET status = 'submitted' WHERE item_id = ?", (submitted_id,))
    conn.commit()
    conn.close()

    results = search_items("Celery")

    returned_names = [result["item_name"] for result in results]
    assert "Live Celery" in returned_names
    assert "Submitted Celery" not in returned_names


def test_search_items_page_returns_offset_pagination_metadata(isolated_db):
    created_ids = []
    for index in range(18):
        created_ids.append(create_base_food(item_name=f"Paged Search Item {index:02d}"))

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE item SET status = 'live' WHERE item_id IN ({})".format(
            ", ".join("?" for _ in created_ids)
        ),
        created_ids,
    )
    conn.commit()
    conn.close()

    first_page = search_items_page("Paged", limit=10, offset=0)
    second_page = search_items_page("Paged", limit=10, offset=10)

    assert len(first_page["items"]) == 10
    assert first_page["has_more"] is True
    assert first_page["next_offset"] == 10
    assert len(second_page["items"]) == 8
    assert second_page["has_more"] is False
    assert second_page["next_offset"] == 18


def test_search_items_page_supports_fuzzy_match_for_close_typo(isolated_db):
    matched_id = create_base_food(item_name="Chicken Stock")
    other_id = create_base_food(item_name="Vegetable Stock")

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE item SET status = 'live' WHERE item_id IN (?, ?)",
        (matched_id, other_id),
    )
    conn.commit()
    conn.close()

    results = search_items("chikcen")

    assert results
    assert results[0]["item_name"] == "Chicken Stock"


def test_search_items_page_keeps_exact_matches_ahead_of_fuzzy_matches(isolated_db):
    exact_id = create_base_food(item_name="Chicken Salad")
    fuzzy_only_id = create_base_food(item_name="Chikcen Seasoning")

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE item SET status = 'live' WHERE item_id IN (?, ?)",
        (exact_id, fuzzy_only_id),
    )
    conn.commit()
    conn.close()

    results = search_items("Chicken")

    assert results[0]["item_name"] == "Chicken Salad"


def test_search_items_page_relaxed_short_query_can_return_close_match(isolated_db):
    mayo_id = create_base_food(item_name="Mayo")
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("UPDATE item SET status = 'live' WHERE item_id = ?", (mayo_id,))
    conn.commit()
    conn.close()

    default_results = search_items("nayo")
    relaxed_results = search_items("nayo", relaxed_short_query=True)

    assert default_results == []
    assert relaxed_results
    assert relaxed_results[0]["item_name"] == "Mayo"


def test_get_item_detail_returns_base_food_payload(isolated_db):
    item_id = create_base_food(
        item_name="Romaine Lettuce",
        notes="Cold prep only.",
    )

    item = get_item_detail(item_id)

    assert item is not None
    assert item["item_type"] == "base_food"
    assert item["item_type_label"] == "Base Food"
    assert item["primary_cooking_method_label"] is None
    assert item["yield_quantity"] is None
    assert item["yield_unit"] is None
    assert item["instruction_steps"] == []
    assert item["ingredients"] == []


def test_get_item_detail_returns_recipe_payload_with_labels(isolated_db):
    greens_id = create_base_food(item_name="Mixed Greens")

    recipe_id = create_recipe(
        {
            "item_name": "Garden Salad",
            "yield_quantity": 6,
            "yield_unit": "each",
            "primary_cooking_method_code": "no_cooking",
            "instruction_steps": ["Prep greens", "Plate salad"],
            "ingredients": [
                {
                    "component_item_id": greens_id,
                    "component_quantity": 1,
                    "component_unit": "lb",
                }
            ],
        }
    )

    item = get_item_detail(recipe_id)

    assert item is not None
    assert item["item_type"] == "recipe"
    assert item["item_type_label"] == "Recipe"
    assert item["primary_cooking_method_label"] == "no cooking"
    assert item["instruction_steps"] == ["Prep greens", "Plate salad"]
    assert item["ingredients"][0]["component_item_type_label"] == "Base Food"


def test_get_item_detail_returns_none_for_missing_item(isolated_db):
    assert get_item_detail(9999) is None
