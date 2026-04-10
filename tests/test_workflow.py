import sqlite3

import pytest

from queries.workflow_items import get_workflow_portal_items
from services.item_service import create_base_food
from services.recipe_service import create_recipe
from services.workflow_service import WorkflowPermissionError, transition_item_status


def _set_status(isolated_db, item_id: int, status: str) -> None:
    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE item SET status = ?, updated_at = datetime('now') WHERE item_id = ?",
        (status, item_id),
    )
    conn.commit()
    conn.close()


def test_transition_item_status_allows_reviewer_submit_and_review_flow(isolated_db):
    base_food_id = create_base_food(item_name="Workflow Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Workflow Recipe",
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

    assert (
        transition_item_status(
            recipe_id,
            {"user_id": "reviewer_001", "display_name": "Chris Vale", "role": "reviewer"},
            "reviewer",
            "advance_reviewed",
            "reviewed",
        )
        == "reviewed"
    )
    assert (
        transition_item_status(
            recipe_id,
            {"user_id": "reviewer_001", "display_name": "Chris Vale", "role": "reviewer"},
            "reviewer",
            "approve_for_dietitian",
            "approved",
        )
        == "approved"
    )


def test_transition_item_status_allows_dietitian_send_back_and_reject(isolated_db):
    base_food_id = create_base_food(item_name="Dietitian Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Dietitian Recipe",
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
    _set_status(isolated_db, recipe_id, "approved")

    assert (
        transition_item_status(
            recipe_id,
            {"user_id": "dietitian_001", "display_name": "Dana Reed", "role": "dietitian"},
            "dietitian",
            "send_back_review",
            "reviewed",
            reason_text="Need clarified allergen handling.",
        )
        == "reviewed"
    )
    _set_status(isolated_db, recipe_id, "approved")
    assert (
        transition_item_status(
            recipe_id,
            {"user_id": "dietitian_001", "display_name": "Dana Reed", "role": "dietitian"},
            "dietitian",
            "reject_approved",
            "rejected",
            reason_text="Nutrition profile does not meet requirements.",
        )
        == "rejected"
    )


def test_transition_item_status_blocks_invalid_role_action(isolated_db):
    base_food_id = create_base_food(item_name="Blocked Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Blocked Recipe",
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

    with pytest.raises(WorkflowPermissionError):
        transition_item_status(
            recipe_id,
            {"user_id": "dietitian_001", "display_name": "Dana Reed", "role": "dietitian"},
            "dietitian",
            "mark_analyzed",
            "analyzed",
        )


def test_transition_item_status_can_return_submitted_recipe_to_submitter(isolated_db):
    base_food_id = create_base_food(item_name="Resubmit Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Needs Rework Recipe",
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

    assert (
        transition_item_status(
            recipe_id,
            {"user_id": "reviewer_001", "display_name": "Chris Vale", "role": "reviewer"},
            "reviewer",
            "return_to_submitter",
            "submitted",
            reason_text="Please clarify the preparation steps.",
        )
        == "submitted"
    )

    conn = sqlite3.connect(isolated_db)
    cursor = conn.cursor()
    cursor.execute("SELECT status, requires_resubmission FROM item WHERE item_id = ?", (recipe_id,))
    row = cursor.fetchone()
    conn.close()

    assert row == ("submitted", 1)


def test_return_to_submitter_is_not_offered_for_base_food(isolated_db):
    create_base_food(item_name="No Resubmit Base")

    reviewer_page = get_workflow_portal_items("reviewer", "reviewer")
    base_food_card = next(item for item in reviewer_page["items"] if item["item_name"] == "No Resubmit Base")

    action_labels = [action["label"] for action in base_food_card["actions"]]
    assert "Return To Submitter" not in action_labels


def test_transition_item_status_requires_reason_for_send_back_and_reject(isolated_db):
    base_food_id = create_base_food(item_name="Reason Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Reason Recipe",
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

    with pytest.raises(WorkflowPermissionError):
        transition_item_status(
            recipe_id,
            {"user_id": "reviewer_001", "display_name": "Chris Vale", "role": "reviewer"},
            "reviewer",
            "return_to_submitter",
            "submitted",
            reason_text="",
        )


def test_get_workflow_portal_items_filters_to_portal_domain(isolated_db):
    base_food_id = create_base_food(item_name="Portal Oil")
    recipe_id = create_recipe(
        {
            "item_name": "Portal Recipe",
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
    _set_status(isolated_db, recipe_id, "approved")

    reviewer_page = get_workflow_portal_items("reviewer", "reviewer")
    dietitian_page = get_workflow_portal_items("dietitian", "dietitian")

    assert recipe_id not in [item["item_id"] for item in reviewer_page["items"]]
    assert [item["item_id"] for item in dietitian_page["items"]] == [recipe_id]
