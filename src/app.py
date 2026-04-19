from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

from config.units import APPROVED_UNITS
from config.cooking_methods import APPROVED_COOKING_METHODS
from config.menu_builder import CONCEPT_OPTIONS, DAY_OF_WEEK_OPTIONS, MEAL_PERIOD_OPTIONS
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
    InvalidMenuPayloadError,
    InvalidMenuDeleteError,
    InvalidMenuSlotAssignmentError,
    create_menu,
    delete_menu,
    replace_menu_slot_items,
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
    can_edit_items,
    can_manage_official_measurements,
    can_view_advanced_workflow,
)
from services.recipe_flattening_service import build_flattened_recipe_view
from services.recipe_scaling_service import build_recipe_scaling_foundation, build_scaled_recipe_view
from services.unit_display_service import (
    DISPLAY_MODE_DEFAULT,
    UNIT_SYSTEM_IMPERIAL,
    apply_display_preferences_to_rows,
    normalize_display_mode,
    normalize_unit_system,
)
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
from queries.my_menus import get_my_menus
from queries.menu_slot_detail import get_menu_slot_detail
from queries.my_recipes import get_my_recipes
from queries.workflow_items import get_workflow_portal_items

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEBPAGE_DIR = PROJECT_ROOT / "webpage"
TEMPLATE_DIR = WEBPAGE_DIR / "templates"
STATIC_DIR = WEBPAGE_DIR / "static"


app = Flask(
    __name__,
    template_folder=str(TEMPLATE_DIR),
    static_folder=str(STATIC_DIR),
)

app.secret_key = "dev-secret-key"


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


@app.context_processor
def inject_mock_auth_context():
    current_user = get_current_mock_user(session)
    return {
        "current_mock_user": current_user,
        "current_mock_user_role_label": ROLE_LABELS.get(current_user["role"], current_user["role"]),
        "current_user_preferences": current_user.get("preferences", {}),
        "available_workflow_portals": get_available_workflow_portals(current_user["role"]),
        "notification_count": get_notification_count(current_user),
    }


@app.route("/new/base-food", methods=["GET", "POST"])
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
        approved_units=APPROVED_UNITS,
        can_manage_official_measurements_for_current_user=False,
    )

@app.route("/new/recipe")
def new_recipe():
    current_user = get_current_mock_user(session)
    return render_template(
        "new_recipe.html",
        approved_units=APPROVED_UNITS,
        approved_cooking_methods=APPROVED_COOKING_METHODS,
        editor_mode="create",
        recipe=None,
        can_manage_official_measurements_for_current_user=can_manage_official_measurements(
            current_user["role"]
        ),
    )


@app.route("/menus/new", methods=["GET", "POST"])
def new_menu():
    form_data = {
        "menu_name": "",
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
                service_days=form_data["service_days"],
                meal_periods=form_data["meal_periods"],
                concepts=form_data["concepts"],
                menu_length_weeks=form_data["menu_length_weeks"],
                allowed_service_days=[option["value"] for option in DAY_OF_WEEK_OPTIONS],
                allowed_meal_periods=[option["value"] for option in MEAL_PERIOD_OPTIONS],
                allowed_concepts=[option["value"] for option in CONCEPT_OPTIONS],
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
    )


@app.route("/menus")
def my_menus():
    current_user = get_current_mock_user(session)
    page_data = get_my_menus(current_user["user_id"])
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
    selected_week = request.args.get("week", "1").strip()
    try:
        selected_week_number = int(selected_week)
    except ValueError:
        selected_week_number = 1

    if selected_week_number not in week_numbers:
        selected_week_number = 1

    week_slots = [slot for slot in menu["slots"] if slot["week_number"] == selected_week_number]

    return render_template(
        "menu_detail.html",
        menu=menu,
        week_numbers=week_numbers,
        selected_week_number=selected_week_number,
        week_slots=week_slots,
        day_options=DAY_OF_WEEK_OPTIONS,
        meal_period_options=MEAL_PERIOD_OPTIONS,
    )


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


