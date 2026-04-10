from db import get_connection, initialize_database


def add_mayonnaise() -> None:
    """Insert a sample base food item: Mayonnaise."""
    initialize_database()

    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT item_name FROM item WHERE item_name = 'Mayonnaise'")

        item_query = cursor.fetchone()

        if item_query is not None:
            print("Mayonnaise already exists in database.")
            return
        else:
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
                    "Mayonnaise",              # item_name
                    "base_food",               # item_type
                    "system_base_food",        # author_user_id
                    "Base Food Submission",    # author_display_name
                    1.0,                       # yield_quantity
                    "each",                    # yield_unit
                    None,                      # serving_size_quantity
                    None,                      # serving_size_unit
                    None,                      # serving_count
                    None,                      # instructions_text
                    None,                      # primary_cooking_method_code
                    "submitted",               # status
                    "Initial sample base food item",  # notes
                    None,                      # concept_classification
                    None,                      # meal_classification
                    None,                      # haccp_process_classification
                ),
            )

            conn.commit()
            print("Inserted base food item: Mayonnaise")


if __name__ == "__main__":
    add_mayonnaise()