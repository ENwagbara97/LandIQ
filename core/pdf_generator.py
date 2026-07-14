"""
LandIQ — core/pdf_generator.py
WeasyPrint PDF + PNG Summary Card Generator

Reads from stored ReportSchema (via SQLite) — never re-runs the pipeline.
Applies persona filter at render time — underlying JSON is identical for all personas.

Exports:
  PDF      — Jinja2 HTML → WeasyPrint
  JSON     — ReportSchema model_dump_json()
  PNG Card — 800×800 traffic-light-dominant summary card with QR code
"""

from __future__ import annotations

import io
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader
from core.schemas import PersonaMode, ReportSchema, TrafficLight

logger = logging.getLogger("landiq.pdf")

ROOT_DIR     = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT_DIR / "templates"
REPORTS_DIR  = ROOT_DIR / "reports"

# Colours per traffic light rating
TRAFFIC_COLOURS = {
    TrafficLight.GREEN: {"bg": "#14532d", "text": "#86efac", "hex": "#22c55e"},
    TrafficLight.AMBER: {"bg": "#713f12", "text": "#fde68a", "hex": "#f59e0b"},
    TrafficLight.RED:   {"bg": "#7f1d1d", "text": "#fca5a5", "hex": "#ef4444"},
}

# Persona display configuration — controls which sections render
PERSONA_CONFIG = {
    PersonaMode.EVERYDAY_BUYER: {
        "label": "Everyday Buyer Report",
        "show_raw_metrics": False,
        "show_crs_detail": False,
        "detail_level": "basic",
        "include_zoning": True,
    },
    PersonaMode.SURVEYOR: {
        "label": "Surveyor Technical Report",
        "show_raw_metrics": True,
        "show_crs_detail": True,
        "detail_level": "advanced",
        "include_zoning": False,
    },
    PersonaMode.REALTOR: {
        "label": "Realtor Risk & Value Report",
        "show_raw_metrics": False,
        "show_crs_detail": False,
        "detail_level": "moderate",
        "include_zoning": True,
    },
    PersonaMode.ARCHITECT: {
        "label": "Architect Site Context Report",
        "show_raw_metrics": True,
        "show_crs_detail": False,
        "detail_level": "advanced",
        "include_zoning": True,
    },
    PersonaMode.DEVELOPER: {
        "label": "Developer Feasibility Report",
        "show_raw_metrics": True,
        "show_crs_detail": True,
        "detail_level": "expert",
        "include_zoning": True,
    },
    PersonaMode.LEGAL_PRACTITIONER: {
        "label": "Legal Practitioner Compliance Report",
        "show_raw_metrics": False,
        "show_crs_detail": False,
        "detail_level": "moderate",
        "include_zoning": True,
    },
    PersonaMode.ESTATE_VALUER: {
        "label": "Estate Valuer Assessment Report",
        "show_raw_metrics": False,
        "show_crs_detail": False,
        "detail_level": "moderate",
        "include_zoning": True,
    },
    PersonaMode.OTHERS: {
        "label": "General Analysis Report",
        "show_raw_metrics": False,
        "show_crs_detail": False,
        "detail_level": "basic",
        "include_zoning": True,
    },
}


# =============================================================================
# JINJA2 ENVIRONMENT
# =============================================================================

def _get_jinja_env() -> Environment:
    TEMPLATES_DIR.mkdir(exist_ok=True)
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

    # Custom filters
    def format_float(val, digits=1):
        if val is None:
            return "—"
        return f"{float(val):.{digits}f}"

    def format_ha(val):
        if val is None:
            return "—"
        return f"{float(val):.2f} ha"

    def format_m(val):
        if val is None:
            return "—"
        v = float(val)
        return f"{v:.0f} m" if v < 1000 else f"{v/1000:.1f} km"

    def traffic_colour(tl: str):
        try:
            return TRAFFIC_COLOURS[TrafficLight(tl)]["hex"]
        except Exception:
            return "#94a3b8"

    def traffic_bg(tl: str):
        try:
            return TRAFFIC_COLOURS[TrafficLight(tl)]["bg"]
        except Exception:
            return "#1e293b"

    env.filters["float1"] = format_float
    env.filters["ha"]     = format_ha
    env.filters["dist"]   = format_m
    env.filters["tcolour"] = traffic_colour
    env.filters["tbg"]    = traffic_bg
    return env


# =============================================================================
# PDF GENERATION
# =============================================================================

