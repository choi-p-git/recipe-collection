import csv
import io
from datetime import date
from pathlib import Path

from flask import Flask, Response, flash, jsonify, redirect, render_template, request, session, url_for

from config.units import APPROVED_UNITS, STANDARD_UNITS
from config.hotel_pan_units import (
    HOTEL_PAN_DEPTH_OPTIONS,
    HOTEL_PAN_SIZE_OPTIONS,
    HOTEL_PAN_UNITS,
)
from config.cooking_methods import APPROVED_COOKING_METHODS
from config.menu_builder import CONCEPT_OPTIONS, DAY_OF_WEEK_OPTIONS, MEAL_PERIOD_OPTIONS
from config.item_categories import ITEM_CATEGORY_LABELS
from config.roles import ROLE_LABELS
from config.statuses import STATUS_LABELS
from services.item_service import (
    DuplicateItemNameError,
    InvalidItemNameError,
    InvalidNumericValueError,
    normalize_item_name,
    create_base_food,
    update_base_food,
)
from services.recipe_service import (
    InvalidRecipePayloadError,
    create_recipe,
    update_recipe,
)
from services.mock_auth_service import (
    apply_debug_override,
    build_auth_shell_context,
    create_mock_user,
    get_current_mock_user,
    select_mock_user,
    update_current_user_preferences,
)
from services.menu_service import (
    DAY_OF_WEEK_ORDER,
    InvalidMenuPayloadError,
    InvalidMenuDeleteError,
    InvalidMenuSlotActionError,
    InvalidMenuSlotAssignmentError,
    clear_menu_slots,
    clear_menu_slot,
    copy_menu_slots,
    create_menu,
    delete_menu,
    get_menu_slot_assignment_ids,
    paste_menu_slot_assignment_ids,
    paste_menu_slots,
    paste_menu_weeks,
    replace_menu_slot_items,
    update_menu_config,
)
from services.menu_forecast_service import (
    get_menu_forecast_by_slot_item,
    InvalidMenuForecastBatchError,
    InvalidMenuForecastError,
    save_menu_forecast_batch_splits,
    save_item_case_pack,
    save_menu_forecast_yield,
)
from services.menu_navigation_service import (
    current_day_of_week,
    current_service_date,
    default_menu_week_number,
)
from services.production_record_service import (
    InvalidProductionRecordError,
    PRODUCTION_RECORD_REASON_OPTIONS,
    build_production_record_unit_options,
    ensure_production_record,
    get_production_record_for_service_day,
    get_production_record_review,
    get_posted_production_facts_for_menu,
    list_production_record_item_trends_for_menu,
    list_production_records_for_menu,
    post_production_record,
    save_production_record_line,
)
from services.inventory_service import (
    InvalidInventoryError,
    add_inventory_location_break,
    create_inventory_location,
    delete_inventory_location,
    delete_inventory_location_break,
    delete_inventory_location_item,
    get_inventory_dashboard,
    get_inventory_location_detail,
    list_live_inventory_items,
    move_inventory_count_row,
    rename_inventory_location,
    save_inventory_location_item,
    transfer_inventory_location_item,
    update_inventory_location_item,
)
from services.inventory_usage_service import (
    get_inventory_item_count_rolldown,
    get_inventory_item_detail,
    get_inventory_item_usage,
    get_inventory_reorder_plan,
)
from services.inventory_bridge_service import get_inventory_catalog_review_page
from services.inventory_ordering_service import (
    DAY_OPTIONS,
    ORDERING_FREQUENCY_OPTIONS,
    InvalidInventoryOrderingPreferenceError,
    delete_inventory_ordering_preference,
    list_inventory_ordering_preferences,
    upsert_inventory_ordering_preferences_for_categories,
)
from services.item_note_service import (
    ItemNoteError,
    acknowledge_item_notes_for_viewer,
    get_item_notes,
    post_item_note,
    resolve_note_recipient,
)
from services.base_food_conversion_service import build_base_food_conversion_preview
from services.notification_service import (
    acknowledge_item_notifications_for_viewer,
    get_notification_count,
    get_notification_rows,
)
from services.policy_service import (
    can_edit_item,
    can_manage_official_measurements,
    can_view_advanced_workflow,
)
from services.recipe_flattening_service import build_flattened_recipe_view
from services.recipe_scaling_service import (
    build_bottom_up_scaled_recipe_view,
    build_recipe_scaling_foundation,
    build_scaled_recipe_view,
)
from services.unit_display_service import (
    DISPLAY_MODE_DEFAULT,
    UNIT_SYSTEM_IMPERIAL,
    apply_display_preferences_to_rows,
    build_display_measurement,
    normalize_display_mode,
    normalize_unit_system,
)
from services.unit_conversion_service import get_unit_measurement_profile
from services.unit_label_service import format_unit_label
from services.user_serving_service import build_desired_portions_yield_target, build_user_serving_preview
from services.workflow_service import (
    WorkflowPermissionError,
    ensure_portal_access,
    get_available_workflow_portals,
    transition_item_status,
)
from queries.item_search import search_items_page
from queries.item_detail import get_item_detail
from queries.item_edit import get_item_edit_payload
from queries.item_events import get_item_events
from queries.live_collection import get_live_collection_page
from queries.menu_detail import get_menu_detail
from queries.menu_forecast import get_menu_forecast_page
from queries.my_menus import get_my_menus
from queries.menu_slot_detail import get_menu_slot_detail
from queries.my_recipes import get_my_recipes
from queries.workflow_items import get_workflow_portal_items

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEBPAGE_DIR = PROJECT_ROOT / "webpage"
TEMPLATE_DIR = WEBPAGE_DIR / "templates"
STATIC_DIR = WEBPAGE_DIR / "static"

UNIT_MEASUREMENT_OPTIONS = [
    {
        "unit": unit,
        "label": format_unit_label(unit),
        "measurement_type": get_unit_measurement_profile(unit)["measurement_type"],
        "canonical_unit": get_unit_measurement_profile(unit)["canonical_unit"],
        "canonical_factor": get_unit_measurement_profile(unit)["canonical_factor"],
    }
    for unit in APPROVED_UNITS
    if get_unit_measurement_profile(unit) and get_unit_measurement_profile(unit)["conversion_ready"]
]


app = Flask(
    __name__,
    template_folder=str(TEMPLATE_DIR),
    static_folder=str(STATIC_DIR),
)

app.secret_key = "dev-secret-key"


@app.route("/favicon.ico")
def favicon():
    return Response(status=204)


def _current_day_of_week() -> str:
    return current_day_of_week(_current_service_date())


def _current_service_date() -> date:
    return current_service_date()


def _default_menu_week_number(menu: dict | None, current_date: date | None = None) -> int:
    return default_menu_week_number(menu, current_date or _current_service_date())


def _build_service_day_navigation(page_data: dict) -> dict:
    entries = [
        {
            "week": week_number,
            "day": day,
            "label": f"Week {week_number} {day.title()}",
            "date_display": page_data.get("week_day_dates", {}).get(week_number, {}).get(day, {}).get("display", ""),
        }
        for week_number in page_data.get("week_numbers", [])
        for day in page_data.get("menu", {}).get("service_days", [])
    ]
    selected = {
        "week": page_data.get("selected_week_number"),
        "day": page_data.get("selected_day"),
    }
    selected_index = next(
        (
            index
            for index, entry in enumerate(entries)
            if entry["week"] == selected["week"] and entry["day"] == selected["day"]
        ),
        None,
    )
    if selected_index is None:
        return {"previous": None, "next": None}
    return {
        "previous": entries[selected_index - 1] if selected_index > 0 else None,
        "next": entries[selected_index + 1] if selected_index + 1 < len(entries) else None,
    }


@app.route("/inventory")
def inventory_dashboard():
    return render_template(
        "inventory.html",
        page_data=get_inventory_dashboard(),
        current_user=get_current_mock_user(session),
    )


@app.route("/inventory/planning")
def inventory_planning():
    current_user = get_current_mock_user(session)
    show_all = request.args.get("view") == "all"
    return render_template(
        "inventory_planning.html",
        plan=get_inventory_reorder_plan(
            actor_user_id=current_user["user_id"],
            operation_day_limit=None if show_all else 3,
        ),
        show_all=show_all,
        current_user=current_user,
    )


@app.route("/inventory/catalog/review")
def inventory_catalog_review():
    current_user = get_current_mock_user(session)
    scope = request.args.get("scope", "relevant")
    return render_template(
        "inventory_catalog_review.html",
        page_data=get_inventory_catalog_review_page(scope=scope, actor_user_id=current_user["user_id"]),
        current_user=current_user,
    )


@app.route("/inventory/planning/preferences")
def inventory_planning_preferences():
    current_user = get_current_mock_user(session)
    preferences = list_inventory_ordering_preferences(current_user["user_id"])
    preferences_by_category = {
        preference["item_category"]: preference
        for preference in preferences
    }
    return render_template(
        "inventory_planning_preferences.html",
        preferences=preferences,
        preferences_by_category=preferences_by_category,
        item_category_options=[
            {"value": value, "label": label}
            for value, label in ITEM_CATEGORY_LABELS.items()
        ],
        day_options=[{"value": value, "label": label} for value, label in DAY_OPTIONS],
        ordering_frequency_options=[
            {"value": value, "label": label}
            for value, label in ORDERING_FREQUENCY_OPTIONS
        ],
        current_user=current_user,
    )


@app.post("/inventory/planning/preferences")
def save_inventory_planning_preference():
    current_user = get_current_mock_user(session)
    cutoff_rules = [
        {
            "delivery_day": delivery_day,
            "cutoff_day": request.form.get(f"cutoff_day_{delivery_day}", ""),
            "cutoff_time": request.form.get(f"cutoff_time_{delivery_day}", ""),
        }
        for delivery_day in request.form.getlist("delivery_days")
    ]
    try:
        saved_preferences = upsert_inventory_ordering_preferences_for_categories(
            user_id=current_user["user_id"],
            item_categories=request.form.getlist("item_categories"),
            vendor_name=request.form.get("vendor_name", ""),
            ordering_frequency=request.form.get("ordering_frequency", "as_needed"),
            cutoff_rules=cutoff_rules,
            preferred_lead_days=request.form.get("preferred_lead_days", 0),
        )
        flash(f"Inventory planning preferences saved for {len(saved_preferences)} categories.", "success")
    except InvalidInventoryOrderingPreferenceError as exc:
        flash(str(exc), "error")
    return redirect(url_for("inventory_planning_preferences"))


@app.post("/inventory/planning/preferences/<item_category>/delete")
def delete_inventory_planning_preference(item_category):
    current_user = get_current_mock_user(session)
    try:
        delete_inventory_ordering_preference(
            user_id=current_user["user_id"],
            item_category=item_category,
        )
        flash("Inventory planning preference deleted.", "success")
    except InvalidInventoryOrderingPreferenceError as exc:
        flash(str(exc), "error")
    return redirect(url_for("inventory_planning_preferences"))


@app.route("/inventory/items/<int:item_id>")
def inventory_item_detail(item_id: int):
    temporary_each_bridge = {
        "quantity": request.args.get("temporary_each_quantity", ""),
        "unit": request.args.get("temporary_each_unit", ""),
    }
    detail = get_inventory_item_detail(item_id, temporary_each_bridge=temporary_each_bridge)
    if detail is None:
        return "Inventory item not found.", 404
    return render_template(
        "inventory_item_detail.html",
        detail=detail,
        temporary_each_bridge=temporary_each_bridge,
        unit_options=STANDARD_UNITS,
        current_user=get_current_mock_user(session),
    )


@app.get("/api/inventory/items/<int:item_id>/usage-summary")
def api_inventory_item_usage_summary(item_id: int):
    usage = get_inventory_item_usage(item_id, limit=5)
    if not usage["item"]["item_name"]:
        return jsonify({"ok": False, "error": "Inventory item not found."}), 404
    for group in ("upcoming", "past"):
        for row in usage[group]:
            row["service_context_url"] = url_for(
                "menu_service_context",
                menu_id=row["menu_id"],
                week=row["week_number"],
                day=row["day_of_week"],
            )
    return jsonify({"ok": True, "usage": usage})


