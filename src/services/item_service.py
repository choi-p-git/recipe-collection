import re
import sqlite3

from db import get_connection, initialize_database
from config.units import STANDARD_UNITS
from services.item_event_service import build_creation_summary, build_update_summary, record_item_event
from services.notification_service import create_post_live_edit_notifications
from services.unit_conversion_service import normalize_unit_symbol


SYSTEM_BASE_FOOD_USER_ID = "system_base_food"
SYSTEM_BASE_FOOD_DISPLAY_NAME = "Base Food Submission"
STANDARD_UNIT_SET = set(STANDARD_UNITS)


class DuplicateItemNameError(ValueError):
    """Raised when an item_name already exists in the database."""

    def __init__(self, message: str, suggested_name: str | None = None) -> None:
        super().__init__(message)
        self.suggested_name = suggested_name

class InvalidItemNameError(ValueError):
    """Raised when item_name is invalid after normalization."""

class InvalidNumericValueError(ValueError):
    """Raised when a numeric field is valid syntax but violates business rules."""


def normalize_item_name(name: str) -> str:
    """
    Normalize item names by:
    - trimming leading/trailing whitespace
    - collapsing repeated internal whitespace to a single space
    """
    return " ".join(name.split())


def normalize_authoring_unit(unit: str | None, field_label: str) -> str | None:
    normalized_unit = normalize_unit_symbol(unit)
    if not normalized_unit:
        return None
    if normalized_unit not in STANDARD_UNIT_SET:
        raise InvalidNumericValueError(f"{field_label} must use a standard authoring unit.")
    return normalized_unit


def get_next_available_item_name(base_name: str) -> str:
    """
    Return the next available unique item name using the pattern:
    'Name', 'Name (1)', 'Name (2)', etc.

    Rule used:
    - if exact base_name exists (case-insensitive), suggest highest existing suffix + 1
    - do not try to fill gaps
    """
    initialize_database()

    base_name = normalize_item_name(base_name)

    pattern = re.compile(rf"^{re.escape(base_name)} \((\d+)\)$", re.IGNORECASE)

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT item_name
            FROM item
            WHERE item_name = ?
               OR item_name LIKE ?
            COLLATE NOCASE
            """,
            (base_name, f"{base_name} (%)"),
        )

        existing_names = [row[0] for row in cursor.fetchall()]

    existing_names_lower = {name.lower() for name in existing_names}

    if base_name.lower() not in existing_names_lower:
        return base_name

    max_suffix = 0

    for name in existing_names:
        match = pattern.match(name)
        if match:
            suffix = int(match.group(1))
            if suffix > max_suffix:
                max_suffix = suffix

    return f"{base_name} ({max_suffix + 1})"


def create_base_food(
    item_name: str,
    yield_quantity: float | None = None,
    yield_unit: str | None = None,
    mass_quantity: float | None = None,
    mass_unit: str | None = None,
    volume_quantity: float | None = None,
    volume_unit: str | None = None,
    nutrition_group: str | None = None,
    kcal_per_serving: float | None = None,
    nutrition_serving_mass_quantity: float | None = None,
    nutrition_serving_mass_unit: str | None = None,
    nutrition_serving_volume_quantity: float | None = None,
    nutrition_serving_volume_unit: str | None = None,
    serving_size_quantity: float | None = None,
    serving_size_unit: str | None = None,
    serving_count: float | None = 1,
    notes: str | None = None,
    actor_user_id: str = SYSTEM_BASE_FOOD_USER_ID,
    actor_display_name: str = SYSTEM_BASE_FOOD_DISPLAY_NAME,
    actor_role: str = "standard_user",
) -> int:
    """Insert a new base food item and return its item_id."""
    initialize_database()

    item_name = normalize_item_name(item_name)

    if not item_name:
        raise InvalidItemNameError("Item name cannot be empty or only whitespace.")

    yield_unit = normalize_authoring_unit(yield_unit, "Yield unit")
    mass_unit = normalize_authoring_unit(mass_unit, "Mass unit")
    volume_unit = normalize_authoring_unit(volume_unit, "Volume unit")
    nutrition_serving_mass_unit = normalize_authoring_unit(
        nutrition_serving_mass_unit,
        "Nutrition serving mass unit",
    )
    nutrition_serving_volume_unit = normalize_authoring_unit(
        nutrition_serving_volume_unit,
        "Nutrition serving volume unit",
    )
    serving_size_unit = normalize_authoring_unit(serving_size_unit, "Serving size unit")

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
                    mass_quantity,
                    mass_unit,
                    volume_quantity,
                    volume_unit,
                    nutrition_group,
                    kcal_per_serving,
                    nutrition_serving_mass_quantity,
                    nutrition_serving_mass_unit,
                    nutrition_serving_volume_quantity,
                    nutrition_serving_volume_unit,
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
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                """,
                (
                    item_name,
                    "base_food",
                    SYSTEM_BASE_FOOD_USER_ID,
                    SYSTEM_BASE_FOOD_DISPLAY_NAME,
                    yield_quantity,
                    yield_unit,
                    mass_quantity,
                    mass_unit,
                    volume_quantity,
                    volume_unit,
                    nutrition_group,
                    kcal_per_serving,
                    nutrition_serving_mass_quantity,
                    nutrition_serving_mass_unit,
                    nutrition_serving_volume_quantity,
                    nutrition_serving_volume_unit,
                    serving_size_quantity,
                    serving_size_unit,
                    serving_count,
                    None,
                    None,
                    "submitted",
                    notes,
                    None,
                    None,
                    None,
                ),
            )

            item_id = int(cursor.lastrowid)
            record_item_event(
                item_id=item_id,
                event_type="item_created",
                actor_user_id=actor_user_id,
                actor_display_name=actor_display_name,
                actor_role=actor_role,
                event_summary=build_creation_summary("base_food"),
                conn=conn,
            )

            conn.commit()
            return item_id

    except sqlite3.IntegrityError as exc:
        error_text = str(exc).lower()

        if "unique constraint failed: item.item_name" in error_text:
            suggested_name = get_next_available_item_name(item_name)
            raise DuplicateItemNameError(
                "Item name already exists. Please enter a unique item name.",
                suggested_name=suggested_name,
            ) from exc

        raise


