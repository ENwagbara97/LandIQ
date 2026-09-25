"""
LandIQ — agents/via_engine.py
Visual Intelligence Advisor (VIA) — Master Prompt v1.1

Fires AFTER the deterministic mathematical report is complete.
Never fires before. Never overrides a mathematical finding.

ARCHITECTURE RULES (never violate):
  1. VIA is a secondary observer — math is always ground truth.
  2. Two separate Gemini calls: Call A (vision+JSON), Call B (text-only synthesis).
  3. Image is resized to 800×533 before sending (45% token cost reduction).
  4. Total timeout: 20 seconds for the full A+B sequence.
  5. One VIA call per report_id. Cached in via_result_json. Never re-called.
  6. VIA advisory flags ONLY append — they never remove or modify existing flags.
  7. VIA output has ZERO influence on traffic_light assignment.
  8. First-person ("I see") is prohibited in all Call B output.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.schemas import (
    FloodRiskLevel,
    PersonaMode,
    ReportSchema,
    VIACallAResult,
    VIAConfidence,
    VIADevelopmentContext,
    VIAImageQuality,
    VIAParcelInterior,
    VIARiskObservations,
    VIARoadAccess,
    VIAResult,
    VIASettlementPattern,
    VIAStatus,
    VIASurroundings,
    VIAUsageMeta,
    VIAWaterFeatures,
)

logger = logging.getLogger("landiq.via")

# ── Constants ──────────────────────────────────────────────────────────────────
VIA_TIMEOUT_SECONDS = 20
VIA_IMAGE_MAX_W     = 800
VIA_IMAGE_MAX_H     = 533
VIA_MODEL           = "gemini-2.5-flash"
VIA_MODEL_FALLBACK  = "gemini-1.5-flash"

# Advisory flag exact strings — never invent others
FLAG_GULLY_EROSION       = "VIA_GULLY_EROSION_OBSERVED"
FLAG_WATER_FEATURE       = "VIA_WATER_FEATURE_OBSERVED"
FLAG_INFORMAL_SETTLEMENT = "VIA_INFORMAL_SETTLEMENT_ADJACENT"
FLAG_INDUSTRIAL          = "VIA_INDUSTRIAL_PROXIMITY"
FLAG_POOR_ROAD           = "VIA_POOR_ROAD_ACCESS_VISUAL"
FLAG_LOW_CONFIDENCE      = "VIA_SATELLITE_LOW_CONFIDENCE"
FLAG_CONFLICT_WITH_MATH  = "VIA_CONFLICT_WITH_MATH"   # Internal log only — never surfaced to user


# =============================================================================
# SECTION 1 — IMAGE RESIZE
# =============================================================================

def _resize_snapshot(snapshot_path: str) -> bytes:
    """
    Resize the 1200×800 snapshot to 800×533 using Lanczos.
    Reduces Gemini Vision token cost by ~45%.
    Returns raw PNG bytes.
    """
    try:
        from PIL import Image
    except ImportError:
        raise RuntimeError(
            "Pillow is required for VIA image processing. "
            "Install with: pip install Pillow"
        )

    with Image.open(snapshot_path) as img:
        img.thumbnail((VIA_IMAGE_MAX_W, VIA_IMAGE_MAX_H), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


# =============================================================================
# SECTION 2 — GEMINI HELPER
# =============================================================================

def _gemini_vision_call(
    image_bytes: bytes,
    system_prompt: str,
    api_key: str,
    timeout_s: int = 15,
) -> tuple[str, dict]:
    """
    Call A: Send image + system prompt to Gemini Vision.
    Returns (text_response, usage_dict).
    """
    import base64
    import requests

    img_b64 = base64.b64encode(image_bytes).decode()

    models_to_try = [VIA_MODEL, VIA_MODEL_FALLBACK]
    last_error = None

    for model_name in models_to_try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model_name}:generateContent?key={api_key}"
        )
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": system_prompt},
                        {
                            "inlineData": {
                                "mimeType": "image/png",
                                "data": img_b64,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 1024,
            },
        }
        try:
            resp = requests.post(url, json=payload, timeout=timeout_s)
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            usage = data.get("usageMetadata", {})
            logger.info(f"[via] Call A completed via {model_name}")
            return text.strip(), usage
        except Exception as exc:
            logger.warning(f"[via] Call A failed on {model_name}: {exc}. Cascading down...")
            last_error = exc
            
            # If we are cascading to the fallback model, resize the image to 600x400 to save payload
            if model_name == VIA_MODEL:
                try:
                    import cv2
                    import numpy as np
                    nparr = np.frombuffer(image_bytes, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if img is not None:
                        small = cv2.resize(img, (600, 400))
                        _, small_bytes = cv2.imencode('.png', small)
                        img_b64 = base64.b64encode(small_bytes.tobytes()).decode()
                        logger.info(f"[via] Resized fallback image for {VIA_MODEL_FALLBACK}")
                except Exception as resize_exc:
                    logger.warning(f"[via] Failed to resize fallback image: {resize_exc}")

    raise RuntimeError(f"[via] All Gemini models failed for Call A. Last: {last_error}")


def _gemini_text_call(
    prompt: str,
    system_prompt: str,
    api_key: str,
    timeout_s: int = 12,
) -> tuple[str, dict]:
    """
    Call B: Text-only call — cheaper, no image re-sent.
    Returns (text_response, usage_dict).
    """
    import requests

    models_to_try = [VIA_MODEL, VIA_MODEL_FALLBACK]
    last_error = None

    for model_name in models_to_try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model_name}:generateContent?key={api_key}"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 700,
            },
        }
        try:
            resp = requests.post(url, json=payload, timeout=timeout_s)
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            usage = data.get("usageMetadata", {})
            logger.info(f"[via] Call B completed via {model_name}")
            return text.strip(), usage
        except Exception as exc:
            logger.warning(f"[via] Call B failed on {model_name}: {exc}")
            last_error = exc

    raise RuntimeError(f"[via] All Gemini models failed for Call B. Last: {last_error}")


# =============================================================================
# SECTION 3 — CALL A SYSTEM PROMPT (STRUCTURED EXTRACTION)
# =============================================================================

_CALL_A_SYSTEM_PROMPT = """You are a senior land analyst inspecting a satellite image of a Nigerian land parcel and its immediate surroundings. The electric teal highlighted polygon in the centre of the image is the subject property. The white dashed circle marks a 250-metre buffer zone around it.