@app.get("/api/inventory/items/<int:item_id>/count-rolldown")
def api_inventory_item_count_rolldown(item_id: int):
    rows = get_inventory_item_count_rolldown(item_id)
    for row in rows:
        row["inventory_location_count_url"] = url_for(
            "inventory_location_count",
            inventory_location_id=row["inventory_location_id"],
        )
    return jsonify({"ok": True, "rows": rows})


@app.post("/inventory/locations")
def create_inventory_location_route():
    current_user = get_current_mock_user(session)
    try:
        parent_id = request.form.get("parent_inventory_location_id", "")
        create_inventory_location(
            location_name=request.form.get("location_name", ""),
            parent_inventory_location_id=parent_id,
            actor_user_id=current_user["user_id"],
            actor_display_name=current_user["display_name"],
        )
        flash("Inventory location created.", "success")
    except InvalidInventoryError as exc:
        flash(str(exc), "error")
    if request.form.get("return_to") == "edit" and request.form.get("parent_inventory_location_id"):
        return redirect(url_for("inventory_location_edit", inventory_location_id=request.form["parent_inventory_location_id"]))
    return redirect(url_for("inventory_dashboard"))


@app.route("/inventory/locations/<int:inventory_location_id>/edit")
def inventory_location_edit(inventory_location_id: int):
    location = get_inventory_location_detail(inventory_location_id)
    if location is None:
        return "Inventory location not found.", 404
    return render_template(
        "inventory_location_edit.html",
        location=location,
    )


@app.post("/inventory/locations/<int:inventory_location_id>/rename")
def rename_inventory_location_route(inventory_location_id: int):
    try:
        rename_inventory_location(
            inventory_location_id=inventory_location_id,
            location_name=request.form.get("location_name", ""),
        )
        flash("Inventory location renamed.", "success")
    except InvalidInventoryError as exc:
        flash(str(exc), "error")
    return redirect(request.form.get("return_url") or url_for("inventory_location_edit", inventory_location_id=inventory_location_id))


@app.post("/inventory/locations/<int:inventory_location_id>/delete")
def delete_inventory_location_route(inventory_location_id: int):
    return_location_id = request.form.get("return_inventory_location_id", "")
    try:
        delete_inventory_location(inventory_location_id=inventory_location_id)
        flash("Inventory location deleted.", "success")
    except InvalidInventoryError as exc:
        flash(str(exc), "error")
    if return_location_id:
        return redirect(url_for("inventory_location_edit", inventory_location_id=return_location_id))
    return redirect(url_for("inventory_dashboard"))


@app.route("/inventory/locations/<int:inventory_location_id>/count")
def inventory_location_count(inventory_location_id: int):
    location = get_inventory_location_detail(inventory_location_id)
    if location is None:
        return "Inventory location not found.", 404
    dashboard = get_inventory_dashboard()
    return render_template(
        "inventory_location_count.html",
        location=location,
        live_items=list_live_inventory_items(),
        unit_options=dashboard["unit_options"],
        unit_of_measurement_options=dashboard["unit_of_measurement_options"],
        count_type_options=dashboard["count_type_options"],
        transfer_locations=[
            candidate
            for candidate in dashboard["active_locations"]
            if candidate["inventory_location_id"] != inventory_location_id
            and candidate["parent_inventory_location_id"] is not None
        ],
        transfer_location_tree=dashboard["location_tree"],
    )


@app.post("/inventory/locations/<int:inventory_location_id>/items")
def save_inventory_location_item_route(inventory_location_id: int):
    try:
        save_inventory_location_item(
            inventory_location_id=inventory_location_id,
            item_id=request.form.get("item_id", ""),
            count_each_quantity=request.form.get("count_each_quantity", ""),
            count_case_quantity=request.form.get("count_case_quantity", ""),
            pack_quantity=request.form.get("pack_quantity", ""),
            pack_size_text=request.form.get("pack_size_text", ""),
            unit_of_measurement=request.form.get("unit_of_measurement", ""),
            count_type=request.form.get("count_type", ""),
        )
        flash("Inventory item count saved.", "success")
    except InvalidInventoryError as exc:
        flash(str(exc), "error")
    return redirect(url_for("inventory_location_count", inventory_location_id=inventory_location_id))


@app.post("/inventory/location-items/<int:inventory_location_item_id>/update")
def update_inventory_location_item_route(inventory_location_item_id: int):
    return_location_id = request.form.get("inventory_location_id", "")
    try:
        update_inventory_location_item(
            inventory_location_item_id=inventory_location_item_id,
            count_each_quantity=request.form.get("count_each_quantity", ""),
            count_case_quantity=request.form.get("count_case_quantity", ""),
            pack_quantity=request.form.get("pack_quantity", ""),
            pack_size_text=request.form.get("pack_size_text", ""),
            unit_of_measurement=request.form.get("unit_of_measurement", ""),
            count_type=request.form.get("count_type", ""),
        )
        flash("Inventory item count updated.", "success")
    except InvalidInventoryError as exc:
        flash(str(exc), "error")
    return redirect(url_for("inventory_location_count", inventory_location_id=return_location_id))


@app.put("/api/inventory/location-items/<int:inventory_location_item_id>")
def api_update_inventory_location_item(inventory_location_item_id: int):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Missing JSON payload."}), 400
    try:
        update_inventory_location_item(
            inventory_location_item_id=inventory_location_item_id,
            count_each_quantity=payload.get("count_each_quantity", ""),
            count_case_quantity=payload.get("count_case_quantity", ""),
            pack_quantity=payload.get("pack_quantity", ""),
            pack_size_text=payload.get("pack_size_text", ""),
            unit_of_measurement=payload.get("unit_of_measurement", ""),
            count_type=payload.get("count_type", ""),
        )
        location = get_inventory_location_detail(payload.get("inventory_location_id", ""))
        line = next(
            (
                row
                for row in (location or {}).get("item_rows", [])
                if row["inventory_location_item_id"] == inventory_location_item_id
            ),
            None,
        )
        return jsonify({"ok": True, "line": line})
    except InvalidInventoryError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unexpected error: {exc}"}), 500


@app.post("/inventory/location-items/<int:inventory_location_item_id>/delete")
def delete_inventory_location_item_route(inventory_location_item_id: int):
    return_location_id = request.form.get("inventory_location_id", "")
    try:
        delete_inventory_location_item(inventory_location_item_id=inventory_location_item_id)
        flash("Inventory item removed.", "success")
    except InvalidInventoryError as exc:
        flash(str(exc), "error")
    return redirect(url_for("inventory_location_count", inventory_location_id=return_location_id))


@app.post("/inventory/locations/<int:inventory_location_id>/breaks")
def add_inventory_location_break_route(inventory_location_id: int):
    try:
        add_inventory_location_break(
            inventory_location_id=inventory_location_id,
            break_label=request.form.get("break_label", ""),
        )
        flash("Inventory break line added.", "success")
    except InvalidInventoryError as exc:
        flash(str(exc), "error")
    return redirect(url_for("inventory_location_count", inventory_location_id=inventory_location_id))


@app.post("/inventory/location-breaks/<int:inventory_location_break_id>/delete")
def delete_inventory_location_break_route(inventory_location_break_id: int):
    return_location_id = request.form.get("inventory_location_id", "")
    try:
        delete_inventory_location_break(inventory_location_break_id=inventory_location_break_id)
        flash("Inventory break line removed.", "success")
    except InvalidInventoryError as exc:
        flash(str(exc), "error")
    return redirect(url_for("inventory_location_count", inventory_location_id=return_location_id))


@app.post("/inventory/count-rows/move")
def move_inventory_count_row_route():
    return_location_id = request.form.get("inventory_location_id", "")
    try:
        move_inventory_count_row(
            row_type=request.form.get("row_type", ""),
            row_id=request.form.get("row_id", ""),
            direction=request.form.get("direction", ""),
        )
    except InvalidInventoryError as exc:
        flash(str(exc), "error")
    return redirect(url_for("inventory_location_count", inventory_location_id=return_location_id))


@app.post("/inventory/location-items/<int:inventory_location_item_id>/transfer")
def transfer_inventory_location_item_route(inventory_location_item_id: int):
    return_location_id = request.form.get("inventory_location_id", "")
    try:
        transfer_inventory_location_item(
            inventory_location_item_id=inventory_location_item_id,
            target_inventory_location_id=request.form.get("target_inventory_location_id", ""),
        )
        flash("Inventory item transferred.", "success")
    except InvalidInventoryError as exc:
        flash(str(exc), "error")
    return redirect(url_for("inventory_location_count", inventory_location_id=return_location_id))


@app.route("/inventory/locations/<int:inventory_location_id>/print")
def inventory_location_print(inventory_location_id: int):
    location = get_inventory_location_detail(inventory_location_id)
    if location is None:
        return "Inventory location not found.", 404
    return render_template("inventory_location_print.html", location=location)


@app.template_filter("unit_label")
def unit_label_filter(unit: str | None) -> str:
    return format_unit_label(unit)


def get_base_food_form_data() -> dict:
    """Collect current form values from POST request for re-rendering."""
    return {
        "item_name": request.form.get("item_name", "").strip(),
        "notes": request.form.get("notes", "").strip(),
        "mass_quantity": request.form.get("mass_quantity", "").strip(),
        "mass_unit": request.form.get("mass_unit", "").strip(),
        "volume_quantity": request.form.get("volume_quantity", "").strip(),
        "volume_unit": request.form.get("volume_unit", "").strip(),
        "nutrition_group": request.form.get("nutrition_group", "").strip(),
        "kcal_per_serving": request.form.get("kcal_per_serving", "").strip(),
        "nutrition_serving_mass_quantity": request.form.get("nutrition_serving_mass_quantity", "").strip(),
        "nutrition_serving_mass_unit": request.form.get("nutrition_serving_mass_unit", "").strip(),
        "nutrition_serving_volume_quantity": request.form.get("nutrition_serving_volume_quantity", "").strip(),
        "nutrition_serving_volume_unit": request.form.get("nutrition_serving_volume_unit", "").strip(),
    }


@app.route("/")
def index():
    return render_template("index.html")


def get_menu_form_data() -> dict:
    return {
        "menu_name": request.form.get("menu_name", "").strip(),
        "menu_start_date": request.form.get("menu_start_date", "").strip(),
        "menu_end_date": request.form.get("menu_end_date", "").strip(),
        "service_days": request.form.getlist("service_days"),
        "meal_periods": request.form.getlist("meal_periods"),
        "concepts": request.form.getlist("concepts"),
        "menu_length_weeks": request.form.get("menu_length_weeks", "").strip(),
    }


def get_current_recipe_author() -> dict[str, str]:
    """
    MVP helper for the current mocked authenticated recipe author.
    Keep this centralized so future mock-login/debug overrides can replace it cleanly.
    """
    current_user = get_current_mock_user(session)
    return {
        "author_user_id": current_user["user_id"],
        "author_display_name": current_user["display_name"],
        "author_role": current_user["role"],
    }


def get_menu_slot_clipboard() -> dict | None:
    clipboard = session.get("menu_slot_clipboard")
    if not isinstance(clipboard, dict):
        return None
    if isinstance(clipboard.get("entries"), list) and clipboard.get("mode") in {"cell", "concept"}:
        return clipboard
    if isinstance(clipboard.get("item_ids"), list):
        return {
            "mode": "cell",
            "entries": [
                {
                    "item_ids": clipboard["item_ids"],
                }
            ],
            "copied_count": 1,
        }
    if not isinstance(clipboard.get("entries"), list):
        return None
    return clipboard


def apply_unit_system_to_recipe_snapshot(scaled_recipe_view: dict | None, unit_system: str) -> list[str]:
    if not scaled_recipe_view or not scaled_recipe_view.get("is_scaled"):
        return []

    snapshot = scaled_recipe_view.get("scaled_snapshot")
    if not snapshot:
        return []

    warnings: list[str] = []
    for measurement_type in ("mass", "volume"):
        quantity = snapshot.get(f"{measurement_type}_quantity")
        unit = snapshot.get(f"{measurement_type}_unit")
        if not quantity or not unit:
            continue

        display_measurement = build_display_measurement(
            quantity=float(quantity),
            source_unit=unit,
            item_type="recipe",
            display_mode=measurement_type,
            unit_system=unit_system,
            mass_quantity=snapshot.get("mass_quantity"),
            mass_unit=snapshot.get("mass_unit"),
            volume_quantity=snapshot.get("volume_quantity"),
            volume_unit=snapshot.get("volume_unit"),
        )
        snapshot[f"{measurement_type}_display_quantity"] = display_measurement["quantity"]
        snapshot[f"{measurement_type}_display_quantity_display"] = display_measurement["quantity_display"]
        snapshot[f"{measurement_type}_display_unit"] = display_measurement["unit"]
        if display_measurement.get("warning") and display_measurement["warning"] not in warnings:
            warnings.append(display_measurement["warning"])

    return warnings


