"""
LandIQ — core/pipeline_stream.py
Async streaming wrapper for the synchronous multi-agent pipeline.
Runs each agent in a thread pool and yields SSE events.
"""
import asyncio
import json
import logging
from typing import AsyncGenerator

from core.schemas import MCPErrorResponse, PipelineStage
from core.gate import update_session_stage, get_session
import core.pipeline as sync_pipeline

logger = logging.getLogger("landiq.pipeline_stream")

def _sse_event(event_type: str, data: dict) -> str:
    """Format data as Server-Sent Event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

async def stream_pipeline(
    run_id: str,
    persona_mode: str,
    snapshot_path: str | None = None,
    llm_provider: str | None = None,
    llm_api_key: str | None = None,
    llm_grounding: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Executes the pipeline stages sequentially but yields progress events back to the client.
    Each agent is run in a separate thread to prevent blocking the asyncio event loop.
    """
    yield _sse_event("pipeline_started", {
        "report_id": run_id,
        "message": "Starting analysis..."
    })

    session = get_session(run_id)
    if not session or not session.coord_extract:
        yield _sse_event("error", {"message": "Session or coordinate data not found."})
        return

    coord_output = session.coord_extract
    centroid = {"lat": coord_output.centroid.lat, "lng": coord_output.centroid.lng}
    
    from core.adapters import AdapterLayer
    from agents.gis_analysis import detect_state_from_centroid
    
    # ── STAGE 1: GEOSPATIAL ──────────────────────────────────────────────
    yield _sse_event("stage_progress", {
        "stage": "geospatial",
        "message": "Fetching satellite data..."
    })
    update_session_stage(run_id, PipelineStage.ADAPTER_FETCH)
    
    bbox = sync_pipeline._compute_bbox(coord_output.coordinates)
    state = detect_state_from_centroid(coord_output.centroid.lat, coord_output.centroid.lng)
    
    feed_schema = await asyncio.to_thread(
        AdapterLayer().fetch, centroid=centroid, bbox=bbox, state=state
    )

    update_session_stage(run_id, PipelineStage.GIS_ANALYSIS)
    
    from agents.gis_analysis import run as gis_run
    
    # This runs the newly parallelized GIS analysis (elevation, rivers, etc.)
    gis_result = await asyncio.to_thread(gis_run, coord_output=coord_output, feed_schema=feed_schema)
    if isinstance(gis_result, MCPErrorResponse):
        yield _sse_event("error", {"message": f"GIS Analysis failed: {gis_result.instruction}"})
        return
        
    # We can stream sections directly now that GIS data is ready
    yield _sse_event("section_ready", {
        "section": "elevation",
        "data": {"elevation_m": gis_result.terrain.elevation_m}
    })
    
    # ── STAGE 2: RISK ASSESS ──────────────────────────────────────────────
    yield _sse_event("stage_progress", {
        "stage": "risk_summary",
        "message": "Computing risk scores..."
    })
    update_session_stage(run_id, PipelineStage.RISK_ASSESS)
    
    from agents.risk_assess import run as risk_run
    risk_result = await asyncio.to_thread(
        risk_run, coord_output=coord_output, gis_output=gis_result, feed_schema=feed_schema, persona_mode=persona_mode
    )
    if isinstance(risk_result, MCPErrorResponse):
        yield _sse_event("error", {"message": f"Risk Assessment failed: {risk_result.instruction}"})
        return

    yield _sse_event("section_ready", {
        "section": "risk_summary",
        "data": risk_result.model_dump()
    })

    # ── STAGE 3: SUITABILITY & GROWTH ──────────────────────────────────────
    update_session_stage(run_id, PipelineStage.SUITABILITY)
    from agents.suitability_growth import run as growth_run
    growth_result = await asyncio.to_thread(
        growth_run, coord_output=coord_output, gis_output=gis_result, risk_output=risk_result, feed_schema=feed_schema
    )
    if isinstance(growth_result, MCPErrorResponse):
        yield _sse_event("error", {"message": f"Suitability Growth failed: {growth_result.instruction}"})
        return
        
    # ── STAGE 4: REPORT GEN (LLM) ──────────────────────────────────────────
    yield _sse_event("stage_progress", {
        "stage": "llm",
        "message": "Writing your report..."
    })
    update_session_stage(run_id, PipelineStage.REPORT_GEN)
    
    from agents.report_gen import run as report_run
    report_result = await asyncio.to_thread(
        report_run, coord=coord_output, gis=gis_result, risk=risk_result, growth=growth_result, feed=feed_schema, persona_mode=persona_mode, llm_provider=llm_provider, llm_api_key=llm_api_key, llm_grounding=llm_grounding
    )
    if isinstance(report_result, MCPErrorResponse):
        yield _sse_event("error", {"message": f"Report Generation failed: {report_result.instruction}"})
        return

    # ── SAVE & COMPLETE ──────────────────────────────────────────────────
    update_session_stage(run_id, PipelineStage.COMPLETE)
    from core.history_manager import save_report
    
    await asyncio.to_thread(
        save_report,
        report=report_result,
        snapshot_path=snapshot_path,
        snapshot_thumb_path=None,
        total_generation_ms=15000,
        user_id=session.user_id
    )

    # Set sessions to completed status
    conn = get_session(run_id) # Just retrieving the session again to verify
    if session:
        from core.gate import _get_conn
        c = _get_conn()
        try:
            c.execute("UPDATE sessions SET status = 'completed' WHERE run_id = ?", (run_id,))
            c.commit()
        finally:
            c.close()

    yield _sse_event("report_complete", report_result.model_dump())
