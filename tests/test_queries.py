from queries.item_detail import get_item_detail
from queries.item_search import search_items
from services.item_service import create_base_food
from services.recipe_service import create_recipe


def test_search_items_returns_matches_for_name_and_id(isolated_db):
    base_food_id = create_base_food(item_name="Granulated Garlic")
    create_base_food(item_name="Spinach")

    name_results = search_items("garlic")
    id_results = search_items(str(base_food_id))

    assert any(result["item_name"] == "Granulated Garlic" for result in name_results)
    assert any(result["item_id"] == base_food_id for result in id_results)


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