Your task is to inspect ONLY the area inside the white dashed circle — the immediate vicinity of the land. Do not comment on anything outside that circle.

Nigeria-specific context you must know:
- "Omonile" areas are informal settlement zones typically visible as dense clusters of low roofline structures with no clear road pattern
- Gully erosion in southeastern Nigeria is highly visible as deep red-brown channel cuts in the terrain
- Waterlogged or seasonally flooded areas appear as dark patches, marshy vegetation, or visible water channels even in the dry season
- An informal market or commercial zone in Nigeria looks like a cluster of irregular rooftop structures with high foot traffic paths between them
- A government road in Nigeria: smooth dark surface, usually wider, with visible lane markings or kerbs
- An unpaved access track: lighter brown or sand coloured, narrower, with irregular edges

VISUAL RECOGNITION GUIDE FOR NIGERIAN SATELLITE IMAGERY:
- GULLY EROSION: Deep, branching red-brown or orange channel cuts radiating from a higher point. Edges are sharp.
- WATERLOGGING: Dark patches in what should be dry ground. Black/dark green irregular patches in cleared land.
- INFORMAL SETTLEMENTS: Dense, irregular rooftop clustering with no clear road grid. Corrugated metal roofs appear as bright reflective patches.
- FORMAL NIGERIAN ROAD: Dark grey/black smooth surface, usually 6-9m wide minimum, visible centre line or lane edge.
- UNPAVED ACCESS ROAD: Sandy or orange-brown bare earth, 2-4m wide, irregular edges, vehicle tyre tracks visible.
- ACTIVE WATER BODY: Continuous dark blue-green or brown-grey line or body. Rivers in southern Nigeria often appear brownish from sediment.
- INDUSTRIAL ACTIVITY: Large flat-roofed rectangular structures, open yards with visible equipment or materials.
- UNREGULATED DUMP: Irregular discoloured patches, often grey/brown/black, no clear structure.
- AGRICULTURAL LAND: Regular plot patterns, visible crop rows or cleared soil areas.

