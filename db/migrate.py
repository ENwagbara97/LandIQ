"""
LandIQ — db/migrate.py
Idempotent database migration runner.

Runs on every application startup. Safe to re-run on an existing database.
Uses CREATE TABLE IF NOT EXISTS — never drops or modifies existing data.

Usage:
    python db/migrate.py
    OR imported and called by the FastAPI startup event.
"""

import sqlite3
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT_DIR    = Path(__file__).resolve().parent.parent
SCHEMA_FILE = Path(__file__).resolve().parent / "db_schema.sql"
DB_PATH     = ROOT_DIR / "db" / "landiq.db"


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Return a SQLite connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _apply_via_columns(conn: sqlite3.Connection) -> None:
    """
    Idempotently add VIA columns to the existing reports table.
    SQLite does not support ALTER TABLE ... ADD COLUMN IF NOT EXISTS,
    so we catch OperationalError (column already exists) silently.
    """
    via_columns = [
        ("via_result_json",   "TEXT"),
        ("via_completed_at",  "TEXT"),
        ("via_status",        "TEXT DEFAULT 'pending'"),
    ]
    for col_name, col_def in via_columns:
        try:
            conn.execute(f"ALTER TABLE reports ADD COLUMN {col_name} {col_def};")
            conn.commit()
            print(f"[migrate] [OK] Added column reports.{col_name}")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" in str(exc).lower():
                pass  # Column already exists — safe to ignore
            else:
                raise


def _apply_nav_columns(conn: sqlite3.Connection) -> None:
    """
    Idempotently add Navigation columns to the existing reports table.
    """
    nav_columns = [
        ("arrived_at",         "TEXT"),
        ("arrival_distance_m", "REAL"),
    ]
    for col_name, col_def in nav_columns:
        try:
            conn.execute(f"ALTER TABLE reports ADD COLUMN {col_name} {col_def};")
            conn.commit()
            print(f"[migrate] [OK] Added column reports.{col_name}")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" in str(exc).lower():
                pass  # Column already exists — safe to ignore
            else:
                raise


def _apply_pdf_columns(conn: sqlite3.Connection) -> None:
    """
    Idempotently add PDF generation columns to the existing reports table.
    """
    pdf_columns = [
        ("pdf_ready", "BOOLEAN DEFAULT FALSE"),
        ("pdf_path",  "TEXT"),
    ]
    for col_name, col_def in pdf_columns:
        try:
            conn.execute(f"ALTER TABLE reports ADD COLUMN {col_name} {col_def};")
            conn.commit()
            print(f"[migrate] [OK] Added column reports.{col_name}")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" in str(exc).lower():
                pass  # Column already exists — safe to ignore
            else:
                raise


def run_migrations(db_path: Path = DB_PATH) -> None:
    """
    Execute the full schema SQL against the target database.
    Idempotent — IF NOT EXISTS guards prevent re-creation of existing tables.
    """
    if not SCHEMA_FILE.exists():
        raise FileNotFoundError(
            f"Schema file not found: {SCHEMA_FILE}\n"
            "Ensure db/db_schema.sql is present before running migrations."
        )

    # Ensure the db directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")

    conn = get_connection(db_path)
    try:
        # executescript commits any pending transaction and runs multiple statements
        conn.executescript(schema_sql)
        conn.commit()
        print(f"[migrate] [OK] Schema applied to: {db_path}")
        _print_table_list(conn)
        # Apply column-level migrations that can't be handled by executescript
        _apply_via_columns(conn)
        _apply_nav_columns(conn)
        _apply_pdf_columns(conn)
    except sqlite3.Error as exc:
        conn.rollback()
        print(f"[migrate] [ERROR] Migration failed: {exc}", file=sys.stderr)
        raise
    finally:
        conn.close()


def _print_table_list(conn: sqlite3.Connection) -> None:
    """Print all tables present in the database for confirmation."""
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
    ).fetchall()
    names = [row["name"] for row in tables]
    print(f"[migrate] Tables present: {', '.join(names)}")


def check_schema_version(conn: sqlite3.Connection) -> str | None:
    """Return the latest applied schema version string, or None if not tracked."""
    try:
        row = conn.execute(
            "SELECT version FROM schema_versions ORDER BY version_id DESC LIMIT 1;"
        ).fetchone()
        return row["version"] if row else None
    except sqlite3.OperationalError:
        return None


if __name__ == "__main__":
    run_migrations()
