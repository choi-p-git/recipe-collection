from pathlib import Path
import sqlite3


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_DIR = PROJECT_ROOT / "database"
DB_PATH = DB_DIR / "recipe_collection.db"
SCHEMA_PATH = DB_DIR / "schema.sql"


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def initialize_database() -> None:
    """Create the database and apply the schema file."""
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema file not found: {SCHEMA_PATH}")

    DB_DIR.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        conn.executescript(schema_sql)
        conn.commit()

if __name__ == "__main__":
    initialize_database()