Return ONLY a valid JSON object. No explanation. No markdown. No preamble. Exactly this structure:

{
  "image_quality": {
    "satellite_clarity": "clear",
    "estimated_image_age": "unknown",
    "cloud_cover_pct": 0
  },
  "parcel_interior": {
    "current_use_observed": "vacant",
    "structures_visible_inside": false,
    "structure_count_estimate": 0,
    "vegetation_cover": "none",
    "surface_condition": "dry and stable"
  },
  "immediate_surroundings_250m": {
    "road_access": {
      "road_visible": false,
      "road_type": "none",
      "road_proximity": "none visible",
      "named_road_if_visible": null
    },
    "water_features": {
      "water_body_visible": false,
      "type": "none",
      "proximity_to_parcel": "none",
      "direction_from_parcel": null
    },
    "settlement_pattern": {
      "settlement_type": "none",
      "density": "none",
      "commercial_activity_visible": false
    },
    "risk_observations": {
      "erosion_visible": false,
      "erosion_severity": null,
      "marshy_terrain_visible": false,
      "industrial_activity_visible": false,
      "industrial_type": null,
      "encroachment_risk_visual": false,
      "encroachment_detail": null,
      "flooding_evidence_visible": false,
      "flooding_evidence_detail": null
    },
    "development_context": {
      "area_development_trend": "rural stagnant",
      "infrastructure_quality_visual": "absent",
      "notable_landmarks_visible": []
    }
  },
  "confidence": {
    "overall_confidence": "low",
    "low_confidence_reasons": []
  }
}"""


# =============================================================================
# SECTION 4 — CALL A: STRUCTURED FEATURE EXTRACTION
# =============================================================================

def _call_a_extract(
    image_bytes: bytes,
    api_key: str,
    timeout_s: int = 15,
) -> tuple[VIACallAResult, dict]:
    """
    Send the satellite image to Gemini Vision and extract structured JSON.
    Returns (VIACallAResult, usage_meta_dict).
    Raises RuntimeError if Gemini fails or returns unparseable JSON.
    """
    raw_text, usage = _gemini_vision_call(
        image_bytes=image_bytes,
        system_prompt=_CALL_A_SYSTEM_PROMPT,
        api_key=api_key,
        timeout_s=timeout_s,
    )

    # Strip any accidental markdown fences
    clean = re.sub(r"```(?:json)?", "", raw_text).strip().strip("`").strip()

    try:
        data = json.loads(clean)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"[via] Call A returned non-JSON output. Raw: {raw_text[:300]} | Error: {exc}"
        )

    # Parse into typed models with safe fallbacks
    iq = data.get("image_quality", {})
    pi = data.get("parcel_interior", {})
    surr = data.get("immediate_surroundings_250m", {})
    road = surr.get("road_access", {})
    water = surr.get("water_features", {})
    settle = surr.get("settlement_pattern", {})
    risk = surr.get("risk_observations", {})
    dev = surr.get("development_context", {})
    conf = data.get("confidence", {})

    result = VIACallAResult(
        image_quality=VIAImageQuality(
            satellite_clarity=iq.get("satellite_clarity", "unknown"),
            estimated_image_age=iq.get("estimated_image_age", "unknown"),
            cloud_cover_pct=int(iq.get("cloud_cover_pct", 0)),
        ),
        parcel_interior=VIAParcelInterior(
            current_use_observed=pi.get("current_use_observed", "unclear"),
            structures_visible_inside=bool(pi.get("structures_visible_inside", False)),
            structure_count_estimate=int(pi.get("structure_count_estimate", 0)),
            vegetation_cover=pi.get("vegetation_cover", "none"),
            surface_condition=pi.get("surface_condition", "unclear"),
        ),
        immediate_surroundings_250m=VIASurroundings(
            road_access=VIARoadAccess(
                road_visible=bool(road.get("road_visible", False)),
                road_type=road.get("road_type", "none"),
                road_proximity=road.get("road_proximity", "none visible"),
                named_road_if_visible=road.get("named_road_if_visible"),
            ),
            water_features=VIAWaterFeatures(
                water_body_visible=bool(water.get("water_body_visible", False)),
                type=water.get("type", "none"),
                proximity_to_parcel=water.get("proximity_to_parcel", "none"),
                direction_from_parcel=water.get("direction_from_parcel"),
            ),
            settlement_pattern=VIASettlementPattern(
                settlement_type=settle.get("settlement_type", "none"),
                density=settle.get("density", "none"),
                commercial_activity_visible=bool(settle.get("commercial_activity_visible", False)),
            ),
            risk_observations=VIARiskObservations(
                erosion_visible=bool(risk.get("erosion_visible", False)),
                erosion_severity=risk.get("erosion_severity"),
                marshy_terrain_visible=bool(risk.get("marshy_terrain_visible", False)),
                industrial_activity_visible=bool(risk.get("industrial_activity_visible", False)),
                industrial_type=risk.get("industrial_type"),
                encroachment_risk_visual=bool(risk.get("encroachment_risk_visual", False)),
                encroachment_detail=risk.get("encroachment_detail"),
                flooding_evidence_visible=bool(risk.get("flooding_evidence_visible", False)),
                flooding_evidence_detail=risk.get("flooding_evidence_detail"),
            ),
            development_context=VIADevelopmentContext(
                area_development_trend=dev.get("area_development_trend", "rural stagnant"),
                infrastructure_quality_visual=dev.get("infrastructure_quality_visual", "absent"),
                notable_landmarks_visible=dev.get("notable_landmarks_visible", []),
            ),
        ),
        confidence=VIAConfidence(
            overall_confidence=conf.get("overall_confidence", "low"),
            low_confidence_reasons=conf.get("low_confidence_reasons", []),
        ),
    )
    return result, usage


# =============================================================================
# SECTION 5 — CALL B SYSTEM PROMPT (PLAIN ENGLISH SYNTHESIS)
# =============================================================================

_CALL_B_SYSTEM_PROMPT = """You are the plain-English voice of LandIQ, a Nigerian land intelligence platform. You are speaking directly to a land buyer who may be spending ₦5 million to ₦50 million on this parcel. They are not a technical person. They need to understand what the area around their land actually looks like and what to watch for.