def generate_pdf(
    report: ReportSchema,
    data_sources: list[dict],
    snapshot_path: str | None = None,
    persona_mode: PersonaMode | None = None,
    include_elevation_profile: bool = False,
    mode: str = "expert",
) -> Path:
    """
    Render the ReportSchema to a PDF using WeasyPrint.
    Returns the Path of the generated PDF file.
    """
    if not include_elevation_profile:
        report = report.model_copy(update={"premium_elevation_profile": None})

    # Ensure location is not "—" or unresolved
    geom = report.parcel_geometry
    loc = geom.location_context
    state_val = getattr(loc, "state", None) or "—"
    lga_val = getattr(loc, "lga", None) or "—"
    if (
        state_val in ("—", "", "None")
        or "Unresolved" in state_val
        or lga_val in ("—", "", "None")
        or "Unresolved" in lga_val
    ):
        from agents.coord_extract import reverse_geocode
        lat = geom.centroid.lat
        lng = geom.centroid.lng
        state_fb, lga_fb = reverse_geocode(lat, lng)
        report = report.model_copy(
            update={
                "parcel_geometry": geom.model_copy(
                    update={
                        "location_context": loc.model_copy(
                            update={"state": state_fb, "lga": lga_fb}
                        )
                    }
                )
            }
        )

    pm = persona_mode or report.persona_mode
    persona_cfg = PERSONA_CONFIG.get(pm, PERSONA_CONFIG[PersonaMode.EVERYDAY_BUYER])
    tl = report.summary.traffic_light
    colours = TRAFFIC_COLOURS[tl]
    REPORTS_DIR.mkdir(exist_ok=True)

    # Read snapshot as base64 for inline embedding
    snapshot_b64: str | None = None
    if snapshot_path and Path(snapshot_path).exists():
        import base64
        snapshot_b64 = base64.b64encode(Path(snapshot_path).read_bytes()).decode()

    # Fetch VIA (Visual Intelligence Advisor) result if available
    via_status = "pending"
    via_result = None
    try:
        import sqlite3
        db_file = ROOT_DIR / "db" / "landiq.db"
        if db_file.exists():
            conn = sqlite3.connect(str(db_file))
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT via_status, via_result_json FROM reports WHERE report_id = ?",
                (report.meta.report_id,),
            ).fetchone()
            conn.close()
            if row:
                via_status = row["via_status"] or "pending"
                if row["via_result_json"]:
                    via_result = json.loads(row["via_result_json"])
    except Exception as exc:
        logger.warning(f"[pdf] Could not fetch VIA details for PDF: {exc}")

    # Build template context
    ctx = {
        "report":         report,
        "persona_cfg":    persona_cfg,
        "tl":             tl.value,
        "tl_colour":      colours["hex"],
        "tl_bg":          colours["bg"],
        "tl_text_colour": colours["text"],
        "snapshot_b64":   snapshot_b64,
        "data_sources":   data_sources,
        "generated_at":   datetime.now(timezone.utc).strftime("%d %B %Y · %H:%M UTC"),
        "due_diligence":  _build_due_diligence(report),
        "mode":           mode,
        "via_status":     via_status,
        "via_result":     via_result,
    }

    env = _get_jinja_env()

    # Try persona-specific template, fall back to base
    template_names = [
        f"report_{pm.value.lower()}.html",
        "report_base.html",
    ]
    template = None
    for name in template_names:
        try:
            template = env.get_template(name)
            break
        except Exception:
            continue

    if template is None:
        # Inline fallback template if no files exist yet
        html = _build_inline_html(ctx)
    else:
        html = template.render(**ctx)

    # Render HTML to PDF (WeasyPrint, with xhtml2pdf pure-Python fallback)
    out_path = REPORTS_DIR / f"{report.meta.report_id}_{pm.value.lower()}.pdf"
    try:
        from weasyprint import HTML as WP_HTML
        WP_HTML(string=html, base_url=str(REPORTS_DIR)).write_pdf(str(out_path))
        logger.info(f"[pdf] Generated PDF via WeasyPrint: {out_path.name}")
        return out_path
    except Exception as exc:
        logger.warning(f"[pdf] WeasyPrint failed ({exc}). Falling back to xhtml2pdf compilation...")
        try:
            import re
            from xhtml2pdf import pisa
            # Strip SVG charts/gauges since xhtml2pdf does not support raw SVG XML tags, preventing raw markup rendering as text in PDF
            clean_html = re.sub(
                r'<svg.*?</svg>', 
                '', 
                html, 
                flags=re.DOTALL
            )
            with open(out_path, "wb") as f:
                pisa_status = pisa.CreatePDF(clean_html, dest=f)
            if pisa_status.err:
                raise RuntimeError(f"xhtml2pdf failed with error: {pisa_status.err}")
            logger.info(f"[pdf] Generated PDF via xhtml2pdf fallback: {out_path.name}")
            return out_path
        except Exception as fallback_exc:
            logger.error(f"[pdf] All PDF compilation engines failed. WeasyPrint: {exc} | xhtml2pdf: {fallback_exc}")
            raise


def _build_due_diligence(report: ReportSchema) -> list[dict]:
    """Extract due diligence checklist from advisory flags."""
    from agents.risk_assess import generate_due_diligence_checklist
    return generate_due_diligence_checklist(
        flood_risk=report.flood_risk_metrics.level,
        terrain_suitability=report.terrain_assessment.suitability,
        traffic_light=report.summary.traffic_light,
        acquisition_flag=report.title_record.acquisition_flag,
        title_verified=report.title_record.source_verified,
        distance_to_river_m=report.flood_risk_metrics.distance_to_nearest_river,
        encroachment_flag=report.encroachment.flag,
        persona_mode=report.persona_mode.value,
    )


