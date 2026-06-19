"""
LandIQ — main.py
FastAPI Backend Server entry point.

Exposes REST APIs for coordinate upload, map previews, confirmation gates,
report queries, PDF and summary card generation, history, and Paystack hooks.
Runs the multi-agent pipeline in background tasks to prevent request timeouts.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
load_dotenv(override=True)

from pydantic import BaseModel
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.schemas import (
    CoordExtractOutput,
    MCPErrorResponse,
    PersonaMode,
    PipelineStage,
    ReportSchema,
    SessionState,
)

class ViewportParams(BaseModel):
    lat: float
    lng: float
    zoom: int

class PrintAdjustmentPayload(BaseModel):
    map_viewport: Optional[ViewportParams] = None

import core.gate as gate
import core.history_manager as history_manager
from core.pipeline import run_pipeline
from db.migrate import run_migrations

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("landiq.server")

app = FastAPI(
    title="LandIQ — Land Risk Intelligence Agent",
    description="Local-First Land Risk Screening System for Nigeria",
    version="2.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    """Run database migrations on server startup to ensure tables exist."""
    logger.info("[server] Starting up... applying database migrations.")
    run_migrations()


# =============================================================================
# BACKGROUND WORKERS
# =============================================================================

def _execute_pipeline_task(
    run_id: str,
    persona_mode: str,
    snapshot_path: str | None = None,
    llm_provider: str | None = None,
    llm_api_key: str | None = None,
    llm_grounding: str | None = None,
):
    """Background task to run the multi-agent pipeline to completion."""
    try:
        session = gate.get_session(run_id)
        if not session or not session.coord_extract:
            logger.error(f"[bg-task] Session {run_id} has no coordinate data.")
            return

        # Run the full pipeline
        report_or_error = run_pipeline(
            coord_output=session.coord_extract,
            persona_mode=persona_mode,
            snapshot_path=snapshot_path,
            skip_gate=True,  # Already confirmed by the gate
            llm_provider=llm_provider,
            llm_api_key=llm_api_key,
            llm_grounding=llm_grounding,
        )

        if isinstance(report_or_error, MCPErrorResponse):
            logger.error(f"[bg-task] Pipeline failed for run_id={run_id} with error: {report_or_error.error_code}")
            # Update session in DB
            conn = gate._get_conn()
            try:
                conn.execute(
                    "UPDATE sessions SET status = 'error', pipeline_stage = 'ERROR', error_detail = ? WHERE run_id = ?",
                    (report_or_error.instruction, run_id),
                )
                conn.commit()
            finally:
                conn.close()
        else:
            # Atomic save of completed report to SQLite
            logger.info(f"[bg-task] Pipeline completed successfully for run_id={run_id}. Saving report.")
            # Calculate total time
            # For simplicity, default to 15000 ms if not tracked
            history_manager.save_report(
                report=report_or_error,
                snapshot_path=snapshot_path,
                snapshot_thumb_path=None, # generated at save time
                total_generation_ms=15000,
                user_id=session.user_id,
            )
            # Update session to COMPLETE
            gate.update_session_stage(run_id, PipelineStage.COMPLETE)
            conn = gate._get_conn()
            try:
                conn.execute(
                    "UPDATE sessions SET status = 'completed' WHERE run_id = ?",
                    (run_id,),
                )
                conn.commit()
            finally:
                conn.close()

    except Exception as exc:
        logger.exception(f"[bg-task] Unexpected failure during background pipeline run: {exc}")
        conn = gate._get_conn()
        try:
            conn.execute(
                "UPDATE sessions SET status = 'error', pipeline_stage = 'ERROR', error_detail = ? WHERE run_id = ?",
                (str(exc), run_id),
            )
            conn.commit()
        finally:
            conn.close()


# =============================================================================
# REST ENDPOINTS
# =============================================================================

@app.post("/api/upload")
async def upload_coordinates(
    file: Optional[UploadFile] = File(None),
    raw_text: Optional[str] = Form(None),
    stated_area_ha: Optional[float] = Form(None),
    coordinate_hint: Optional[str] = Form(None),
    datum_label: Optional[str] = Form(None),
    persona_mode: str = Form("EVERYDAY_BUYER"),
    user_id: str = Form("anonymous"),
    vision_provider: Optional[str] = Form(None),
    vision_api_key: Optional[str] = Form(None),
):
    """
    Accept coordinates text, manual fields, or an uploaded survey plan.
    Initializes a session and runs Coordinate Extraction.
    """
    logger.info(f"[server] /api/upload received file={file.filename if file else None} raw_text={raw_text[:30] if raw_text else None}")

    file_bytes = None
    filename = None
    if file:
        file_bytes = await file.read()
        filename = file.filename

    # Extract OCR if it's an image/pdf so Cadastral Engine can use it
    if file_bytes and filename:
        from pathlib import Path
        ext = Path(filename).suffix.lower()
        if ext in (".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".bmp"):
            # Convert PDF to image bytes so Gemini Vision can read the scanned pixels directly
            if ext == ".pdf":
                try:
                    import fitz  # PyMuPDF
                    pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
                    page = pdf_doc.load_page(0)
                    pix = page.get_pixmap(dpi=200)
                    file_bytes = pix.tobytes("png")
                    filename = filename.replace(".pdf", ".png")
                except ImportError:
                    pass

            from agents.coord_extract import ocr_file
            try:
                raw_text = ocr_file(
                    file_bytes, filename,
                    vision_provider=vision_provider,
                    vision_api_key=vision_api_key,
                    stated_area_ha=stated_area_ha,
                )
                with open(r"C:\Users\Admin\Downloads\Land Risk Intelligent Agent\scratch\ocr_dump.txt", "w", encoding="utf-8") as f:
                    f.write(raw_text or "")
            except Exception:
                pass

    from agents.cadastral_engine import run as run_cadastral
    from core.schemas import MCPErrorResponse
    from agents.coord_extract import ocr_file

    # Only pass file_bytes to Cadastral Engine if it's a tabular file it can natively parse.
    # Images/PDFs are already OCR'd into raw_text above.
    cad_file_bytes = None
    cad_filename = None
    if file_bytes and filename:
        ext = Path(filename).suffix.lower()
        if ext in (".csv", ".xlsx", ".xls"):
            cad_file_bytes = file_bytes
            cad_filename = filename

    # Execute and retry on SANITY_CHECK_FAILED up to 2 times (total 3 attempts)
    max_attempts = 3
    cad_result = None
    for attempt in range(max_attempts):
        if attempt > 0:
            logger.info(f"[server] Retry attempt {attempt}/2 on sanity check failure...")
            # Re-run OCR file with stated_area_ha to get fresh/rechecked extraction
            if file_bytes and filename:
                ext = Path(filename).suffix.lower()
                if ext in (".jpg", ".jpeg", ".png", ".tiff", ".bmp"): # it was converted to png already if PDF
                    try:
                        raw_text = ocr_file(
                            file_bytes, filename,
                            vision_provider=vision_provider,
                            vision_api_key=vision_api_key,
                            stated_area_ha=stated_area_ha,
                        )
                        with open(r"C:\Users\Admin\Downloads\Land Risk Intelligent Agent\scratch\ocr_dump.txt", "w", encoding="utf-8") as f:
                            f.write(raw_text or "")
                    except Exception as exc:
                        logger.error(f"[server] Re-OCR failed: {exc}")

        cad_result = run_cadastral(
            raw_text=raw_text,
            file_bytes=cad_file_bytes,
            filename=cad_filename,
            stated_area_ha=stated_area_ha,
            property_owner="Unknown",
            location_context="Not specified",
        )

        # Stop retrying if result is not an error or is a non-sanity error
        if not isinstance(cad_result, MCPErrorResponse):
            break
        if cad_result.error_code != "SANITY_CHECK_FAILED":
            break

    if not isinstance(cad_result, MCPErrorResponse):
        import uuid
        from core.schemas import SessionState, CoordExtractOutput, Coordinate, PipelineStage, CRSName
        
        run_id = f"cad-{uuid.uuid4().hex[:8]}"
        data_dump = cad_result.model_dump()
        data_dump["run_id"] = run_id

        # Only create a session if the polygon is closed and valid
        if cad_result.polygon and cad_result.polygon.is_closed and len(cad_result.polygon.wgs84_coordinates) >= 3:
            coords = [[c[0], c[1]] for c in cad_result.polygon.wgs84_coordinates]
            center_lat = sum(c[0] for c in coords)/len(coords)
            center_lng = sum(c[1] for c in coords)/len(coords)

            epsg = 32632
            if "31" in cad_result.polygon.crs_input: epsg = 32631
            elif "33" in cad_result.polygon.crs_input: epsg = 32633

            crs_name = CRSName.UNKNOWN
            if "MINNA" in cad_result.polygon.crs_input.upper(): crs_name = CRSName.MINNA
            elif "31" in cad_result.polygon.crs_input: crs_name = CRSName.UTM_31N
            elif "32" in cad_result.polygon.crs_input: crs_name = CRSName.UTM_32N
            elif "33" in cad_result.polygon.crs_input: crs_name = CRSName.UTM_33N
            elif "WGS84" in cad_result.polygon.crs_input.upper(): crs_name = CRSName.WGS84

            computed_ha = cad_result.polygon.computed_area_ha
            if computed_ha <= 0: computed_ha = 0.001

            c_out = CoordExtractOutput(
                run_id=run_id,
                coordinates=coords,
                centroid=Coordinate(lat=center_lat, lng=center_lng),
                detected_crs=crs_name,
                crs_confidence=100.0,
                metric_analysis_epsg=epsg,
                is_inside_nigeria=True,
                computed_area_ha=computed_ha,
                stated_area_ha=(cad_result.polygon.stated_area_sqm / 10000.0) if cad_result.polygon.stated_area_sqm else None,
                area_discrepancy_pct=cad_result.polygon.area_discrepancy_pct,
                discovery_method=cad_result.extraction_meta.extraction_method,
                warnings=[]
            )

            try: pm = PersonaMode(persona_mode)
            except ValueError: pm = PersonaMode.EVERYDAY_BUYER

            from datetime import datetime, timezone
            session = SessionState(
                run_id=run_id,
                user_id=user_id,
                created_at=datetime.now(timezone.utc).isoformat(),
                coord_extract=c_out,
                pipeline_stage=PipelineStage.GATE,
                persona_mode=pm
            )
            gate._save_session(session)
            
        return {"cadastral_mode": True, "data": data_dump}

    # Allow fallback to the standard gate if Cadastral Engine couldn't handle it
    if cad_result.error_code not in ("INSUFFICIENT_SPATIAL_DATA", "UNSUPPORTED_FORMAT", "FILE_PARSE_ERROR"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=cad_result.model_dump(),
        )

    # Fallback to standard gate (for simple DD/DMS/KML coordinates)
    try:
        pm = PersonaMode(persona_mode)
    except ValueError:
        pm = PersonaMode.EVERYDAY_BUYER

    result = gate.initiate(
        raw_input=raw_text or "",
        file_bytes=file_bytes,
        filename=filename,
        user_id=user_id,
        persona_mode=pm,
        coordinate_hint=coordinate_hint,
        datum_label=datum_label,
        stated_area_ha=stated_area_ha,
    )

    if result.get("status") in ("error", "EXECUTION_HAZARD"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result,
        )

    return result


@app.get("/api/session/{run_id}")
async def get_session_status(run_id: str):
    """Retrieve the current session status and pipeline progress stage."""
    session = gate.get_session(run_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID {run_id} not found.",
        )

    return {
        "run_id": session.run_id,
        "user_id": session.user_id,
        "created_at": session.created_at,
        "confirmed": session.confirmed,
        "confirmed_at": session.confirmed_at,
        "status": session.status,
        "pipeline_stage": session.pipeline_stage.value,
        "error_detail": session.error_detail,
        "snapshot_path": session.snapshot_path,
    }


@app.get("/api/preview/{run_id}")
async def get_map_preview_html(run_id: str):
    """Serve an interactive Folium Map preview for the confirmation screen."""
    session = gate.get_session(run_id)
    if not session or not session.coord_extract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID {run_id} or coordinate extract not found.",
        )

    map_html = gate.generate_preview_map_html(session.coord_extract)
    return HTMLResponse(content=map_html)


from pydantic import BaseModel

class ConfirmPayload(BaseModel):
    responses: Optional[dict] = None
    map_viewport: Optional[dict] = None
    llm_provider: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_grounding: Optional[str] = None

@app.post("/api/confirm/{run_id}")
async def confirm_gate(
    run_id: str,
    background_tasks: BackgroundTasks,
    payload: ConfirmPayload,
):
    """
    User confirms the map preview coordinates.
    Saves dialog answers, triggers the static map snapshot,
    and starts the full multi-agent pipeline in a background thread.
    """
    logger.info(f"[server] /api/confirm/{run_id} received. Triggering background pipeline.")

    # Call gate.confirm which handles database update + snapshot generation
    confirm_result = gate.confirm(
        run_id=run_id,
        dialog_responses=payload.responses or {},
        trigger_snapshot=True,
        map_viewport=payload.map_viewport,
    )

    if confirm_result.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=confirm_result,
        )

    session = gate.get_session(run_id)
    if not session:
         raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found after confirmation.",
        )

    background_tasks.add_task(
        _execute_pipeline_task,
        run_id=run_id,
        persona_mode=session.persona_mode.value,
        snapshot_path=confirm_result.get("snapshot_path"),
        llm_provider=payload.llm_provider,
        llm_api_key=payload.llm_api_key,
        llm_grounding=payload.llm_grounding,
    )

    return confirm_result


@app.post("/api/reject/{run_id}")
async def reject_gate(run_id: str):
    """User rejects the map preview coordinates. Aborts analysis."""
    result = gate.reject(run_id)
    if result.get("status") == "error":
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result,
        )
    return result


@app.get("/api/report/{report_id}")
async def get_report(report_id: str):
    """Fetch the full, structured JSON report from SQLite database."""
    report = history_manager.get_report(report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with ID {report_id} not found.",
        )
    return report


@app.post("/api/report/{report_id}/generate-pdf")
async def generate_adjusted_pdf(
    report_id: str,
    payload: PrintAdjustmentPayload,
    include_elevation_profile: bool = False,
    mode: str = "expert",
):
    """Regenerate snapshot with manual framing and compile PDF."""
    report = history_manager.get_report(report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found.",
        )

    try:
        from core.pdf_generator import generate_pdf
        from core.snapshot_engine import capture as generate_snapshot
        
        row = history_manager.get_report_row(report_id)
        session_state = gate._load_session(report_id) # The run_id is often the report_id

        # Re-generate snapshot if map_viewport provided
        snapshot_path = row.get("snapshot_path") if row else None
        if payload.map_viewport and session_state and session_state.coord_extract:
            map_view = {
                "lat": payload.map_viewport.lat,
                "lng": payload.map_viewport.lng,
                "zoom": payload.map_viewport.zoom
            }
            logger.info(f"Regenerating snapshot for {report_id} with custom viewport {map_view}")
            coords = [[pt[0], pt[1]] for pt in session_state.coord_extract.coordinates]
            centroid_dict = {"lat": session_state.coord_extract.centroid.lat, "lng": session_state.coord_extract.centroid.lng}
            snapshot_path = generate_snapshot(
                coordinates=coords,
                centroid=centroid_dict,
                report_id=report_id,
                map_viewport=map_view
            )
            # Update DB with new snapshot path
            history_manager.update_snapshot_path(report_id, str(snapshot_path))

        sources = history_manager.get_data_sources(report_id)
        
        pdf_path = generate_pdf(
            report=report,
            data_sources=sources,
            snapshot_path=snapshot_path,
            include_elevation_profile=include_elevation_profile,
            mode=mode,
        )

        history_manager.log_export(
            report_id=report_id,
            export_format="pdf",
            export_path=str(pdf_path),
            persona_mode=report.persona_mode.value,
            file_size_bytes=pdf_path.stat().st_size if pdf_path.exists() else None,
        )

        headers = {
            "Content-Disposition": f"attachment; filename=\"{pdf_path.name}\""
        }
        return FileResponse(
            path=str(pdf_path),
            filename=pdf_path.name,
            headers=headers,
            media_type="application/pdf",
        )
    except Exception as exc:
        logger.exception(f"[server] Failed to generate adjusted report PDF: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate adjusted report PDF: {str(exc)}",
        )


@app.get("/api/report/{report_id}/pdf")
@app.get("/api/report/{report_id}/report.pdf")
async def get_report_pdf(
    report_id: str,
    persona: Optional[str] = None,
    include_elevation_profile: bool = False,
    mode: str = "expert",
):
    """
    Download a WeasyPrint-rendered PDF of the report.
    If 'persona' query param is passed, renders using that persona's filter.
    """
    report = history_manager.get_report(report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found.",
        )

    # If a custom persona is requested, update it at render time
    if persona:
        try:
            report.persona_mode = PersonaMode(persona.upper())
        except ValueError:
            pass

    # Use pdf_generator to create the PDF
    try:
        from core.pdf_generator import generate_pdf
        # Get data sources
        sources = history_manager.get_data_sources(report_id)
        # Load DB row to get snapshot_path
        row = history_manager.get_report_row(report_id)
        snapshot_path = row.get("snapshot_path") if row else None

        # Call pdf generator
        pdf_path = generate_pdf(
            report=report,
            data_sources=sources,
            snapshot_path=snapshot_path,
            include_elevation_profile=include_elevation_profile,
            mode=mode,
        )

        # Log export audit trail
        history_manager.log_export(
            report_id=report_id,
            export_format="pdf",
            export_path=str(pdf_path),
            persona_mode=report.persona_mode.value,
            file_size_bytes=pdf_path.stat().st_size if pdf_path.exists() else None,
        )

        headers = {
            "Content-Disposition": f"attachment; filename=\"{pdf_path.name}\""
        }
        return FileResponse(
            path=str(pdf_path),
            filename=pdf_path.name,
            headers=headers,
            media_type="application/pdf",
        )
    except Exception as exc:
        logger.exception(f"[server] Failed to generate report PDF: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate report PDF: {str(exc)}",
        )


@app.get("/api/report/{report_id}/export/{export_format}")
async def get_report_export(report_id: str, export_format: str, persona: Optional[str] = None):
    """
    Export report as JSON, PNG card, or other formats.
    export_format can be: 'json' or 'png'.
    """
    report = history_manager.get_report(report_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")

    if persona:
        try:
            report.persona_mode = PersonaMode(persona.upper())
        except ValueError:
            pass

    export_format = export_format.lower()

    if export_format == "json":
        json_path = Path(history_manager.ROOT_DIR) / "reports" / f"report_{report_id}.json"
        json_path.write_text(report.model_dump_json(), encoding="utf-8")
        history_manager.log_export(
            report_id=report_id,
            export_format="json",
            export_path=str(json_path),
            persona_mode=report.persona_mode.value,
            file_size_bytes=json_path.stat().st_size,
        )
        return report

    elif export_format == "png":
        try:
            from core.pdf_generator import generate_png_card
            # Load DB row to get snapshot_path
            row = history_manager.get_report_row(report_id)
            snapshot_path = row.get("snapshot_path") if row else None

            # Generate card image
            png_path = generate_png_card(report, snapshot_path)

            history_manager.log_export(
                report_id=report_id,
                export_format="png",
                export_path=str(png_path),
                persona_mode=report.persona_mode.value,
                file_size_bytes=png_path.stat().st_size,
            )
            return FileResponse(str(png_path), media_type="image/png")
        except Exception as exc:
            logger.exception(f"Failed to generate PNG summary card: {exc}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate PNG summary card: {str(exc)}",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported export format: {export_format}. Use 'json' or 'png'.",
        )


@app.get("/api/report/{report_id}/sources")
async def get_report_data_sources(report_id: str):
    """Retrieve data sources line-item transparency scores from SQLite."""
    sources = history_manager.get_data_sources(report_id)
    if not sources:
        # Check if report exists
        report = history_manager.get_report(report_id)
        if not report:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")
        return []
    return sources


@app.get("/api/history")
async def get_report_history(
    user_id: str = "anonymous",
    limit: int = 50,
    offset: int = 0,
    state: Optional[str] = None,
    traffic_light: Optional[str] = None,
):
    """Return paginated search history list for the current user."""
    history = history_manager.get_history(
        user_id=user_id,
        limit=limit,
        offset=offset,
        state_filter=state,
        traffic_light_filter=traffic_light,
    )
    return history


@app.get("/api/compare/{id_a}/{id_b}")
async def compare_reports(id_a: str, id_b: str):
    """Generate and return delta details between two reports."""
    delta = history_manager.build_comparison_delta(id_a, id_b)
    if not delta:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or both reports for comparison not found.",
        )

    # Save to SQLite database
    history_manager.save_comparison(id_a, id_b, delta)

    return delta


# =============================================================================
# PAYSTACK PAYMENT INTEGRATION STUBS
# =============================================================================

@app.post("/api/payment/initiate")
async def initiate_payment(report_id: str, email: str, amount_ngn: int = 3000):
    """
    Mock Paystack transaction initialization.
    Returns payment checkout URL and transaction reference.
    In real app, this wraps a POST call to api.paystack.co/transaction/initialize.
    """
    import uuid
    tx_ref = f"LNDIQ-{uuid.uuid4().hex[:8].upper()}"
    logger.info(f"[payment] Initiating payment for report {report_id[:8]} email={email} ref={tx_ref}")

    # Mock checkout URL (in development, redirects back to confirmation page)
    # The frontend will show a simulated payment modal or mock redirect.
    return {
        "status": "success",
        "message": "Authorization URL created",
        "data": {
            "authorization_url": f"/payment-mock.html?ref={tx_ref}&email={email}&amount={amount_ngn}&report_id={report_id}",
            "access_code": f"ACCESS-{uuid.uuid4().hex[:6].upper()}",
            "reference": tx_ref,
        }
    }


@app.post("/api/payment/webhook")
async def payment_webhook(payload: dict):
    """
    Handle Paystack webhook events.
    Verifies signature and unlocks locked reports/credits.
    """
    event = payload.get("event")
    data = payload.get("data", {})
    reference = data.get("reference")
    status_label = data.get("status")

    logger.info(f"[payment-webhook] Received Paystack event={event} ref={reference} status={status_label}")

    if event == "charge.success" and status_label == "success":
        # In production, look up the transaction by reference,
        # set payment_status = 'paid' on the report/session,
        # and notify any listeners.
        return {"status": "event_processed", "reference": reference}

    return {"status": "ignored"}


# =============================================================================
# STATIC DASHBOARD ROUTING
# =============================================================================

@app.get("/", response_class=HTMLResponse)
def serve_index():
    """Serve the main frontend application file directly from the workspace root."""
    frontend_path = Path(history_manager.ROOT_DIR) / "frontend" / "index.html"
    if not frontend_path.exists():
        return f"""
        <html>
          <head><title>LandIQ Server</title></head>
          <body style="font-family:sans-serif;padding:40px;background:#1e293b;color:#f8fafc;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
            <div style="text-align:center;background:#0f172a;padding:40px;border-radius:12px;border:1px solid #334155;max-width:600px;box-shadow:0 10px 15px -3px rgba(0,0,0,0.3)">
              <h1 style="color:#3b82f6;margin-top:0;">LandIQ API Server is Running</h1>
              <p>The backend server is up and listening. However, the frontend dashboard files have not been generated yet under <code>/frontend/index.html</code>.</p>
              <p style="color:#94a3b8;font-size:14px;margin-bottom:0;">Please wait a moment while the agent completes the build of the Tier 3 Frontend Dashboard.</p>
            </div>
          </body>
        </html>
        """
    return HTMLResponse(content=frontend_path.read_text(encoding="utf-8"))


# Serve other frontend assets if any
app.mount("/static", StaticFiles(directory=str(Path(history_manager.ROOT_DIR) / "frontend" / "static"), check_dir=False), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