def apply_unit_system_to_recipe_item_snapshot(item: dict, unit_system: str) -> list[str]:
    if item.get("item_type") != "recipe":
        return []

    warnings: list[str] = []
    for measurement_type in ("mass", "volume"):
        quantity = item.get(f"{measurement_type}_quantity")
        unit = item.get(f"{measurement_type}_unit")
        if not quantity or not unit:
            continue

        display_measurement = build_display_measurement(
            quantity=float(quantity),
            source_unit=unit,
            item_type="recipe",
            display_mode=measurement_type,
            unit_system=unit_system,
            mass_quantity=item.get("mass_quantity"),
            mass_unit=item.get("mass_unit"),
            volume_quantity=item.get("volume_quantity"),
            volume_unit=item.get("volume_unit"),
        )
        item[f"{measurement_type}_display_quantity"] = display_measurement["quantity"]
        item[f"{measurement_type}_display_quantity_display"] = display_measurement["quantity_display"]
        item[f"{measurement_type}_display_unit"] = display_measurement["unit"]
        if display_measurement.get("warning") and display_measurement["warning"] not in warnings:
            warnings.append(display_measurement["warning"])

    return warnings


def _redirect_with_query(endpoint: str, **values):
    target = url_for(endpoint, **values)
    if request.query_string:
        target = f"{target}?{request.query_string.decode()}"
    return redirect(target, code=301)


@app.context_processor
def inject_mock_auth_context():
    current_user = get_current_mock_user(session)
    return {
        "current_mock_user": current_user,
        "current_mock_user_role_label": ROLE_LABELS.get(current_user["role"], current_user["role"]),
        "current_user_preferences": current_user.get("preferences", {}),
        "available_workflow_portals": get_available_workflow_portals(current_user["role"]),
        "notification_count": get_notification_count(current_user),
        "advanced_unit_options": {
            "sizes": HOTEL_PAN_SIZE_OPTIONS,
            "depths": HOTEL_PAN_DEPTH_OPTIONS,
            "units": HOTEL_PAN_UNITS,
        },
        "approved_unit_options": [
            {"value": unit, "label": format_unit_label(unit)}
            for unit in APPROVED_UNITS
        ],
        "recipe_authoring_unit_options": [
            {"value": unit, "label": format_unit_label(unit)}
            for unit in STANDARD_UNITS
        ],
        "unit_measurement_options": UNIT_MEASUREMENT_OPTIONS,
    }


@app.route("/recipe-collection/new/base-food", methods=["GET", "POST"])
def new_base_food():
    form_data = {
        "item_name": "",
        "notes": "",
        "mass_quantity": "",
        "mass_unit": "",
        "volume_quantity": "",
        "volume_unit": "",
        "nutrition_group": "",
        "kcal_per_serving": "",
        "nutrition_serving_mass_quantity": "",
        "nutrition_serving_mass_unit": "",
        "nutrition_serving_volume_quantity": "",
        "nutrition_serving_volume_unit": "",
    }

    if request.method == "POST":
        form_data = get_base_food_form_data()

        try:
            item_name = normalize_item_name(form_data["item_name"])
            form_data["item_name"] = item_name

            if not item_name:
                raise InvalidItemNameError("Item name cannot be empty or only whitespace.")

            notes = form_data["notes"] or None

            item_id = create_base_food(
                item_name=item_name,
                notes=notes,
                actor_user_id=get_current_mock_user(session)["user_id"],
                actor_display_name=get_current_mock_user(session)["display_name"],
                actor_role=get_current_mock_user(session)["role"],
            )

            flash(f"Base food '{item_name}' created successfully.", "success")
            return redirect(url_for("item_detail", item_id=item_id))

        except DuplicateItemNameError as exc:
            if exc.suggested_name:
                form_data["item_name"] = exc.suggested_name
                flash(
                    f"{exc} Suggested available name: {exc.suggested_name}",
                    "error",
                )
            else:
                flash(str(exc), "error")

        except InvalidItemNameError as exc:
            flash(str(exc), "error")

        except Exception as exc:
            flash(f"Unexpected error: {exc}", "error")

    return render_template(
        "new_base_food.html",
        form_data=form_data,
        form_mode="create",
        approved_units=STANDARD_UNITS,
        can_manage_official_measurements_for_current_user=False,
    )


@app.route("/new/base-food", methods=["GET", "POST"])
def legacy_new_base_food():
    if request.method == "POST":
        return new_base_food()
    return _redirect_with_query("new_base_food")


@app.route("/recipe-collection/new/recipe")
def new_recipe():
    current_user = get_current_mock_user(session)
    return render_template(
        "new_recipe.html",
        approved_units=STANDARD_UNITS,
        approved_cooking_methods=APPROVED_COOKING_METHODS,
        editor_mode="create",
        recipe=None,
        can_manage_official_measurements_for_current_user=can_manage_official_measurements(
            current_user["role"]
        ),
    )


@app.route("/new/recipe")
def legacy_new_recipe():
    return _redirect_with_query("new_recipe")


@app.route("/menus/new", methods=["GET", "POST"])
def new_menu():
    form_data = {
        "menu_name": "",
        "menu_start_date": "",
        "menu_end_date": "",
        "service_days": [],
        "meal_periods": [],
        "concepts": [],
        "menu_length_weeks": "1",
    }

    if request.method == "POST":
        form_data = get_menu_form_data()
        current_user = get_current_mock_user(session)

        try:
            menu_id = create_menu(
                menu_name=form_data["menu_name"],
                author_user_id=current_user["user_id"],
                author_display_name=current_user["display_name"],
                menu_start_date=form_data["menu_start_date"],
                menu_end_date=form_data["menu_end_date"],
                service_days=form_data["service_days"],
                meal_periods=form_data["meal_periods"],
                concepts=form_data["concepts"],
                menu_length_weeks=form_data["menu_length_weeks"],
                allowed_service_days=[option["value"] for option in DAY_OF_WEEK_OPTIONS],
                allowed_meal_periods=[option["value"] for option in MEAL_PERIOD_OPTIONS],
                allowed_concepts=[option["value"] for option in CONCEPT_OPTIONS],
                require_date_range=True,
            )
            flash(f"Menu '{form_data['menu_name']}' created successfully.", "success")
            return redirect(url_for("menu_detail", menu_id=menu_id))
        except InvalidMenuPayloadError as exc:
            flash(str(exc), "error")

    return render_template(
        "new_menu.html",
        form_data=form_data,
        day_options=DAY_OF_WEEK_OPTIONS,
        meal_period_options=MEAL_PERIOD_OPTIONS,
        concept_options=CONCEPT_OPTIONS,
        page_mode="create",
        menu_id=None,
    )


@app.route("/menus/<int:menu_id>/edit", methods=["GET", "POST"])
def edit_menu(menu_id: int):
    menu = get_menu_detail(menu_id)
    if menu is None:
        return "Menu not found.", 404

    current_user = get_current_mock_user(session)
    if menu["author_user_id"] != current_user["user_id"]:
        flash("You can only edit menus you created.", "error")
        return redirect(url_for("menu_detail", menu_id=menu_id))

    form_data = {
        "menu_name": menu["menu_name"],
        "menu_start_date": menu["menu_start_date"],
        "menu_end_date": menu["menu_end_date"],
        "service_days": menu["service_days"],
        "meal_periods": menu["meal_periods"],
        "concepts": menu["concepts"],
        "menu_length_weeks": str(menu["menu_length_weeks"]),
    }

    if request.method == "POST":
        form_data = get_menu_form_data()
        try:
            update_menu_config(
                menu_id=menu_id,
                actor_user_id=current_user["user_id"],
                menu_name=form_data["menu_name"],
                menu_start_date=form_data["menu_start_date"],
                menu_end_date=form_data["menu_end_date"],
                service_days=form_data["service_days"],
                meal_periods=form_data["meal_periods"],
                concepts=form_data["concepts"],
                menu_length_weeks=form_data["menu_length_weeks"],
                allowed_service_days=[option["value"] for option in DAY_OF_WEEK_OPTIONS],
                allowed_meal_periods=[option["value"] for option in MEAL_PERIOD_OPTIONS],
                allowed_concepts=[option["value"] for option in CONCEPT_OPTIONS],
                require_date_range=True,
            )
            flash(f"Menu '{form_data['menu_name']}' config updated successfully.", "success")
            return redirect(url_for("menu_detail", menu_id=menu_id))
        except InvalidMenuPayloadError as exc:
            flash(str(exc), "error")

    return render_template(
        "new_menu.html",
        form_data=form_data,
        day_options=DAY_OF_WEEK_OPTIONS,
        meal_period_options=MEAL_PERIOD_OPTIONS,
        concept_options=CONCEPT_OPTIONS,
        page_mode="edit",
        menu_id=menu_id,
    )


@app.route("/menus")
def my_menus():
    current_user = get_current_mock_user(session)
    page_data = get_my_menus(current_user["user_id"])
    for menu in page_data["menus"]:
        menu["current_week_number"] = _default_menu_week_number(menu)
    return render_template(
        "menus.html",
        page_data=page_data,
        current_user=current_user,
    )


@app.route("/menus/<int:menu_id>")
def menu_detail(menu_id: int):
    menu = get_menu_detail(menu_id)
    if menu is None:
        return "Menu not found.", 404

    week_numbers = list(range(1, menu["menu_length_weeks"] + 1))
    selected_week = request.args.get("week", "").strip()
    try:
        selected_week_number = int(selected_week) if selected_week else _default_menu_week_number(menu)
    except ValueError:
        selected_week_number = 1

    if selected_week_number not in week_numbers:
        selected_week_number = 1

    week_slots = [slot for slot in menu["slots"] if slot["week_number"] == selected_week_number]
    bulk_action = request.args.get("bulk_action", "").strip()
    bulk_scope = request.args.get("bulk_scope", "").strip()
    if bulk_action not in {"copy", "paste", "clear"}:
        bulk_action = ""
    if bulk_action == "copy" and bulk_scope not in {"cell", "concept", "day", "week"}:
        bulk_scope = "cell"
    elif bulk_action == "clear" and bulk_scope not in {"cell", "concept", "day", "week"}:
        bulk_scope = "cell"
    elif bulk_action == "paste":
        bulk_scope = ""

    return render_template(
        "menu_detail.html",
        menu=menu,
        week_numbers=week_numbers,
        selected_week_number=selected_week_number,
        week_slots=week_slots,
        day_options=DAY_OF_WEEK_OPTIONS,
        meal_period_options=MEAL_PERIOD_OPTIONS,
        menu_slot_clipboard=get_menu_slot_clipboard(),
        bulk_action=bulk_action,
        bulk_scope=bulk_scope,
        day_order=DAY_OF_WEEK_ORDER,
    )


@app.route("/menus/<int:menu_id>/print")
def menu_print(menu_id: int):
    menu = get_menu_detail(menu_id)
    if menu is None:
        return "Menu not found.", 404

    week_numbers = list(range(1, menu["menu_length_weeks"] + 1))
    selected_week = request.args.get("week", "").strip()
    try:
        selected_week_number = int(selected_week) if selected_week else _default_menu_week_number(menu)
    except ValueError:
        selected_week_number = _default_menu_week_number(menu)
    if selected_week_number not in week_numbers:
        selected_week_number = 1

    print_mode = request.args.get("mode", "week").strip()
    if print_mode not in {"week", "day"}:
        print_mode = "week"

    service_days = menu.get("service_days", [])
    current_week_number = _default_menu_week_number(menu)
    requested_day = request.args.get("day", "").strip()
    if requested_day in service_days:
        selected_day = requested_day
    elif selected_week_number == current_week_number and _current_day_of_week() in service_days:
        selected_day = _current_day_of_week()
    else:
        selected_day = service_days[0] if service_days else ""

    week_slots = [slot for slot in menu["slots"] if slot["week_number"] == selected_week_number]
    day_slots = [slot for slot in week_slots if slot["day_of_week"] == selected_day]

    return render_template(
        "menu_print.html",
        menu=menu,
        week_numbers=week_numbers,
        selected_week_number=selected_week_number,
        current_week_number=current_week_number,
        selected_day=selected_day,
        print_mode=print_mode,
        week_slots=week_slots,
        day_slots=day_slots,
        day_options=DAY_OF_WEEK_OPTIONS,
        meal_period_options=MEAL_PERIOD_OPTIONS,
    )


