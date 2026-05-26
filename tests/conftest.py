from pathlib import Path
import gc
import shutil
import sys
import time
import uuid

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


FILE_MARKERS = {
    "test_db_init.py": {"module_database", "relation_persistence"},
    "test_db_seed.py": {"module_database", "relation_persistence"},
    "test_dev_automation.py": {"module_menu", "module_forecast", "module_production", "module_inventory", "relation_service"},
    "test_item_notes.py": {"module_item", "module_workflow", "relation_service"},
    "test_item_service.py": {"module_item", "relation_service"},
    "test_inventory_service.py": {"module_inventory", "relation_service"},
    "test_menu_forecast_service.py": {"module_forecast", "relation_service"},
    "test_menu_service.py": {"module_menu", "relation_service"},
    "test_my_recipes.py": {"module_recipe", "module_item", "relation_service"},
    "test_policy_service.py": {"module_workflow", "relation_service"},
    "test_production_record_service.py": {"module_production", "relation_service"},
    "test_queries.py": {"module_search", "relation_service"},
    "test_recipe_flattening_service.py": {"module_recipe", "relation_service"},
    "test_recipe_instruction_codec.py": {"module_recipe", "relation_unit"},
    "test_recipe_scaling_service.py": {"module_recipe", "relation_service"},
    "test_recipe_service.py": {"module_recipe", "relation_service"},
    "test_workflow.py": {"module_workflow", "relation_service"},
}

ROUTE_MARKER_PATTERNS = [
    (("production_record",), {"module_production", "module_forecast"}),
    (("inventory",), {"module_inventory"}),
    (("menu_forecast", "forecast", "advanced_case"), {"module_forecast"}),
    (
        (
            "menu_",
            "my_menus",
            "bulk",
            "slot",
            "copy",
            "paste",
            "clear_menu",
            "delete_menu",
            "edit_menu",
            "new_menu",
        ),
        {"module_menu"},
    ),
    (("api_search", "live_collection", "search_items"), {"module_search"}),
    (
        (
            "workflow",
            "reviewer",
            "dietitian",
            "admin_",
            "send_back",
            "return_to_submitter",
            "transition",
            "portal",
            "go_live",
        ),
        {"module_workflow"},
    ),
    (("notification", "note"), {"module_workflow", "module_item"}),
    (
        (
            "recipe",
            "flattened",
            "scaling",
            "scale_",
            "yield",
            "my_recipes",
        ),
        {"module_recipe"},
    ),
    (
        (
            "base_food",
            "item_detail",
            "edit_item",
            "live_item",
            "new_base_food",
        ),
        {"module_item"},
    ),
    (("login", "preferences"), {"module_auth"}),
]


def _normalize_scope_option(raw_value: str | None, prefix: str) -> set[str]:
    if not raw_value:
        return set()

    selected = set()
    for value in raw_value.split(","):
        value = value.strip().replace("-", "_")
        if not value:
            continue

        selected.add(value if value.startswith(prefix) else f"{prefix}{value}")
    return selected


def _marker_names_for_item(item) -> set[str]:
    path = Path(str(item.fspath))
    markers = set(FILE_MARKERS.get(path.name, set()))

    if path.name == "test_routes.py":
        markers.add("relation_api")
        test_name = item.name.lower()
        for patterns, pattern_markers in ROUTE_MARKER_PATTERNS:
            if any(pattern in test_name for pattern in patterns):
                markers.update(pattern_markers)
                break

        if not any(marker.startswith("module_") for marker in markers):
            markers.add("module_routes")

    return markers


def pytest_addoption(parser):
    parser.addoption(
        "--module-scope",
        action="store",
        default="",
        help="Comma-separated module selectors such as menu,recipe,forecast.",
    )
    parser.addoption(
        "--relation-scope",
        action="store",
        default="",
        help="Comma-separated relation selectors: unit,service,api,persistence.",
    )


def pytest_collection_modifyitems(config, items):
    selected_modules = _normalize_scope_option(config.getoption("--module-scope"), "module_")
    selected_relations = _normalize_scope_option(config.getoption("--relation-scope"), "relation_")
    kept = []
    deselected = []

    for item in items:
        marker_names = _marker_names_for_item(item)
        for marker_name in marker_names:
            item.add_marker(getattr(pytest.mark, marker_name))

        module_match = not selected_modules or bool(marker_names & selected_modules)
        relation_match = not selected_relations or bool(marker_names & selected_relations)
        if module_match and relation_match:
            kept.append(item)
        else:
            deselected.append(item)

    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = kept


def _remove_tree(path: Path, *, attempts: int = 8, delay_seconds: float = 0.1) -> None:
    last_error = None
    for attempt in range(attempts):
        if not path.exists():
            return

        gc.collect()
        try:
            shutil.rmtree(path, ignore_errors=False)
        except OSError as exc:
            last_error = exc

        if not path.exists():
            return

        if attempt < attempts - 1:
            time.sleep(delay_seconds)

    if path.exists():
        if last_error:
            raise last_error
        shutil.rmtree(path, ignore_errors=False)


def _remove_pycache_dirs() -> None:
    roots = [
        PROJECT_ROOT / "__pycache__",
        PROJECT_ROOT / "tests",
        SRC_PATH,
    ]
    seen = set()
    for root in roots:
        if not root.exists():
            continue

        pycache_dirs = [root] if root.name == "__pycache__" else root.rglob("__pycache__")
        for pycache_dir in pycache_dirs:
            resolved = pycache_dir.resolve()
            if resolved in seen:
                continue

            seen.add(resolved)
            try:
                _remove_tree(resolved)
            except OSError:
                pass


def _remove_generated_test_artifacts() -> None:
    import db

    db.garbage_collect_test_tmp(min_age_hours=0, dry_run=False)
    try:
        _remove_tree(PROJECT_ROOT / ".pytest_cache")
    except OSError:
        pass
    _remove_pycache_dirs()


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    _remove_generated_test_artifacts()


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config):
    _remove_generated_test_artifacts()


@pytest.fixture
def isolated_db(monkeypatch):
    import db

    temp_dir = PROJECT_ROOT / ".test_tmp" / f"run-{uuid.uuid4().hex}"
    db_dir = temp_dir / "database"
    db_path = db_dir / "test_recipe_collection.db"

    monkeypatch.setattr(db, "DB_DIR", db_dir)
    monkeypatch.setattr(db, "DB_PATH", db_path)
    monkeypatch.setattr(db, "MIGRATIONS_DIR", PROJECT_ROOT / "database" / "migrations")
    monkeypatch.setattr(db, "SCHEMA_PATH", PROJECT_ROOT / "database" / "schema.sql")
    monkeypatch.setattr(db, "AUTO_SEED_ENABLED", False)

    db.initialize_database()
    try:
        yield db_path
    finally:
        _remove_tree(temp_dir)


@pytest.fixture
def app_client(isolated_db):
    from app import app

    app.config["TESTING"] = True

    try:
        with app.test_client() as client:
            yield client
    finally:
        gc.collect()