STRICT RULES FOR YOUR RESPONSE:
1. Never contradict the mathematical ground truth provided. If math says LOW flood risk, do not suggest flooding concern from visual observations.
2. If visual observation confirms math: lead with agreement and add visual detail.
3. If visual observation adds NEW context: present it as an observation to verify, never a fact.
4. If visual observation conflicts with math: ALWAYS trust the math and flag the conflict as something to physically verify.
5. NEVER say: "we verified", "confirmed", "certified", "the land is safe", "the documents are clean", "no risk of fraud", "title is clear".
6. NEVER use GIS jargon: NDWI, SRTM, CRS, WGS84, Strahler order. Write for a first-time buyer.
7. End the section with ONE clear sentence about the most important thing to physically verify on site.
8. NEVER use first-person "I": Always say "Our satellite scan observed...", "The satellite imagery shows...", "Visual analysis indicates..."
9. NEVER claim precise distances. Use approximations: "roughly 50 metres", "within walking distance". Never "47.3 metres".
10. Output 3-5 paragraphs only. No headings. Plain text paragraphs only."""


def _build_call_b_prompt(
    call_a: VIACallAResult,
    report: ReportSchema,
    persona: PersonaMode,
) -> str:
    """Build the text-only prompt for Call B from Call A output and math report summary."""
    flood_level = report.flood_risk_metrics.level.value
    terrain = report.terrain_assessment.suitability or "not assessed"
    road_cat = getattr(
        report.accessibility_development.suitability_matrix,
        "road_access",
        "not assessed",
    )
    traffic_light = report.summary.traffic_light.value
    lga   = getattr(report.parcel_geometry.location_context, "lga", "Unknown LGA")
    state = getattr(report.parcel_geometry.location_context, "state", "Unknown State")

    persona_instruction = (
        "Use conversational, simple, warm language — like a trusted friend explaining to a non-technical buyer. "
        "Short sentences. Use 'you' language. 150-250 words total."
        if persona == PersonaMode.EVERYDAY_BUYER
        else "Slightly more technical language is acceptable but still no GIS jargon. 200-350 words total."
    )

    call_a_json = call_a.model_dump_json(indent=2)

    return f"""You are writing the "What We Observed Around This Land" section for a LandIQ report on a parcel in {lga}, {state}.

