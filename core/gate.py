"""
LandIQ — core/gate.py
Step 0: Sanitization Filter & User Confirmation Gate

This is the most critical component in the entire system.
Analysis is COMPLETELY FROZEN until this gate emits a logged
boolean confirmed=true. Zero exceptions, no partial bypasses.

Architecture note:
  The gate is event-driven, not blocking. It works as follows:
    1. Pipeline calls gate.initiate(coord_output) → returns preview_payload
       (centroid, polygon, CRS dialogs, map HTML)
    2. FastAPI serves this to the frontend
    3. Frontend renders Leaflet map + dialogs
    4. User resolves all dialogs and clicks YES
    5. Frontend POSTs to /api/confirm/{run_id}
    6. gate.confirm(run_id) → logs confirmed=True → triggers snapshot → unlocks pipeline
    7. gate.is_confirmed(run_id) → polled by pipeline before Step 1 begins

Security:
  Input Sanitization Filter runs FIRST before any parsing.
  Detects: prompt injection, override syntax, destructive keywords.
  On detection → EXECUTION_HAZARD, pipeline fully aborted.
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.schemas import (
    CoordExtractOutput,
    CRSName,
    MCPErrorResponse,
    PipelineStage,
    SessionState,
    PersonaMode,
)

# ── Database path ────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = ROOT_DIR / "db" / "landiq.db"

# =============================================================================
# SECTION 1 — INPUT SANITIZATION FILTER
# Runs before any parsing. Detects injection attempts.
# =============================================================================

# Prompt injection patterns — covers common jailbreak and override attempts
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:a|an|the)\s+\w+", re.IGNORECASE),
    re.compile(r"system\s*prompt\s*[:=]", re.IGNORECASE),
    re.compile(r"<\s*(?:system|user|assistant)\s*>", re.IGNORECASE),
    re.compile(r"\\n\s*###\s*(?:system|instruction|prompt)", re.IGNORECASE),
    re.compile(r"act\s+as\s+(?:a|an|the|if)\s+", re.IGNORECASE),
    re.compile(r"disregard\s+(?:all|your|the)\s+", re.IGNORECASE),
    re.compile(r"override\s+(?:safety|system|prompt|filter|instruction)", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"DAN\s+mode", re.IGNORECASE),
]

# Destructive command patterns
_DESTRUCTIVE_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?:rm|del|delete|drop|truncate|format)\s+[-/\\*]", re.IGNORECASE),
    re.compile(r"(?:exec|execute|eval|subprocess|os\.system|__import__)", re.IGNORECASE),
    re.compile(r"(?:curl|wget|http[s]?://)\s+\S+\s+[|;]", re.IGNORECASE),
    re.compile(r"base64", re.IGNORECASE),
    re.compile(r"powershell\s+-", re.IGNORECASE),
]


def sanitize_input(raw_text: str) -> tuple[bool, str | None]:
    """
    Run all injection and destructive pattern checks on raw text input.

    Returns:
        (is_clean, hazard_description)
        is_clean=True  → proceed
        is_clean=False → abort with EXECUTION_HAZARD
    """
    for pattern in _INJECTION_PATTERNS:
        m = pattern.search(raw_text)
        if m:
            return False, f"Prompt injection pattern detected: '{m.group(0)[:60]}'"

    for pattern in _DESTRUCTIVE_PATTERNS:
        m = pattern.search(raw_text)
        if m:
            return False, f"Destructive command pattern detected: '{m.group(0)[:60]}'"

    return True, None


# =============================================================================
# SECTION 2 — CRS DIALOG DEFINITIONS
# =============================================================================

DIALOG_MESSAGES = {
    "T1": {
        "code": "T1",
        "icon": "⚠️",
        "title": "Coordinate System Not Confirmed",
        "message": (
            "We could not confidently identify your coordinate system. "
            "Please confirm which system was used on your survey plan."
        ),
        "options": [
            {"value": "WGS84",   "label": "WGS84 (standard GPS coordinates)"},
            {"value": "MINNA",   "label": "Minna Datum (Nigerian survey datum)"},
            {"value": "UTM_31N", "label": "UTM Zone 31N"},
            {"value": "UTM_32N", "label": "UTM Zone 32N (most common in Nigeria)"},
            {"value": "UTM_33N", "label": "UTM Zone 33N"},
        ],
        "type": "select",
    },
    "T2": {
        "code": "T2",
        "icon": "⚠️",
        "title": "Coordinates Outside Nigeria",
        "message": (
            "These coordinates fall outside Nigeria. "
            "A common cause is Easting and Northing being swapped on the survey plan. "
            "Please review your input."
        ),
        "options": [
            {"value": "swap",   "label": "Swap Easting and Northing"},
            {"value": "reenter","label": "Re-enter coordinates manually"},
            {"value": "proceed","label": "Proceed anyway (I am confident in these coordinates)"},
        ],
        "type": "select",
    },
    "T3": {
        "code": "T3",
        "icon": "⚠️",
        "title": "Area Discrepancy Detected",
        "message": (
            "The area we computed from your coordinates differs from your stated area. "
            "One or more coordinates may be missing or incorrect."
        ),
        "options": [
            {"value": "continue", "label": "Continue with computed area"},
            {"value": "review",   "label": "Let me review my coordinates"},
            {"value": "upload",   "label": "Upload a new plan"},
        ],
        "type": "select",
    },
    "T4": {
        "code": "T4",
        "icon": "ℹ️",
        "title": "Minna Datum Detected",
        "message": (
            "Minna Datum has been detected on your survey plan. "
            "We will convert these coordinates to WGS84 for analysis. "
            "Please be aware: position accuracy after conversion is approximately ±5 metres."
        ),
        "options": [
            {"value": "confirm", "label": "Confirm — proceed with conversion"},
            {"value": "cancel",  "label": "Cancel — I will re-enter coordinates"},
        ],
        "type": "select",
    },
    "T5": {
        "code": "T5",
        "icon": "ℹ️",
        "title": "Degrees-Minutes-Seconds Format Detected",
        "message": (
            "Your coordinates appear to be in Degrees-Minutes-Seconds (DMS) format. "
            "We have automatically converted them to Decimal Degrees for analysis. "
            "Please confirm the conversion is correct."
        ),
        "options": [
            {"value": "confirm",  "label": "Confirm — conversion looks correct"},
            {"value": "manual",   "label": "Enter coordinates manually in Decimal Degrees"},
        ],
        "type": "select",
    },
}


# =============================================================================
# SECTION 3 — SESSION STATE (SQLite-backed)
# =============================================================================

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _save_session(session: SessionState) -> None:
    """Persist session state to SQLite sessions table."""
    import json
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO sessions
              (run_id, user_id, created_at, confirmed, confirmed_at, status,
               coord_extract_json, snapshot_path, pipeline_stage, persona_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.run_id,
                session.user_id,
                session.created_at,
                1 if session.confirmed else 0,
                session.confirmed_at,
                session.status,
                session.coord_extract.model_dump_json() if session.coord_extract else None,
                session.snapshot_path,
                session.pipeline_stage.value,
                session.persona_mode.value,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _load_session(run_id: str) -> SessionState | None:
    """Load session state from SQLite by run_id."""
    import json
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM sessions WHERE run_id = ?", (run_id,)
        ).fetchone()
        if not row:
            return None
        coord_extract = None
        if row["coord_extract_json"]:
            coord_extract = CoordExtractOutput.model_validate_json(row["coord_extract_json"])
        return SessionState(
            run_id=row["run_id"],
            user_id=row["user_id"],
            created_at=row["created_at"],
            confirmed=bool(row["confirmed"]),
            confirmed_at=row["confirmed_at"],
            status=row["status"],
            pipeline_stage=PipelineStage(row["pipeline_stage"]),
            persona_mode=PersonaMode(row["persona_mode"]),
            coord_extract=coord_extract,
            snapshot_path=row["snapshot_path"],
            error_detail=row["error_detail"],
        )
    finally:
        conn.close()


# =============================================================================
# SECTION 4 — GATE FUNCTIONS
# =============================================================================

def initiate(
    raw_input: str = "",
    file_bytes: bytes | None = None,
    filename: str | None = None,
    user_id: str = "anonymous",
    persona_mode: PersonaMode = PersonaMode.EVERYDAY_BUYER,
    coordinate_hint: str | None = None,
    datum_label: str | None = None,
    stated_area_ha: float | None = None,
) -> dict:
    """
    Gate initiation — Step 0 first action.

    1. Run input sanitization filter
    2. Run CoordExtract
    3. Evaluate dialog triggers
    4. Store session state (confirmed=False)
    5. Return preview payload for the frontend (map polygon + dialogs)

    The pipeline CANNOT advance until confirm() is called.
    """
    # ── 1. SANITIZATION FILTER ────────────────────────────────────────────
    text_to_scan = raw_input or ""
    is_clean, hazard_detail = sanitize_input(text_to_scan)

    if not is_clean:
        return {
            "status": "EXECUTION_HAZARD",
            "error_code": "EXECUTION_HAZARD",
            "message": (
                "Your input has been flagged and cannot be processed. "
                "Please re-submit your land coordinates without any instructions or commands."
            ),
            "detail": hazard_detail,
        }

    # ── 2. RUN COORD EXTRACT ──────────────────────────────────────────────
    from agents.coord_extract import run as coord_extract_run

    run_id = str(uuid.uuid4())
    coord_result = coord_extract_run(
        raw_input=raw_input,
        file_bytes=file_bytes,
        filename=filename,
        run_id=run_id,
        coordinate_hint=coordinate_hint,
        datum_label=datum_label,
        stated_area_ha=stated_area_ha,
    )

    # Propagate MCP errors immediately
    if isinstance(coord_result, MCPErrorResponse):
        return {
            "status": "error",
            "error_code": coord_result.error_code,
            "instruction": coord_result.instruction,
            "run_id": run_id,
        }

    # ── 3. PERSIST SESSION (confirmed=False) ──────────────────────────────
    now = datetime.now(timezone.utc).isoformat()
    session = SessionState(
        run_id=run_id,
        user_id=user_id,
        created_at=now,
        confirmed=False,
        status="pending",
        persona_mode=persona_mode,
        pipeline_stage=PipelineStage.GATE,
        coord_extract=coord_result,
    )
    _save_session(session)

    # ── 4. BUILD DIALOG PAYLOADS ──────────────────────────────────────────
    active_dialogs = [
        {**DIALOG_MESSAGES[code], "run_id": run_id}
        for code in coord_result.crs_dialog_triggers
        if code in DIALOG_MESSAGES
    ]

    # ── 5. BUILD MAP PREVIEW PAYLOAD ──────────────────────────────────────
    # This is consumed by the Leaflet frontend to render the polygon
    coords_for_leaflet = [
        {"lat": pt[0], "lng": pt[1]}
        for pt in coord_result.coordinates
    ]

    area_discrepancy_msg: str | None = None
    if (coord_result.area_discrepancy_pct is not None
            and abs(coord_result.area_discrepancy_pct) > 10):
        area_discrepancy_msg = (
            f"The area we computed ({coord_result.computed_area_ha:.2f} ha) differs "
            f"from the stated area ({coord_result.stated_area_ha:.2f} ha) "
            f"by {coord_result.area_discrepancy_pct:+.1f}%."
        )

    return {
        "status": "awaiting_confirmation",
        "run_id": run_id,
        "map_preview": {
            "coordinates": coords_for_leaflet,
            "centroid": {
                "lat": coord_result.centroid.lat,
                "lng": coord_result.centroid.lng,
            },
            "computed_area_ha": coord_result.computed_area_ha,
            "detected_crs": coord_result.detected_crs.value,
            "crs_confidence": coord_result.crs_confidence,
            "is_inside_nigeria": coord_result.is_inside_nigeria,
            "discovery_method": getattr(coord_result, "discovery_method", "Unknown"),
        },
        "dialogs": active_dialogs,
        "warnings": coord_result.warnings,
        "area_discrepancy_message": area_discrepancy_msg,
        "confirmation_prompt": "Is this your land boundary?",
    }


def confirm(
    run_id: str,
    dialog_responses: dict | None = None,
    trigger_snapshot: bool = True,
    map_viewport: dict | None = None,
) -> dict:
    """
    Called when the user clicks YES on the map preview.

    1. Validate run_id exists and is pending
    2. Store dialog responses
    3. Set confirmed=True + confirmed_at timestamp
    4. Trigger snapshot capture
    5. Return confirmed session state for pipeline to proceed

    Args:
        run_id          : The pipeline run ID.
        dialog_responses: Dict of {dialog_code: selected_value} e.g. {"T1": "WGS84"}
        trigger_snapshot: Whether to immediately capture the map snapshot.
        map_viewport    : Optional {lat, lng, zoom} from the frontend preview map.
    """
    session = _load_session(run_id)
    if not session:
        return {
            "status": "error",
            "error_code": "SESSION_NOT_FOUND",
            "instruction": "No active session found for this run ID. Please start a new analysis.",
        }

    if session.confirmed:
        return {
            "status": "already_confirmed",
            "run_id": run_id,
            "message": "This session was already confirmed.",
        }

    # Apply dialog responses (e.g. user selected CRS manually)
    if dialog_responses and session.coord_extract:
        session.coord_extract = _apply_dialog_responses(
            session.coord_extract, dialog_responses
        )

    # Mark confirmed
    now = datetime.now(timezone.utc).isoformat()
    session.confirmed = True
    session.confirmed_at = now
    session.status = "running"
    session.pipeline_stage = PipelineStage.ADAPTER_FETCH

    # Trigger snapshot capture
    snapshot_path: str | None = None
    if trigger_snapshot and session.coord_extract:
        try:
            from core.snapshot_engine import capture
            snapshot_path = capture(
                coordinates=session.coord_extract.coordinates,
                centroid={
                    "lat": session.coord_extract.centroid.lat,
                    "lng": session.coord_extract.centroid.lng,
                },
                report_id=run_id,
                map_viewport=map_viewport,
            )
            session.snapshot_path = snapshot_path
        except Exception as exc:
            # Snapshot failure NEVER blocks the pipeline
            session.snapshot_path = None

    _save_session(session)

    return {
        "status": "confirmed",
        "run_id": run_id,
        "confirmed_at": now,
        "snapshot_path": snapshot_path,
        "coord_extract": session.coord_extract.model_dump() if session.coord_extract else None,
        "message": "Confirmation recorded. Analysis will begin shortly.",
    }


def reject(run_id: str) -> dict:
    """
    Called when the user clicks NO on the map preview.
    Halts the pipeline and marks session as cancelled.
    """
    session = _load_session(run_id)
    if not session:
        return {"status": "error", "error_code": "SESSION_NOT_FOUND"}

    session.confirmed = False
    session.status = "cancelled"
    session.pipeline_stage = PipelineStage.ERROR
    _save_session(session)

    return {
        "status": "rejected",
        "run_id": run_id,
        "message": "Analysis cancelled. Please correct your coordinates and try again.",
    }


def is_confirmed(run_id: str) -> bool:
    """
    Lightweight check — returns True only if session is confirmed.
    Called by the pipeline before each downstream step.
    """
    session = _load_session(run_id)
    return bool(session and session.confirmed)


def get_session(run_id: str) -> SessionState | None:
    """Return the full session state for a given run_id."""
    return _load_session(run_id)


def update_session_stage(run_id: str, stage: PipelineStage) -> None:
    """Update the pipeline_stage field in the session record."""
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE sessions SET pipeline_stage = ? WHERE run_id = ?",
            (stage.value, run_id),
        )
        conn.commit()
    finally:
        conn.close()


# =============================================================================
# SECTION 5 — DIALOG RESPONSE HANDLERS
# =============================================================================

def _apply_dialog_responses(
    coord_output: CoordExtractOutput,
    responses: dict,
) -> CoordExtractOutput:
    """
    Apply user selections from dialog responses to the coord output.
    e.g. T1 response "WGS84" overrides detected_crs.
    """
    from agents.coord_extract import transform_to_wgs84

    updated = coord_output.model_copy(deep=True)

    # T1: User manually selected CRS
    if "T1" in responses:
        crs_value = responses["T1"]
        try:
            new_crs = CRSName(crs_value)
            updated = updated.model_copy(update={
                "detected_crs": new_crs,
                "crs_confidence": 100.0,  # User confirmed
            })
        except ValueError:
            pass  # Unknown value — ignore

    # T2: User chose to swap Easting/Northing
    if "T2" in responses and responses["T2"] == "swap":
        original = [(pt[0], pt[1]) for pt in updated.coordinates]
        swapped = [(b, a) for a, b in original]
        from agents.coord_extract import (
            compute_centroid, compute_area_ha, is_inside_nigeria
        )
        centroid = compute_centroid(swapped)
        area = compute_area_ha(swapped)
        updated = updated.model_copy(update={
            "coordinates": [[lat, lng] for lat, lng in swapped],
            "centroid": centroid,
            "computed_area_ha": area,
            "is_inside_nigeria": is_inside_nigeria(centroid),
        })

    return updated


# =============================================================================
# SECTION 6 — FOLIUM MAP GENERATOR (for browser preview only, NOT snapshot)
# =============================================================================

def generate_preview_map_html(coord_output: CoordExtractOutput) -> str:
    """
    Generate an HTML Folium map showing the parcel polygon.
    This is served to the browser for the interactive confirmation step.
    NOT used for the snapshot PNG (snapshot_engine handles that).
    """
    try:
        import folium

        centroid = [coord_output.centroid.lat, coord_output.centroid.lng]
        m = folium.Map(location=centroid, zoom_start=17, tiles="OpenStreetMap")

        coords_leaflet = [[pt[0], pt[1]] for pt in coord_output.coordinates]
        folium.Polygon(
            locations=coords_leaflet,
            color="#3b82f6",
            weight=2,
            fill=True,
            fill_color="#3b82f6",
            fill_opacity=0.25,
            popup=folium.Popup(
                f"Area: {coord_output.computed_area_ha:.2f} ha<br>"
                f"CRS: {coord_output.detected_crs.value} "
                f"({coord_output.crs_confidence:.0f}% confidence)",
                max_width=250,
            ),
        ).add_to(m)

        folium.Marker(
            location=centroid,
            popup=f"Centroid: {centroid[0]:.5f}°N, {centroid[1]:.5f}°E",
            icon=folium.Icon(color="blue", icon="map-pin", prefix="fa"),
        ).add_to(m)

        return m._repr_html_()

    except ImportError:
        # Folium not available — return minimal fallback HTML
        coords_json = str([[pt[0], pt[1]] for pt in coord_output.coordinates])
        return f"""
        <div id="map-placeholder" style="background:#f0f4f8;padding:20px;border-radius:8px;">
          <p>Map preview unavailable (folium not installed).</p>
          <p>Centroid: {coord_output.centroid.lat:.5f}°N, {coord_output.centroid.lng:.5f}°E</p>
          <p>Computed Area: {coord_output.computed_area_ha:.2f} ha</p>
          <pre style="font-size:11px;">{coords_json}</pre>
        </div>
        """