@app.route("/menus/<int:menu_id>/forecast")
def menu_forecast(menu_id: int):
    menu_context = get_menu_detail(menu_id)
    week = request.args.get("week", "").strip()
    try:
        week_number = int(week) if week else _default_menu_week_number(menu_context)
    except ValueError:
        week_number = _default_menu_week_number(menu_context)

    requested_day = request.args.get("day", "").strip()

    page_data = get_menu_forecast_page(
        menu_id,
        week_number=week_number,
        day_of_week=requested_day or _current_day_of_week(),
        search_term=request.args.get("q", "").strip(),
        meal_period=request.args.get("meal_period", "").strip(),
        concept=request.args.get("concept", "").strip(),
        sort_by=request.args.get("sort", "").strip(),
        sort_order=request.args.get("order", "").strip(),
    )
    if page_data is None:
        return "Menu not found.", 404

    return render_template(
        "menu_forecast.html",
        page_data=page_data,
        day_options=DAY_OF_WEEK_OPTIONS,
        meal_period_options=MEAL_PERIOD_OPTIONS,
        approved_units=APPROVED_UNITS,
        serving_size_units=STANDARD_UNITS,
    )


@app.route("/menus/<int:menu_id>/service-context")
def menu_service_context(menu_id: int):
    menu = get_menu_detail(menu_id)
    if menu is None:
        return "Menu not found.", 404

    week = request.args.get("week", "").strip()
    try:
        week_number = int(week) if week else _default_menu_week_number(menu)
    except ValueError:
        week_number = _default_menu_week_number(menu)
    if week_number not in range(1, int(menu["menu_length_weeks"]) + 1):
        week_number = 1

    day = request.args.get("day", "").strip()
    selected_day = day if day in menu["service_days"] else (menu["service_days"][0] if menu["service_days"] else "")
    service_date = menu.get("week_day_dates", {}).get(week_number, {}).get(selected_day, {})
    day_label = next(
        (option["label"] for option in DAY_OF_WEEK_OPTIONS if option["value"] == selected_day),
        selected_day.title(),
    )
    forecast_page_data = get_menu_forecast_page(
        menu_id,
        week_number=week_number,
        day_of_week=selected_day,
    )
    current_user = get_current_mock_user(session)
    try:
        production_record_data = get_production_record_for_service_day(
            menu_id=menu_id,
            week_number=week_number,
            day_of_week=selected_day,
            actor_user_id=current_user["user_id"],
        )
    except InvalidProductionRecordError:
        production_record_data = None

    return render_template(
        "menu_service_context.html",
        menu=menu,
        week_number=week_number,
        selected_day=selected_day,
        selected_day_label=day_label,
        service_date=service_date,
        forecast_page_data=forecast_page_data,
        production_record=production_record_data,
    )


@app.route("/menus/<int:menu_id>/production-record")
def production_record(menu_id: int):
    menu_context = get_menu_detail(menu_id)
    week = request.args.get("week", "").strip()
    try:
        week_number = int(week) if week else _default_menu_week_number(menu_context)
    except ValueError:
        week_number = _default_menu_week_number(menu_context)

    current_user = get_current_mock_user(session)
    requested_day = request.args.get("day", "").strip()
    page_data = get_menu_forecast_page(
        menu_id,
        week_number=week_number,
        day_of_week=requested_day or _current_day_of_week(),
        search_term=request.args.get("q", "").strip(),
        meal_period=request.args.get("meal_period", "").strip(),
        concept=request.args.get("concept", "").strip(),
        sort_by=request.args.get("sort", "").strip(),
        sort_order=request.args.get("order", "").strip(),
    )
    if page_data is None:
        return "Menu not found.", 404

    try:
        production_record_data = ensure_production_record(
            menu_id=menu_id,
            week_number=page_data["selected_week_number"],
            day_of_week=page_data["selected_day"],
            production_summary=page_data["production_summary"],
            actor_user_id=current_user["user_id"],
        )
    except InvalidProductionRecordError as exc:
        flash(str(exc), "error")
        return redirect(url_for("menu_detail", menu_id=menu_id, week=week_number))

    summary_lookup = {
        int(row["item_id"]): row
        for row in page_data["production_summary"]["rows"]
    }
    for line in production_record_data["lines"]:
        summary_row = summary_lookup.get(line["item_id"], {})
        line["unit_options"] = build_production_record_unit_options(summary_row) if summary_row else [line["forecast_unit"]]

    return render_template(
        "production_record.html",
        page_data=page_data,
        production_record=production_record_data,
        service_day_navigation=_build_service_day_navigation(page_data),
        production_record_reason_options=PRODUCTION_RECORD_REASON_OPTIONS,
        day_options=DAY_OF_WEEK_OPTIONS,
        approved_units=APPROVED_UNITS,
    )


@app.route("/menus/<int:menu_id>/production-record/history")
def production_record_history(menu_id: int):
    menu = get_menu_detail(menu_id)
    if menu is None:
        return "Menu not found.", 404

    current_user = get_current_mock_user(session)
    history_filter_payload = _production_history_filter_payload(request.args)
    history_view = history_filter_payload.get("view", "records")
    if history_view not in {"records", "items"}:
        history_view = "records"
        history_filter_payload["view"] = "records"

    history = None
    item_trends = None
    try:
        if history_view == "items":
            default_date_from = str(menu.get("menu_start_date") or "").strip()
            default_date_to = _current_service_date().isoformat()
            if default_date_from:
                try:
                    menu_start = date.fromisoformat(default_date_from)
                    current_service_day = date.fromisoformat(default_date_to)
                    if current_service_day < menu_start:
                        default_date_to = default_date_from
                except ValueError:
                    pass
            item_trends = list_production_record_item_trends_for_menu(
                menu_id=menu_id,
                actor_user_id=current_user["user_id"],
                service_date_lookup=menu.get("week_day_dates", {}),
                filters=history_filter_payload,
                default_date_from=default_date_from,
                default_date_to=default_date_to,
            )
            history_filters = item_trends["filters"]
        else:
            history = list_production_records_for_menu(
                menu_id=menu_id,
                actor_user_id=current_user["user_id"],
                service_date_lookup=menu.get("week_day_dates", {}),
                filters=history_filter_payload,
            )
            history_filters = history["filters"]
    except InvalidProductionRecordError as exc:
        flash(str(exc), "error")
        return redirect(url_for("menus"))

    def _history_url(**overrides) -> str:
        args = request.args.to_dict()
        args.update(overrides)
        if args.get("view") == "records":
            args.pop("view", None)
        clean_args = {key: value for key, value in args.items() if value}
        return url_for("production_record_history", menu_id=menu_id, **clean_args)

    def _history_sort_url(sort_param: str, direction_param: str, sort_value: str) -> str:
        args = request.args.to_dict()
        current_sort = args.get(sort_param, "")
        current_direction = args.get(direction_param, "desc")
        args[sort_param] = sort_value
        args[direction_param] = (
            "asc"
            if current_sort == sort_value and current_direction != "asc"
            else "desc"
        )
        clean_args = {key: value for key, value in args.items() if value}
        return url_for("production_record_history", menu_id=menu_id, **clean_args)

    def _variance_occurrences_url(item: dict, kind: str) -> str:
        args = request.args.to_dict()
        args.update(
            {
                "item_id": item["item_id"],
                "unit": item["unit"],
                "kind": kind,
            }
        )
        clean_args = {key: value for key, value in args.items() if value}
        return url_for("api_production_record_variance_occurrences", menu_id=menu_id, **clean_args)

    for item in (history or {}).get("report", {}).get("variance_by_item", []):
        item["leftover_occurrences_url"] = _variance_occurrences_url(item, "leftover")
        item["shortage_occurrences_url"] = _variance_occurrences_url(item, "shortage")

    reset_url_args = {"view": "items"} if history_view == "items" else {}

    return render_template(
        "production_record_history.html",
        menu=menu,
        history=history,
        item_trends=item_trends,
        history_view=history_view,
        history_filters=history_filters,
        history_view_urls={
            "records": _history_url(view="records"),
            "items": _history_url(view="items"),
        },
        history_reset_url=url_for(
            "production_record_history",
            menu_id=menu_id,
            **reset_url_args,
        ),
        history_sort_urls={
            "reason_lines": _history_sort_url("reason_sort", "reason_dir", "lines"),
            "variance_leftover": _history_sort_url("variance_sort", "variance_dir", "leftover"),
            "variance_shortage": _history_sort_url("variance_sort", "variance_dir", "shortage"),
        },
        day_options=DAY_OF_WEEK_OPTIONS,
        production_record_reason_options=PRODUCTION_RECORD_REASON_OPTIONS,
    )


def _production_history_filter_payload(args) -> dict:
    return {
        "view": args.get("view", "records"),
        "status": args.get("status", ""),
        "accuracy": args.get("accuracy", ""),
        "reason_code": args.get("reason_code", ""),
        "item_query": args.get("item", ""),
        "week": args.get("week", ""),
        "day": args.get("day", ""),
        "date_from": args.get("date_from", ""),
        "date_to": args.get("date_to", ""),
        "reason_sort": args.get("reason_sort", ""),
        "reason_dir": args.get("reason_dir", ""),
        "variance_sort": args.get("variance_sort", ""),
        "variance_dir": args.get("variance_dir", ""),
    }


@app.get("/api/menus/<int:menu_id>/production-record/history/variance-occurrences")
def api_production_record_variance_occurrences(menu_id: int):
    menu = get_menu_detail(menu_id)
    if menu is None:
        return "Menu not found.", 404

    current_user = get_current_mock_user(session)
    history_filter_payload = _production_history_filter_payload(request.args)
    try:
        history = list_production_records_for_menu(
            menu_id=menu_id,
            actor_user_id=current_user["user_id"],
            service_date_lookup=menu.get("week_day_dates", {}),
            filters=history_filter_payload,
        )
    except InvalidProductionRecordError as exc:
        return str(exc), 400

    try:
        item_id = int(request.args.get("item_id", ""))
    except (TypeError, ValueError):
        return "Item is required.", 400
    unit = request.args.get("unit", "").strip()
    kind = request.args.get("kind", "").strip()
    if kind not in {"leftover", "shortage"}:
        return "Variance kind is required.", 400

    selected_item = next(
        (
            item
            for item in history["report"]["variance_by_item"]
            if int(item["item_id"]) == item_id and item["unit"] == unit
        ),
        None,
    )
    occurrences = selected_item[f"{kind}_occurrences"] if selected_item else []
    kind_label = "Leftover" if kind == "leftover" else "Shortage"
    return render_template(
        "partials/production_record_variance_occurrences.html",
        menu=menu,
        occurrences=occurrences,
        heading=f"{kind_label} Occurrences",
        kind_label=kind_label,
    )


@app.route("/api/menus/<int:menu_id>/production-record/lines/<int:production_record_line_id>", methods=["PUT"])
def api_update_production_record_line(menu_id: int, production_record_line_id: int):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Missing JSON payload."}), 400

    current_user = get_current_mock_user(session)
    try:
        line = save_production_record_line(
            menu_id=menu_id,
            production_record_line_id=production_record_line_id,
            actor_user_id=current_user["user_id"],
            actual_quantity=payload.get("actual_quantity"),
            actual_unit=payload.get("actual_unit"),
            end_service_variance_quantity=payload.get("end_service_variance_quantity"),
            end_service_variance_unit=payload.get("end_service_variance_unit"),
            reason_code=payload.get("reason_code"),
            reason_note=payload.get("reason_note"),
            notes=payload.get("notes"),
        )
        return jsonify({"ok": True, "line": line})
    except InvalidProductionRecordError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unexpected error: {exc}"}), 500


