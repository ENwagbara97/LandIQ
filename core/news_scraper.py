"""
LandIQ — core/news_scraper.py
News Intelligence Feed — Layer 0: RSS Ingestion

Fetches articles from Nigerian newspaper RSS feeds, deduplicates by content hash,
and stores raw articles to the news_raw table in db/landiq.db.

Feeds configured in config/news_feeds.json (auto-created if missing).
"""
from __future__ import annotations

import hashlib
import logging
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from db.migrate import get_connection

logger = logging.getLogger("landiq.news_scraper")

# ── Default RSS feeds ─────────────────────────────────────────────────────────
DEFAULT_FEEDS = [
    {"name": "Punch Nigeria",       "url": "https://punchng.com/feed/"},
    {"name": "Guardian Nigeria",    "url": "https://guardian.ng/feed/"},
    {"name": "Vanguard Nigeria",    "url": "https://www.vanguardngr.com/feed/"},
    {"name": "Channels Television", "url": "https://www.channelstv.com/feed/"},
    {"name": "NAN Wire",            "url": "https://www.nan.ng/feed/"},
    {"name": "Thisday Live",        "url": "https://www.thisdaylive.com/feed/"},
]

FEED_CONFIG = Path(__file__).parent.parent / "config" / "news_feeds.json"


def _load_feeds() -> list[dict]:
    """Load feeds from config/news_feeds.json, falling back to defaults."""
    import json
    if FEED_CONFIG.exists():
        try:
            return json.loads(FEED_CONFIG.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"[scraper] Failed to load news_feeds.json: {exc}, using defaults")
    return DEFAULT_FEEDS


def _content_hash(title: str, pub_date: str) -> str:
    raw = f"{title.strip().lower()}|{pub_date.strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _parse_rss(xml_text: str, source_name: str) -> Generator[dict, None, None]:
    """Parse an RSS XML string and yield article dicts."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning(f"[scraper] XML parse error from {source_name}: {exc}")
        return

    ns = {"dc": "http://purl.org/dc/elements/1.1/"}
    channel = root.find("channel")
    if channel is None:
        return

    for item in channel.findall("item"):
        title   = (item.findtext("title") or "").strip()
        link    = (item.findtext("link")  or "").strip()
        pubdate = (item.findtext("pubDate") or item.findtext("dc:date", namespaces=ns) or "").strip()
        desc    = (item.findtext("description") or "").strip()
        content = (item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded") or desc).strip()

        if not title or not link:
            continue

        yield {
            "source":       source_name,
            "url":          link,
            "title":        title,
            "body":         content or desc,
            "published_at": pubdate,
            "content_hash": _content_hash(title, pubdate),
        }


def _fetch_url(url: str, timeout: int = 15) -> str | None:
    """Fetch URL with a simple user-agent header."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "LandIQ-NewsBot/1.0 (+https://landiq.app)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning(f"[scraper] Fetch failed for {url}: {exc}")
        return None


def scrape_all_feeds() -> dict:
    """
    Fetch all configured RSS feeds and store new articles to news_raw.
    Returns summary dict: {fetched, new, skipped, errors}.
    """
    feeds   = _load_feeds()
    conn    = get_connection()
    summary = {"fetched": 0, "new": 0, "skipped": 0, "errors": 0}

    try:
        for feed in feeds:
            name = feed.get("name", "Unknown")
            url  = feed.get("url", "")
            if not url:
                continue

            logger.info(f"[scraper] Fetching {name} — {url}")
            xml_text = _fetch_url(url)
            if xml_text is None:
                summary["errors"] += 1
                continue

            for article in _parse_rss(xml_text, name):
                summary["fetched"] += 1
                try:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO news_raw
                            (url, source, title, body, published_at, scraped_at, content_hash)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            article["url"],
                            article["source"],
                            article["title"],
                            article["body"],
                            article["published_at"],
                            datetime.now(timezone.utc).isoformat(),
                            article["content_hash"],
                        ),
                    )
                    if conn.execute("SELECT changes()").fetchone()[0]:
                        summary["new"] += 1
                    else:
                        summary["skipped"] += 1
                except Exception as exc:
                    logger.warning(f"[scraper] DB insert error: {exc}")
                    summary["errors"] += 1

            time.sleep(0.5)  # polite crawl delay

        conn.commit()
        logger.info(f"[scraper] Done: {summary}")
    except Exception as exc:
        logger.error(f"[scraper] Fatal error: {exc}")
        conn.rollback()
        raise
    finally:
        conn.close()

    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = scrape_all_feeds()
    print(result)
