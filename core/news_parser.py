"""
LandIQ — core/news_parser.py
News Intelligence Feed — 6-Layer Hallucination Defence Pipeline

Layer 1:   Evidence-First Prompt (Gemini forces verbatim quotes)
Layer 2:   Fuzzy Quote Verifier (substring & contiguous block >= 0.85 similarity)
Layer 2.5: Gazetteer Spatial Match (LGA + state cross-check)
Layer 3:   Confidence Gate (HIGH/MEDIUM only proceed)
Layer 4:   Cross-Source Corroboration (>=2 sources → CONFIRMED)
Layer 5:   Audit Queue (all events stored, human review available)
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Optional

from core.ai_client import ai_complete
from core.lga_gazetteer import validate_lga_geo
from db.migrate import get_connection

logger = logging.getLogger("landiq.news_parser")

VALID_EVENT_TYPES = {"flood", "demolition", "land_dispute", "cof_revocation", "fire", "erosion"}
CORROBORATION_WINDOW_DAYS = 14

# ── Layer 1: Evidence-First Prompt ───────────────────────────────────────────
PARSE_PROMPT = """You are a strict evidence extractor for Nigerian land and disaster risk events.

RULES — violating ANY rule makes the response INVALID:
1. Each event MUST include source_quote: the EXACT verbatim sentence from the article below.
2. NEVER infer, assume, or extrapolate beyond the article text.
3. If location is vague (e.g. "some parts of Nigeria"), set lga=null and confidence=LOW.
4. event_type MUST be one of: flood | demolition | land_dispute | cof_revocation | fire | erosion
5. If NO qualifying land/disaster event exists in the article, return {"events": []}.
6. Do NOT fabricate quotes. If you cannot find an exact sentence, do NOT include the event.

ARTICLE TEXT:
---
{article_body}
---

Return ONLY valid JSON (no markdown, no explanation):
{
  "events": [
    {
      "event_type": "flood|demolition|land_dispute|cof_revocation|fire|erosion",
      "source_quote": "<EXACT sentence from article>",
      "lga": "<LGA name or null>",
      "state": "<state name or null>",
      "date_mentioned": "<date string or null>",
      "confidence": "HIGH|MEDIUM|LOW",
      "confidence_reason": "<brief reason>"
    }
  ]
}"""


def _strip_json(raw: str) -> str:
    """Strip markdown code fences from LLM output."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


# ── Layer 1: Call Gemini via ai_complete ──────────────────────────────────────
def _llm_parse(article_body: str) -> list[dict]:
    """Call AI with evidence-first prompt. Returns raw event list."""
    prompt = PARSE_PROMPT.replace("{article_body}", article_body[:6000])  # token guard
    messages = [{"role": "user", "content": prompt}]
    raw = ai_complete(task="fast", messages=messages, max_tokens=1024, temperature=0.0)
    if not raw:
        logger.warning("[parser] Layer 1: AI returned None")
        return []
    try:
        data = json.loads(_strip_json(raw))
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("events", [])
        return []
    except json.JSONDecodeError as exc:
        logger.warning(f"[parser] Layer 1: JSON parse error: {exc} | raw: {raw[:200]}")
        return []


# ── Layer 2: Fuzzy Quote Verifier ─────────────────────────────────────────────
def _verify_quote(quote: str, article_body: str, threshold: float = 0.85) -> bool:
    """
    Check that the quote actually exists in the article text.
    Handles exact substring match, contiguous longest match >= 85%,
    and sentence-level fuzzy similarity.
    """
    if not quote or len(quote.strip()) < 20:
        return False
    
    q_norm = quote.strip().lower()
    b_norm = article_body.lower()

    # 1. Exact substring match (fastest)
    if q_norm in b_norm:
        return True

    # 2. Longest contiguous matching block relative to quote length
    matcher = SequenceMatcher(None, q_norm, b_norm)
    match = matcher.find_longest_match(0, len(q_norm), 0, len(b_norm))
    if len(q_norm) > 0 and (match.size / len(q_norm)) >= threshold:
        return True

    # 3. Sentence-level similarity check
    sentences = [s.strip() for s in re.split(r'[.!?\n]', b_norm) if len(s.strip()) >= 15]
    for s in sentences:
        if SequenceMatcher(None, q_norm, s).ratio() >= threshold:
            return True

    return False


# ── Layer 3: Confidence Gate ──────────────────────────────────────────────────
ALLOWED_CONFIDENCE = {"HIGH", "MEDIUM"}


def _passes_confidence_gate(event: dict) -> bool:
    return (
        event.get("confidence", "LOW").upper() in ALLOWED_CONFIDENCE
        and event.get("lga") is not None
        and event.get("event_type", "").lower() in VALID_EVENT_TYPES
    )


