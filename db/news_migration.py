"""
LandIQ — db/news_migration.py
Idempotent migration: adds news_raw and news_events tables.

Called from migrate.py _apply_news_tables() during startup.
Safe to re-run — uses IF NOT EXISTS throughout.
"""
import sqlite3

NEWS_RAW_SQL = """
CREATE TABLE IF NOT EXISTS news_raw (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    url          TEXT    UNIQUE NOT NULL,
    source       TEXT    NOT NULL,
    title        TEXT    NOT NULL,
    body         TEXT    NOT NULL DEFAULT '',
    published_at TEXT,
    scraped_at   TEXT    NOT NULL,
    content_hash TEXT    UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_news_raw_scraped ON news_raw(scraped_at);
CREATE INDEX IF NOT EXISTS idx_news_raw_source  ON news_raw(source);
"""

NEWS_EVENTS_SQL = """
CREATE TABLE IF NOT EXISTS news_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id          INTEGER REFERENCES news_raw(id),
    event_type          TEXT    NOT NULL,
    lga                 TEXT,
    state               TEXT,
    source_quote        TEXT    NOT NULL,
    date_mentioned      TEXT,
    confidence          TEXT    NOT NULL,
    corroboration_count INTEGER NOT NULL DEFAULT 1,
    status              TEXT    NOT NULL DEFAULT 'PENDING',
    dismissed_reason    TEXT,
    created_at          TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_news_events_lga    ON news_events(lga, state, status);
CREATE INDEX IF NOT EXISTS idx_news_events_status ON news_events(status, created_at);
"""


def apply_news_tables(conn: sqlite3.Connection) -> None:
    """Create news_raw and news_events tables if they do not exist."""
    try:
        conn.executescript(NEWS_RAW_SQL)
        conn.executescript(NEWS_EVENTS_SQL)
        conn.commit()
        print("[migrate] [OK] news_raw and news_events tables ready")
    except sqlite3.Error as exc:
        print(f"[migrate] [WARN] News table migration: {exc}")