@app.route("/api/menus/<int:menu_id>/production-record/posted-facts")
def api_posted_production_facts(menu_id: int):
    menu = get_menu_detail(menu_id)
    if menu is None:
        return jsonify({"ok": False, "error": "Menu not found."}), 404

    current_user = get_current_mock_user(session)
    try:
        contract = get_posted_production_facts_for_menu(
            menu_id=menu_id,
            actor_user_id=current_user["user_id"],
            service_date_lookup=menu.get("week_day_dates", {}),
        )
        return jsonify({"ok": True, "contract": contract})
    except InvalidProductionRecordError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unexpected error: {exc}"}), 500


@app.route("/menus/<int:menu_id>/production-record/<int:production_record_id>/post", methods=["POST"])
def post_production_record_route(menu_id: int, production_record_id: int):
    week = request.form.get("week", "1").strip() or "1"
    day = request.form.get("day", "").strip()
    current_user = get_current_mock_user(session)

    try:
        post_production_record(
            menu_id=menu_id,
            production_record_id=production_record_id,
            actor_user_id=current_user["user_id"],
        )
        flash("Production record posted.", "success")
        return redirect(url_for("production_record_review", menu_id=menu_id, production_record_id=production_record_id))
    except InvalidProductionRecordError as exc:
        flash(str(exc), "error")

    return redirect(url_for("production_record", menu_id=menu_id, week=week, day=day or None))


@app.route("/menus/<int:menu_id>/production-record/<int:production_record_id>/review")
def production_record_review(menu_id: int, production_record_id: int):
    current_user = get_current_mock_user(session)
    try:
        production_record_data = get_production_record_review(
            menu_id=menu_id,
            production_record_id=production_record_id,
            actor_user_id=current_user["user_id"],
        )
    except InvalidProductionRecordError as exc:
        flash(str(exc), "error")
        return redirect(url_for("menu_detail", menu_id=menu_id))

    menu = get_menu_detail(menu_id)
    if menu is None:
        return "Menu not found.", 404

    service_date = menu.get("week_day_dates", {}).get(production_record_data["week_number"], {}).get(
        production_record_data["day_of_week"],
        {},
    )

    return render_template(
        "production_record_review.html",
        menu=menu,
        production_record=production_record_data,
        service_date=service_date,
    )


@app.route("/menus/<int:menu_id>/production-record/<int:production_record_id>/export.csv")
def production_record_export_csv(menu_id: int, production_record_id: int):
    current_user = get_current_mock_user(session)
    try:
        production_record_data = get_production_record_review(
            menu_id=menu_id,
            production_record_id=production_record_id,
            actor_user_id=current_user["user_id"],
        )
    except InvalidProductionRecordError as exc:
        flash(str(exc), "error")
        return redirect(url_for("menu_detail", menu_id=menu_id))

    menu = get_menu_detail(menu_id)
    if menu is None:
        return "Menu not found.", 404

    service_date = menu.get("week_day_dates", {}).get(production_record_data["week_number"], {}).get(
        production_record_data["day_of_week"],
        {},
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Menu",
            "Week",
            "Day",
            "Service Date",
            "Status",
            "Item",
            "Slots",
            "Forecast Quantity",
            "Forecast Unit",
            "Actual Quantity",
            "Actual Unit",
            "Actual Formula",
            "Leftover / Shortage Quantity",
            "Leftover / Shortage Unit",
            "Leftover / Shortage Formula",
            "Implied Demand Quantity",
            "Implied Demand Unit",
            "Forecast Error Quantity",
            "Forecast Error Unit",
            "Forecast Error Percent",
            "Forecast Accuracy",
            "Reason",
            "Reason Note",
            "Line Notes",
        ],
    )
    for line in production_record_data["lines"]:
        writer.writerow(
            [
                menu["menu_name"],
                production_record_data["week_number"],
                production_record_data["day_of_week"].title(),
                service_date.get("iso", ""),
                production_record_data["status_label"],
                line["recipe_name"],
                ", ".join(line["slot_labels"]),
                line["forecast_quantity_display"],
                format_unit_label(line["forecast_unit"]),
                line["actual_quantity_display"],
                format_unit_label(line["actual_unit"]),
                line["actual_quantity_formula"],
                line["end_service_variance_quantity_display"],
                format_unit_label(line["end_service_variance_unit"]),
                line["end_service_variance_quantity_formula"],
                line["implied_demand_quantity_display"],
                format_unit_label(line["implied_demand_unit"]),
                line["forecast_error_quantity_display"],
                format_unit_label(line["forecast_error_unit"]),
                line["forecast_error_percent_display"],
                line["forecast_accuracy_level"],
                line["reason_label"],
                line["reason_note"],
                line["notes"],
            ],
        )

    filename = (
        f"production-record-menu-{menu_id}-week-{production_record_data['week_number']}-"
        f"{production_record_data['day_of_week']}.csv"
    )
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _build_recipe_print_context(item_id: int) -> dict | None:
    item = get_item_detail(item_id)
    if item is None or item["item_type"] != "recipe":
        return None

    current_user = get_current_mock_user(session)
    current_preferences = current_user.get("preferences", {})
    display_mode = normalize_display_mode(
        request.args.get("display_mode", current_preferences.get("display_mode", DISPLAY_MODE_DEFAULT))
    )
    unit_system = normalize_unit_system(
        request.args.get("unit_system", current_preferences.get("unit_system", UNIT_SYSTEM_IMPERIAL))
    )

    scale_quantity = request.args.get("scale_quantity", "").strip()
    scale_unit = request.args.get("scale_unit", "").strip()
    user_serving_size_quantity = request.args.get("user_serving_size_quantity", "").strip()
    user_serving_size_unit = request.args.get("user_serving_size_unit", "").strip()
    desired_portions = request.args.get("desired_portions", "").strip()
    scale_mode = request.args.get("scale_mode", "yield").strip()
    advanced_scale_row_key = request.args.get("advanced_scale_row_key", "").strip()
    advanced_scale_quantity = request.args.get("advanced_scale_quantity", "").strip()
    advanced_scale_unit = request.args.get("advanced_scale_unit", "").strip()
    source_ingredient_view = request.args.get("ingredient_view", "hierarchical").strip()
    if source_ingredient_view not in {"hierarchical", "flattened"}:
        source_ingredient_view = "hierarchical"

    desired_portions_target = None
    if item["status"] == "live" and desired_portions:
        desired_portions_target = build_desired_portions_yield_target(
            recipe_measurements=item,
            desired_portions=desired_portions,
            serving_quantity=user_serving_size_quantity or item.get("serving_size_quantity"),
            serving_unit=user_serving_size_unit or item.get("serving_size_unit"),
            target_unit=scale_unit or item.get("yield_unit"),
        )
        if desired_portions_target and desired_portions_target.get("available"):
            scale_quantity = f"{desired_portions_target['target_quantity']:g}"
            scale_unit = desired_portions_target["target_unit"]
            scale_mode = "yield"

    bottom_up_scaled_recipe_view = (
        build_bottom_up_scaled_recipe_view(
            item_id,
            ingredient_view=source_ingredient_view,
            target_row_key=advanced_scale_row_key,
            target_quantity=advanced_scale_quantity,
            target_unit=advanced_scale_unit,
        )
        if item["status"] == "live"
        and scale_mode == "ingredient"
        and (advanced_scale_row_key or advanced_scale_quantity or advanced_scale_unit)
        else None
    )
    if bottom_up_scaled_recipe_view and bottom_up_scaled_recipe_view.get("is_scaled"):
        scale_quantity = f"{bottom_up_scaled_recipe_view['forecast_yield_quantity']:g}"
        scale_unit = bottom_up_scaled_recipe_view["forecast_yield_unit"]

    scaled_recipe_view = (
        build_scaled_recipe_view(
            item_id,
            target_quantity=scale_quantity,
            target_unit=scale_unit,
            ingredient_view="flattened",
        )
        if item["status"] == "live" and (scale_quantity or scale_unit)
        else None
    )
    flattened_recipe_view = (
        build_flattened_recipe_view(item_id)
        if item["status"] == "live" and not (scaled_recipe_view and scaled_recipe_view.get("is_scaled"))
        else None
    )

    ingredient_rows = []
    warnings = []
    if scaled_recipe_view and scaled_recipe_view.get("is_scaled"):
        apply_unit_system_to_recipe_snapshot(scaled_recipe_view, unit_system)
        processed_rows = apply_display_preferences_to_rows(
            rows=scaled_recipe_view.get("rows", []),
            row_mode="flattened",
            display_mode=display_mode,
            unit_system=unit_system,
        )
        ingredient_rows = processed_rows["rows"]
        warnings = [*scaled_recipe_view.get("warnings", []), *processed_rows["warnings"]]
        yield_snapshot = scaled_recipe_view["scaled_snapshot"]
        yield_quantity = yield_snapshot["yield_quantity"]
        yield_unit = yield_snapshot["yield_unit"]
        mass_quantity = yield_snapshot.get("mass_display_quantity_display") or yield_snapshot.get("mass_quantity")
        mass_unit = yield_snapshot.get("mass_display_unit") or yield_snapshot.get("mass_unit")
        volume_quantity = yield_snapshot.get("volume_display_quantity_display") or yield_snapshot.get("volume_quantity")
        volume_unit = yield_snapshot.get("volume_display_unit") or yield_snapshot.get("volume_unit")
        is_scaled = True
    else:
        apply_unit_system_to_recipe_item_snapshot(item, unit_system)
        processed_rows = apply_display_preferences_to_rows(
            rows=(flattened_recipe_view or {}).get("rows", []),
            row_mode="flattened",
            display_mode=display_mode,
            unit_system=unit_system,
        )
        ingredient_rows = processed_rows["rows"]
        warnings = [*((flattened_recipe_view or {}).get("warnings", [])), *processed_rows["warnings"]]
        yield_quantity = item["yield_quantity"]
        yield_unit = item["yield_unit"]
        mass_quantity = item.get("mass_display_quantity_display") or item.get("mass_quantity")
        mass_unit = item.get("mass_display_unit") or item.get("mass_unit")
        volume_quantity = item.get("volume_display_quantity_display") or item.get("volume_quantity")
        volume_unit = item.get("volume_display_unit") or item.get("volume_unit")
        is_scaled = False

    return {
        "item": item,
        "display_mode": display_mode,
        "unit_system": unit_system,
        "is_scaled": is_scaled,
        "yield_quantity": yield_quantity,
        "yield_unit": yield_unit,
        "mass_quantity": mass_quantity,
        "mass_unit": mass_unit,
        "volume_quantity": volume_quantity,
        "volume_unit": volume_unit,
        "ingredient_rows": ingredient_rows,
        "warnings": warnings,
    }


@app.route("/recipe-collection/items/<int:item_id>/print")
def recipe_print(item_id: int):
    context = _build_recipe_print_context(item_id)
    if context is None:
        return "Recipe not found.", 404
    return render_template("recipe_print.html", **context)


@app.route("/items/<int:item_id>/print")
def legacy_recipe_print(item_id: int):
    return _redirect_with_query("recipe_print", item_id=item_id)


@app.route("/menus/<int:menu_id>/forecast/recipes/<int:item_id>/advanced")
def menu_forecast_recipe_advanced(menu_id: int, item_id: int):
    menu_slot_item_id = request.args.get("menu_slot_item_id", None)
    forecast = (
        get_menu_forecast_by_slot_item(int(menu_slot_item_id), menu_id=menu_id)
        if str(menu_slot_item_id or "").isdigit()
        else None
    )
    scale_quantity = None
    scale_unit = None
    if forecast:
        scale_quantity = (
            forecast["calculated_forecast_quantity"]
            if forecast["calculated_forecast_quantity"] is not None
            else forecast["forecast_yield_quantity"]
        )
        scale_unit = forecast["calculated_forecast_unit"] or forecast["forecast_yield_unit"]
    return redirect(
        url_for(
            "item_detail",
            item_id=item_id,
            forecast_menu_id=menu_id,
            forecast_menu_slot_item_id=menu_slot_item_id,
            forecast_week=request.args.get("week", None),
            forecast_day=request.args.get("day", None),
            scale_quantity=f"{scale_quantity:g}" if scale_quantity is not None else None,
            scale_unit=scale_unit,
            user_serving_size_quantity=f"{forecast['user_serving_size_quantity']:g}" if forecast and forecast["user_serving_size_quantity"] is not None else None,
            user_serving_size_unit=forecast["user_serving_size_unit"] if forecast else None,
            desired_portions=f"{forecast['desired_portions']:g}" if forecast and forecast["desired_portions"] is not None else None,
            ingredient_view=request.args.get("ingredient_view", "hierarchical"),
        )
    )


