from services.policy_service import (
    can_edit_item,
    can_edit_items,
    can_view_advanced_workflow,
    is_dietitian_domain_role,
    is_reviewer_domain_role,
    is_workflow_staff,
)


def test_workflow_staff_role_sets_match_expected_capabilities():
    assert not is_workflow_staff("standard_user")
    assert is_workflow_staff("reviewer")
    assert is_workflow_staff("dietitian")
    assert is_workflow_staff("admin")
    assert is_workflow_staff("super_user")

    assert not is_reviewer_domain_role("standard_user")
    assert not is_reviewer_domain_role("dietitian")
    assert is_reviewer_domain_role("reviewer")
    assert is_reviewer_domain_role("admin")
    assert is_reviewer_domain_role("super_user")

    assert not is_dietitian_domain_role("standard_user")
    assert is_dietitian_domain_role("dietitian")
    assert is_dietitian_domain_role("admin")
    assert is_dietitian_domain_role("super_user")


def test_editor_and_advanced_workflow_capabilities_align():
    assert not can_edit_items("standard_user")
    assert can_edit_items("reviewer")
    assert can_edit_items("dietitian")
    assert can_edit_items("admin")
    assert can_edit_items("super_user")

    assert not can_view_advanced_workflow("standard_user")
    assert can_view_advanced_workflow("reviewer")
    assert can_view_advanced_workflow("dietitian")
    assert can_view_advanced_workflow("admin")
    assert can_view_advanced_workflow("super_user")


def test_can_edit_item_allows_workflow_staff_and_returned_submitter():
    returned_recipe = {
        "author_user_id": "dev_user_001",
        "item_type": "recipe",
        "status": "submitted",
        "requires_resubmission": True,
    }
    normal_recipe = {
        "author_user_id": "dev_user_001",
        "item_type": "recipe",
        "status": "reviewed",
        "requires_resubmission": False,
    }

    assert can_edit_item(
        {"user_id": "reviewer_001", "role": "reviewer"},
        normal_recipe,
    )
    assert can_edit_item(
        {"user_id": "dev_user_001", "role": "standard_user"},
        returned_recipe,
    )
    assert not can_edit_item(
        {"user_id": "dev_user_001", "role": "standard_user"},
        normal_recipe,
    )
    assert not can_edit_item(
        {"user_id": "other_user", "role": "standard_user"},
        returned_recipe,
    )