def _generate_svg_chart(report: ReportSchema) -> str:
    """Generate the exact same SVG profile chart as the frontend."""
    if not report.premium_elevation_profile:
        return ""
    
    internal_pts = report.premium_elevation_profile.internal_profile_points
    outfall_pts = report.premium_elevation_profile.outfall_profile_points
    
    all_pts = internal_pts + outfall_pts
    elevations = [p.elevation_m for p in all_pts if p.elevation_m is not None]
    
    if not elevations:
        return '<svg width="100%" height="180" viewBox="0 0 500 180"><text x="50%" y="50%" fill="#94a3b8" text-anchor="middle" font-size="12">No elevation data available</text></svg>'
        
    min_e = min(elevations)
    max_e = max(elevations)
    range_e = max_e - min_e
    if range_e == 0:
        range_e = 10
    min_e -= range_e * 0.1
    max_e += range_e * 0.1
    range_e = max_e - min_e
    
    max_d_internal = max([p.distance_m for p in internal_pts] + [1])
    max_d_outfall = max([p.distance_m for p in outfall_pts] + [1])
    
    width = 500
    height = 180
    padding = 25
    
    def get_svg_coords(dist, elev, is_outfall):
        max_dist = max_d_outfall if is_outfall else max_d_internal
        x = padding + (dist / max_dist) * (width - 2 * padding)
        y = height - padding - ((elev - min_e) / range_e) * (height - 2 * padding)
        return f"{x:.1f},{y:.1f}"
        
    # Internal Line
    internal_coords = [get_svg_coords(p.distance_m, p.elevation_m, False) for p in internal_pts if p.elevation_m is not None]
    internal_line = f'<polyline points="{" ".join(internal_coords)}" fill="none" stroke="#3b82f6" stroke-width="3" />' if internal_coords else ""
    
    # Internal Dots
    internal_dots = ""
    for p in internal_pts:
        if p.elevation_m is not None:
            c = get_svg_coords(p.distance_m, p.elevation_m, False).split(',')
            internal_dots += f'<circle cx="{c[0]}" cy="{c[1]}" r="4" fill="#3b82f6" stroke="#080c14" stroke-width="1"></circle>'
            
    # Outfall Line
    outfall_coords = [get_svg_coords(p.distance_m, p.elevation_m, True) for p in outfall_pts if p.elevation_m is not None]
    outfall_line = f'<polyline points="{" ".join(outfall_coords)}" fill="none" stroke="#10b981" stroke-dasharray="4,4" stroke-width="3" />' if outfall_coords else ""
    
    # Outfall Dots
    outfall_dots = ""
    for p in outfall_pts:
        if p.elevation_m is not None:
            c = get_svg_coords(p.distance_m, p.elevation_m, True).split(',')
            outfall_dots += f'<circle cx="{c[0]}" cy="{c[1]}" r="4" fill="#10b981" stroke="#080c14" stroke-width="1"></circle>'
            
    # Grids
    grids = ""
    for i in range(5):
        val = min_e + (range_e * i / 4)
        y = height - padding - (i / 4) * (height - 2 * padding)
        grids += f'<line x1="{padding}" y1="{y}" x2="{width - padding}" y2="{y}" stroke="#e2e8f0" stroke-width="1" />'
        grids += f'<text x="{padding - 5}" y="{y + 3}" fill="#64748b" font-size="8" text-anchor="end">{val:.1f}m</text>'
        
    return f'<svg width="100%" height="180" viewBox="0 0 500 180" style="background:#fff; border:1px solid #e2e8f0; border-radius:6px; margin-bottom:12px; display:block;">{grids}{internal_line}{outfall_line}{internal_dots}{outfall_dots}</svg>'