@app.route("/api/menus/<int:menu_id>/forecast/<int:menu_slot_item_id>", methods=["PUT"])
def api_update_menu_forecast(menu_id: int, menu_slot_item_id: int):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Missing JSON payload."}), 400

    current_user = get_current_mock_user(session)
    try:
        forecast = save_menu_forecast_yield(
            menu_id=menu_id,
            menu_slot_item_id=menu_slot_item_id,
            actor_user_id=current_user["user_id"],
            forecast_yield_quantity=payload.get("forecast_yield_quantity"),
            forecast_yield_unit=payload.get("forecast_yield_unit"),
            user_serving_size_quantity=payload.get("user_serving_size_quantity"),
            user_serving_size_unit=payload.get("user_serving_size_unit"),
            desired_portions=payload.get("desired_portions"),
            case_pack_quantity=payload.get("case_pack_quantity"),
            case_subunit_quantity=payload.get("case_subunit_quantity"),
            case_subunit_unit=payload.get("case_subunit_unit"),
            case_basis_component_item_id=payload.get("case_basis_component_item_id"),
            case_basis_component_name=payload.get("case_basis_component_name"),
            case_basis_view_mode=payload.get("case_basis_view_mode"),
            case_basis_row_key=payload.get("case_basis_row_key"),
        )
        return jsonify({"ok": True, "forecast": forecast})
    except InvalidMenuForecastError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unexpected error: {exc}"}), 500


@app.route("/api/menus/<int:menu_id>/forecast/<int:menu_slot_item_id>/batches", methods=["PUT"])
def api_update_menu_forecast_batches(menu_id: int, menu_slot_item_id: int):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Missing JSON payload."}), 400

    current_user = get_current_mock_user(session)
    try:
        batch_plan = save_menu_forecast_batch_splits(
            menu_id=menu_id,
            menu_slot_item_id=menu_slot_item_id,
            actor_user_id=current_user["user_id"],
            batch_splits=payload.get("batch_splits", []),
        )
        return jsonify({"ok": True, "batch_plan": batch_plan})
    except InvalidMenuForecastBatchError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unexpected error: {exc}"}), 500


@app.route("/api/menus/<int:menu_id>/forecast/<int:menu_slot_item_id>/case-packs", methods=["POST"])
def api_save_menu_forecast_case_pack(menu_id: int, menu_slot_item_id: int):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Missing JSON payload."}), 400

    current_user = get_current_mock_user(session)
    try:
        case_pack = save_item_case_pack(
            menu_id=menu_id,
            menu_slot_item_id=menu_slot_item_id,
            actor_user_id=current_user["user_id"],
            item_id=payload.get("item_id"),
            pack_quantity=payload.get("pack_quantity"),
            subunit_quantity=payload.get("subunit_quantity"),
            subunit_unit=payload.get("subunit_unit"),
        )
        return jsonify({"ok": True, "case_pack": case_pack})
    except InvalidMenuForecastError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unexpected error: {exc}"}), 500


@app.route("/menus/<int:menu_id>/forecast/<int:menu_slot_item_id>/confirm-scaling", methods=["POST"])
def confirm_menu_forecast_scaling(menu_id: int, menu_slot_item_id: int):
    current_user = get_current_mock_user(session)
    forecast_week = request.form.get("forecast_week", "1")
    forecast_day = request.form.get("forecast_day", "")
    try:
        save_menu_forecast_yield(
            menu_id=menu_id,
            menu_slot_item_id=menu_slot_item_id,
            actor_user_id=current_user["user_id"],
            forecast_yield_quantity=request.form.get("forecast_yield_quantity"),
            forecast_yield_unit=request.form.get("forecast_yield_unit"),
            user_serving_size_quantity=request.form.get("user_serving_size_quantity"),
            user_serving_size_unit=request.form.get("user_serving_size_unit"),
            desired_portions=request.form.get("desired_portions"),
        )
        flash("Forecast scaling confirmed.", "success")
        return redirect(url_for("menu_forecast", menu_id=menu_id, week=forecast_week, day=forecast_day))
    except InvalidMenuForecastError as exc:
        flash(str(exc), "error")
        return redirect(request.referrer or url_for("menu_forecast", menu_id=menu_id, week=forecast_week, day=forecast_day))


@app.route("/menus/<int:menu_id>/delete", methods=["POST"])
def delete_menu_route(menu_id: int):
    current_user = get_current_mock_user(session)
    try:
        delete_menu(menu_id=menu_id, actor_user_id=current_user["user_id"])
        flash("Menu deleted successfully.", "success")
    except InvalidMenuDeleteError as exc:
        flash(str(exc), "error")
        return redirect(url_for("menu_detail", menu_id=menu_id))

    return redirect(url_for("my_menus"))


@app.route("/menus/<int:menu_id>/slots/<int:menu_slot_id>/copy", methods=["POST"])
def copy_menu_slot_route(menu_id: int, menu_slot_id: int):
    current_user = get_current_mock_user(session)
    week = request.form.get("week", "1")
    try:
        copied_item_ids = get_menu_slot_assignment_ids(
            menu_slot_id=menu_slot_id,
            actor_user_id=current_user["user_id"],
        )
        session["menu_slot_clipboard"] = {
            "mode": "cell",
            "entries": [
                {
                    "item_ids": copied_item_ids,
                }
            ],
            "copied_count": len(copied_item_ids),
        }
        flash(
            (
                f"Copied {len(copied_item_ids)} slot item{'s' if len(copied_item_ids) != 1 else ''}."
                if copied_item_ids
                else "Copied an empty slot."
            ),
            "success",
        )
    except InvalidMenuSlotActionError as exc:
        flash(str(exc), "error")

    return redirect(url_for("menu_detail", menu_id=menu_id, week=week))


@app.route("/menus/<int:menu_id>/slots/<int:menu_slot_id>/paste", methods=["POST"])
def paste_menu_slot_route(menu_id: int, menu_slot_id: int):
    current_user = get_current_mock_user(session)
    week = request.form.get("week", "1")
    clipboard = get_menu_slot_clipboard()

    try:
        copied_item_ids = clipboard["entries"][0]["item_ids"] if clipboard else []
        paste_menu_slot_assignment_ids(
            menu_slot_id=menu_slot_id,
            actor_user_id=current_user["user_id"],
            copied_item_ids=copied_item_ids,
        )
        flash("Pasted copied slot items.", "success")
    except InvalidMenuSlotActionError as exc:
        flash(str(exc), "error")

    return redirect(url_for("menu_detail", menu_id=menu_id, week=week))


@app.route("/menus/<int:menu_id>/slots/<int:menu_slot_id>/clear", methods=["POST"])
def clear_menu_slot_route(menu_id: int, menu_slot_id: int):
    current_user = get_current_mock_user(session)
    week = request.form.get("week", "1")
    try:
        clear_menu_slot(
            menu_slot_id=menu_slot_id,
            actor_user_id=current_user["user_id"],
        )
        flash("Cleared slot assignments.", "success")
    except InvalidMenuSlotActionError as exc:
        flash(str(exc), "error")

    return redirect(url_for("menu_detail", menu_id=menu_id, week=week))


@app.route("/menus/<int:menu_id>/bulk-action", methods=["POST"])
def menu_bulk_action_route(menu_id: int):
    current_user = get_current_mock_user(session)
    action = request.form.get("action", "").strip()
    scope = request.form.get("scope", "").strip()
    week = request.form.get("week", "1")
    selected_slot_ids = request.form.getlist("selected_slot_ids")

    try:
        if action == "copy":
            clipboard = copy_menu_slots(
                menu_id=menu_id,
                actor_user_id=current_user["user_id"],
                selected_slot_ids=selected_slot_ids,
                scope=scope,
            )
            session["menu_slot_clipboard"] = clipboard
            flash(
                f"Copied {clipboard['copied_count']} {scope}{'s' if clipboard['copied_count'] != 1 else ''}.",
                "success",
            )
            if scope == "week":
                return redirect(url_for("menu_week_paste", menu_id=menu_id, source_week=week))
        elif action == "paste":
            pasted_count = paste_menu_slots(
                menu_id=menu_id,
                actor_user_id=current_user["user_id"],
                selected_slot_ids=selected_slot_ids,
                clipboard=get_menu_slot_clipboard(),
            )
            flash(
                f"Pasted into {pasted_count} slot{'s' if pasted_count != 1 else ''}.",
                "success",
            )
        elif action == "clear":
            cleared_count = clear_menu_slots(
                menu_id=menu_id,
                actor_user_id=current_user["user_id"],
                selected_slot_ids=selected_slot_ids,
                scope=scope,
            )
            flash(
                f"Cleared {cleared_count} slot{'s' if cleared_count != 1 else ''}.",
                "success",
            )
        else:
            flash("Select a valid bulk action.", "error")
    except InvalidMenuSlotActionError as exc:
        flash(str(exc), "error")

    return redirect(url_for("menu_detail", menu_id=menu_id, week=week))


@app.route("/menus/<int:menu_id>/paste-weeks")
def menu_week_paste(menu_id: int):
    menu = get_menu_detail(menu_id)
    if menu is None:
        return "Menu not found.", 404

    clipboard = get_menu_slot_clipboard()
    if not clipboard or clipboard.get("mode") != "week":
        flash("Copy a week first before choosing destination weeks.", "error")
        return redirect(url_for("menu_detail", menu_id=menu_id, week=1))

    source_week = request.args.get("source_week", "1").strip()
    try:
        source_week_number = int(source_week)
    except ValueError:
        source_week_number = 1

    week_numbers = list(range(1, menu["menu_length_weeks"] + 1))
    if source_week_number not in week_numbers:
        source_week_number = 1

    week_rows = [
        week_numbers[index:index + 4]
        for index in range(0, len(week_numbers), 4)
    ]
    week_date_ranges = {}
    for week_number in week_numbers:
        week_dates = [
            day_date
            for day_date in menu.get("week_day_dates", {}).get(week_number, {}).values()
            if day_date.get("display")
        ]
        if not week_dates:
            continue
        first_date = week_dates[0]["display"]
        last_date = week_dates[-1]["display"]
        week_date_ranges[week_number] = first_date if first_date == last_date else f"{first_date} - {last_date}"

    return render_template(
        "menu_week_paste.html",
        menu=menu,
        source_week_number=source_week_number,
        week_rows=week_rows,
        week_date_ranges=week_date_ranges,
    )


@app.route("/menus/<int:menu_id>/paste-weeks", methods=["POST"])
def menu_week_paste_post(menu_id: int):
    current_user = get_current_mock_user(session)
    source_week = request.form.get("source_week", "1").strip()
    try:
        source_week_number = int(source_week)
    except ValueError:
        source_week_number = 1

    selected_weeks = request.form.getlist("selected_weeks")

    try:
        pasted_week_count = paste_menu_weeks(
            menu_id=menu_id,
            actor_user_id=current_user["user_id"],
            selected_week_numbers=selected_weeks,
            clipboard=get_menu_slot_clipboard(),
        )
        flash(
            f"Pasted copied week into {pasted_week_count} destination week{'s' if pasted_week_count != 1 else ''}.",
            "success",
        )
    except InvalidMenuSlotActionError as exc:
        flash(str(exc), "error")
        return redirect(url_for("menu_week_paste", menu_id=menu_id, source_week=source_week_number))

    return redirect(url_for("menu_detail", menu_id=menu_id, week=source_week_number))


@app.route("/menus/<int:menu_id>/slots/<int:menu_slot_id>/assign", methods=["GET", "POST"])
def menu_slot_assign(menu_id: int, menu_slot_id: int):
    search_term = request.values.get("q", "").strip()
    item_type = request.values.get("item_type", "").strip()

    if request.method == "POST":
        try:
            replace_menu_slot_items(
                menu_slot_id=menu_slot_id,
                selected_item_ids=request.form.getlist("selected_item_ids"),
                actor_user_id=get_current_mock_user(session)["user_id"],
            )
            flash("Menu slot assignments updated.", "success")
            return redirect(url_for("menu_detail", menu_id=menu_id, week=request.form.get("week", "1")))
        except InvalidMenuSlotAssignmentError as exc:
            flash(str(exc), "error")

    slot_detail = get_menu_slot_detail(
        menu_id,
        menu_slot_id,
        search_term=search_term,
        item_type=item_type,
    )
    if slot_detail is None:
        return "Menu slot not found.", 404

    return render_template(
        "menu_slot_assign.html",
        slot_detail=slot_detail,
        search_term=search_term,
        selected_item_type=item_type,
    )


