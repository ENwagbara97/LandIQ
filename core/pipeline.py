"""
LandIQ — core/pipeline.py
Main Pipeline Orchestrator

Coordinates all agents in strict order:
  Gate confirmed? → AdapterLayer → GISAnalysis → RiskAssess → SuitabilityGrowth → ReportGen

Every agent output is Pydantic-validated before the next agent receives it.
Any MCPErrorResponse from any agent aborts the pipeline immediately.
The pipeline never swallows errors silently.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from core.schemas import (
    CoordExtractOutput,
    MCPErrorResponse,
    PersonaMode,
    PipelineStage,
    ReportSchema,
)

logger = logging.getLogger("landiq.pipeline")


def run_pipeline(
    coord_output: CoordExtractOutput,
    persona_mode: str = "EVERYDAY_BUYER",
    snapshot_path: str | None = None,
    skip_gate: bool = False,
    llm_provider: str | None = None,
    llm_api_key: str | None = None,
    llm_grounding: str | None = None,
) -> ReportSchema | MCPErrorResponse:
    """
    Execute the full analysis pipeline from CoordExtractOutput → ReportSchema.

    Args:
        coord_output : Validated CoordExtractOutput (confirmed by gate).
        persona_mode : Active persona string.
        snapshot_path: Path to pre-captured snapshot PNG (from gate.confirm()).
        skip_gate    : True for golden tests only — bypasses gate confirmation check.

    Returns:
        ReportSchema on success.
        MCPErrorResponse on any pipeline failure.
    """
    start_ms = time.monotonic()
    run_id = coord_output.run_id
    pm = PersonaMode(persona_mode)

    logger.info(f"[pipeline] run_id={run_id[:8]} Starting pipeline. persona={persona_mode}")

    # ── GATE CHECK ─────────────────────────────────────────────────────────────
    if not skip_gate:
        from core.gate import is_confirmed, update_session_stage
        if not is_confirmed(run_id):
            return MCPErrorResponse(
                error_code="GATE_NOT_CONFIRMED",
                instruction=(
                    "Analysis cannot proceed until you confirm your land boundary. "
                    "Please review the map and click 'Yes, this is my land.'"
                ),
                run_id=run_id,
                stage=PipelineStage.GATE,
            )
        update_session_stage(run_id, PipelineStage.ADAPTER_FETCH)

    # ── STEP 1: ADAPTER LAYER ─────────────────────────────────────────────────
    from core.adapters import AdapterLayer
    from agents.gis_analysis import detect_state_from_centroid

    logger.info(f"[pipeline] run_id={run_id[:8]} Step: AdapterLayer.fetch()")
    centroid = {"lat": coord_output.centroid.lat, "lng": coord_output.centroid.lng}
    bbox = _compute_bbox(coord_output.coordinates)
    state = detect_state_from_centroid(coord_output.centroid.lat, coord_output.centroid.lng)

    feed_schema = AdapterLayer().fetch(centroid=centroid, bbox=bbox, state=state)

    if not skip_gate:
        from core.gate import update_session_stage
        update_session_stage(run_id, PipelineStage.GIS_ANALYSIS)

    # ── STEP 2: GIS ANALYSIS ──────────────────────────────────────────────────
    from agents.gis_analysis import run as gis_run

    logger.info(f"[pipeline] run_id={run_id[:8]} Step: GISAnalysis")
    gis_result = gis_run(coord_output=coord_output, feed_schema=feed_schema)

    if isinstance(gis_result, MCPErrorResponse):
        logger.error(f"[pipeline] GISAnalysis failed: {gis_result.error_code}")
        return gis_result

    if not skip_gate:
        from core.gate import update_session_stage
        update_session_stage(run_id, PipelineStage.RISK_ASSESS)

    # ── STEP 3: RISK ASSESSMENT ───────────────────────────────────────────────
    from agents.risk_assess import run as risk_run

    logger.info(f"[pipeline] run_id={run_id[:8]} Step: RiskAssess")
    risk_result = risk_run(
        coord_output=coord_output,
        gis_output=gis_result,
        feed_schema=feed_schema,
        persona_mode=persona_mode,
    )

    if isinstance(risk_result, MCPErrorResponse):
        logger.error(f"[pipeline] RiskAssess failed: {risk_result.error_code}")
        return risk_result

    if not skip_gate:
        from core.gate import update_session_stage
        update_session_stage(run_id, PipelineStage.SUITABILITY)

    # ── STEP 4: SUITABILITY & GROWTH ─────────────────────────────────────────
    from agents.suitability_growth import run as growth_run

    logger.info(f"[pipeline] run_id={run_id[:8]} Step: SuitabilityGrowth")
    growth_result = growth_run(
        coord_output=coord_output,
        gis_output=gis_result,
        risk_output=risk_result,
        feed_schema=feed_schema,
    )

    if isinstance(growth_result, MCPErrorResponse):
        logger.error(f"[pipeline] SuitabilityGrowth failed: {growth_result.error_code}")
        return growth_result

    if not skip_gate:
        from core.gate import update_session_stage
        update_session_stage(run_id, PipelineStage.REPORT_GEN)

    # ── STEP 5: REPORT GENERATION ─────────────────────────────────────────────
    from agents.report_gen import run as report_run

    logger.info(f"[pipeline] run_id={run_id[:8]} Step: ReportGen (2 Ollama calls)")
    report = report_run(
        coord=coord_output,
        gis=gis_result,
        risk=risk_result,
        growth=growth_result,
        feed=feed_schema,
        persona_mode=pm,
        snapshot_path=snapshot_path,
        pipeline_start_ms=start_ms,
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
        llm_grounding=llm_grounding,
    )

    if isinstance(report, MCPErrorResponse):
        logger.error(f"[pipeline] ReportGen failed: {report.error_code}")
        return report

    # ── COMPLETE ──────────────────────────────────────────────────────────────
    total_ms = int((time.monotonic() - start_ms) * 1000)
    logger.info(
        f"[pipeline] run_id={run_id[:8]} COMPLETE in {total_ms}ms. "
        f"traffic_light={report.summary.traffic_light.value} "
        f"risk_score={report.summary.overall_risk_score}"
    )

    if not skip_gate:
        from core.gate import update_session_stage
        update_session_stage(run_id, PipelineStage.COMPLETE)

    return report


def _compute_bbox(coordinates: list[list[float]]) -> dict:
    lats = [pt[0] for pt in coordinates]
    lngs = [pt[1] for pt in coordinates]
    return {
        "min_lat": min(lats), "max_lat": max(lats),
        "min_lng": min(lngs), "max_lng": max(lngs),
    }
