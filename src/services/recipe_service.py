from typing import Any
import sqlite3

from db import get_connection, initialize_database
from services.item_service import (
    DuplicateItemNameError,
    InvalidItemNameError,
    InvalidNumericValueError,
    get_next_available_item_name,
    normalize_item_name,
)
from services.recipe_instruction_codec import encode_instruction_steps_to_text


MOCK_RECIPE_AUTHOR_USER_ID = "dev_user_001"
MOCK_RECIPE_AUTHOR_DISPLAY_NAME = "Plato Choi"


class InvalidRecipePayloadError(ValueError):
    """Raised when the recipe payload is structurally invalid."""


def create_recipe(payload: dict[str, Any]) -> int:
    """
    Validate and insert a recipe plus its component rows.

    Returns the new recipe item_id.
    """
    initialize_database()

    recipe_name = normalize_item_name(str(payload.get("item_name", "")))
    if not recipe_name:
        raise InvalidItemNameError("Recipe name cannot be empty or only whitespace.")

    yield_quantity = payload.get("yield_quantity")
    yield_unit = str(payload.get("yield_unit", "")).strip()

    try:
        yield_quantity = float(yield_quantity)
    except (TypeError, ValueError):
        raise InvalidNumericValueError("Yield quantity must be a valid number.")

    if yield_quantity <= 0:
        raise InvalidNumericValueError("Yield quantity must be greater than 0.")

    if not yield_unit:
        raise InvalidRecipePayloadError("Yield unit is required.")

    serving_size_quantity = payload.get("serving_size_quantity")
    if serving_size_quantity not in (None, ""):
        try:
            serving_size_quantity = float(serving_size_quantity)
        except (TypeError, ValueError):
            raise InvalidNumericValueError("Serving size quantity must be a valid number.")

        if serving_size_quantity <= 0:
            raise InvalidNumericValueError("Serving size quantity must be greater than 0.")
    else:
        serving_size_quantity = None

    serving_size_unit = payload.get("serving_size_unit")
    serving_size_unit = str(serving_size_unit).strip() if serving_size_unit else None

    serving_count = payload.get("serving_count")
    if serving_count not in (None, ""):
        try:
            serving_count = float(serving_count)
        except (TypeError, ValueError):
            raise InvalidNumericValueError("Serving count must be a valid number.")

        if serving_count <= 0:
            raise InvalidNumericValueError("Serving count must be greater than 0.")
    else:
        serving_count = None

    notes = payload.get("notes")
    notes = str(notes).strip() if notes else None

    primary_cooking_method_code = str(payload.get("primary_cooking_method_code", "")).strip()
    if not primary_cooking_method_code:
        raise InvalidRecipePayloadError("Primary cooking method is required.")

    instruction_steps = payload.get("instruction_steps", [])
    if not isinstance(instruction_steps, list):
        raise InvalidRecipePayloadError("Instruction steps must be a list.")

    instructions_text = encode_instruction_steps_to_text(
        [str(step) for step in instruction_steps]
    )

    ingredients = payload.get("ingredients", [])
    if not isinstance(ingredients, list) or not ingredients:
        raise InvalidRecipePayloadError("At least one ingredient is required.")

    validated_ingredients: list[dict[str, Any]] = []
    for index, ingredient in enumerate(ingredients, start=1):
        if not isinstance(ingredient, dict):
            raise InvalidRecipePayloadError("Each ingredient must be an object.")

        component_item_id = ingredient.get("component_item_id")
        component_unit = str(ingredient.get("component_unit", "")).strip()
        component_quantity = ingredient.get("component_quantity")

        try:
            component_item_id = int(component_item_id)
        except (TypeError, ValueError):
            raise InvalidRecipePayloadError("Each ingredient must reference a valid selected item.")

        try:
            component_quantity = float(component_quantity)
        except (TypeError, ValueError):
            raise InvalidNumericValueError("Ingredient quantity must be a valid number.")

        if component_quantity <= 0:
            raise InvalidNumericValueError("Ingredient quantity must be greater than 0.")

        if not component_unit:
            raise InvalidRecipePayloadError("Ingredient unit is required.")

        validated_ingredients.append(
            {
                "component_item_id": component_item_id,
                "component_quantity": component_quantity,
                "component_unit": component_unit,
                "component_sequence": index,
            }
        )

    try:
        with get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO item (
                    item_name,
                    item_type,
                    author_user_id,
                    author_display_name,
                    yield_quantity,
                    yield_unit,
                    serving_size_quantity,
                    serving_size_unit,
                    serving_count,
                    instructions_text,
                    primary_cooking_method_code,
                    status,
                    notes,
                    concept_classification,
                    meal_classification,
                    haccp_process_classification,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                """,
                (
                    recipe_name,
                    "recipe",
                    MOCK_RECIPE_AUTHOR_USER_ID,
                    MOCK_RECIPE_AUTHOR_DISPLAY_NAME,
                    yield_quantity,
                    yield_unit,
                    serving_size_quantity,
                    serving_size_unit,
                    serving_count,
                    instructions_text,
                    primary_cooking_method_code,
                    "submitted",
                    notes,
                    None,
                    None,
                    None,
                ),
            )

            recipe_item_id = cursor.lastrowid

            for ingredient in validated_ingredients:
                cursor.execute(
                    """
                    INSERT INTO recipe_component (
                        parent_recipe_item_id,
                        component_item_id,
                        component_quantity,
                        component_unit,
                        component_sequence,
                        component_notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        recipe_item_id,
                        ingredient["component_item_id"],
                        ingredient["component_quantity"],
                        ingredient["component_unit"],
                        ingredient["component_sequence"],
                        None,
                    ),
                )

            conn.commit()
            return int(recipe_item_id)

    except sqlite3.IntegrityError as exc:
        error_text = str(exc).lower()

        if "unique constraint failed: item.item_name" in error_text:
            suggested_name = get_next_available_item_name(recipe_name)
            raise DuplicateItemNameError(
                "Recipe name already exists. Please enter a unique recipe name.",
                suggested_name=suggested_name,
            ) from exc

        raise