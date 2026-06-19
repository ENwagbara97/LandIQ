"""
LandIQ — agents/report_gen.py
Step 5: Report Generation Agent

Assembles the full ReportSchema from all upstream agent outputs.
Makes exactly 2 Ollama calls — with streaming, timeout fallback, and output scrubbing.

ARCHITECTURE RULES (never violate):
  1. Python fills ALL structured schema fields before any LLM call.
  2. LLM writes narrative prose ONLY — never touches numeric/boolean/classification fields.
  3. Max 2 Ollama calls per report. No exceptions.
  4. All Ollama output passes through the prohibited phrase scrubber before storage.
  5. If Ollama times out (> OLLAMA_TIMEOUT_SECONDS), template strings are used. Report always completes.

Call 1 — Metric Translation:
  Input: merged GISAnalysis + RiskAssess JSON slice
  Task:  Translate ALL GIS metrics to plain-English consequences in one pass
  Output: plain_english_metrics{} block
  Limits: < 800 tokens in / < 400 tokens out

Call 2 — Executive Summary:
  Input: plain_english_metrics{} + traffic light + advisory flags
  Task:  3-sentence executive summary + AI recommendation paragraph
  Limits: < 600 tokens in / < 300 tokens out
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from core.schemas import (
    AccessibilityDevelopment,
    CoordExtractOutput,
    CoordinateValidation,
    DevelopmentSuitability,
    EncroachmentRecord,
    FloodRiskMetrics,
    GISAnalysisOutput,
    GrowthPotentialRecord,
    LocationContext,
    MCPErrorResponse,
    NormalisedFeedSchema,
    ParcelGeometry,
    PersonaMode,
    PipelineStage,
    ReportMeta,
    ReportSchema,
    ReportSummary,
    RiskAssessOutput,
    SuitabilityGrowthOutput,
    TerrainAssessment,
    TitleRecord,
    TrafficLight,
    Coordinate,
)

logger = logging.getLogger("landiq.report_gen")

# ── Config ────────────────────────────────────────────────────────────────────
ROOT_DIR    = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config" / "feed_flags.json"


def _load_flags() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


# =============================================================================
# SECTION 1 — OUTPUT SCRUBBER
# Applied to ALL Ollama-generated text before it enters the report.
# =============================================================================

# Exact phrases that are NEVER permitted in any user-facing output
_PROHIBITED_PHRASES: list[tuple[str, str]] = [
    ("no flood risk",            "[flood risk assessment not available]"),
    ("land is safe to buy",      "[transaction safety cannot be confirmed]"),
    ("title is clear",           "[title status not verified]"),
    ("no government acquisition risk", "[acquisition status not verified]"),
    ("100% accurate",            "[indicative assessment only]"),
    ("c of o verified",          "[C of O status not verified via live registry]"),
    ("official government acquisition check", "[live acquisition check not available]"),
    # Raw technical leakage patterns
    ("null",                     "[data not available]"),
    ("none",                     "[not assessed]"),
    ("localhost",                ""),
    ("127.0.0.1",                ""),
    ("/data/",                   ""),
    (".tif",                     ""),
    (".shp",                     ""),
    ("traceback",                ""),
    ("exception",                ""),
    ("error:",                   ""),
]

# Regex-based scrubber for file paths and ports
import re

_PATH_PATTERN = re.compile(
    r"""(?:C:\\|/[a-z]+/|[A-Za-z]:\\)[^\s,;'\"]{3,}""",
    re.IGNORECASE,
)
_PORT_PATTERN = re.compile(r":\d{4,5}\b")


def scrub_output(text: str) -> str:
    """Remove all prohibited phrases, file paths, and connection strings."""
    if not text:
        return text
    result = text
    for phrase, replacement in _PROHIBITED_PHRASES:
        result = re.sub(re.escape(phrase), replacement, result, flags=re.IGNORECASE)
    result = _PATH_PATTERN.sub("[path redacted]", result)
    result = _PORT_PATTERN.sub("", result)
    return result.strip()


# =============================================================================
# SECTION 2 — LLM CALL ROUTER (Gemini auto-detected from .env; Ollama fallback)
# =============================================================================

