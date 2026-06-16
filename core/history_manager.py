"""
LandIQ — core/history_manager.py
SQLite Persistence Layer

All reads/writes to the reports, sessions, exports, comparisons,
and lga_benchmarks tables go through this module.

Never re-runs the pipeline — exports always read from stored report_json.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.schemas import (
    ComparisonDelta,
    DeltaField,
    PersonaMode,
    ReportSchema,
)

logger = logging.getLogger("landiq.history")

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = ROOT_DIR / "db" / "landiq.db"


# =============================================================================
# CONNECTION
# =============================================================================

def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("PRAGMA foreign_keys=ON;")
    return c


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# SAVE REPORT
# =============================================================================

def save_report(
    report: ReportSchema,
    snapshot_path: str | None = None,
    snapshot_thumb_path: str | None = None,
    total_generation_ms: int | None = None,
    user_id: str = "anonymous",
) -> str:
    """
    Atomic write of a completed report to SQLite.
    Returns the report_id.
    """
    report_id  = report.meta.report_id
    report_json = report.model_dump_json()
    centroid_json = json.dumps({
        "lat": report.parcel_geometry.centroid.lat,
        "lng": report.parcel_geometry.centroid.lng,
    })

    conn = _conn()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO reports (
                report_id, user_id, generated_at,
                parcel_centroid, parcel_state, parcel_lga,
                traffic_light, overall_risk_score,
                report_json, snapshot_path, snapshot_thumb_path,
                persona_mode, pipeline_version,
                ollama_model_used, llm_timeout_fired,
                total_generation_ms
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                report_id,
                user_id,
                report.meta.generated_at,
                centroid_json,
                report.parcel_geometry.location_context.state,
                report.parcel_geometry.location_context.lga,
                report.summary.traffic_light.value,
                report.summary.overall_risk_score,
                report_json,
                snapshot_path,
                snapshot_thumb_path,
                report.persona_mode.value,
                report.pipeline_version,
                report.ollama_model_used,
                1 if report.llm_timeout_fired else 0,
                total_generation_ms,
            ),
        )
        # Save data sources
        _save_data_sources(conn, report_id, report)
        conn.commit()
        logger.info(f"[history] Saved report {report_id[:8]}")
        return report_id
    finally:
        conn.close()


def update_snapshot_path(report_id: str, new_snapshot_path: str) -> None:
    """Update the snapshot path for a report."""
    conn = _conn()
    try:
        conn.execute("UPDATE reports SET snapshot_path = ? WHERE report_id = ?", (new_snapshot_path, report_id))
        # Also update the sessions table just in case they share the ID
        conn.execute("UPDATE sessions SET snapshot_path = ? WHERE run_id = ?", (new_snapshot_path, report_id))
        conn.commit()
    finally:
        conn.close()


def _save_data_sources(conn: sqlite3.Connection, report_id: str, report: ReportSchema) -> None:
    """Write per-field data lineage to report_data_sources."""
    feed = report.feed_context or {}
    feed_meta = feed.get("feed_meta", {})
    adapter_id   = feed_meta.get("adapter_id", "offline_raster")
    source_label = feed_meta.get("source_name", "Offline Data")
    vintage      = feed_meta.get("data_vintage", "unknown")
    fallback     = feed_meta.get("fallback_used", False)

    # Delete existing data sources to prevent duplicates
    conn.execute("DELETE FROM report_data_sources WHERE report_id = ?", (report_id,))

    sources = [
        ("elevation_m",          "SRTM DEM (NASA)",        "2000–2024",  88.0),
        ("flood_risk",           "HydroSHEDS + SRTM",      "2022",       74.0),
        ("distance_to_river_m",  "HydroRIVERS",            "2022",       74.0),
        ("distance_to_road_m",   "OpenStreetMap",          "live-cache", 83.0),
        ("ndwi",                 "Sentinel-2 NDWI",        "2023-Q4",    69.0),
        ("ndvi",                 "Sentinel-2 NDVI",        "2023-Q4",    69.0),
        ("growth_potential",     "OSM + LGA Benchmarks",   "live-cache", 71.0),
        ("title_status",         source_label,              vintage,       0.0),  # 0 until NLIR live
    ]
    for field, label, vtg, conf in sources:
        conn.execute(
            """
            INSERT OR IGNORE INTO report_data_sources
              (source_id, report_id, field_name, source_adapter,
               source_label, data_vintage, confidence_score,
               live_feed_used, fallback_used)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                uuid.uuid4().hex, report_id, field, adapter_id,
                label, vtg, conf,
                0,  # live_feed_used=false for MVP
                1 if fallback else 0,
            ),
        )