def _build_inline_html(ctx: dict) -> str:
    """Fallback inline HTML when no template files exist (bootstrapping)."""
    r = ctx["report"]
    tl = ctx["tl"]
    tl_colour = ctx["tl_colour"]
    tl_bg = ctx["tl_bg"]

    via_html = ""
    via_status_val = ctx.get("via_status", "pending")
    via_res = ctx.get("via_result")
    if via_status_val == "complete" and via_res:
        call_b_paragraphs = ""
        call_b_text = via_res.get("call_b_text", "")
        if call_b_text:
            for p in call_b_text.split("\n\n"):
                if p.strip():
                    call_b_paragraphs += f"<p>{p.strip()}</p>"
        
        # Advisory observations list
        via_flags_html = ""
        for flag in via_res.get("advisory_flags", []):
            text = flag.split(":", 1)[-1].strip() if ":" in flag else flag
            via_flags_html += f"""
            <li style="margin-bottom: 4px; font-size: 9.5pt; color: #475569;">
              <strong>SATELLITE OBSERVATION</strong>: {text}
            </li>"""
        if via_flags_html:
            via_flags_html = f"<ul style='margin-top: 10px; padding-left: 20px;'>{via_flags_html}</ul>"

        # Key Observations Strip
        chips_html = ""
        call_a = via_res.get("call_a", {})
        confidence = call_a.get("confidence", {}).get("overall_confidence", "low")
        if confidence != "low":
            surr = call_a.get("immediate_surroundings_250m", {})
            road = surr.get("road_access", {})
            water = surr.get("water_features", {})
            risk = surr.get("risk_observations", {})
            settle = surr.get("settlement_pattern", {})

            chips = []
            if road.get("road_visible"):
                chips.append(("Road nearby", "#3b82f6"))
            if water.get("water_body_visible"):
                chips.append(("Water visible", "#f59e0b"))
            if risk.get("erosion_visible"):
                chips.append(("Erosion risk", "#ef4444"))
            if "informal" in settle.get("settlement_type", "").lower():
                chips.append(("Informal settlement", "#f59e0b"))
            if settle.get("commercial_activity_visible"):
                chips.append(("Commercial activity", "#3b82f6"))
            if risk.get("industrial_activity_visible"):
                chips.append(("Industrial nearby", "#ef4444"))

            for label, color in chips[:3]:
                chips_html += f"""
                <span style="display: inline-block; margin-right: 15px; font-size: 9pt; font-weight: bold; color: {color};">
                  ● {label}
                </span>"""
            if chips_html:
                chips_html = f"<div style='margin-top: 12px;'>{chips_html}</div>"

        via_html = f"""
        <section style="page-break-inside: avoid; border-left: 3px solid #3b82f6; padding-left: 15px; margin: 20px 0;">
          <h2>What We Observed Around This Land</h2>
          {call_b_paragraphs}
          {chips_html}
          {via_flags_html}
          <p style="font-size: 8pt; color: #94a3b8; font-style: italic; margin-top: 10px; border-top: 1px solid #e2e8f0; padding-top: 4px;">
            Visual observations based on satellite imagery (may be 1–3 years old). Verify on-site.
          </p>
        </section>
        """
    else:
        via_html = f"""
        <section style="page-break-inside: avoid; border-left: 3px solid #3b82f6; padding-left: 15px; margin: 20px 0;">
          <h2>What We Observed Around This Land</h2>
          <p style="color: #64748b; font-style: italic;">Visual satellite scan was not available for this report. A physical site visit is recommended.</p>
        </section>
        """

    profile_html = ""
    if r.premium_elevation_profile:
        # Build internal points rows
        internal_pts_html = ""
        for i, pt in enumerate(r.premium_elevation_profile.internal_profile_points):
            elev_str = f"{pt.elevation_m:.1f}m" if pt.elevation_m is not None else "—"
            internal_pts_html += f"""
            <tr>
              <td>{pt.label or f"Point {i+1}"}</td>
              <td>{pt.distance_m:.1f} m</td>
              <td>{elev_str}</td>
            </tr>"""

        # Build outfall points rows
        outfall_pts_html = ""
        if not r.premium_elevation_profile or not r.premium_elevation_profile.outfall_profile_points:
            outfall_pts_html = """
            <tr>
              <td colspan="3" style="text-align: center; color: #64748b;">No mapped public drainage or road networks within a 200m radius</td>
            </tr>"""
        else:
            for pt in r.premium_elevation_profile.outfall_profile_points:
                elev_str = f"{pt.elevation_m:.1f}m" if pt.elevation_m is not None else "—"
                outfall_pts_html += f"""
                <tr>
                  <td>{pt.label or "—"}</td>
                  <td>{pt.distance_m:.1f} m</td>
                  <td>{elev_str}</td>
                </tr>"""

        outfall_status = "Connected" if r.terrain_assessment.outfall_connected else "Not Connected"
        outfall_dist = f"{r.terrain_assessment.outfall_distance_m:.1f} m" if r.terrain_assessment.outfall_distance_m is not None else "—"
        outfall_asset = r.terrain_assessment.outfall_asset_type or "—"
        block_warning_text = ""
        if r.terrain_assessment.drainage_block_warning:
            block_warning_text = "<p style='color:#b91c1c; font-weight:600; margin-top: 6px;'>⚠ GRAVITY DRAINAGE BLOCK WARNING: The outfall asset sits higher than the property lowest edge. Water will not drain naturally.</p>"
        else:
            block_warning_text = "<p style='color:#15803d; font-weight:600; margin-top: 6px;'>✓ Natural slope drainage verified. Rainwater flows naturally to the street outfall.</p>"

        profile_html = f"""
        <section>
          <h2>Elevation & Outfall Drainage Profile</h2>
          <div class="summary-box" style="background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; padding: 12px; margin-bottom: 12px;">
            <p><strong>Drainage Connection Status:</strong> {outfall_status}</p>
            <p><strong>Outfall Distance:</strong> {outfall_dist}</p>
            <p><strong>Outfall Asset Type:</strong> {outfall_asset}</p>
            {block_warning_text}
          </div>
          
          {_generate_svg_chart(r)}
          
          <h3 style="font-size: 10pt; font-weight: 600; margin: 10px 0 4px 0;">Internal Plot Axis Elevation (10 points)</h3>
          <table>
            <tr><th>Point</th><th>Distance (m)</th><th>Elevation (m)</th></tr>
            {internal_pts_html}
          </table>

          <h3 style="font-size: 10pt; font-weight: 600; margin: 10px 0 4px 0;">Outfall Axis Elevation (10 points)</h3>
          <table>
            <tr><th>Point</th><th>Distance (m)</th><th>Elevation (m)</th></tr>
            {outfall_pts_html}
          </table>
        </section>
        """

    sources_html = ""
    for src in ctx["data_sources"]:
        # confidence_score stored as plain float e.g. 74.0 means 74%
        conf = src.get("confidence_score", 0)
        conf_pct = f"{conf:.0f}%"
        row_class = "amber" if conf < 50 else ("red" if conf < 30 else "")
        sources_html += f"""
        <tr class="{row_class}">
          <td>{src.get('field_name','—')}</td>
          <td>{src.get('source_label','—')}</td>
          <td>{src.get('data_vintage','—')}</td>
          <td>{conf_pct}</td>
          <td>{"Offline Cache" if src.get('fallback_used') else "✓ Live"}</td>
        </tr>"""

    checklist_html = ""
    for item in ctx["due_diligence"]:
        p = item["priority"]
        colour = "#ef4444" if p == "CRITICAL" else ("#f59e0b" if p == "HIGH" else "#94a3b8")
        checklist_html += f"""
        <div class="dd-item">
            <span class="dd-priority" style="color:{colour}">{p}</span>
            <strong>{item["action"]}</strong>
            <p>{item["rationale"]}</p>
        </div>
        """

    flags_html = ""
    for flag in r.advisory_flags:
        p_class = "#f59e0b"  # WARNING default
        p_text = "WARNING"
        if "HIGH" in flag or "CRITICAL" in flag:
            p_class = "#ef4444"
            p_text = "CRITICAL"
        elif "MODERATE" in flag:
            p_class = "#f59e0b"
            p_text = "WARNING"

        parts = flag.split(":", 1)
        action = parts[0].strip() if len(parts) > 1 else "Advisory"
        rationale = parts[1].strip() if len(parts) > 1 else flag

        flags_html += f"""
        <li style="margin-bottom: 8px;">
            <span class="dd-priority" style="color:{p_class}; font-weight:bold;">{p_text}</span>
            <strong>{action}</strong>: {rationale}
        </li>"""

    title_display = r.title_record.title_status if r.title_record.title_status else "Not Checked"
    if r.title_record.source_verified:
        verified_display = '<span style="color:#10b981; font-weight:bold;">✓ Yes (Live Registry)</span>'
    else:
        verified_display = '<span style="color:#94a3b8; font-weight:bold;">Offline/Mock</span>'
    advisory_text = r.title_record.advisory_text or "No registry verification was performed."

    snap_html = ""
    if ctx["snapshot_b64"]:
        snap_html = f'''
        <div class="map-container">
          <img src="data:image/png;base64,{ctx["snapshot_b64"]}" alt="Parcel Boundary Snapshot" />
        </div>
        '''

    # Only fall back to bare SVG chart if the expert outfall block didn't build a full profile_html above
    if not profile_html:
        profile_html = _generate_svg_chart(r)

    # ── Topographic Contour Map (Phase 4) ──────────────────────────────
    topo_html = ""
    try:
        from core.elevation_contour import get_gee_elevation_contours, generate_static_contour_map
        coords = r.parcel_geometry.coordinates
        topo_data = get_gee_elevation_contours(r.meta.report_id, coords)
        
        if topo_data.get("elevation_available"):
            import uuid
            temp_png = REPORTS_DIR / f"temp_topo_{uuid.uuid4().hex}.png"
            success = generate_static_contour_map(
                coordinates=coords,
                grid_data=topo_data["grid"],
                bounds=topo_data["bounds"],
                interval_m=topo_data["interval_m"],
                output_path=temp_png
            )
            
            if success and temp_png.exists():
                import base64
                topo_b64 = base64.b64encode(temp_png.read_bytes()).decode()
                try:
                    temp_png.unlink()
                except Exception:
                    pass
                
                relief = round(topo_data['max_elevation'] - topo_data['min_elevation'], 2)
                topo_html = f"""
                <section style="page-break-before: always;">
                  <h2>Engineering Topographic Assessment</h2>
                  <div class="map-container" style="text-align: center; margin: 12px 0;">
                    <img src="data:image/png;base64,{topo_b64}" style="width: 100%; max-height: 450px; object-fit: contain; border: 1px solid #e2e8f0; border-radius: 6px;" alt="2D Topographic Contours Map" />
                  </div>
                  <div class="elevation-stats-panel" style="margin-top: 16px;">
                    <h4 style="margin-bottom: 8px; color: #0f172a; font-size: 11pt;">Terrain Elevation Summary</h4>
                    <table style="width: 100%; border-collapse: collapse; font-size: 10pt;">
                      <tr>
                        <th style="border: 1px solid #cbd5e1; padding: 6px 12px; background-color: #f8fafc; text-align: left; width: 40%;">Indicator</th>
                        <th style="border: 1px solid #cbd5e1; padding: 6px 12px; background-color: #f8fafc; text-align: left;">Value</th>
                      </tr>
                      <tr>
                        <td style="border: 1px solid #cbd5e1; padding: 6px 12px;">Minimum Elevation</td>
                        <td style="border: 1px solid #cbd5e1; padding: 6px 12px;">{topo_data['min_elevation']}m AMSL</td>
                      </tr>
                      <tr>
                        <td style="border: 1px solid #cbd5e1; padding: 6px 12px;">Maximum Elevation</td>
                        <td style="border: 1px solid #cbd5e1; padding: 6px 12px;">{topo_data['max_elevation']}m AMSL</td>
                      </tr>
                      <tr>
                        <td style="border: 1px solid #cbd5e1; padding: 6px 12px;">Total Relief</td>
                        <td style="border: 1px solid #cbd5e1; padding: 6px 12px;">{relief}m</td>
                      </tr>
                      <tr>
                        <td style="border: 1px solid #cbd5e1; padding: 6px 12px;">Contour Interval</td>
                        <td style="border: 1px solid #cbd5e1; padding: 6px 12px;">{topo_data['interval_m']}m</td>
                      </tr>
                      <tr>
                        <td style="border: 1px solid #cbd5e1; padding: 6px 12px;">Data Source</td>
                        <td style="border: 1px solid #cbd5e1; padding: 6px 12px;">Copernicus GLO-30 (NASADEM)</td>
                      </tr>
                    </table>
                    <p style="font-size: 8pt; color: #64748b; font-style: italic; margin-top: 8px;">Note: This contour model is an engineering approximation processed directly from NASADEM satellite data. It does not replace a physical on-site topographic survey.</p>
                  </div>
                </section>
                """
    except Exception as topo_err:
        logger.warning(f"Failed to generate topographic assessment for PDF: {topo_err}")

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: 'Times New Roman', Times, serif; font-size: 11pt; color: #1e293b; margin: 0; padding: 20px; }}
  h1, h2, h3 {{ color: #0f172a; margin-top: 24px; margin-bottom: 8px; font-weight: 700; }}
  h2 {{ font-size: 14pt; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; }}
  .header {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #0f172a; padding-bottom: 16px; margin-bottom: 24px; }}
  .logo {{ font-size: 24pt; font-weight: 800; color: #0f172a; letter-spacing: -1px; }}
  .logo span {{ color: #3b82f6; }}
  .dd-priority {{ font-size: 8pt; font-weight: 700; margin-right: 6px; }}
  .dd-item p {{ font-size: 9pt; color: #64748b; margin-top: 3px; }}
  .summary-box {{ background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px; padding: 14px 18px; margin: 14px 0; }}
  .disclaimer {{ font-size: 8pt; color: #64748b; border-top: 1px solid #e2e8f0; margin-top: 24px; padding-top: 12px; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; margin-top: 10px; }}
  th, td {{ border: 1px solid #1e293b; padding: 8px; text-align: left; }}
  th {{ background-color: #f1f5f9; font-weight: bold; }}
  @media print {{ body {{ padding: 0; }} }}
</style>
</head>
<body>

<div class="header">
  <div class="logo">Land<span>IQ</span></div>
  <div class="report-meta">
    Report ID: {r.meta.report_id[:12]}…<br/>
    Generated: {ctx["generated_at"]}<br/>
    Persona: {ctx["persona_cfg"]["label"]}<br/>
    Pipeline v{r.pipeline_version}
  </div>
</div>

<div class="traffic-badge">
  <div class="tl-dot"></div>
  <div>
    <div class="tl-label">{tl} — {"Proceed with Caution" if tl == "AMBER" else ("High Risk" if tl == "RED" else "Lower Risk Indicators")}</div>
    <div style="font-size:10pt; margin-top:2px;">Parcel Risk Rating</div>
  </div>
  <div class="tl-score">Risk Score: {r.summary.overall_risk_score:.1f}/100</div>
</div>

{snap_html}

<section>
  <h2>Executive Summary</h2>
  <div class="summary-box">
    <p>{r.summary.executive_summary}</p>
  </div>
</section>

<section>
  <h2>Parcel Details</h2>
  <div class="metric-grid">
    <div class="metric"><div class="metric-label">Location</div><div class="metric-val">{r.parcel_geometry.location_context.lga or "—"}, {r.parcel_geometry.location_context.state or "—"}</div></div>
    <div class="metric"><div class="metric-label">Area</div><div class="metric-val">{__import__('core.units', fromlist=['ha_to_area_display']).ha_to_area_display(r.parcel_geometry.computed_area_ha, r.parcel_geometry.location_context.state)['display_expert']}</div></div>
    <div class="metric"><div class="metric-label">Centroid</div><div class="metric-val">{r.parcel_geometry.centroid.lat:.5f}°N, {r.parcel_geometry.centroid.lng:.5f}°E</div></div>
    <div class="metric"><div class="metric-label">CRS</div><div class="metric-val">{r.coordinate_validation.detected_crs} ({r.coordinate_validation.crs_confidence:.0f}%)</div></div>
  </div>
</section>

<section>
  <h2>Flood Risk Assessment</h2>
  <div class="metric-grid">
    <div class="metric"><div class="metric-label">Flood Risk Level</div><div class="metric-val" style="color:{tl_colour}">{r.flood_risk_metrics.level.value}</div></div>
    <div class="metric"><div class="metric-label">Elevation</div><div class="metric-val">{f"{r.terrain_assessment.elevation_m:.1f}m above sea level" if r.terrain_assessment.elevation_m is not None else "—"}</div></div>
    <div class="metric"><div class="metric-label">Nearest River</div><div class="metric-val">{f"{r.flood_risk_metrics.distance_to_nearest_river:.0f}m" if r.flood_risk_metrics.distance_to_nearest_river is not None else "—"}</div></div>
    <div class="metric"><div class="metric-label">Water Presence (NDWI)</div><div class="metric-val">{f"{r.flood_risk_metrics.water_presence_index:.2f}" if r.flood_risk_metrics.water_presence_index is not None else "—"}</div></div>
  </div>
  <p style="margin-top:8px; font-size:10pt; color:#475569;">{r.flood_risk_metrics.reason_in_plain_english}</p>
</section>

<section>
  <h2>Terrain & Access</h2>
  <div class="metric-grid">
    <div class="metric"><div class="metric-label">Terrain Suitability</div><div class="metric-val">{r.terrain_assessment.suitability or "—"}</div></div>
    <div class="metric"><div class="metric-label">Slope</div><div class="metric-val">{f"{r.terrain_assessment.steepness_of_land:.1f}%" if r.terrain_assessment.steepness_of_land is not None else "—"}</div></div>
    <div class="metric"><div class="metric-label">Road Access</div><div class="metric-val">{f"{r.accessibility_development.distance_to_road_m:.0f}m" if r.accessibility_development.distance_to_road_m is not None else "—"}</div></div>
    <div class="metric"><div class="metric-label">Growth Potential</div><div class="metric-val">{r.growth_potential.level.value}</div></div>
  </div>
</section>

{topo_html}

{profile_html}

{via_html}

<section>
  <h2>Advisory Flags</h2>
  <ul class="flag-list">{flags_html}</ul>
</section>

{f'''
<section>
  <h2>Due Diligence Checklist</h2>
  {checklist_html}
</section>

<section>
  <h2>Verification Sources</h2>
  <table>
    <tr><th>What We Measured</th><th>Source</th><th>Data Age</th><th>Confidence</th><th>Status</th></tr>
    {sources_html}
  </table>
</section>
''' if ctx.get('mode') != 'simple' else ''}

<section>
  <h2>AI Recommendation</h2>
  <div class="summary-box">
    <p>{r.summary.ai_recommendation}</p>
  </div>
</section>

<div class="disclaimer">
  {r.meta.disclaimer}<br/>
  Report generated by LandIQ v{r.meta.version} on {ctx["generated_at"]}.
  {"⚠ One or more language sections used template fallback (Ollama timeout)." if r.llm_timeout_fired else ""}
</div>

</body>
</html>"""


# =============================================================================
# JSON EXPORT
# =============================================================================

def export_json(report: ReportSchema) -> Path:
    """Export the full ReportSchema as a JSON file."""
    REPORTS_DIR.mkdir(exist_ok=True)
    out_path = REPORTS_DIR / f"{report.meta.report_id}_report.json"
    out_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    logger.info(f"[pdf] JSON export: {out_path.name}")
    return out_path


# =============================================================================
# PNG SUMMARY CARD
# =============================================================================

def generate_png_card(
    report: ReportSchema,
    snapshot_path: str | None = None,
) -> Path:
    """
    Generate a premium 900×640 summary card PNG — realtor sharing format.

    Layout (top-down):
      - Hero: full-bleed satellite snapshot fills the top 420px
      - Gradient: dark scrim fades up from bottom of hero so text is legible
      - Overlay (top-left on hero): LandIQ logo + risk score pill
      - Overlay (bottom of hero): Location name + area in large white text
      - Footer (220px): dark navy — 3 metric cards side-by-side + QR + watermark
    """
    from PIL import Image, ImageDraw, ImageFont, ImageFilter

    REPORTS_DIR.mkdir(exist_ok=True)
    out_path = REPORTS_DIR / f"{report.meta.report_id}_card.png"

    # ── Dimensions ─────────────────────────────────────────────────────────
    W, H        = 900, 640
    HERO_H      = 420          # satellite image occupies top portion
    FOOTER_H    = H - HERO_H  # metric cards live here
    DARK_NAVY   = (10, 15, 28)
    CARD_BG     = (18, 24, 40)
    BORDER_CLR  = (36, 46, 70)

    # ── Traffic-light palette ───────────────────────────────────────────────
    tl = report.summary.traffic_light
    tl_text = tl.value  # "GREEN" / "AMBER" / "RED"

    tl_palette = {
        "GREEN": {"rgb": (16, 185, 129),  "pill_bg": (6, 78, 59,  200)},
        "AMBER": {"rgb": (245, 158, 11),  "pill_bg": (92, 55, 0,  200)},
        "RED":   {"rgb": (239, 68, 68),   "pill_bg": (127, 29, 29, 200)},
    }
    pal       = tl_palette.get(tl_text, tl_palette["AMBER"])
    tl_rgb    = pal["rgb"]
    pill_bg   = pal["pill_bg"][:3]          # opaque version for rounded rect
    sub_label = {
        "GREEN": "Lower Risk — Proceed",
        "AMBER": "Proceed with Caution",
        "RED":   "High Risk — Review Required",
    }.get(tl_text, "")

    # ── Font loader ─────────────────────────────────────────────────────────
    def _font(size: int, bold: bool = False):
        faces = (
            ["arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold
            else ["arial.ttf", "DejaVuSans.ttf", "arialbd.ttf"]
        )
        for face in faces:
            try:
                return ImageFont.truetype(face, size)
            except (IOError, OSError):
                pass
        return ImageFont.load_default()

    font_hero_loc  = _font(26, bold=True)   # location name on hero
    font_hero_sub  = _font(14)              # area/centroid on hero
    font_pill_big  = _font(18, bold=True)   # AMBER / GREEN text in pill
    font_pill_sm   = _font(12)              # sub-label in pill
    font_score     = _font(28, bold=True)   # risk score
    font_label     = _font(11)             # metric card label
    font_val       = _font(17, bold=True)  # metric card value
    font_watermark = _font(10)             # bottom ID line

    # ── Build canvas ────────────────────────────────────────────────────────
    img  = Image.new("RGBA", (W, H), (*DARK_NAVY, 255))
    draw = ImageDraw.Draw(img)

    # ── 1. HERO: paste satellite snapshot ───────────────────────────────────
    hero_placed = False
    if snapshot_path and Path(snapshot_path).exists():
        try:
            sat = Image.open(snapshot_path).convert("RGBA")
            # Scale to fill full width, crop to HERO_H
            scale  = W / sat.width
            new_h  = int(sat.height * scale)
            sat    = sat.resize((W, new_h), Image.LANCZOS)
            # Centre-crop vertically
            crop_y = max(0, (new_h - HERO_H) // 2)
            sat    = sat.crop((0, crop_y, W, crop_y + HERO_H))
            img.paste(sat, (0, 0))
            hero_placed = True
        except Exception as e:
            logger.warning(f"[png_card] Could not load snapshot: {e}")

    if not hero_placed:
        # Fallback: textured dark gradient background
        for y in range(HERO_H):
            shade = int(20 + 30 * (y / HERO_H))
            draw.rectangle([(0, y), (W, y + 1)], fill=(shade, shade + 5, shade + 18, 255))

    # ── 2. Gradient scrim over hero (bottom fade to near-black) ─────────────
    scrim = Image.new("RGBA", (W, HERO_H), (0, 0, 0, 0))
    scrim_draw = ImageDraw.Draw(scrim)
    scrim_start = HERO_H // 3           # gradient starts at 1/3 down
    for y in range(scrim_start, HERO_H):
        progress = (y - scrim_start) / (HERO_H - scrim_start)
        alpha    = int(220 * (progress ** 1.6))  # eased curve
        scrim_draw.rectangle([(0, y), (W, y + 1)], fill=(5, 10, 20, alpha))
    img = Image.alpha_composite(img, Image.new("RGBA", (W, H), (0, 0, 0, 0)))
    img.paste(scrim, (0, 0), scrim)
    draw = ImageDraw.Draw(img)

    # ── 3. Top-left: LandIQ logo ─────────────────────────────────────────────
    logo_font  = _font(15, bold=True)
    # Small semi-transparent pill behind logo
    draw.rounded_rectangle([(16, 16), (106, 42)], radius=10, fill=(0, 0, 0, 160))
    draw.text((28, 22), "Land", fill=(255, 255, 255), font=logo_font)
    # measure "Land" width
    land_w = int(draw.textlength("Land", font=logo_font))
    draw.text((28 + land_w, 22), "IQ", fill=(59, 130, 246), font=logo_font)

    # ── 4. Top-right: Risk Score pill ────────────────────────────────────────
    score_val  = f"{report.summary.overall_risk_score:.0f}/100"
    score_w    = int(draw.textlength(score_val, font=font_score)) + 40
    pill_x1    = W - score_w - 16
    pill_y1, pill_y2 = 12, 60
    draw.rounded_rectangle([(pill_x1, pill_y1), (W - 16, pill_y2)], radius=14, fill=(*pill_bg, 210))
    draw.text((pill_x1 + 20, pill_y1 + 6), score_val, fill=tl_rgb, font=font_score)

    # ── 5. Bottom of hero: Traffic-light badge + location ────────────────────
    tl_badge_y = HERO_H - 88

    # Badge pill (e.g. "● AMBER  Proceed with Caution")
    badge_text_w = int(draw.textlength(f"  {tl_text}  {sub_label}  ", font=font_pill_big))
    bx1, bx2    = 24, min(24 + badge_text_w + 32, W - 24)
    draw.rounded_rectangle([(bx1, tl_badge_y), (bx2, tl_badge_y + 34)], radius=17, fill=(*pill_bg, 230))
    # Coloured dot
    draw.ellipse([(bx1 + 10, tl_badge_y + 9), (bx1 + 26, tl_badge_y + 25)], fill=tl_rgb)
    draw.text((bx1 + 34, tl_badge_y + 6),
              f"{tl_text}  ·  {sub_label}",
              fill=(240, 240, 240), font=font_pill_big)

    # Location name large white text
    loc_lga   = report.parcel_geometry.location_context.lga   or "Unknown LGA"
    loc_state = report.parcel_geometry.location_context.state or "Unknown State"
    area_ha   = report.parcel_geometry.computed_area_ha or 0
    area_str  = f"{area_ha:.2f} ha"

    draw.text((24, HERO_H - 50), f"{loc_lga}, {loc_state}",
              fill=(255, 255, 255), font=font_hero_loc)
    draw.text((24, HERO_H - 24),
              f"Area: {area_str}  ·  {report.parcel_geometry.centroid.lat:.4f}°N, {report.parcel_geometry.centroid.lng:.4f}°E",
              fill=(180, 195, 215), font=font_hero_sub)

    # ── 6. Footer: dark navy background ─────────────────────────────────────
    draw.rectangle([(0, HERO_H), (W, H)], fill=(*CARD_BG, 255))
    # Thin top separator line
    draw.rectangle([(0, HERO_H), (W, HERO_H + 1)], fill=(*BORDER_CLR, 255))

    # ── 7. Footer: 3 metric cards ────────────────────────────────────────────
    metrics = [
        ("Flood Risk",       report.flood_risk_metrics.level.value),
        ("Terrain",          report.terrain_assessment.suitability or "—"),
        ("Growth Potential", report.growth_potential.level.value),
    ]
    col_w   = (W - 180) // 3   # leave 180px on right for QR
    card_y1 = HERO_H + 16
    card_y2 = H - 16
    for i, (label, val) in enumerate(metrics):
        cx1 = 12 + i * (col_w + 10)
        cx2 = cx1 + col_w
        draw.rounded_rectangle([(cx1, card_y1), (cx2, card_y2)], radius=10,
                                fill=(*DARK_NAVY, 255), outline=(*BORDER_CLR, 255), width=1)
        draw.text((cx1 + 14, card_y1 + 12), label.upper(),
                  fill=(75, 95, 130), font=font_label)
        draw.text((cx1 + 14, card_y1 + 30), val,
                  fill=(225, 232, 245), font=font_val)

    # ── 8. QR code (bottom-right of footer) ─────────────────────────────────
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=4, border=2)
        qr.add_data(f"landiq://report/{report.meta.report_id[:12]}")
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="white", back_color="#0a0f1c").convert("RGB")
        qr_size = FOOTER_H - 28
        qr_img  = qr_img.resize((qr_size, qr_size), Image.LANCZOS)
        img.paste(qr_img, (W - qr_size - 10, HERO_H + 14))
        # "Scan to view" label
        draw.text((W - qr_size - 10, HERO_H + 14 + qr_size + 2),
                  "Scan report", fill=(60, 80, 110), font=font_watermark)
    except Exception:
        pass

    # ── 9. Watermark ────────────────────────────────────────────────────────
    draw.text((14, H - 14),
              f"ID: {report.meta.report_id[:12]}  ·  LandIQ v{report.meta.version}",
              fill=(36, 50, 75), font=font_watermark)

    # Convert RGBA → RGB for PNG save (no alpha needed)
    img = img.convert("RGB")
    img.save(str(out_path), "PNG", optimize=True)
    logger.info(f"[pdf] PNG card (hero layout): {out_path.name}")
    return out_path


def _draw_wrapped(draw: ImageDraw.ImageDraw, text: str, font, xy: tuple, max_width: int, fill=(255, 255, 255)) -> None:
    """Simple word-wrap text draw."""
    words = text.split()
    line = ""
    y = xy[1]
    for word in words:
        test = (line + " " + word).strip()
        if draw.textlength(test, font=font) <= max_width:
            line = test
        else:
            if line:
                draw.text((xy[0], y), line, fill=fill, font=font)
                y += 18
            line = word
    if line:
        draw.text((xy[0], y), line, fill=fill, font=font)
