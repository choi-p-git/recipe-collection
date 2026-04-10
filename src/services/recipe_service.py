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
from services.item_event_service import (
    build_creation_summary,
    build_resubmission_summary,
    build_update_summary,
    record_item_event,
)
from services.recipe_instruction_codec import encode_instruction_steps_to_text


MOCK_RECIPE_AUTHOR_USER_ID = "dev_user_001"
MOCK_RECIPE_AUTHOR_DISPLAY_NAME = "Plato Choi"


class InvalidRecipePayloadError(ValueError):
    """Raised when the recipe payload is structurally invalid."""


def _validate_recipe_payload(payload: dict[str, Any]) -> dict[str, Any]:
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

    concept_classification = str(payload.get("concept_classification", "")).strip() or None
    meal_classification = str(payload.get("meal_classification", "")).strip() or None
    haccp_process_classification = (
        str(payload.get("haccp_process_classification", "")).strip() or None
    )

    return {
        "recipe_name": recipe_name,
        "yield_quantity": yield_quantity,
        "yield_unit": yield_unit,
        "serving_size_quantity": serving_size_quantity,
        "serving_size_unit": serving_size_unit,
        "serving_count": serving_count,
        "notes": notes,
        "primary_cooking_method_code": primary_cooking_method_code,
        "instructions_text": instructions_text,
        "validated_ingredients": validated_ingredients,
        "concept_classification": concept_classification,
        "meal_classification": meal_classification,
        "haccp_process_classification": haccp_process_classification,
    }


def create_recipe(
    payload: dict[str, Any],
    author_user_id: str = MOCK_RECIPE_AUTHOR_USER_ID,
    author_display_name: str = MOCK_RECIPE_AUTHOR_DISPLAY_NAME,
    author_role: str = "standard_user",
) -> int:
    """
    Validate and insert a recipe plus its component rows.

    Returns the new recipe item_id.
    """
    initialize_database()

    validated = _validate_recipe_payload(payload)

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
                    validated["recipe_name"],
                    "recipe",
                    author_user_id,
                    author_display_name,
                    validated["yield_quantity"],
                    validated["yield_unit"],
                    validated["serving_size_quantity"],
                    validated["serving_size_unit"],
                    validated["serving_count"],
                    validated["instructions_text"],
                    validated["primary_cooking_method_code"],
                    "submitted",
                    validated["notes"],
                    validated["concept_classification"],
                    validated["meal_classification"],
                    validated["haccp_process_classification"],
                ),
            )

            recipe_item_id = cursor.lastrowid

            for ingredient in validated["validated_ingredients"]:
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

            record_item_event(
                item_id=int(recipe_item_id),
                event_type="item_created",
                actor_user_id=author_user_id,
                actor_display_name=author_display_name,
                actor_role=author_role,
                event_summary=build_creation_summary("recipe"),
                conn=conn,
            )

            conn.commit()
            return int(recipe_item_id)

    except sqlite3.IntegrityError as exc:
        error_text = str(exc).lower()

        if "unique constraint failed: item.item_name" in error_text:
            suggested_name = get_next_available_item_name(validated["recipe_name"])
            raise DuplicateItemNameError(
                "Recipe name already exists. Please enter a unique recipe name.",
                suggested_name=suggested_name,
            ) from exc

        raise


def update_recipe(
    item_id: int,
    payload: dict[str, Any],
    clear_resubmission_request: bool = False,
    actor_user_id: str = MOCK_RECIPE_AUTHOR_USER_ID,
    actor_display_name: str = MOCK_RECIPE_AUTHOR_DISPLAY_NAME,
    actor_role: str = "standard_user",
) -> None:
    """Validate and update an existing recipe plus its component rows."""
    initialize_database()

    validated = _validate_recipe_payload(payload)

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE item
                SET item_name = ?,
                    yield_quantity = ?,
                    yield_unit = ?,
                    serving_size_quantity = ?,
                    serving_size_unit = ?,
                    serving_count = ?,
                    instructions_text = ?,
                    primary_cooking_method_code = ?,
                    notes = ?,
                    concept_classification = ?,
                    meal_classification = ?,
                    haccp_process_classification = ?,
                    requires_resubmission = CASE
                        WHEN ? THEN 0
                        ELSE requires_resubmission
                    END,
                    updated_at = datetime('now')
                WHERE item_id = ?
                  AND item_type = 'recipe'
                """,
                (
                    validated["recipe_name"],
                    validated["yield_quantity"],
                    validated["yield_unit"],
                    validated["serving_size_quantity"],
                    validated["serving_size_unit"],
                    validated["serving_count"],
                    validated["instructions_text"],
                    validated["primary_cooking_method_code"],
                    validated["notes"],
                    validated["concept_classification"],
                    validated["meal_classification"],
                    validated["haccp_process_classification"],
                    1 if clear_resubmission_request else 0,
                    item_id,
                ),
            )

            if cursor.rowcount == 0:
                raise InvalidRecipePayloadError("Recipe not found.")

            cursor.execute(
                "DELETE FROM recipe_component WHERE parent_recipe_item_id = ?",
                (item_id,),
            )

            for ingredient in validated["validated_ingredients"]:
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
                        item_id,
                        ingredient["component_item_id"],
                        ingredient["component_quantity"],
                        ingredient["component_unit"],
                        ingredient["component_sequence"],
                        None,
                    ),
                )

            record_item_event(
                item_id=item_id,
                event_type="item_resubmitted" if clear_resubmission_request else "item_updated",
                actor_user_id=actor_user_id,
                actor_display_name=actor_display_name,
                actor_role=actor_role,
                event_summary=(
                    build_resubmission_summary()
                    if clear_resubmission_request
                    else build_update_summary("recipe")
                ),
                conn=conn,
            )

            conn.commit()

    except sqlite3.IntegrityError as exc:
        error_text = str(exc).lower()

        if "unique constraint failed: item.item_name" in error_text:
            suggested_name = get_next_available_item_name(validated["recipe_name"])
            raise DuplicateItemNameError(
                "Recipe name already exists. Please enter a unique recipe name.",
                suggested_name=suggested_name,
            ) from exc

        raise