def update_base_food(
    item_id: int,
    item_name: str,
    notes: str | None = None,
    mass_quantity: float | None = None,
    mass_unit: str | None = None,
    volume_quantity: float | None = None,
    volume_unit: str | None = None,
    nutrition_group: str | None = None,
    kcal_per_serving: float | None = None,
    nutrition_serving_mass_quantity: float | None = None,
    nutrition_serving_mass_unit: str | None = None,
    nutrition_serving_volume_quantity: float | None = None,
    nutrition_serving_volume_unit: str | None = None,
    actor_user_id: str = SYSTEM_BASE_FOOD_USER_ID,
    actor_display_name: str = SYSTEM_BASE_FOOD_DISPLAY_NAME,
    actor_role: str = "standard_user",
) -> None:
    """Update an existing base food item."""
    initialize_database()

    item_name = normalize_item_name(item_name)

    if not item_name:
        raise InvalidItemNameError("Item name cannot be empty or only whitespace.")

    if mass_quantity in ("", None):
        mass_quantity = None
    elif not isinstance(mass_quantity, (int, float)):
        try:
            mass_quantity = float(mass_quantity)
        except (TypeError, ValueError):
            raise InvalidNumericValueError("Mass quantity must be a valid number.")

    if mass_quantity is not None and mass_quantity <= 0:
        raise InvalidNumericValueError("Mass quantity must be greater than 0.")

    if volume_quantity in ("", None):
        volume_quantity = None
    elif not isinstance(volume_quantity, (int, float)):
        try:
            volume_quantity = float(volume_quantity)
        except (TypeError, ValueError):
            raise InvalidNumericValueError("Volume quantity must be a valid number.")

    if volume_quantity is not None and volume_quantity <= 0:
        raise InvalidNumericValueError("Volume quantity must be greater than 0.")

    mass_unit = normalize_authoring_unit(mass_unit, "Mass unit")
    volume_unit = normalize_authoring_unit(volume_unit, "Volume unit")

    nutrition_group = str(nutrition_group).strip() if nutrition_group else None

    if kcal_per_serving in ("", None):
        kcal_per_serving = None
    elif not isinstance(kcal_per_serving, (int, float)):
        try:
            kcal_per_serving = float(kcal_per_serving)
        except (TypeError, ValueError):
            raise InvalidNumericValueError("Calories per serving must be a valid number.")

    if kcal_per_serving is not None and kcal_per_serving < 0:
        raise InvalidNumericValueError("Calories per serving cannot be negative.")

    if nutrition_serving_mass_quantity in ("", None):
        nutrition_serving_mass_quantity = None
    elif not isinstance(nutrition_serving_mass_quantity, (int, float)):
        try:
            nutrition_serving_mass_quantity = float(nutrition_serving_mass_quantity)
        except (TypeError, ValueError):
            raise InvalidNumericValueError("Nutrition serving mass quantity must be a valid number.")

    if (
        nutrition_serving_mass_quantity is not None
        and nutrition_serving_mass_quantity <= 0
    ):
        raise InvalidNumericValueError("Nutrition serving mass quantity must be greater than 0.")

    nutrition_serving_mass_unit = (
        normalize_authoring_unit(nutrition_serving_mass_unit, "Nutrition serving mass unit")
        if nutrition_serving_mass_unit
        else None
    )

    if nutrition_serving_volume_quantity in ("", None):
        nutrition_serving_volume_quantity = None
    elif not isinstance(nutrition_serving_volume_quantity, (int, float)):
        try:
            nutrition_serving_volume_quantity = float(nutrition_serving_volume_quantity)
        except (TypeError, ValueError):
            raise InvalidNumericValueError("Nutrition serving volume quantity must be a valid number.")

    if (
        nutrition_serving_volume_quantity is not None
        and nutrition_serving_volume_quantity <= 0
    ):
        raise InvalidNumericValueError("Nutrition serving volume quantity must be greater than 0.")

    nutrition_serving_volume_unit = (
        normalize_authoring_unit(nutrition_serving_volume_unit, "Nutrition serving volume unit")
        if nutrition_serving_volume_unit
        else None
    )

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT author_user_id, status
                FROM item
                WHERE item_id = ?
                  AND item_type = 'base_food'
                """,
                (item_id,),
            )
            existing_row = cursor.fetchone()
            if existing_row is None:
                raise InvalidItemNameError("Base food not found.")

            cursor.execute(
                """
                UPDATE item
                SET item_name = ?,
                    mass_quantity = ?,
                    mass_unit = ?,
                    volume_quantity = ?,
                    volume_unit = ?,
                    nutrition_group = ?,
                    kcal_per_serving = ?,
                    nutrition_serving_mass_quantity = ?,
                    nutrition_serving_mass_unit = ?,
                    nutrition_serving_volume_quantity = ?,
                    nutrition_serving_volume_unit = ?,
                    serving_count = 1,
                    notes = ?,
                    updated_at = datetime('now')
                WHERE item_id = ?
                  AND item_type = 'base_food'
                """,
                (
                    item_name,
                    mass_quantity,
                    mass_unit,
                    volume_quantity,
                    volume_unit,
                    nutrition_group,
                    kcal_per_serving,
                    nutrition_serving_mass_quantity,
                    nutrition_serving_mass_unit,
                    nutrition_serving_volume_quantity,
                    nutrition_serving_volume_unit,
                    notes,
                    item_id,
                ),
            )

            record_item_event(
                item_id=item_id,
                event_type="item_updated",
                actor_user_id=actor_user_id,
                actor_display_name=actor_display_name,
                actor_role=actor_role,
                event_summary=build_update_summary("base_food"),
                conn=conn,
            )
            if existing_row[1] == "live":
                create_post_live_edit_notifications(
                    item={
                        "item_id": item_id,
                        "author_user_id": existing_row[0],
                    },
                    actor_user_id=actor_user_id,
                    actor_display_name=actor_display_name,
                    actor_role=actor_role,
                    message_text="Live base food updated.",
                    conn=conn,
                )

            conn.commit()

    except sqlite3.IntegrityError as exc:
        error_text = str(exc).lower()

        if "unique constraint failed: item.item_name" in error_text:
            suggested_name = get_next_available_item_name(item_name)
            raise DuplicateItemNameError(
                "Item name already exists. Please enter a unique item name.",
                suggested_name=suggested_name,
            ) from exc

        raise
