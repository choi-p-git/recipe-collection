from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

from config.units import APPROVED_UNITS
from config.cooking_methods import APPROVED_COOKING_METHODS
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
)
from services.item_note_service import (
    ItemNoteError,
    acknowledge_item_notes_for_viewer,
    get_item_notes,
    post_item_note,
    resolve_note_recipient,
)
from services.notification_service import (
    acknowledge_item_notifications_for_viewer,
    get_notification_count,
    get_notification_rows,
)
from services.policy_service import can_edit_item, can_edit_items, can_view_advanced_workflow
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
    }


@app.route("/")
def index():
    return render_template("index.html")


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
        "available_workflow_portals": get_available_workflow_portals(current_user["role"]),
        "notification_count": get_notification_count(current_user),
    }


@app.route("/new/base-food", methods=["GET", "POST"])
def new_base_food():
    form_data = {
        "item_name": "",
        "notes": "",
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
    )

@app.route("/new/recipe")
def new_recipe():
    return render_template(
        "new_recipe.html",
        approved_units=APPROVED_UNITS,
        approved_cooking_methods=APPROVED_COOKING_METHODS,
        editor_mode="create",
        recipe=None,
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
        }

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

        return render_template(
            "new_base_food.html",
            form_data=form_data,
            form_mode="edit",
            item_id=item_id,
        )

    return render_template(
        "new_recipe.html",
        approved_units=APPROVED_UNITS,
        approved_cooking_methods=APPROVED_COOKING_METHODS,
        editor_mode="edit",
        recipe=item,
        submit_url=url_for("api_update_recipe", recipe_id=item_id),
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
    advanced_workflow_enabled = (
        item["status"] == "live"
        and can_use_advanced_workflow
        and request.args.get("workflow_view", "").strip() == "advanced"
    )
    show_workflow_panels = item["status"] != "live" or advanced_workflow_enabled
    note_recipient = (
        resolve_note_recipient(item, current_user)
        if show_workflow_panels
        else None
    )

    return render_template(
        "item_detail.html",
        item=item,
        item_notes=get_item_notes(item_id),
        item_events=get_item_events(item_id),
        note_recipient=note_recipient,
        can_edit_item_for_current_user=editable,
        can_use_advanced_workflow=can_use_advanced_workflow,
        advanced_workflow_enabled=advanced_workflow_enabled,
        show_workflow_panels=show_workflow_panels,
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