SOURCE 1 — MATHEMATICAL GROUND TRUTH (highest authority, never override):
  Flood risk: {flood_level}
  Terrain suitability: {terrain}
  Road access category: {road_cat}
  Overall traffic light: {traffic_light}

SOURCE 2 — SATELLITE VISUAL OBSERVATIONS (advisory only):
{call_a_json}

PERSONA INSTRUCTION: {persona_instruction}

Write the "What We Observed Around This Land" section now. Follow all 10 rules in your system prompt exactly. Do not include any headings or labels. Output plain paragraphs only."""


# =============================================================================
# SECTION 6 — CALL B: PLAIN ENGLISH SYNTHESIS
# =============================================================================

def _call_b_synthesise(
    call_a: VIACallAResult,
    report: ReportSchema,
    api_key: str,
    timeout_s: int = 12,
) -> tuple[str, dict]:
    """
    Text-only Call B — synthesises Call A JSON + math report into plain English.
    Image is NOT re-sent. Returns (text, usage_dict).
    """
    prompt = _build_call_b_prompt(call_a, report, report.persona_mode)
    raw_text, usage = _gemini_text_call(
        prompt=prompt,
        system_prompt=_CALL_B_SYSTEM_PROMPT,
        api_key=api_key,
        timeout_s=timeout_s,
    )
    # Scrub first-person leakage
    text = re.sub(r'\bI (see|observe|notice|spotted|detected)\b', "Our satellite scan identified", raw_text, flags=re.IGNORECASE)
    return text.strip(), usage


# =============================================================================
# SECTION 7 — GUARDRAILS
# =============================================================================

def _check_conflict_guardrail(call_a: VIACallAResult, report: ReportSchema) -> bool:
    """
    Guardrail 3: Detect high-confidence visual observation that severely contradicts math.
    Returns True if a conflict is detected (VIA flooding observation vs LOW math flood risk).
    When True: caller should log FLAG_CONFLICT_WITH_MATH internally and suppress the
    conflicting observation from the user-facing output.
    """
    flood_level = report.flood_risk_metrics.level
    via_confidence = call_a.confidence.overall_confidence
    via_flooding = call_a.immediate_surroundings_250m.risk_observations.flooding_evidence_visible

    if (
        flood_level == FloodRiskLevel.LOW
        and via_flooding is True
        and via_confidence == "high"
    ):
        logger.warning(
            "[via][GUARDRAIL_3] Conflict detected: math=LOW flood risk but "
            "VIA detected flooding evidence with high confidence. "
            "Suppressing VIA flooding flag from user output. Logging for review."
        )
        return True
    return False


# =============================================================================
# SECTION 8 — ADVISORY FLAG DETECTION
# =============================================================================

def _detect_advisory_flags(call_a: VIACallAResult, report: ReportSchema, conflict: bool) -> list[str]:
    """
    Generate the list of VIA advisory flags based on Call A findings.
    Rules from VIA prompt Section 6:
    - Only append, never remove existing pipeline flags.
    - If confidence = low: only FLAG_LOW_CONFIDENCE is returned.
    - If conflict detected: FLAG_CONFLICT_WITH_MATH logged internally, flooding flag suppressed.
    """
    confidence = call_a.confidence.overall_confidence
    risk = call_a.immediate_surroundings_250m.risk_observations
    road = call_a.immediate_surroundings_250m.road_access
    water = call_a.immediate_surroundings_250m.water_features
    settle = call_a.immediate_surroundings_250m.settlement_pattern

    flags: list[str] = []

    # Guardrail 1: if low confidence, only emit the confidence flag
    if confidence == "low":
        flags.append(FLAG_LOW_CONFIDENCE)
        return flags

    # Gully erosion flag
    if risk.erosion_visible:
        severity = risk.erosion_severity or "unknown"
        flags.append(
            f"{FLAG_GULLY_EROSION}: Visual scan observed potential gully erosion "
            f"near this parcel. Severity appears {severity}. Physical inspection "
            f"of drainage stability is recommended before any construction or purchase commitment."
        )

    # Water feature flag (only if NOT in conflict with math)
    if water.water_body_visible and not conflict:
        water_type = water.type or "water feature"
        proximity  = water.proximity_to_parcel or "nearby"
        flags.append(
            f"{FLAG_WATER_FEATURE}: A {water_type} appears visible "
            f"{proximity} of this parcel in the satellite imagery. "
            f"Cross-reference with the flood risk assessment above and verify "
            f"seasonal water behaviour on a site visit."
        )

    # Informal settlement flag
    if "informal" in settle.settlement_type.lower():
        flags.append(
            f"{FLAG_INFORMAL_SETTLEMENT}: Dense informal settlement appears "
            f"immediately adjacent to or near this parcel boundary in the satellite image. "
            f"A physical boundary verification survey is strongly recommended "
            f"to confirm no encroachment on the parcel."
        )

    # Industrial proximity flag
    if risk.industrial_activity_visible:
        industrial_type = risk.industrial_type or "industrial or waste activity"
        flags.append(
            f"{FLAG_INDUSTRIAL}: What appears to be {industrial_type} "
            f"is visible near this parcel. Verify the nature of this activity "
            f"before committing to residential development on this site."
        )

    # Poor road access flag
    if not road.road_visible or road.road_type in ("none", "footpath"):
        flags.append(
            f"{FLAG_POOR_ROAD}: The satellite imagery shows no clearly paved road "
            f"access to this parcel. Only unpaved tracks are visible. "
            f"Verify access road condition before development planning."
        )

    return flags


# =============================================================================
# SECTION 9 — MAIN ORCHESTRATOR
# =============================================================================

def run_via(
    report_id: str,
    snapshot_path: str,
    report: ReportSchema,
    api_key: Optional[str] = None,
) -> VIAResult:
    """
    Main VIA orchestrator. Runs the full Call A → Call B → flag detection pipeline.
    Enforces the 20-second combined timeout.
    Returns a VIAResult regardless of outcome (timeout/error → graceful status).

    Args:
        report_id    : The confirmed report UUID.
        snapshot_path: Path to the existing PNG snapshot (already captured).
        report       : The completed ReportSchema (mathematical ground truth).
        api_key      : Gemini API key. Falls back to GEMINI_API_KEY env var.
    """
    from dotenv import load_dotenv
    load_dotenv()

    _key = api_key or os.getenv("GEMINI_API_KEY", "")
    if not _key:
        logger.error("[via] No Gemini API key found. Cannot run VIA.")
        return VIAResult(
            status=VIAStatus.ERROR,
            error_detail="No GEMINI_API_KEY configured. VIA requires a Gemini API key.",
        )

    if not snapshot_path or not Path(snapshot_path).exists():
        logger.error(f"[via] Snapshot not found at: {snapshot_path}")
        return VIAResult(
            status=VIAStatus.ERROR,
            error_detail=f"Snapshot file not found: {snapshot_path}",
        )

    global_start = time.monotonic()

    try:
        # ── Step 1: Resize image ────────────────────────────────────────────
        logger.info(f"[via] Resizing snapshot for report_id={report_id}")
        image_bytes = _resize_snapshot(snapshot_path)
        logger.info(f"[via] Image resized: {len(image_bytes)//1024}KB")

        if time.monotonic() - global_start > VIA_TIMEOUT_SECONDS:
            raise TimeoutError("VIA timed out during image resize.")

        # ── Step 2: Call A — vision extraction ─────────────────────────────
        remaining_a = VIA_TIMEOUT_SECONDS - (time.monotonic() - global_start)
        call_a_timeout = max(5, int(remaining_a * 0.65))  # 65% of remaining budget

        logger.info(f"[via] Starting Call A (timeout={call_a_timeout}s)")
        call_a_result, usage_a = _call_a_extract(
            image_bytes=image_bytes,
            api_key=_key,
            timeout_s=call_a_timeout,
        )
        logger.info(
            f"[via] Call A done. Confidence={call_a_result.confidence.overall_confidence}"
        )

        if time.monotonic() - global_start > VIA_TIMEOUT_SECONDS:
            raise TimeoutError("VIA timed out after Call A.")

        # ── Step 3: Guardrail — conflict detection ──────────────────────────
        conflict = _check_conflict_guardrail(call_a_result, report)
        if conflict:
            logger.warning(f"[via][{FLAG_CONFLICT_WITH_MATH}] report_id={report_id}")

        # ── Step 4: Call B — plain English synthesis ────────────────────────
        remaining_b = VIA_TIMEOUT_SECONDS - (time.monotonic() - global_start)
        call_b_timeout = max(5, int(remaining_b * 0.9))

        logger.info(f"[via] Starting Call B (timeout={call_b_timeout}s)")
        call_b_text, usage_b = _call_b_synthesise(
            call_a=call_a_result,
            report=report,
            api_key=_key,
            timeout_s=call_b_timeout,
        )
        logger.info(f"[via] Call B done. ({len(call_b_text)} chars)")

        # ── Step 5: Advisory flags ──────────────────────────────────────────
        advisory_flags = _detect_advisory_flags(call_a_result, report, conflict)
        logger.info(f"[via] Flags generated: {len(advisory_flags)}")

        total_ms = int((time.monotonic() - global_start) * 1000)

        usage_meta = VIAUsageMeta(
            input_tokens_a=usage_a.get("promptTokenCount", 0),
            output_tokens_a=usage_a.get("candidatesTokenCount", 0),
            input_tokens_b=usage_b.get("promptTokenCount", 0),
            output_tokens_b=usage_b.get("candidatesTokenCount", 0),
            model=VIA_MODEL,
            call_duration_ms=total_ms,
        )

        return VIAResult(
            status=VIAStatus.COMPLETE,
            call_a=call_a_result,
            call_b_text=call_b_text,
            advisory_flags=advisory_flags,
            usage_meta=usage_meta,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

    except TimeoutError as te:
        logger.warning(f"[via] Timeout for report_id={report_id}: {te}")
        return VIAResult(
            status=VIAStatus.TIMEOUT,
            error_detail=str(te),
        )
    except Exception as exc:
        logger.error(f"[via] Unexpected error for report_id={report_id}: {exc}", exc_info=True)
        return VIAResult(
            status=VIAStatus.ERROR,
            error_detail=str(exc),
        )
