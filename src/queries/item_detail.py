from config.cooking_methods import COOKING_METHOD_LABELS
from config.item_types import ITEM_TYPE_LABELS
from config.statuses import STATUS_LABELS
from db import get_connection
from services.recipe_instruction_codec import decode_instruction_text_to_steps


def get_item_detail(item_id: int) -> dict | None:
    """
    Return a rendered-ready item detail payload for a single item.
    Returns None if not found.
    """
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                item_id,
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
                serving_size_quantity,
                serving_size_unit,
                serving_count,
                instructions_text,
                primary_cooking_method_code,
                status,
                requires_resubmission,
                notes,
                concept_classification,
                meal_classification,
                haccp_process_classification,
                created_at,
                updated_at
            FROM item
            WHERE item_id = ?
            """,
            (item_id,),
        )

        item_row = cursor.fetchone()

        if item_row is None:
            return None

        ingredient_rows = []
        if item_row[2] == "recipe":
            cursor.execute(
                """
                SELECT
                    rc.recipe_component_id,
                    rc.component_item_id,
                    i.item_name,
                    i.item_type,
                    rc.component_quantity,
                    rc.component_unit,
                    rc.component_sequence,
                    rc.component_notes
                FROM recipe_component rc
                JOIN item i
                  ON rc.component_item_id = i.item_id
                WHERE rc.parent_recipe_item_id = ?
                ORDER BY rc.component_sequence ASC, rc.recipe_component_id ASC
                """,
                (item_id,),
            )

            ingredient_rows = cursor.fetchall()

    instructions_text = item_row[14] or ""
    primary_cooking_method_code = item_row[15]
    item_type = item_row[2]

    return {
        "item_id": item_row[0],
        "item_name": item_row[1],
        "item_type": item_type,
        "item_type_label": ITEM_TYPE_LABELS.get(item_type, item_type),
        "author_user_id": item_row[3],
        "author_display_name": item_row[4],
        "yield_quantity": item_row[5],
        "yield_unit": item_row[6],
        "mass_quantity": item_row[7],
        "mass_unit": item_row[8],
        "volume_quantity": item_row[9],
        "volume_unit": item_row[10],
        "serving_size_quantity": item_row[11],
        "serving_size_unit": item_row[12],
        "serving_count": item_row[13],
        "instructions_text": instructions_text,
        "instruction_steps": decode_instruction_text_to_steps(instructions_text),
        "primary_cooking_method_code": primary_cooking_method_code,
        "primary_cooking_method_label": (
            COOKING_METHOD_LABELS.get(primary_cooking_method_code)
            if primary_cooking_method_code
            else None
        ),
        "status": item_row[16],
        "status_label": STATUS_LABELS.get(item_row[16], item_row[16]),
        "requires_resubmission": bool(item_row[17]),
        "notes": item_row[18],
        "concept_classification": item_row[19],
        "meal_classification": item_row[20],
        "haccp_process_classification": item_row[21],
        "created_at": item_row[22],
        "updated_at": item_row[23],
        "ingredients": [
            {
                "recipe_component_id": row[0],
                "component_item_id": row[1],
                "component_item_name": row[2],
                "component_item_type": row[3],
                "component_item_type_label": ITEM_TYPE_LABELS.get(row[3], row[3]),
                "component_quantity": row[4],
                "component_unit": row[5],
                "component_sequence": row[6],
                "component_notes": row[7],
            }
            for row in ingredient_rows
        ],
    }