@app.route("/login")
def login_shell():
    auth_context = build_auth_shell_context(session)
    return render_template("login.html", auth_context=auth_context)


@app.route("/notifications")
def notifications():
    current_user = get_current_mock_user(session)
    notification_rows = get_notification_rows(current_user)
    return render_template(
        "notifications.html",
        notification_rows=notification_rows,
        current_user=current_user,
    )


@app.route("/preferences", methods=["GET", "POST"])
def user_preferences():
    current_user = get_current_mock_user(session)

    if request.method == "POST":
        updated_user = update_current_user_preferences(
            session,
            display_mode=request.form.get("display_mode", ""),
            unit_system=request.form.get("unit_system", ""),
        )
        flash(
            f"Preferences updated for {updated_user['display_name']}.",
            "success",
        )
        return redirect(url_for("user_preferences"))

    return render_template(
        "preferences.html",
        current_user=current_user,
    )


@app.route("/login/select", methods=["POST"])
def login_select():
    selected_user_id = request.form.get("selected_user_id", "").strip()

    try:
        selected_user = select_mock_user(session, selected_user_id)
        flash(
            f"Signed in as {selected_user['display_name']} ({ROLE_LABELS[selected_user['role']]})",
            "success",
        )
    except ValueError as exc:
        flash(str(exc), "error")

    return redirect(url_for("login_shell"))


@app.route("/login/create-user", methods=["POST"])
def login_create_user():
    display_name = request.form.get("display_name", "").strip()
    role = request.form.get("role", "").strip()

    try:
        created_user = create_mock_user(session, display_name=display_name, role=role)
        flash(
            f"Created and signed in as {created_user['display_name']} ({ROLE_LABELS[created_user['role']]})",
            "success",
        )
    except ValueError as exc:
        flash(str(exc), "error")

    return redirect(url_for("login_shell"))


@app.route("/login/debug-override", methods=["POST"])
def login_debug_override():
    selected_user_id = request.form.get("override_user_id", "").strip()
    display_name = request.form.get("override_display_name", "").strip()
    role = request.form.get("override_role", "").strip()

    try:
        current_user = apply_debug_override(
            session,
            base_user_id=selected_user_id,
            role=role,
            display_name=display_name,
        )
        flash(
            f"Debug override applied: {current_user['display_name']} ({ROLE_LABELS[current_user['role']]})",
            "success",
        )
    except ValueError as exc:
        flash(str(exc), "error")

    return redirect(url_for("login_shell"))


@app.route("/recipe-collection/my-recipes")
def my_recipes():
    current_user = get_current_recipe_author()
    selected_status = request.args.get("status", "").strip()
    selected_sort = request.args.get("sort", "updated_desc").strip()

    page_data = get_my_recipes(
        author_user_id=current_user["author_user_id"],
        status=selected_status,
        sort=selected_sort,
    )

    return render_template(
        "my_recipes.html",
        current_user=current_user,
        page_data=page_data,
        status_labels=STATUS_LABELS,
    )


@app.route("/my-recipes")
def legacy_my_recipes():
    return _redirect_with_query("my_recipes")


@app.route("/recipe-collection")
def live_collection():
    page_data = get_live_collection_page(
        search_term=request.args.get("q", ""),
        item_type=request.args.get("item_type", ""),
        sort=request.args.get("sort", "updated_desc"),
        offset=request.args.get("offset", 0),
    )
    return render_template("collection.html", page_data=page_data)


@app.route("/collection")
def legacy_live_collection():
    return _redirect_with_query("live_collection")


@app.route("/workflow/<portal_name>")
def workflow_portal(portal_name: str):
    current_user = get_current_mock_user(session)

    try:
        portal_definition = ensure_portal_access(current_user["role"], portal_name)
        page_data = get_workflow_portal_items(
            role=current_user["role"],
            portal_name=portal_name,
            selected_status=request.args.get("status", "").strip(),
            selected_item_type=request.args.get("item_type", "").strip(),
            sort=request.args.get("sort", "updated_desc").strip(),
        )
    except WorkflowPermissionError as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))

    return render_template(
        "workflow_portal.html",
        portal_name=portal_name,
        portal_definition=portal_definition,
        current_user=current_user,
        page_data=page_data,
    )


@app.route("/workflow/items/<int:item_id>/transition", methods=["POST"])
def workflow_transition(item_id: int):
    current_user = get_current_mock_user(session)
    portal_name = request.form.get("portal_name", "").strip()
    action_code = request.form.get("action_code", "").strip()
    target_status = request.form.get("target_status", "").strip()
    reason_text = request.form.get("reason_text", "").strip()
    selected_status = request.form.get("selected_status", "").strip()
    selected_item_type = request.form.get("selected_item_type", "").strip()
    selected_sort = request.form.get("selected_sort", "updated_desc").strip()

    try:
        page_data = get_workflow_portal_items(
            role=current_user["role"],
            portal_name=portal_name,
            selected_status=selected_status,
            selected_item_type=selected_item_type,
            sort=selected_sort,
        )
        matching_item = next(
            (item for item in page_data["items"] if item["item_id"] == item_id),
            None,
        )
        new_status = transition_item_status(
            item_id=item_id,
            current_user=current_user,
            portal_name=portal_name,
            action_code=action_code,
            target_status=target_status,
            reason_text=reason_text,
        )
        flash(
            (
                f"{matching_item['display_title']} moved to {STATUS_LABELS.get(new_status, new_status)}."
                if matching_item
                else f"Item {item_id} moved to {STATUS_LABELS.get(new_status, new_status)}."
            ),
            "success",
        )
    except WorkflowPermissionError as exc:
        flash(str(exc), "error")

    return redirect(
        url_for(
            "workflow_portal",
            portal_name=portal_name,
            status=selected_status,
            item_type=selected_item_type,
            sort=selected_sort,
        )
    )


@app.route("/recipe-collection/items/<int:item_id>/edit", methods=["GET", "POST"])
def edit_item(item_id: int):
    current_user = get_current_mock_user(session)
    item = get_item_edit_payload(item_id)
    if item is None:
        return "Item not found.", 404

    if not can_edit_item(current_user, item):
        flash("Your current role does not have access to item editing.", "error")
        return redirect(url_for("item_detail", item_id=item_id))

    if item["item_type"] == "base_food":
        form_data = {
            "item_name": item["item_name"],
            "notes": item["notes"] or "",
            "mass_quantity": item.get("mass_quantity") or "",
            "mass_unit": item.get("mass_unit") or "",
            "volume_quantity": item.get("volume_quantity") or "",
            "volume_unit": item.get("volume_unit") or "",
            "nutrition_group": item.get("nutrition_group") or "",
            "kcal_per_serving": item.get("kcal_per_serving") or "",
            "nutrition_serving_mass_quantity": item.get("nutrition_serving_mass_quantity") or "",
            "nutrition_serving_mass_unit": item.get("nutrition_serving_mass_unit") or "",
            "nutrition_serving_volume_quantity": item.get("nutrition_serving_volume_quantity") or "",
            "nutrition_serving_volume_unit": item.get("nutrition_serving_volume_unit") or "",
        }
        can_manage_measurements = can_manage_official_measurements(current_user["role"])

        if request.method == "POST":
            form_data = get_base_food_form_data()

            try:
                item_name = normalize_item_name(form_data["item_name"])
                form_data["item_name"] = item_name

                if not item_name:
                    raise InvalidItemNameError("Item name cannot be empty or only whitespace.")

                update_base_food(
                    item_id=item_id,
                    item_name=item_name,
                    notes=form_data["notes"] or None,
                    mass_quantity=form_data["mass_quantity"] if can_manage_measurements else item.get("mass_quantity"),
                    mass_unit=(
                        form_data["mass_unit"] or None
                        if can_manage_measurements
                        else item.get("mass_unit")
                    ),
                    volume_quantity=(
                        form_data["volume_quantity"] if can_manage_measurements else item.get("volume_quantity")
                    ),
                    volume_unit=(
                        form_data["volume_unit"] or None
                        if can_manage_measurements
                        else item.get("volume_unit")
                    ),
                    nutrition_group=(
                        form_data["nutrition_group"] or None
                        if can_manage_measurements
                        else item.get("nutrition_group")
                    ),
                    kcal_per_serving=(
                        form_data["kcal_per_serving"]
                        if can_manage_measurements
                        else item.get("kcal_per_serving")
                    ),
                    nutrition_serving_mass_quantity=(
                        form_data["nutrition_serving_mass_quantity"]
                        if can_manage_measurements
                        else item.get("nutrition_serving_mass_quantity")
                    ),
                    nutrition_serving_mass_unit=(
                        form_data["nutrition_serving_mass_unit"] or None
                        if can_manage_measurements
                        else item.get("nutrition_serving_mass_unit")
                    ),
                    nutrition_serving_volume_quantity=(
                        form_data["nutrition_serving_volume_quantity"]
                        if can_manage_measurements
                        else item.get("nutrition_serving_volume_quantity")
                    ),
                    nutrition_serving_volume_unit=(
                        form_data["nutrition_serving_volume_unit"] or None
                        if can_manage_measurements
                        else item.get("nutrition_serving_volume_unit")
                    ),
                    actor_user_id=current_user["user_id"],
                    actor_display_name=current_user["display_name"],
                    actor_role=current_user["role"],
                )
                flash(f"Base Food {item_name} updated successfully.", "success")
                return redirect(url_for("item_detail", item_id=item_id))
            except DuplicateItemNameError as exc:
                if exc.suggested_name:
                    form_data["item_name"] = exc.suggested_name
                    flash(
                        f"{exc} Suggested available name: {exc.suggested_name}",
                        "error",
                    )
                else:
                    flash(str(exc), "error")
            except InvalidItemNameError as exc:
                flash(str(exc), "error")
            except InvalidNumericValueError as exc:
                flash(str(exc), "error")

        return render_template(
            "new_base_food.html",
            form_data=form_data,
            form_mode="edit",
            item_id=item_id,
            approved_units=STANDARD_UNITS,
            can_manage_official_measurements_for_current_user=can_manage_measurements,
        )

    return render_template(
        "new_recipe.html",
        approved_units=STANDARD_UNITS,
        approved_cooking_methods=APPROVED_COOKING_METHODS,
        editor_mode="edit",
        recipe=item,
        submit_url=url_for("api_update_recipe", recipe_id=item_id),
        can_manage_official_measurements_for_current_user=can_manage_official_measurements(
            current_user["role"]
        ),
    )


@app.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
def legacy_edit_item(item_id: int):
    if request.method == "POST":
        return edit_item(item_id)
    return _redirect_with_query("edit_item", item_id=item_id)


@app.route("/recipe-collection/api/items/search")
def api_search_items():
    query = request.args.get("q", "").strip()
    results = search_items_page(
        search_term=query,
        limit=request.args.get("limit", 15),
        offset=request.args.get("offset", 0),
        item_type=request.args.get("item_type", ""),
        relaxed_short_query=request.args.get("relax_short_query", ""),
    )
    return jsonify(results)


@app.route("/api/items/search")
def legacy_api_search_items():
    return api_search_items()


