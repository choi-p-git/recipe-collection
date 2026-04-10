from db import get_connection
from services.recipe_instruction_codec import decode_instruction_text_to_steps


def get_item_edit_payload(item_id: int) -> dict | None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                item_id,
                item_name,
                item_type,
                author_user_id,
                yield_quantity,
                yield_unit,
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
                haccp_process_classification
            FROM item
            WHERE item_id = ?
            """,
            (item_id,),
        )
        row = cursor.fetchone()

        if row is None:
            return None

        ingredients = []
        if row[2] == "recipe":
            cursor.execute(
                """
                SELECT
                    rc.component_item_id,
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
            ingredients = [
                {
                    "component_item_id": ingredient_row[0],
                    "component_item_name": ingredient_row[1],
                    "component_quantity": ingredient_row[2],
                    "component_unit": ingredient_row[3],
                }
                for ingredient_row in cursor.fetchall()
            ]

    return {
        "item_id": row[0],
        "item_name": row[1],
        "item_type": row[2],
        "author_user_id": row[3],
        "yield_quantity": row[4],
        "yield_unit": row[5],
        "serving_size_quantity": row[6],
        "serving_size_unit": row[7],
        "serving_count": row[8],
        "instruction_steps": decode_instruction_text_to_steps(row[9] or ""),
        "primary_cooking_method_code": row[10],
        "status": row[11],
        "requires_resubmission": bool(row[12]),
        "notes": row[13],
        "concept_classification": row[14],
        "meal_classification": row[15],
        "haccp_process_classification": row[16],
        "ingredients": ingredients,
    }