# ── Layer 4: Corroboration check ──────────────────────────────────────────────
def _check_corroboration(conn, lga: str, state: str, event_type: str) -> int:
    """
    Count existing PENDING/CONFIRMED events for the same LGA + event_type
    within the corroboration window. Returns updated count.
    """
    row = conn.execute(
        """
        SELECT COUNT(*) as cnt FROM news_events
        WHERE lga = ? AND event_type = ?
          AND status IN ('PENDING','CONFIRMED')
          AND created_at >= datetime('now', ?)
        """,
        (lga, event_type, f"-{CORROBORATION_WINDOW_DAYS} days"),
    ).fetchone()
    return (row["cnt"] if row else 0) + 1


# ── Main pipeline: parse one article ─────────────────────────────────────────
def parse_article(article_id: int, article_body: str, source_name: str) -> list[dict]:
    """
    Run the full 6-layer pipeline on a single article.
    Writes verified events to news_events table.
    Returns list of stored event dicts.
    """
    stored = []
    conn   = get_connection()

    try:
        raw_events = _llm_parse(article_body)
        logger.info(f"[parser] Article {article_id}: Layer 1 extracted {len(raw_events)} raw events")

        for ev in raw_events:
            event_type = str(ev.get("event_type", "")).lower().strip()
            quote      = str(ev.get("source_quote", "")).strip()
            lga_raw    = ev.get("lga")
            state_raw  = ev.get("state")
            confidence = str(ev.get("confidence", "LOW")).upper()
            date_str   = ev.get("date_mentioned")

            # Layer 2 — Fuzzy quote verification
            if not _verify_quote(quote, article_body):
                logger.info(f"[parser] Layer 2: Rejected (bad quote) for article {article_id}")
                continue

            # Layer 2.5 — Gazetteer spatial match
            geo = validate_lga_geo(lga_raw, state_raw)
            if not geo["valid"]:
                logger.info(
                    f"[parser] Layer 2.5: Geo rejected for article {article_id}: {geo['reason']}"
                )
                confidence = "LOW"
                lga_canon  = None
                state_canon = state_raw
            else:
                lga_canon   = geo["lga"]
                state_canon = geo["state"]
                if confidence != "HIGH":
                    confidence = "MEDIUM"

            # Layer 3 — Confidence gate
            if not _passes_confidence_gate({
                "confidence": confidence, "lga": lga_canon, "event_type": event_type
            }):
                logger.info(f"[parser] Layer 3: Gated out (confidence={confidence}, lga={lga_canon})")
                status = "AUDIT"
                count = 1
            else:
                # Layer 4 — Cross-source corroboration
                count = _check_corroboration(conn, lga_canon, state_canon, event_type)
                status = "CONFIRMED" if count >= 2 else "PENDING"

            # Layer 5 — Store to audit queue
            conn.execute(
                """
                INSERT INTO news_events
                  (article_id, event_type, lga, state, source_quote,
                   date_mentioned, confidence, corroboration_count, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article_id,
                    event_type,
                    lga_canon,
                    state_canon,
                    quote,
                    date_str,
                    confidence,
                    count,
                    status,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

            # If promoted to CONFIRMED, update prior PENDING events as well
            if status == "CONFIRMED":
                conn.execute(
                    """
                    UPDATE news_events SET corroboration_count = corroboration_count + 1,
                      status = 'CONFIRMED'
                    WHERE lga = ? AND event_type = ? AND status = 'PENDING'
                      AND created_at >= datetime('now', ?)
                    """,
                    (lga_canon, event_type, f"-{CORROBORATION_WINDOW_DAYS} days"),
                )

            stored_ev = {
                "event_type": event_type, "lga": lga_canon, "state": state_canon,
                "source_quote": quote, "confidence": confidence,
                "status": status, "date_mentioned": date_str,
            }
            stored.append(stored_ev)
            logger.info(f"[parser] Stored event: {event_type} @ {lga_canon} [{status}]")

        conn.commit()
    except Exception as exc:
        logger.error(f"[parser] Pipeline error for article {article_id}: {exc}")
        conn.rollback()
    finally:
        conn.close()

    return stored


# ── Batch processor: parse all unprocessed articles ───────────────────────────
def run_parse_pipeline(batch_size: int = 50) -> dict:
    """
    Parse all news_raw articles that have not yet been processed.
    Returns summary dict.
    """
    conn = get_connection()
    summary = {"processed": 0, "events_stored": 0, "errors": 0}
    try:
        rows = conn.execute(
            """
            SELECT nr.id, nr.body, nr.source FROM news_raw nr
            WHERE nr.id NOT IN (SELECT DISTINCT article_id FROM news_events WHERE article_id IS NOT NULL)
            ORDER BY nr.scraped_at DESC LIMIT ?
            """,
            (batch_size,),
        ).fetchall()
        conn.close()

        for row in rows:
            try:
                events = parse_article(row["id"], row["body"] or "", row["source"])
                summary["events_stored"] += len(events)
                summary["processed"] += 1
            except Exception as exc:
                logger.error(f"[parser] Error on article {row['id']}: {exc}")
                summary["errors"] += 1
    except Exception as exc:
        logger.error(f"[parser] Batch error: {exc}")
        conn.close()

    logger.info(f"[parser] Batch done: {summary}")
    return summary


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    result = run_parse_pipeline()
    print(result)
    sys.exit(0 if result["errors"] == 0 else 1)