@app.route("/menus/<int:menu_id>/slots/<int:menu_slot_id>/assign", methods=["GET", "POST"])
def menu_slot_assign(menu_id: int, menu_slot_id: int):
    search_term = request.values.get("q", "").strip()
    item_type = request.values.get("item_type", "").strip()

    if request.method == "POST":
        try:
            replace_menu_slot_items(
                menu_slot_id=menu_slot_id,
                selected_item_ids=request.form.getlist("selected_item_ids"),
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


@app.route("/my-recipes")
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


@app.route("/collection")
def live_collection():
    page_data = get_live_collection_page(
        search_term=request.args.get("q", ""),
        item_type=request.args.get("item_type", ""),
        sort=request.args.get("sort", "updated_desc"),
        offset=request.args.get("offset", 0),
    )
    return render_template("collection.html", page_data=page_data)


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


@app.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
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
            approved_units=APPROVED_UNITS,
            can_manage_official_measurements_for_current_user=can_manage_measurements,
        )

    return render_template(
        "new_recipe.html",
        approved_units=APPROVED_UNITS,
        approved_cooking_methods=APPROVED_COOKING_METHODS,
        editor_mode="edit",
        recipe=item,
        submit_url=url_for("api_update_recipe", recipe_id=item_id),
        can_manage_official_measurements_for_current_user=can_manage_official_measurements(
            current_user["role"]
        ),
    )

@app.route("/api/items/search")
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

@app.route("/api/recipes", methods=["POST"])
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


@app.route("/api/recipes/<int:recipe_id>", methods=["PUT"])
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
    
@app.route("/items/<int:item_id>")
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
    base_food_convert_quantity = request.args.get("convert_quantity", "").strip()
    base_food_convert_unit = request.args.get("convert_unit", "").strip()
    scaled_recipe_view = (
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
        if scaled_recipe_view is not None:
            processed_scaled = apply_display_preferences_to_rows(
                rows=scaled_recipe_view.get("rows", []),
                row_mode=scaled_recipe_view.get("row_mode", "hierarchical"),
                display_mode=display_mode,
                unit_system=unit_system,
            )
            scaled_recipe_view["rows"] = processed_scaled["rows"]
            ingredient_display_warnings = processed_scaled["warnings"]
        elif ingredient_view_mode == "flattened" and flattened_recipe_view is not None:
            processed_flattened = apply_display_preferences_to_rows(
                rows=flattened_recipe_view["rows"],
                row_mode="flattened",
                display_mode=display_mode,
                unit_system=unit_system,
            )
            flattened_recipe_view["rows"] = processed_flattened["rows"]
            ingredient_display_warnings = processed_flattened["warnings"]
        else:
            processed_hierarchical = apply_display_preferences_to_rows(
                rows=item["ingredients"],
                row_mode="hierarchical",
                display_mode=display_mode,
                unit_system=unit_system,
            )
            item["ingredients"] = processed_hierarchical["rows"]
            ingredient_display_warnings = processed_hierarchical["warnings"]

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
        base_food_convert_quantity=base_food_convert_quantity,
        base_food_convert_unit=base_food_convert_unit,
        base_food_conversion_preview=base_food_conversion_preview,
        scaled_recipe_view=scaled_recipe_view,
        flattened_recipe_view=flattened_recipe_view,
        scaling_foundation=scaling_foundation,
        ingredient_display_warnings=ingredient_display_warnings,
        approved_units=APPROVED_UNITS,
        default_display_mode=DISPLAY_MODE_DEFAULT,
        default_unit_system=UNIT_SYSTEM_IMPERIAL,
    )


@app.route("/items/<int:item_id>/notes", methods=["POST"])
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


@app.route("/recipes/<int:recipe_id>")
def recipe_detail_redirect(recipe_id: int):
    return redirect(url_for("item_detail", item_id=recipe_id))

if __name__ == "__main__":
    app.run(debug=True)