def _llm_call(
    prompt: str,
    system: str,
    model: str,
    timeout_s: int,
    stream: bool = True,
    max_tokens: int = 400,
    llm_provider: str | None = None,
    llm_api_key: str | None = None,
) -> tuple[str, bool]:
    """
    Make one LLM call. Returns (text, timeout_fired).
    Routes to Cloud APIs (Gemini/OpenAI/Anthropic) if provided, else falls back to Ollama.
    """
    import requests
    import os
    from dotenv import load_dotenv

    load_dotenv()

    start = time.monotonic()
    
    # Auto-detect Gemini key from environment if not explicitly provided
    if not llm_provider and os.getenv("GEMINI_API_KEY"):
        llm_provider = "gemini"
        llm_api_key = os.getenv("GEMINI_API_KEY")

    # ── CLOUD ROUTING ──
    if llm_provider and llm_api_key:
        provider = llm_provider.lower().strip()
        try:
            if provider == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={llm_api_key}"
                payload = {
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.3, "maxOutputTokens": max_tokens}
                }
                resp = requests.post(url, json=payload, timeout=timeout_s)
                resp.raise_for_status()
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                logger.info(f"[report_gen] Gemini call completed in {time.monotonic()-start:.2f}s")
                return text.strip(), False
                
            elif provider == "openai":
                url = "https://api.openai.com/v1/chat/completions"
                headers = {"Authorization": f"Bearer {llm_api_key}"}
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": max_tokens
                }
                resp = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                logger.info(f"[report_gen] OpenAI call completed in {time.monotonic()-start:.2f}s")
                return text.strip(), False
                
            elif provider == "anthropic":
                url = "https://api.anthropic.com/v1/messages"
                headers = {
                    "x-api-key": llm_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                payload = {
                    "model": "claude-3-haiku-20240307",
                    "system": system,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": max_tokens
                }
                resp = requests.post(url, headers=headers, json=payload, timeout=timeout_s)
                resp.raise_for_status()
                data = resp.json()
                text = data["content"][0]["text"]
                logger.info(f"[report_gen] Anthropic call completed in {time.monotonic()-start:.2f}s")
                return text.strip(), False
                
        except Exception as e:
            logger.warning(f"[report_gen] Cloud LLM ({provider}) failed: {e}. Falling back to local Ollama.")
            # Fall through to Ollama

    # ── LOCAL OLLAMA FALLBACK ──
    try:
        import ollama

        full_text = ""

        if stream:
            response_iter = ollama.chat(
                model=model,
                messages=[
                    {"role": "system",  "content": system},
                    {"role": "user",    "content": prompt},
                ],
                stream=True,
                options={"num_predict": max_tokens, "temperature": 0.3},
            )
            for chunk in response_iter:
                if time.monotonic() - start > timeout_s:
                    logger.warning(f"[LLM_TIMEOUT] Ollama stream exceeded {timeout_s}s")
                    return full_text or "", True
                content = chunk.get("message", {}).get("content", "")
                full_text += content
        else:
            response = ollama.chat(
                model=model,
                messages=[
                    {"role": "system",  "content": system},
                    {"role": "user",    "content": prompt},
                ],
                options={"num_predict": max_tokens, "temperature": 0.3},
            )
            elapsed = time.monotonic() - start
            if elapsed > timeout_s:
                logger.warning(f"[LLM_TIMEOUT] Ollama non-stream exceeded {timeout_s}s")
                return "", True
            full_text = response.get("message", {}).get("content", "")

        elapsed = round(time.monotonic() - start, 2)
        logger.info(f"[report_gen] Ollama call completed in {elapsed}s ({len(full_text)} chars)")
        return full_text.strip(), False

    except ImportError:
        logger.error("[report_gen] ollama library not installed. Run: pip install ollama")
        return "", True
    except Exception as exc:
        logger.warning(f"[report_gen] Ollama call failed: {exc}")
        return "", True


def _get_ollama_model(flags: dict) -> tuple[str, str]:
    """Return (primary_model, fallback_model) from feed_flags."""
    return (
        flags.get("OLLAMA_MODEL", "mistral:7b-instruct-q4_K_M"),
        flags.get("OLLAMA_FALLBACK_MODEL", "llama3:8b-instruct-q4_0"),
    )


# =============================================================================
# SECTION 3 — CALL 1: METRIC TRANSLATION
# =============================================================================

_METRIC_TRANSLATION_SYSTEM = """You are a plain-language translator for a Nigerian land risk screening system.
You receive technical GIS measurements and translate them into clear, jargon-free consequence statements.
Rules:
- Write in second person ("Your land is...", "This parcel...")
- Never say the land is safe to buy or that there is no risk
- Never state or imply that titles or documents have been verified
- Never invent data — only translate what is given to you
- Keep each consequence to one sentence
- NEVER use hyphens (-) in your output text. Write phrases as full words instead.
- Output JSON only — no prose, no markdown"""

def _build_metric_translation_prompt(
    gis: GISAnalysisOutput,
    risk: RiskAssessOutput,
    area_ha: float | None = None,
    state: str | None = None,
) -> str:
    from core.units import ha_to_area_display
    slope_val = f"{gis.slope_pct:.1f}" if gis.slope_pct is not None else "N/A"
    elev_val = f"{gis.elevation_m:.1f}" if gis.elevation_m is not None else "N/A"
    ndwi_val = f"{gis.ndwi:.2f}" if gis.ndwi is not None else "N/A"
    outfall_status = "Connected" if gis.outfall_connected else "Not Connected"

    # Nigerian-native area display
    area_display = "N/A"
    if area_ha:
        ad = ha_to_area_display(area_ha, state=state)
        area_display = ad["display_simple"]

    inference_payload = (
        f"Area={area_display}, "
        f"Slope={slope_val}%, Elevation={elev_val}m, "
        f"NDWI={ndwi_val}, Outfall={outfall_status}."
    )
    return (
        f"Translate these land risk measurements into plain-English consequence statements. "
        f"Output JSON with one key per metric. Example: "
        f'{{"elevation_m": "Your land sits at X metres above sea level, which means..."}}\n\n'
        f"Metrics: {inference_payload}"
    )


_METRIC_FALLBACK_TEMPLATES: dict[str, str] = {
    "elevation_m": (
        "Elevation data is available for this parcel. "
        "Elevation affects flood risk and foundation design requirements."
    ),
    "slope_pct": (
        "Slope information is available. "
        "Slope affects drainage patterns and construction suitability."
    ),
    "distance_to_river_m": (
        "River proximity data has been measured. "
        "Distance to the nearest watercourse is a key flood risk factor."
    ),
    "flood_proximity_score": (
        "A flood risk proximity score has been computed from multiple data sources."
    ),
    "ndwi": (
        "Satellite water presence data has been assessed for this parcel area."
    ),
    "distance_to_road_m": (
        "Road access distance has been measured. "
        "Road access affects construction logistics and property value."
    ),
    "terrain_suitability": (
        "Terrain suitability for development has been assessed based on slope and elevation."
    ),
    "flood_risk": (
        "Flood risk has been assessed based on elevation, river proximity, and satellite data."
    ),
}


def call_metric_translation(
    gis: GISAnalysisOutput,
    risk: RiskAssessOutput,
    model: str,
    timeout_s: int,
    stream: bool,
    area_ha: float | None = None,
    state: str | None = None,
    llm_provider: str | None = None,
    llm_api_key: str | None = None,
) -> tuple[dict, bool] | MCPErrorResponse:
    """
    Call 1 — Metric Translation.
    Returns (plain_english_metrics_dict, timeout_fired).
    """
    prompt = _build_metric_translation_prompt(gis, risk, area_ha=area_ha, state=state)
    raw, timed_out = _llm_call(
        prompt=prompt,
        system=_METRIC_TRANSLATION_SYSTEM,
        model=model,
        timeout_s=timeout_s,
        stream=stream,
        max_tokens=450,
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
    )

    if timed_out or not raw:
        return MCPErrorResponse(
            error_code="LLM_TIMEOUT",
            instruction="[PIPELINE HALTED] Call 1 (Metric Translation) timed out. The local Ollama model failed to respond within the allowed window.",
            run_id="system",
            stage=PipelineStage.REPORT_GEN,
        )

    # Parse JSON from response
    try:
        # Strip markdown fences if present
        clean = re.sub(r"```(?:json)?", "", raw).strip()
        metrics = json.loads(clean)
        # Scrub each value
        return {k: scrub_output(str(v)) for k, v in metrics.items()}, False
    except (json.JSONDecodeError, ValueError):
        return MCPErrorResponse(
            error_code="LLM_PARSE_ERROR",
            instruction="[PIPELINE HALTED] Call 1 (Metric Translation) returned invalid JSON.",
            run_id="system",
            stage=PipelineStage.REPORT_GEN,
        )


# =============================================================================
# SECTION 4 — CALL 2: EXECUTIVE SUMMARY
# =============================================================================

_EXECUTIVE_SUMMARY_SYSTEM = """You are a professional land risk analyst writing authoritative, confident advisory summaries for Nigerian land buyers.
Rules:
- Write exactly 3 sentences for the executive summary.
- Be highly confident and factual based on the data provided. NEVER undermine the report or claim data is limited or insufficient.
- NEVER mention title verification, land registry, or ownership status. Those are explicitly out of scope for this spatial report.
- Remember causality: The Traffic Light rating is the RESULT of the metrics (e.g. flood risk causes a RED rating). Do not say the rating causes the risk.
- Do not add your own legal disclaimers (the system automatically appends them).
- Do not use markdown, bullet points, or headers in your output.
- NEVER use hyphens (-) anywhere in your output. Write all compound phrases and ranges as full words with spaces."""


def _build_executive_summary_prompt(
    plain_english_metrics: dict,
    traffic_light: str,
    advisory_flags: list[str],
    growth_potential: str,
) -> str:
    flags_text = "\n".join(f"- {f}" for f in advisory_flags[:5])  # cap at 5 to control tokens
    # Truncate metrics context and use string interpolation to prevent Ollama timeout
    metrics_bullets = "\n".join(f"- {k}: {v}" for k, v in list(plain_english_metrics.items())[:4])

    return (
        f"Write a 3-sentence executive summary and a 2-sentence AI recommendation "
        f"for a land parcel with the following risk profile.\n\n"
        f"Traffic light rating: {traffic_light}\n"
        f"Growth potential: {growth_potential}\n\n"
        f"Key metrics:\n"
        f"{metrics_bullets}\n\n"
        f"Advisory flags:\n{flags_text}\n\n"
        f"Output format:\n"
        f"EXECUTIVE_SUMMARY: [3 sentences]\n"
        f"RECOMMENDATION: [2 sentences — end with the mandatory disclaimer]"
    )


def _parse_executive_summary_response(raw: str) -> tuple[str, str]:
    """Extract EXECUTIVE_SUMMARY and RECOMMENDATION from Ollama response."""
    exec_summary = ""
    ai_rec = ""
    for line in raw.splitlines():
        if line.upper().startswith("EXECUTIVE_SUMMARY:"):
            exec_summary = line.split(":", 1)[1].strip()
        elif line.upper().startswith("RECOMMENDATION:") or line.upper().startswith("AI_RECOMMENDATION:"):
            ai_rec = line.split(":", 1)[1].strip()

    # Fallback: use raw as exec summary if parse fails
    if not exec_summary and raw:
        exec_summary = raw[:500].strip()

    return exec_summary, ai_rec


_EXECUTIVE_SUMMARY_TEMPLATE = (
    "This land parcel has been assessed across flood risk, terrain suitability, "
    "infrastructure access, and growth potential. "
    "Multiple risk indicators were computed from offline satellite and geospatial data. "
    "Please review all advisory flags carefully before proceeding."
)

_AI_RECOMMENDATION_TEMPLATE = (
    "Based on the assessed risk profile, engage qualified professionals to verify "
    "ground conditions and legal title before committing any funds. "
    "This report is advisory only. Engage a SURCON-registered surveyor and a qualified "
    "property lawyer before committing funds."
)


def call_executive_summary(
    plain_english_metrics: dict,
    traffic_light: str,
    advisory_flags: list[str],
    growth_potential: str,
    model: str,
    timeout_s: int,
    stream: bool,
    outfall_status: str = "Connected",
    llm_provider: str | None = None,
    llm_api_key: str | None = None,
) -> tuple[str, str, bool]:
    """
    Call 2 — Executive Summary.
    Returns (executive_summary, ai_recommendation, timeout_fired).
    """
    prompt = _build_executive_summary_prompt(
        plain_english_metrics, traffic_light, advisory_flags, growth_potential
    )
    raw, timed_out = _llm_call(
        prompt=prompt,
        system=_EXECUTIVE_SUMMARY_SYSTEM,
        model=model,
        timeout_s=timeout_s,
        stream=stream,
        max_tokens=350,
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
    )

    if timed_out or not raw:
        logger.warning("[LLM_TIMEOUT] Call 2 timed out — using deterministic fallback generator")
        
        if advisory_flags:
            # Piece together advisory flags into a summary
            bullets = " ".join([f"• {flag.split(':')[0].replace('HIGH - ', '').replace('CRITICAL - ', '').replace('MODERATE - ', '')}" for flag in advisory_flags[:4]])
            fallback_text = f"Automated Assessment: This parcel has been evaluated deterministically due to system load. Key risk indicators identified: {bullets}."
        else:
            fallback_text = "Automated Assessment: This parcel has been evaluated deterministically. No critical advisory flags were detected in the primary geospatial sweep."
            
        return fallback_text, _AI_RECOMMENDATION_TEMPLATE, True

    exec_summary, ai_rec = _parse_executive_summary_response(raw)

    # Ensure mandatory disclaimer is always in ai_recommendation
    disclaimer = (
        "This report is advisory only. Engage a SURCON-registered surveyor "
        "and a qualified property lawyer before committing funds."
    )
    if disclaimer.lower() not in (ai_rec or "").lower():
        ai_rec = (ai_rec or _AI_RECOMMENDATION_TEMPLATE) + " " + disclaimer

    return scrub_output(exec_summary), scrub_output(ai_rec), False


# =============================================================================
# SECTION 5 — SCHEMA ASSEMBLY (all structured fields — no LLM)
# =============================================================================

def assemble_report(
    coord: CoordExtractOutput,
    gis: GISAnalysisOutput,
    risk: RiskAssessOutput,
    growth: SuitabilityGrowthOutput,
    feed: NormalisedFeedSchema,
    persona_mode: PersonaMode,
    plain_english_metrics: dict,
    executive_summary: str,
    ai_recommendation: str,
    snapshot_path: str | None,
    ollama_model_used: str,
    llm_timeout_fired: bool,
    pipeline_start_ms: float,
) -> ReportSchema:
    """
    Populate the full v2.0 ReportSchema from all upstream agent outputs.
    Python fills every field — LLM text is injected into prose fields only.
    """
    import uuid

    report_id = coord.run_id
    now = datetime.now(timezone.utc).isoformat()

    # ── Location context ───────────────────────────────────────────────────────
    location = LocationContext(
        lga=feed.supplemental_gis.lga_confirmed or coord.lga,
        state=feed.supplemental_gis.state_confirmed or coord.state,
        community=None,
    )

    # ── Parcel geometry ────────────────────────────────────────────────────────
    parcel_geometry = ParcelGeometry(
        centroid=coord.centroid,
        coordinates=coord.coordinates,
        computed_area_ha=coord.computed_area_ha,
        stated_area_ha=coord.stated_area_ha,
        location_context=location,
        health_check_stats=coord.health_check_stats,
    )

    # ── Coordinate validation ──────────────────────────────────────────────────
    coord_validation = CoordinateValidation(
        detected_crs=coord.detected_crs.value,
        crs_confidence=coord.crs_confidence,
        is_inside_nigeria=coord.is_inside_nigeria,
        area_discrepancy_pct=coord.area_discrepancy_pct,
        warnings=coord.warnings,
    )

    # ── Terrain assessment ─────────────────────────────────────────────────────
    terrain = TerrainAssessment(
        elevation_m=gis.elevation_m,
        steepness_of_land=gis.slope_pct,
        terrain_difficulty=gis.terrain_difficulty.value if gis.terrain_difficulty else None,
        suitability=risk.terrain_suitability.value,
        drainage_block_warning=risk.drainage_block_warning,
        outfall_connected=gis.outfall_connected,
        outfall_distance_m=gis.outfall_distance_m,
        outfall_asset_type=gis.outfall_asset_type,
    )

    # ── Flood risk metrics ─────────────────────────────────────────────────────
    flood = FloodRiskMetrics(
        level=risk.flood_risk,
        score=gis.flood_proximity_score,
        reason_in_plain_english=plain_english_metrics.get(
            "flood_risk", risk.flood_risk_reason
        ),
        distance_to_nearest_river=gis.distance_to_river_m,
        water_presence_index=gis.ndwi,
    )

    # ── Accessibility & development ────────────────────────────────────────────
    access = AccessibilityDevelopment(
        distance_to_road_m=gis.distance_to_road_m,
        road_category=gis.road_access_category.value if gis.road_access_category else None,
        suitability_matrix=risk.development_suitability,
    )

    # ── Encroachment ──────────────────────────────────────────────────────────
    encroachment = EncroachmentRecord(
        flag=gis.encroachment_flag,
        detail=gis.encroachment_detail,
        satellite_epoch_comparison="2019 vs 2023 Sentinel-2 NDVI" if gis.ndvi is not None else None,
    )

    # ── Growth potential ───────────────────────────────────────────────────────
    growth_record = GrowthPotentialRecord(
        level=growth.growth_potential,
        urban_expansion_score=growth.urban_expansion_score,
        infrastructure_proximity=growth.infrastructure_proximity,
        summary_notes=plain_english_metrics.get("growth_potential", growth.growth_notes),
    )

    # ── Title record ───────────────────────────────────────────────────────────
    title = TitleRecord(
        title_status=(
            feed.title_data.title_status.value
            if feed.title_data.title_status
            else "Not verified via live registry."
        ),
        title_type=(
            feed.title_data.title_type.value if feed.title_data.title_type else None
        ),
        acquisition_flag=feed.title_data.acquisition_flag,
        source_verified=feed.title_data.source_verified,
    )

    # ── Combined advisory flags (FIX 2.5) ──────────────────────────────────────
    all_advisory = risk.advisory_flags.copy()
    if growth.growth_notes and growth.growth_notes not in all_advisory:
        all_advisory.append(growth.growth_notes)
        
    try:
        import os, json
        from pathlib import Path
        lga_name = feed.supplemental_gis.lga_confirmed or coord.lga
        state_name = feed.supplemental_gis.state_confirmed or coord.state
        registry_path = Path("data/registry_locations.json")
        registry_location = "State Ministry of Lands / Surveyor General's Office"
        
        if registry_path.exists():
            with open(registry_path, "r") as f:
                regs = json.load(f)
                state_data = regs.get(state_name)
                if state_data:
                    registry_location = state_data.get(lga_name, state_data.get("default", registry_location))
                else:
                    registry_location = regs.get("default", registry_location)
                    
        all_advisory.append(f"MODERATE - Localized Registry Search: Visit {registry_location} to conduct an in-person manual search on this coordinate's charting status.")
    except Exception as e:
        logger.warning(f"Failed to load localized registry: {e}")

    # ── Summary ───────────────────────────────────────────────────────────────
    total_ms = int((time.monotonic() - pipeline_start_ms) * 1000)
    summary = ReportSummary(
        traffic_light=risk.traffic_light,
        executive_summary=executive_summary,
        ai_recommendation=ai_recommendation,
        overall_risk_score=risk.overall_risk_score,
    )

    feed_dict = feed.model_dump()
    from core.units import ha_to_area_display
    ad = ha_to_area_display(coord.computed_area_ha, state=coord.state)
    feed_dict["area_display"] = ad

    return ReportSchema(
        meta=ReportMeta(report_id=report_id, generated_at=now),
        parcel_geometry=parcel_geometry,
        coordinate_validation=coord_validation,
        terrain_assessment=terrain,
        flood_risk_metrics=flood,
        accessibility_development=access,
        encroachment=encroachment,
        growth_potential=growth_record,
        title_record=title,
        advisory_flags=all_advisory,
        summary=summary,
        premium_elevation_profile=gis.premium_elevation_profile,
        pipeline_version="2.0",
        persona_mode=persona_mode,
        ollama_model_used=ollama_model_used,
        llm_timeout_fired=llm_timeout_fired,
        feed_context=feed_dict,
    )


# =============================================================================
# SECTION 6 — MAIN RUN FUNCTION
# =============================================================================

def run(
    coord: CoordExtractOutput,
    gis: GISAnalysisOutput,
    risk: RiskAssessOutput,
    growth: SuitabilityGrowthOutput,
    feed: NormalisedFeedSchema,
    persona_mode: PersonaMode = PersonaMode.EVERYDAY_BUYER,
    snapshot_path: str | None = None,
    pipeline_start_ms: float | None = None,
    llm_provider: str | None = None,
    llm_api_key: str | None = None,
    llm_grounding: str | None = None,
) -> ReportSchema | MCPErrorResponse:
    """
    Main entrypoint for the ReportGen agent.
    Makes exactly 2 LLM calls. Returns ReportSchema.
    """
    if pipeline_start_ms is None:
        pipeline_start_ms = time.monotonic()

    flags = _load_flags()
    model, fallback_model = _get_ollama_model(flags)
    timeout_s = max(int(flags.get("OLLAMA_TIMEOUT_SECONDS", 60)), 60)
    stream    = bool(flags.get("OLLAMA_STREAM", True))
    any_timeout = False

    logger.info(f"[report_gen] Starting report generation. Model: {model}")

    # ── CALL 1: METRIC TRANSLATION ────────────────────────────────────────────
    call1_result = call_metric_translation(
        gis=gis,
        risk=risk,
        model=model,
        timeout_s=timeout_s,
        stream=stream,
        area_ha=coord.computed_area_ha,
        state=coord.state,
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
    )
    
    if isinstance(call1_result, MCPErrorResponse):
        any_timeout = True
        logger.warning(f"Call 1 failed with primary model: {call1_result.error_code}. Trying fallback.")
        # Try fallback model if primary timed out
        call1_result = call_metric_translation(
            gis=gis, risk=risk,
            model=fallback_model, timeout_s=timeout_s, stream=stream,
        )
        if isinstance(call1_result, MCPErrorResponse):
            logger.error("Call 1 failed with fallback model as well. Halting pipeline.")
            return call1_result
            
    plain_english_metrics, call1_timeout = call1_result

    # ── CALL 2: EXECUTIVE SUMMARY ─────────────────────────────────────────────
    call2_result = call_executive_summary(
        plain_english_metrics=plain_english_metrics,
        traffic_light=risk.traffic_light.value,
        advisory_flags=risk.advisory_flags,
        growth_potential=growth.growth_potential.value,
        model=model,
        timeout_s=timeout_s,
        stream=stream,
        outfall_status="Connected" if gis.outfall_connected else "Not Connected",
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
    )
    
    if isinstance(call2_result, MCPErrorResponse):
        any_timeout = True
        logger.warning(f"Call 2 failed with primary model: {call2_result.error_code}. Trying fallback.")
        call2_result = call_executive_summary(
            plain_english_metrics=plain_english_metrics,
            traffic_light=risk.traffic_light.value,
            advisory_flags=risk.advisory_flags,
            growth_potential=growth.growth_potential.value,
            model=fallback_model,
            timeout_s=timeout_s,
            stream=stream,
            outfall_status="Connected" if gis.outfall_connected else "Not Connected",
            llm_provider=llm_provider,
            llm_api_key=llm_api_key,
        )
        if isinstance(call2_result, MCPErrorResponse):
            logger.error("Call 2 failed with fallback model as well.")
            return call2_result

    executive_summary, ai_recommendation, call2_timeout = call2_result
    if call2_timeout:
        any_timeout = True

    # ── ASSEMBLE FULL REPORT SCHEMA ───────────────────────────────────────────
    model_used = model
    report = assemble_report(
        coord=coord,
        gis=gis,
        risk=risk,
        growth=growth,
        feed=feed,
        persona_mode=persona_mode,
        plain_english_metrics=plain_english_metrics,
        executive_summary=executive_summary,
        ai_recommendation=ai_recommendation,
        snapshot_path=snapshot_path,
        ollama_model_used=model_used,
        llm_timeout_fired=any_timeout,
        pipeline_start_ms=pipeline_start_ms,
    )

    total_ms = int((time.monotonic() - pipeline_start_ms) * 1000)
    logger.info(
        f"[report_gen] Report assembled in {total_ms}ms. "
        f"traffic_light={report.summary.traffic_light.value} "
        f"llm_timeout_fired={any_timeout}"
    )

    return report
