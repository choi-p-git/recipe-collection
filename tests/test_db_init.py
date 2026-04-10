import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_DIR = PROJECT_ROOT / "database"
DB_PATH = DB_DIR / "recipe_collection.db"

def test_db_exists():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type=?;", ("table",))
    tables = [row[0] for row in cursor.fetchall()]

    conn.close()

    print(tables)
    assert tables != []

if __name__ == "__main__":
    test_db_exists()