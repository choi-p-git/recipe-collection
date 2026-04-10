from services.item_note_service import (
    acknowledge_item_notes_for_viewer,
    post_item_note,
    resolve_note_recipient,
)
from services.notification_service import get_notification_count, get_notification_rows
from services.item_service import create_base_food
from services.recipe_service import create_recipe


def test_resolve_note_recipient_for_reviewer_and_author(isolated_db):
    item_id = create_base_food(item_name="Celery Notes")
    item = {
        "item_id": item_id,
        "author_user_id": "system_base_food",
        "author_display_name": "Base Food Submission",
        "status": "reviewed",
    }

    reviewer_target = resolve_note_recipient(
        item,
        {"user_id": "reviewer_001", "display_name": "Chris Vale", "role": "reviewer"},
    )
    author_target = resolve_note_recipient(
        {
            "item_id": 99,
            "author_user_id": "dev_user_001",
            "author_display_name": "Plato Choi",
            "status": "reviewed",
        },
        {"user_id": "dev_user_001", "display_name": "Plato Choi", "role": "standard_user"},
    )

    assert reviewer_target["recipient_user_id"] == "system_base_food"
    assert author_target["recipient_role"] == "reviewer"


def test_resolve_note_recipient_for_submitted_recipe(isolated_db):
    item = {
        "item_id": 25,
        "item_type": "recipe",
        "author_user_id": "dev_user_001",
        "author_display_name": "Plato Choi",
        "status": "submitted",
    }

    reviewer_target = resolve_note_recipient(
        item,
        {"user_id": "reviewer_001", "display_name": "Chris Vale", "role": "reviewer"},
    )
    author_target = resolve_note_recipient(
        item,
        {"user_id": "dev_user_001", "display_name": "Plato Choi", "role": "standard_user"},
    )

    assert reviewer_target["recipient_user_id"] == "dev_user_001"
    assert author_target["recipient_role"] == "reviewer"


def test_post_item_note_creates_notification_and_reply_acknowledges(isolated_db):
    base_food_id = create_base_food(item_name="Notification Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Notification Recipe",
            "yield_quantity": 1,
            "yield_unit": "each",
            "primary_cooking_method_code": "bake",
            "instruction_steps": ["Mix", "Bake"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "oz",
                }
            ],
        }
    )

    item = {
        "item_id": recipe_id,
        "author_user_id": "dev_user_001",
        "author_display_name": "Plato Choi",
        "status": "reviewed",
    }

    post_item_note(
        item=item,
        current_user={"user_id": "reviewer_001", "display_name": "Chris Vale", "role": "reviewer"},
        note_text="Please revise seasoning.",
    )

    assert get_notification_count(
        {"user_id": "dev_user_001", "display_name": "Plato Choi", "role": "standard_user"}
    ) == 1

    post_item_note(
        item=item,
        current_user={"user_id": "dev_user_001", "display_name": "Plato Choi", "role": "standard_user"},
        note_text="Updated and ready.",
    )

    assert get_notification_count(
        {"user_id": "dev_user_001", "display_name": "Plato Choi", "role": "standard_user"}
    ) == 0
    reviewer_notifications = get_notification_rows(
        {"user_id": "reviewer_001", "display_name": "Chris Vale", "role": "reviewer"}
    )
    assert len(reviewer_notifications) == 1
    assert reviewer_notifications[0]["item_id"] == recipe_id


def test_acknowledge_item_notes_for_viewer_marks_open_notifications_read(isolated_db):
    base_food_id = create_base_food(item_name="Acknowledge Base")
    recipe_id = create_recipe(
        {
            "item_name": "Acknowledge Recipe",
            "yield_quantity": 1,
            "yield_unit": "each",
            "primary_cooking_method_code": "bake",
            "instruction_steps": ["Mix", "Bake"],
            "ingredients": [
                {
                    "component_item_id": base_food_id,
                    "component_quantity": 1,
                    "component_unit": "oz",
                }
            ],
        }
    )
    item = {
        "item_id": recipe_id,
        "item_type": "recipe",
        "author_user_id": "dev_user_001",
        "author_display_name": "Plato Choi",
        "status": "submitted",
    }

    post_item_note(
        item=item,
        current_user={"user_id": "reviewer_001", "display_name": "Chris Vale", "role": "reviewer"},
        note_text="Please tighten the method copy.",
    )

    viewer = {"user_id": "dev_user_001", "display_name": "Plato Choi", "role": "standard_user"}
    assert get_notification_count(viewer) == 1
    assert acknowledge_item_notes_for_viewer(recipe_id, viewer) == 1
    assert get_notification_count(viewer) == 0
