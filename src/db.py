from pathlib import Path
import argparse
import shutil
import sqlite3
import time


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_DIR = PROJECT_ROOT / "database"
DB_PATH = DB_DIR / "recipe_collection.db"
MIGRATIONS_DIR = DB_DIR / "migrations"
SCHEMA_PATH = DB_DIR / "schema.sql"
MIGRATION_TABLE = "schema_migration"
AUTO_SEED_ENABLED = True
TEST_TMP_DIR = PROJECT_ROOT / ".test_tmp"
TEST_TMP_PREFIXES = ("run-", "debug-")


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


def load_seed_catalog_if_needed() -> bool:
    from seed_catalog import seed_database_if_empty, sync_seed_base_food_nutrition

    with get_connection() as conn:
        did_seed = seed_database_if_empty(conn)
        sync_seed_base_food_nutrition(conn)
        conn.commit()
        return did_seed


def initialize_database(seed: bool | None = None) -> None:
    """Create the database, apply pending SQL migrations, and optionally seed items."""
    if seed is None:
        seed = AUTO_SEED_ENABLED

    apply_migrations()
    if seed:
        load_seed_catalog_if_needed()
    from services.item_category_service import sync_item_categories

    sync_item_categories()


def garbage_collect_test_tmp(
    *,
    test_tmp_dir: Path | None = None,
    min_age_hours: float = 24,
    dry_run: bool = True,
) -> dict:
    """
    Remove stale isolated-test database directories from .test_tmp.

    Test fixtures remove their own run directories after normal completion, so this
    collector is intended for interrupted runs or leftover debug directories. It
    only considers direct children named run-* or debug-* and skips anything newer
    than the configured age threshold.
    """
    root = (test_tmp_dir or TEST_TMP_DIR).resolve()
    if min_age_hours < 0:
        raise ValueError("min_age_hours cannot be negative.")

    result = {
        "root": str(root),
        "dry_run": dry_run,
        "min_age_hours": min_age_hours,
        "scanned": 0,
        "eligible": 0,
        "deleted": 0,
        "skipped": [],
        "failed": [],
    }

    if not root.exists():
        return result
    if not root.is_dir():
        raise ValueError(f"Test temp path is not a directory: {root}")

    cutoff = time.time() - (min_age_hours * 60 * 60)
    for child in root.iterdir():
        if not child.is_dir():
            result["skipped"].append({"path": str(child), "reason": "not a directory"})
            continue

        result["scanned"] += 1
        if not child.name.startswith(TEST_TMP_PREFIXES):
            result["skipped"].append({"path": str(child), "reason": "unrecognized name"})
            continue

        try:
            modified_at = child.stat().st_mtime
        except OSError as exc:
            result["failed"].append({"path": str(child), "error": str(exc)})
            continue

        age_hours = (time.time() - modified_at) / 60 / 60
        if min_age_hours > 0 and modified_at > cutoff:
            result["skipped"].append(
                {
                    "path": str(child),
                    "reason": "too new",
                    "age_hours": round(age_hours, 3),
                }
            )
            continue

        result["eligible"] += 1
        if dry_run:
            continue

        try:
            shutil.rmtree(child)
            result["deleted"] += 1
        except OSError as exc:
            result["failed"].append({"path": str(child), "error": str(exc)})

    return result


def _main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the recipe collection database.")
    parser.add_argument(
        "--gc-test-tmp",
        action="store_true",
        help="Garbage collect stale .test_tmp/run-* and .test_tmp/debug-* directories instead of initializing the database.",
    )
    parser.add_argument(
        "--gc-min-age-hours",
        type=float,
        default=24,
        help="Minimum age in hours before a .test_tmp child directory is eligible for deletion.",
    )
    parser.add_argument(
        "--gc-apply",
        action="store_true",
        help="Actually delete eligible .test_tmp directories. Without this flag, garbage collection is a dry run.",
    )
    args = parser.parse_args()

    if args.gc_test_tmp:
        result = garbage_collect_test_tmp(
            min_age_hours=args.gc_min_age_hours,
            dry_run=not args.gc_apply,
        )
        action = "would delete" if result["dry_run"] else "deleted"
        print(
            f"Scanned {result['scanned']} test temp directories; "
            f"{action} {result['eligible'] if result['dry_run'] else result['deleted']}."
        )
        if result["failed"]:
            print(f"Failed: {len(result['failed'])}")
        return

    initialize_database()


if __name__ == "__main__":
    _main()