# =============================================================================
# GET REPORT
# =============================================================================

def get_report(report_id: str) -> ReportSchema | None:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT report_json FROM reports WHERE report_id = ?", (report_id,)
        ).fetchone()
        if not row:
            return None
        return ReportSchema.model_validate_json(row["report_json"])
    finally:
        conn.close()


def get_report_row(report_id: str) -> dict | None:
    """Return the full DB row as a dict (includes snapshot paths, timings etc.)."""
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT * FROM reports WHERE report_id = ?", (report_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# =============================================================================
# HISTORY LIST
# =============================================================================

def get_history(
    user_id: str = "anonymous",
    limit: int = 50,
    offset: int = 0,
    state_filter: str | None = None,
    traffic_light_filter: str | None = None,
) -> list[dict]:
    """Return paginated report history for a user, newest first."""
    conn = _conn()
    try:
        where = ["user_id = ?"]
        params: list[Any] = [user_id]

        if state_filter:
            where.append("parcel_state = ?")
            params.append(state_filter)
        if traffic_light_filter:
            where.append("traffic_light = ?")
            params.append(traffic_light_filter.upper())

        where_clause = " AND ".join(where)
        rows = conn.execute(
            f"""
            SELECT report_id, generated_at, parcel_state, parcel_lga,
                   traffic_light, overall_risk_score, report_json,
                   snapshot_thumb_path, persona_mode
            FROM reports
            WHERE {where_clause}
            ORDER BY generated_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        ).fetchall()
        
        res = []
        for r in rows:
            d = dict(r)
            try:
                report_data = json.loads(d["report_json"])
                d["computed_area_ha"] = report_data.get("parcel_geometry", {}).get("computed_area_ha")
            except Exception:
                d["computed_area_ha"] = None
            d.pop("report_json", None)
            res.append(d)
        return res
    finally:
        conn.close()


# =============================================================================
# DATA SOURCES TRANSPARENCY
# =============================================================================

def get_data_sources(report_id: str) -> list[dict]:
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT * FROM report_data_sources WHERE report_id = ? GROUP BY field_name ORDER BY field_name",
            (report_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# =============================================================================
# FIND PRIOR REPORT (for comparison)
# =============================================================================

def find_prior_report(
    centroid_lat: float, centroid_lng: float, tolerance_m: float = 10.0
) -> dict | None:
    """
    Find the most recent previous report for a parcel within tolerance_m of the centroid.
    Uses Haversine approximation via SQLite — works for small distances.
    """
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT report_id, parcel_centroid, generated_at FROM reports ORDER BY generated_at DESC LIMIT 500"
        ).fetchall()
        import math
        R = 6_371_000.0
        best: dict | None = None

        for row in rows:
            try:
                c = json.loads(row["parcel_centroid"])
                lat2, lng2 = c["lat"], c["lng"]
                phi1 = math.radians(centroid_lat)
                phi2 = math.radians(lat2)
                dphi = math.radians(lat2 - centroid_lat)
                dlam = math.radians(lng2 - centroid_lng)
                a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
                dist = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                if dist <= tolerance_m:
                    best = dict(row)
                    break
            except Exception:
                continue
        return best
    finally:
        conn.close()


# =============================================================================
# COMPARISON ENGINE
# =============================================================================

def save_comparison(
    report_id_a: str,
    report_id_b: str,
    delta: ComparisonDelta,
) -> str:
    """Store a delta comparison between two reports. Returns comparison_id."""
    comparison_id = uuid.uuid4().hex
    conn = _conn()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO report_comparisons
              (comparison_id, report_id_a, report_id_b, parcel_match,
               delta_json, plain_english_delta, generated_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                comparison_id,
                report_id_a,
                report_id_b,
                1 if delta.parcel_match else 0,
                delta.model_dump_json(),
                delta.plain_english_delta,
                _iso(),
            ),
        )
        conn.commit()
        return comparison_id
    finally:
        conn.close()


def build_comparison_delta(
    report_id_a: str, report_id_b: str
) -> ComparisonDelta | None:
    """
    Compute a field-by-field delta between two reports.
    Returns None if either report is not found.
    """
    report_a = get_report(report_id_a)
    report_b = get_report(report_id_b)
    if not report_a or not report_b:
        return None

    fields: list[DeltaField] = []

    def _delta(field: str, val_a: Any, val_b: Any, better_if: str = "lower") -> None:
        if val_a == val_b:
            direction = "unchanged"
        elif val_a is None or val_b is None:
            direction = "unchanged"
        elif isinstance(val_a, str) and isinstance(val_b, str):
            ranks = {"GREEN": 1, "AMBER": 2, "RED": 3, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "SUITABLE": 1, "MARGINAL": 2, "UNSUITABLE": 3}
            if val_a.upper() in ranks and val_b.upper() in ranks:
                ra, rb = ranks[val_a.upper()], ranks[val_b.upper()]
                if ra == rb:
                    direction = "unchanged"
                elif better_if == "lower":
                    direction = "improved" if rb < ra else "worsened"
                else:
                    direction = "improved" if rb > ra else "worsened"
            else:
                direction = "changed"
        else:
            try:
                if better_if == "lower":
                    direction = "improved" if float(val_b) < float(val_a) else "worsened"
                else:
                    direction = "improved" if float(val_b) > float(val_a) else "worsened"
            except (TypeError, ValueError):
                direction = "changed"

        fields.append(DeltaField(
            field_name=field,
            value_a=val_a,
            value_b=val_b,
            direction=direction,
            plain_english=_describe_delta(field, val_a, val_b, direction),
        ))

    _delta("traffic_light",        report_a.summary.traffic_light.value,
                                   report_b.summary.traffic_light.value)
    _delta("overall_risk_score",   report_a.summary.overall_risk_score,
                                   report_b.summary.overall_risk_score, "lower")
    _delta("flood_risk",           report_a.flood_risk_metrics.level.value,
                                   report_b.flood_risk_metrics.level.value)
    _delta("terrain_suitability",  report_a.terrain_assessment.suitability,
                                   report_b.terrain_assessment.suitability)
    _delta("growth_potential",     report_a.growth_potential.level.value,
                                   report_b.growth_potential.level.value, "higher")
    _delta("elevation_m",          report_a.terrain_assessment.elevation_m,
                                   report_b.terrain_assessment.elevation_m, "higher")
    _delta("distance_to_river_m",  report_a.flood_risk_metrics.distance_to_nearest_river,
                                   report_b.flood_risk_metrics.distance_to_nearest_river, "higher")

    # Check centroid proximity
    lat_a = report_a.parcel_geometry.centroid.lat
    lng_a = report_a.parcel_geometry.centroid.lng
    lat_b = report_b.parcel_geometry.centroid.lat
    lng_b = report_b.parcel_geometry.centroid.lng
    import math
    dphi = math.radians(lat_b - lat_a)
    dlam = math.radians(lng_b - lng_a)
    dist = 6371000 * 2 * math.atan2(
        math.sqrt(math.sin(dphi/2)**2 + math.cos(math.radians(lat_a)) *
                  math.cos(math.radians(lat_b)) * math.sin(dlam/2)**2),
        math.sqrt(1 - math.sin(dphi/2)**2 - math.cos(math.radians(lat_a)) *
                  math.cos(math.radians(lat_b)) * math.sin(dlam/2)**2),
    )
    parcel_match = dist <= 10.0

    return ComparisonDelta(
        comparison_id=uuid.uuid4().hex,
        report_id_a=report_id_a,
        report_id_b=report_id_b,
        generated_at_a=report_a.meta.generated_at,
        generated_at_b=report_b.meta.generated_at,
        parcel_match=parcel_match,
        fields=fields,
        plain_english_delta=None,  # Filled by Ollama in future
    )


def _describe_delta(field: str, val_a: Any, val_b: Any, direction: str) -> str:
    if direction == "unchanged":
        return f"{field} remained the same ({val_a})."
    arrow = "improved" if direction == "improved" else "worsened"
    return f"{field} {arrow}: {val_a} → {val_b}."


# =============================================================================
# LOG EXPORT
# =============================================================================

def log_export(
    report_id: str,
    export_format: str,
    export_path: str,
    persona_mode: str,
    file_size_bytes: int | None = None,
) -> str:
    """Write an export audit log record. Returns export_id."""
    export_id = uuid.uuid4().hex
    conn = _conn()
    try:
        conn.execute(
            """
            INSERT INTO exports
              (export_id, report_id, export_format, export_path, persona_mode, exported_at, file_size_bytes)
            VALUES (?,?,?,?,?,?,?)
            """,
            (export_id, report_id, export_format, export_path, persona_mode, _iso(), file_size_bytes),
        )
        conn.commit()
        return export_id
    finally:
        conn.close()
