from pathlib import Path
import shutil
import sys
import uuid

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = PROJECT_ROOT / "src"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


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
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def app_client(isolated_db):
    from app import app

    app.config["TESTING"] = True

    with app.test_client() as client:
        yield client
