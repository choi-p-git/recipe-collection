from pathlib import Path
import sqlite3


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_DIR = PROJECT_ROOT / "database"
DB_PATH = DB_DIR / "recipe_collection.db"
MIGRATIONS_DIR = DB_DIR / "migrations"
SCHEMA_PATH = DB_DIR / "schema.sql"
MIGRATION_TABLE = "schema_migration"


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def get_migration_files() -> list[Path]:
    if not MIGRATIONS_DIR.exists():
        raise FileNotFoundError(f"Migrations directory not found: {MIGRATIONS_DIR}")

    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def _ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE} (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )


def _get_applied_migrations(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(f"SELECT version FROM {MIGRATION_TABLE}").fetchall()
    return {row[0] for row in rows}


def _has_existing_app_tables(conn: sqlite3.Connection) -> bool:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
          AND name != ?
        """,
        (MIGRATION_TABLE,),
    ).fetchall()
    return bool(rows)


def _stamp_existing_database(conn: sqlite3.Connection, migration_files: list[Path]) -> None:
    if not migration_files:
        return

    conn.executemany(
        f"INSERT OR IGNORE INTO {MIGRATION_TABLE} (version, applied_at) VALUES (?, datetime('now'))",
        [(migration_file.name,) for migration_file in migration_files],
    )


def apply_migrations() -> None:
    migration_files = get_migration_files()

    DB_DIR.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        _ensure_migration_table(conn)

        applied_migrations = _get_applied_migrations(conn)
        if not applied_migrations and _has_existing_app_tables(conn):
            _stamp_existing_database(conn, migration_files)
            applied_migrations = _get_applied_migrations(conn)

        for migration_file in migration_files:
            if migration_file.name in applied_migrations:
                continue

            migration_sql = migration_file.read_text(encoding="utf-8")
            conn.executescript(migration_sql)
            conn.execute(
                f"INSERT INTO {MIGRATION_TABLE} (version, applied_at) VALUES (?, datetime('now'))",
                (migration_file.name,),
            )

        conn.commit()


def initialize_database() -> None:
    """Create the database and apply pending SQL migrations."""
    apply_migrations()

if __name__ == "__main__":
    initialize_database()
