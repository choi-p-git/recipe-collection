from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from config.units import APPROVED_UNITS
from config.cooking_methods import APPROVED_COOKING_METHODS
from services.item_service import (
    DuplicateItemNameError,
    InvalidItemNameError,
    InvalidNumericValueError,
    normalize_item_name,
    create_base_food,
)
from services.recipe_service import (
    InvalidRecipePayloadError,
    create_recipe,
)
from queries.item_search import search_items

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
        "yield_quantity": request.form.get("yield_quantity", "").strip(),
        "yield_unit": request.form.get("yield_unit", "").strip(),
        "serving_size_quantity": request.form.get("serving_size_quantity", "").strip(),
        "serving_size_unit": request.form.get("serving_size_unit", "").strip(),
        "serving_count": request.form.get("serving_count", "").strip(),
        "notes": request.form.get("notes", "").strip(),
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/new/base-food", methods=["GET", "POST"])
def new_base_food():
    form_data = {
        "item_name": "",
        "yield_quantity": "",
        "yield_unit": "",
        "serving_size_quantity": "",
        "serving_size_unit": "",
        "serving_count": "",
        "notes": "",
    }

    if request.method == "POST":
        form_data = get_base_food_form_data()

        try:
            item_name = normalize_item_name(form_data["item_name"])
            form_data["item_name"] = item_name

            if not item_name:
                raise InvalidItemNameError("Item name cannot be empty or only whitespace.")

            yield_quantity = float(form_data["yield_quantity"])
            yield_unit = form_data["yield_unit"]

            if yield_quantity <= 0:
                raise InvalidNumericValueError("Yield quantity must be greater than 0.")

            serving_size_quantity = (
                float(form_data["serving_size_quantity"])
                if form_data["serving_size_quantity"]
                else None
            )

            if serving_size_quantity is not None and serving_size_quantity <= 0:
                raise InvalidNumericValueError("Serving size quantity must be greater than 0.")


            serving_size_unit = form_data["serving_size_unit"] or None

            serving_count = (
                float(form_data["serving_count"])
                if form_data["serving_count"]
                else None
            )

            if serving_count is not None and serving_count <= 0:
                raise InvalidNumericValueError("Serving count must be greater than 0.")

            notes = form_data["notes"] or None

            create_base_food(
                item_name=item_name,
                yield_quantity=yield_quantity,
                yield_unit=yield_unit,
                serving_size_quantity=serving_size_quantity,
                serving_size_unit=serving_size_unit,
                serving_count=serving_count,
                notes=notes,
            )

            flash(f"Base food '{item_name}' created successfully.", "success")
            return redirect(url_for("new_base_food"))

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

        except ValueError:
            flash("Please enter valid numeric values.", "error")

        except Exception as exc:
            flash(f"Unexpected error: {exc}", "error")

    return render_template(
        "new_base_food.html",
        approved_units=APPROVED_UNITS,
        form_data=form_data,
    )

@app.route("/new/recipe")
def new_recipe():
    return render_template(
        "new_recipe.html",
        approved_units=APPROVED_UNITS,
        approved_cooking_methods=APPROVED_COOKING_METHODS,
    )

@app.route("/api/items/search")
def api_search_items():
    query = request.args.get("q", "").strip()

    if not query:
        return jsonify([])

    results = search_items(query)
    return jsonify(results)

@app.route("/api/recipes", methods=["POST"])
def api_create_recipe():
    try:
        payload = request.get_json(silent=True)

        if not payload:
            return jsonify({"ok": False, "error": "Missing JSON payload."}), 400

        recipe_item_id = create_recipe(payload)

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

if __name__ == "__main__":
    app.run(debug=True)