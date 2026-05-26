from config.item_categories import ITEM_CATEGORY_VALUES
from db import get_connection


PRODUCE_TERMS = {
    "apple",
    "apricot",
    "avocado",
    "banana",
    "bean sprout",
    "beet",
    "berry",
    "broccoli",
    "cabbage",
    "carrot",
    "cauliflower",
    "celery",
    "cherry",
    "cilantro",
    "corn",
    "cucumber",
    "eggplant",
    "garlic",
    "grape",
    "green bean",
    "greens",
    "kale",
    "leek",
    "lettuce",
    "lime",
    "melon",
    "mushroom",
    "onion",
    "orange",
    "parsley",
    "pea",
    "pepper",
    "pineapple",
    "potato",
    "radish",
    "spinach",
    "squash",
    "strawberry",
    "tomato",
    "zucchini",
}
MEAT_TERMS = {
    "bacon",
    "beef",
    "burger",
    "chicken",
    "fish",
    "ham",
    "lamb",
    "meat",
    "pork",
    "salmon",
    "sausage",
    "seafood",
    "shrimp",
    "steak",
    "turkey",
    "tuna",
}
DAIRY_TERMS = {
    "butter",
    "cheddar",
    "cheese",
    "cream",
    "dairy",
    "egg",
    "half and half",
    "milk",
    "mozzarella",
    "parmesan",
    "yogurt",
}
BAKERY_TERMS = {
    "bagel",
    "bakery",
    "biscuit",
    "bread",
    "bun",
    "cake",
    "croissant",
    "dough",
    "muffin",
    "pastry",
    "pita",
    "roll",
    "tortilla",
}
BEVERAGE_TERMS = {
    "beverage",
    "coffee",
    "drink",
    "juice",
    "lemonade",
    "milkshake",
    "soda",
    "tea",
    "water",
}
FROZEN_TERMS = {
    "frozen",
    "ice cream",
    "sorbet",
}


def _contains_any(text: str, terms: set[str]) -> bool:
    return any(term in text for term in terms)


def infer_item_category(*, item_name: str, nutrition_group: str | None = None) -> str:
    text = f"{item_name or ''} {nutrition_group or ''}".casefold()
    if _contains_any(text, FROZEN_TERMS):
        return "frozen"
    if _contains_any(text, BEVERAGE_TERMS):
        return "beverages"
    if _contains_any(text, DAIRY_TERMS):
        return "dairy"
    if _contains_any(text, MEAT_TERMS):
        return "meat"
    if _contains_any(text, BAKERY_TERMS):
        return "bakery"
    if _contains_any(text, PRODUCE_TERMS):
        return "produce"
    return "grocery"


def sync_item_categories() -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT item_id, item_name, nutrition_group
            FROM item
            WHERE item_category NOT IN ({})
               OR item_category = 'grocery'
            """.format(", ".join("?" for _ in ITEM_CATEGORY_VALUES)),
            ITEM_CATEGORY_VALUES,
        )
        rows = cursor.fetchall()
        updated_count = 0
        for item_id, item_name, nutrition_group in rows:
            category = infer_item_category(
                item_name=item_name,
                nutrition_group=nutrition_group,
            )
            cursor.execute(
                """
                UPDATE item
                SET item_category = ?,
                    updated_at = updated_at
                WHERE item_id = ?
                  AND item_category != ?
                """,
                (category, item_id, category),
            )
            updated_count += cursor.rowcount
        conn.commit()
        return updated_count
