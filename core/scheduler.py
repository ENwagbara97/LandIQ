"""
LandIQ — core/scheduler.py
Background scheduler for the News Intelligence Feed.

Runs the scrape + parse pipeline daily at 02:00 WAT (Africa/Lagos).
Started as a background thread from main.py lifespan handler.

Usage (from main.py):
    from core.scheduler import start_news_scheduler
    start_news_scheduler()
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger("landiq.scheduler")

_scheduler_thread: threading.Thread | None = None
_stop_event = threading.Event()


def _run_news_pipeline_safe() -> None:
    """Run scrape + parse with full error isolation."""
    try:
        from core.news_scraper import scrape_all_feeds
        from core.news_parser  import run_parse_pipeline

        logger.info("[scheduler] Starting daily news scrape...")
        scrape_result = scrape_all_feeds()
        logger.info(f"[scheduler] Scrape done: {scrape_result}")

        logger.info("[scheduler] Starting news parse pipeline...")
        parse_result = run_parse_pipeline(batch_size=100)
        logger.info(f"[scheduler] Parse done: {parse_result}")
    except Exception as exc:
        logger.error(f"[scheduler] Pipeline error: {exc}", exc_info=True)


def _scheduler_loop() -> None:
    """Run the pipeline daily at 02:00 WAT. Checks every 60s."""
    last_run_date: str | None = None
    logger.info("[scheduler] News scheduler thread started")

    while not _stop_event.is_set():
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        # Run at 02:00 WAT (UTC+1 — approximate via local server time)
        if now.hour == 2 and last_run_date != today:
            last_run_date = today
            logger.info(f"[scheduler] Triggering daily news pipeline for {today}")
            _run_news_pipeline_safe()

        _stop_event.wait(timeout=60)  # check every minute

    logger.info("[scheduler] News scheduler thread stopped")


def start_news_scheduler() -> None:
    """Start the background scheduler thread. Safe to call multiple times."""
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        logger.info("[scheduler] Scheduler already running")
        return
    _stop_event.clear()
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop,
        name="LandIQ-NewsScheduler",
        daemon=True,
    )
    _scheduler_thread.start()
    logger.info("[scheduler] News scheduler started (daily at 02:00 WAT)")


def stop_news_scheduler() -> None:
    """Signal the scheduler to stop gracefully."""
    _stop_event.set()
    if _scheduler_thread:
        _scheduler_thread.join(timeout=5)
    logger.info("[scheduler] News scheduler stopped")


def trigger_now() -> dict:
    """Manually trigger one run of the pipeline (for admin/testing)."""
    logger.info("[scheduler] Manual trigger requested")
    thread = threading.Thread(target=_run_news_pipeline_safe, name="LandIQ-NewsManual", daemon=True)
    thread.start()
    return {"triggered": True, "message": "Pipeline started in background"}
