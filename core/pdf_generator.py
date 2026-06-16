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
        "show_confidence_intervals": False,
        "show_development_matrix": False,
        "language": "conversational",
    },
    PersonaMode.SURVEYOR: {
        "label": "Technical Surveyor Report",
        "show_raw_metrics": True,
        "show_crs_detail": True,
        "show_confidence_intervals": True,
        "show_development_matrix": True,
        "language": "technical",
    },
    PersonaMode.REALTOR: {
        "label": "Real Estate Professional Report",
        "show_raw_metrics": False,
        "show_crs_detail": False,
        "show_confidence_intervals": False,
        "show_development_matrix": True,
        "language": "value_forward",
    },
    PersonaMode.ARCHITECT: {
        "label": "Architect/Developer Report",
        "show_raw_metrics": True,
        "show_crs_detail": False,
        "show_confidence_intervals": False,
        "show_development_matrix": True,
        "language": "technical_consequence",
    },
    PersonaMode.INSTITUTIONAL_DEV: {
        "label": "Institutional Developer Report",
        "show_raw_metrics": True,
        "show_crs_detail": True,
        "show_confidence_intervals": True,
        "show_development_matrix": True,
        "language": "institutional",
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

    profile_html = _generate_svg_chart(r)

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

{profile_html}

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
    Generate an 800×800 summary card PNG.
    Layout: Traffic light badge (dominant) + 3 key metrics + LandIQ branding + QR code.
    """
    from PIL import Image, ImageDraw, ImageFont

    REPORTS_DIR.mkdir(exist_ok=True)
    out_path = REPORTS_DIR / f"{report.meta.report_id}_card.png"

    tl = report.summary.traffic_light
    tl_colour_hex  = TRAFFIC_COLOURS[tl]["hex"]
    tl_bg_hex      = TRAFFIC_COLOURS[tl]["bg"]

    # Parse hex colours to RGB
    def hex_rgb(h: str) -> tuple:
        h = h.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    tl_rgb    = hex_rgb(tl_colour_hex)
    tl_bg_rgb = hex_rgb(tl_bg_hex)

    W, H = 800, 800
    img  = Image.new("RGB", (W, H), (15, 23, 42))   # dark navy
    draw = ImageDraw.Draw(img)

    # Try to load a font
    def _font(size: int):
        for face in ["arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"]:
            try:
                return ImageFont.truetype(face, size)
            except (IOError, OSError):
                pass
        return ImageFont.load_default()

    font_xl   = _font(52)
    font_lg   = _font(32)
    font_md   = _font(22)
    font_sm   = _font(16)
    font_xs   = _font(12)

    # Header bar
    draw.rectangle([(0, 0), (W, 72)], fill=(30, 64, 175))
    draw.text((24, 14), "LandIQ", fill=(255, 255, 255), font=font_lg)
    draw.text((W - 24, 14), "Land Risk Report", fill=(147, 197, 253), font=font_sm, anchor="ra")

    # Traffic light badge (large centre block)
    badge_top, badge_bottom = 90, 310
    draw.rounded_rectangle([(40, badge_top), (W - 40, badge_bottom)], radius=16, fill=tl_bg_rgb)

    # Big coloured circle
    cx, cy = 120, (badge_top + badge_bottom) // 2
    draw.ellipse([(cx - 42, cy - 42), (cx + 42, cy + 42)], fill=tl_rgb)

    tl_text = tl.value
    sub_text = {
        "GREEN": "Lower Risk Indicators",
        "AMBER": "Proceed with Caution",
        "RED":   "High Risk — Review Required",
    }.get(tl_text, "")

    draw.text((180, badge_top + 44), tl_text, fill=tl_rgb, font=font_xl)
    draw.text((180, badge_top + 108), sub_text, fill=(203, 213, 225), font=font_md)
    draw.text((180, badge_top + 148), f"Risk Score: {report.summary.overall_risk_score:.1f}/100", fill=(148, 163, 184), font=font_sm)

    # 3 key metrics
    metrics = [
        ("Flood Risk",      report.flood_risk_metrics.level.value,                   None),
        ("Terrain",         report.terrain_assessment.suitability or "—",             None),
        ("Growth Potential",report.growth_potential.level.value,                      None),
    ]
    col_w = (W - 80) // 3
    for i, (label, val, _) in enumerate(metrics):
        x = 40 + i * col_w
        draw.rounded_rectangle([(x, 328), (x + col_w - 12, 448)], radius=8, fill=(30, 41, 59))
        draw.text((x + 14, 342), label, fill=(100, 116, 139), font=font_xs)
        draw.text((x + 14, 368), val, fill=(226, 232, 240), font=font_md)

    # Location
    loc_lga   = report.parcel_geometry.location_context.lga   or "Unknown LGA"
    loc_state = report.parcel_geometry.location_context.state or "Unknown State"
    draw.text((40, 464), f"📍 {loc_lga}, {loc_state}", fill=(148, 163, 184), font=font_sm)
    draw.text((40, 490), f"Area: {report.parcel_geometry.computed_area_ha:.2f} ha  ·  "
              f"Centroid: {report.parcel_geometry.centroid.lat:.4f}°N, {report.parcel_geometry.centroid.lng:.4f}°E",
              fill=(100, 116, 139), font=font_xs)

    # Snapshot thumbnail (if available)
    if snapshot_path and Path(snapshot_path).exists():
        try:
            thumb = Image.open(snapshot_path).convert("RGB")
            thumb.thumbnail((720, 200), Image.LANCZOS)
            x_off = (W - thumb.width) // 2
            img.paste(thumb, (x_off, 514))
        except Exception:
            pass

    # Executive summary (truncated)
    summary_text = report.summary.executive_summary[:180] + ("…" if len(report.summary.executive_summary) > 180 else "")
    _draw_wrapped(draw, summary_text, font_xs, (40, 722), (W - 80), fill=(148, 163, 184))

    # QR code
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=3, border=2)
        qr.add_data(f"landiq://report/{report.meta.report_id[:12]}")
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="white", back_color="#0f172a").convert("RGB")
        qr_img = qr_img.resize((96, 96), Image.LANCZOS)
        img.paste(qr_img, (W - 112, H - 112))
    except Exception:
        pass

    # Report ID watermark (bottom)
    draw.text((40, H - 22), f"ID: {report.meta.report_id[:12]}  ·  LandIQ v{report.meta.version}", fill=(51, 65, 85), font=font_xs)

    img.save(str(out_path), "PNG", optimize=True)
    logger.info(f"[pdf] PNG card: {out_path.name}")
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