@app.route("/recipe-collection/api/recipes", methods=["POST"])
def api_create_recipe():
    try:
        payload = request.get_json(silent=True)

        if not payload:
            return jsonify({"ok": False, "error": "Missing JSON payload."}), 400

        current_user = get_current_recipe_author()
        if not can_manage_official_measurements(current_user["author_role"]):
            payload["serving_size_quantity"] = None
            payload["serving_size_unit"] = None
            payload["serving_count"] = None
        recipe_item_id = create_recipe(
            payload,
            author_user_id=current_user["author_user_id"],
            author_display_name=current_user["author_display_name"],
            author_role=current_user["author_role"],
        )

        return jsonify(
            {
                "ok": True,
                "recipe_item_id": recipe_item_id,
                "message": "Recipe created successfully.",
            }
        )

    except DuplicateItemNameError as exc:
        response = {
            "ok": False,
            "error": str(exc),
        }
        if exc.suggested_name:
            response["suggested_name"] = exc.suggested_name
        return jsonify(response), 400

    except (InvalidItemNameError, InvalidNumericValueError, InvalidRecipePayloadError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unexpected error: {exc}"}), 500


@app.route("/api/recipes", methods=["POST"])
def legacy_api_create_recipe():
    return api_create_recipe()


@app.route("/recipe-collection/api/recipes/<int:recipe_id>", methods=["PUT"])
def api_update_recipe(recipe_id: int):
    current_user = get_current_mock_user(session)
    item = get_item_detail(recipe_id)
    if item is None:
        return jsonify({"ok": False, "error": "Recipe not found."}), 404

    if not can_edit_item(current_user, item):
        return jsonify({"ok": False, "error": "Your current role does not have access to item editing."}), 403

    try:
        payload = request.get_json(silent=True)

        if not payload:
            return jsonify({"ok": False, "error": "Missing JSON payload."}), 400

        if not can_manage_official_measurements(current_user["role"]):
            payload["serving_size_quantity"] = None
            payload["serving_size_unit"] = None
            payload["serving_count"] = None

        update_recipe(
            recipe_id,
            payload,
            clear_resubmission_request=current_user["user_id"] == item["author_user_id"],
            actor_user_id=current_user["user_id"],
            actor_display_name=current_user["display_name"],
            actor_role=current_user["role"],
        )

        return jsonify(
            {
                "ok": True,
                "recipe_item_id": recipe_id,
                "message": "Recipe updated successfully.",
            }
        )

    except DuplicateItemNameError as exc:
        response = {
            "ok": False,
            "error": str(exc),
        }
        if exc.suggested_name:
            response["suggested_name"] = exc.suggested_name
        return jsonify(response), 400

    except (InvalidItemNameError, InvalidNumericValueError, InvalidRecipePayloadError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    except Exception as exc:
        return jsonify({"ok": False, "error": f"Unexpected error: {exc}"}), 500


@app.route("/api/recipes/<int:recipe_id>", methods=["PUT"])
def legacy_api_update_recipe(recipe_id: int):
    return api_update_recipe(recipe_id)


@app.route("/recipe-collection/items/<int:item_id>")
def item_detail(item_id: int):
    item = get_item_detail(item_id)

    if item is None:
        return "Item not found.", 404
    current_user = get_current_mock_user(session)
    acknowledge_item_notes_for_viewer(item_id, current_user)
    acknowledge_item_notifications_for_viewer(item_id, current_user)
    editable = can_edit_item(current_user, item)
    can_use_advanced_workflow = can_view_advanced_workflow(current_user["role"])
    technical_details_enabled = (
        can_use_advanced_workflow
        and request.args.get("technical_view", "").strip() == "advanced"
    )
    advanced_workflow_enabled = (
        item["status"] == "live"
        and can_use_advanced_workflow
        and request.args.get("workflow_view", "").strip() == "advanced"
    )
    show_workflow_panels = item["status"] != "live" or advanced_workflow_enabled
    ingredient_view_mode = (
        "flattened"
        if item["item_type"] == "recipe"
        and item["status"] == "live"
        and request.args.get("ingredient_view", "").strip() == "flattened"
        else "hierarchical"
    )
    current_preferences = current_user.get("preferences", {})
    display_mode = normalize_display_mode(
        request.args.get("display_mode", current_preferences.get("display_mode", DISPLAY_MODE_DEFAULT))
    )
    unit_system = normalize_unit_system(
        request.args.get("unit_system", current_preferences.get("unit_system", UNIT_SYSTEM_IMPERIAL))
    )
    scale_quantity = request.args.get("scale_quantity", "").strip()
    scale_unit = request.args.get("scale_unit", "").strip()
    user_serving_size_quantity = request.args.get("user_serving_size_quantity", "").strip()
    user_serving_size_unit = request.args.get("user_serving_size_unit", "").strip()
    desired_portions = request.args.get("desired_portions", "").strip()
    scale_mode = request.args.get("scale_mode", "yield").strip()
    advanced_scale_row_key = request.args.get("advanced_scale_row_key", "").strip()
    advanced_scale_quantity = request.args.get("advanced_scale_quantity", "").strip()
    advanced_scale_unit = request.args.get("advanced_scale_unit", "").strip()
    advanced_unit_profile = get_unit_measurement_profile(advanced_scale_unit)
    if (
        item["item_type"] == "recipe"
        and item["status"] == "live"
        and scale_mode == "ingredient"
        and advanced_scale_quantity
        and advanced_unit_profile
        and advanced_unit_profile["measurement_type"] in {"mass", "volume"}
        and request.args.get("advanced_scale_submit", "").strip() == "1"
    ):
        display_mode = advanced_unit_profile["measurement_type"]
    forecast_context = {
        "menu_id": request.args.get("forecast_menu_id", "").strip(),
        "menu_slot_item_id": request.args.get("forecast_menu_slot_item_id", "").strip(),
        "week": request.args.get("forecast_week", "").strip(),
        "day": request.args.get("forecast_day", "").strip(),
    }
    has_forecast_context = bool(forecast_context["menu_id"] and forecast_context["menu_slot_item_id"])
    desired_portions_target = None
    if item["item_type"] == "recipe" and item["status"] == "live" and desired_portions:
        desired_portions_target = build_desired_portions_yield_target(
            recipe_measurements=item,
            desired_portions=desired_portions,
            serving_quantity=user_serving_size_quantity or item.get("serving_size_quantity"),
            serving_unit=user_serving_size_unit or item.get("serving_size_unit"),
            target_unit=scale_unit or item.get("yield_unit"),
        )
        if desired_portions_target and desired_portions_target.get("available"):
            scale_quantity = f"{desired_portions_target['target_quantity']:g}"
            scale_unit = desired_portions_target["target_unit"]
            scale_mode = "yield"
    base_food_convert_quantity = request.args.get("convert_quantity", "").strip()
    base_food_convert_unit = request.args.get("convert_unit", "").strip()
    bottom_up_scaled_recipe_view = (
        build_bottom_up_scaled_recipe_view(
            item_id,
            ingredient_view=ingredient_view_mode,
            target_row_key=advanced_scale_row_key,
            target_quantity=advanced_scale_quantity,
            target_unit=advanced_scale_unit,
        )
        if item["item_type"] == "recipe"
        and item["status"] == "live"
        and scale_mode == "ingredient"
        and (advanced_scale_row_key or advanced_scale_quantity or advanced_scale_unit)
        else None
    )
    scaled_recipe_view = bottom_up_scaled_recipe_view or (
        build_scaled_recipe_view(
            item_id,
            target_quantity=scale_quantity,
            target_unit=scale_unit,
            ingredient_view=ingredient_view_mode,
        )
        if item["item_type"] == "recipe" and item["status"] == "live" and (scale_quantity or scale_unit)
        else None
    )
    base_food_conversion_preview = (
        build_base_food_conversion_preview(
            item,
            target_quantity=base_food_convert_quantity,
            target_unit=base_food_convert_unit,
        )
        if item["item_type"] == "base_food" and technical_details_enabled and (base_food_convert_quantity or base_food_convert_unit)
        else None
    )
    flattened_recipe_view = (
        build_flattened_recipe_view(item_id)
        if item["item_type"] == "recipe" and item["status"] == "live" and not scaled_recipe_view
        else None
    )
    scaling_foundation = (
        build_recipe_scaling_foundation(item_id)
        if item["item_type"] == "recipe"
        else None
    )
    note_recipient = (
        resolve_note_recipient(item, current_user)
        if show_workflow_panels
        else None
    )

    ingredient_display_warnings: list[str] = []
    if item["item_type"] == "recipe" and item["status"] == "live":
        item_snapshot_display_warnings = apply_unit_system_to_recipe_item_snapshot(
            item,
            unit_system,
        )
        if scaled_recipe_view is not None:
            snapshot_display_warnings = apply_unit_system_to_recipe_snapshot(
                scaled_recipe_view,
                unit_system,
            )
            processed_scaled = apply_display_preferences_to_rows(
                rows=scaled_recipe_view.get("rows", []),
                row_mode=scaled_recipe_view.get("row_mode", "hierarchical"),
                display_mode=display_mode,
                unit_system=unit_system,
            )
            scaled_recipe_view["rows"] = processed_scaled["rows"]
            ingredient_display_warnings = [*item_snapshot_display_warnings, *snapshot_display_warnings, *processed_scaled["warnings"]]
        elif ingredient_view_mode == "flattened" and flattened_recipe_view is not None:
            processed_flattened = apply_display_preferences_to_rows(
                rows=flattened_recipe_view["rows"],
                row_mode="flattened",
                display_mode=display_mode,
                unit_system=unit_system,
            )
            flattened_recipe_view["rows"] = processed_flattened["rows"]
            ingredient_display_warnings = [*item_snapshot_display_warnings, *processed_flattened["warnings"]]
        else:
            processed_hierarchical = apply_display_preferences_to_rows(
                rows=item["ingredients"],
                row_mode="hierarchical",
                display_mode=display_mode,
                unit_system=unit_system,
            )
            item["ingredients"] = processed_hierarchical["rows"]
            ingredient_display_warnings = [*item_snapshot_display_warnings, *processed_hierarchical["warnings"]]

    user_serving_preview = None
    if item["item_type"] == "recipe" and item["status"] == "live":
        recipe_measurements = (
            scaled_recipe_view.get("scaled_snapshot")
            if scaled_recipe_view is not None and scaled_recipe_view.get("is_scaled")
            else item
        )
        user_serving_preview = build_user_serving_preview(
            recipe_measurements=recipe_measurements,
            serving_quantity=user_serving_size_quantity,
            serving_unit=user_serving_size_unit,
        )

    return render_template(
        "item_detail.html",
        item=item,
        item_notes=get_item_notes(item_id),
        item_events=get_item_events(item_id),
        note_recipient=note_recipient,
        can_edit_item_for_current_user=editable,
        can_use_advanced_workflow=can_use_advanced_workflow,
        technical_details_enabled=technical_details_enabled,
        advanced_workflow_enabled=advanced_workflow_enabled,
        show_workflow_panels=show_workflow_panels,
        ingredient_view_mode=ingredient_view_mode,
        display_mode=display_mode,
        unit_system=unit_system,
        scale_quantity=scale_quantity,
        scale_unit=scale_unit,
        user_serving_size_quantity=user_serving_size_quantity,
        user_serving_size_unit=user_serving_size_unit,
        desired_portions=desired_portions,
        desired_portions_target=desired_portions_target,
        user_serving_preview=user_serving_preview,
        scale_mode=scale_mode,
        advanced_scale_row_key=advanced_scale_row_key,
        advanced_scale_quantity=advanced_scale_quantity,
        advanced_scale_unit=advanced_scale_unit,
        forecast_context=forecast_context,
        has_forecast_context=has_forecast_context,
        base_food_convert_quantity=base_food_convert_quantity,
        base_food_convert_unit=base_food_convert_unit,
        base_food_conversion_preview=base_food_conversion_preview,
        scaled_recipe_view=scaled_recipe_view,
        flattened_recipe_view=flattened_recipe_view,
        scaling_foundation=scaling_foundation,
        ingredient_display_warnings=ingredient_display_warnings,
        approved_units=APPROVED_UNITS,
        serving_size_units=STANDARD_UNITS,
        default_display_mode=DISPLAY_MODE_DEFAULT,
        default_unit_system=UNIT_SYSTEM_IMPERIAL,
    )


@app.route("/items/<int:item_id>")
def legacy_item_detail(item_id: int):
    return _redirect_with_query("item_detail", item_id=item_id)


@app.route("/recipe-collection/items/<int:item_id>/notes", methods=["POST"])
def item_post_note(item_id: int):
    item = get_item_detail(item_id)
    if item is None:
        return "Item not found.", 404

    current_user = get_current_mock_user(session)

    try:
        post_item_note(
            item=item,
            current_user=current_user,
            note_text=request.form.get("note_text", ""),
        )
        flash("Note posted.", "success")
    except ItemNoteError as exc:
        flash(str(exc), "error")

    return redirect(url_for("item_detail", item_id=item_id))


@app.route("/items/<int:item_id>/notes", methods=["POST"])
def legacy_item_post_note(item_id: int):
    return item_post_note(item_id)


@app.route("/recipes/<int:recipe_id>")
def recipe_detail_redirect(recipe_id: int):
    return redirect(url_for("item_detail", item_id=recipe_id))

if __name__ == "__main__":
    app.run(debug=True)
