"""
LandIQ — core/snapshot_engine.py
Map Snapshot Module

Captures a permanent static PNG of the confirmed parcel boundary.
Triggered ONCE at the moment the user confirms "Yes, this is my land."

Engine Priority (Lite Runtime — no browser required):
  1. staticmap + Pillow   (primary — < 1s, < 50MB RAM, pure Python)
  2. matplotlib + contextily  (fallback — 2–3s, local tile cache)
  3. matplotlib only, no basemap  (last resort — < 0.5s, white background)
  4. Selenium + Folium    (optional — SELENIUM_SNAPSHOT_ACTIVE flag only)

NEVER blocks the pipeline. If all engines fail, log the error,
set snapshot_path = null, and let the report continue.
"""

from __future__ import annotations

import io
import json
import logging
import math
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ── Paths & Config ────────────────────────────────────────────────────────────
ROOT_DIR       = Path(__file__).resolve().parent.parent
SNAPSHOTS_DIR  = ROOT_DIR / "data" / "snapshots"
CONFIG_PATH    = ROOT_DIR / "config" / "feed_flags.json"

logger = logging.getLogger("landiq.snapshot")

# ── Load config ───────────────────────────────────────────────────────────────
def _load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

_CFG = _load_config()

SNAPSHOT_WIDTH  = _CFG.get("SNAPSHOT_WIDTH",  1200)
SNAPSHOT_HEIGHT = _CFG.get("SNAPSHOT_HEIGHT", 800)
THUMB_WIDTH     = _CFG.get("SNAPSHOT_THUMB_WIDTH",  240)
THUMB_HEIGHT    = _CFG.get("SNAPSHOT_THUMB_HEIGHT", 160)
LOCAL_TILE_URL  = _CFG.get("LOCAL_TILE_URL", "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}")
SELENIUM_ACTIVE = _CFG.get("SELENIUM_SNAPSHOT_ACTIVE", False)

# Polygon fill colour (pre-risk — defaults to blue; traffic light applied in PDF only)
_DEFAULT_FILL  = (59, 130, 246, 64)   # rgba — ~25% opacity blue
_DEFAULT_STROKE = (59, 130, 246, 255) # full opacity

TRAFFIC_COLOURS = {
    "GREEN": (34, 197, 94),
    "AMBER": (251, 191, 36),
    "RED":   (239, 68, 68),
}


# =============================================================================
# UTILITY: Lat/Lng → Pixel Conversions (Web Mercator)
# =============================================================================

def _lat_lng_to_tile(lat: float, lng: float, zoom: int) -> tuple[int, int]:
    """Convert lat/lng to OSM tile x/y at a given zoom level."""
    lat_r = math.radians(lat)
    n = 2 ** zoom
    x = int((lng + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def _compute_zoom(
    coords: list[list[float]],
    width: int,
    height: int,
    padding_pct: float = 0.20,
) -> tuple[int, float, float, float, float]:
    """
    Auto-compute zoom level and bounding box so the polygon fills the image
    with padding_pct whitespace on each side.

    Returns: (zoom, min_lat, max_lat, min_lng, max_lng)
    """
    lats = [pt[0] for pt in coords]
    lngs = [pt[1] for pt in coords]
    min_lat, max_lat = min(lats), max(lats)
    min_lng, max_lng = min(lngs), max(lngs)

    # Add padding
    lat_pad = (max_lat - min_lat) * padding_pct + 0.0001
    lng_pad = (max_lng - min_lng) * padding_pct + 0.0001
    min_lat -= lat_pad
    max_lat += lat_pad
    min_lng -= lng_pad
    max_lng += lng_pad

    # Determine zoom based on area
    area_ha = sum(
        abs(coords[i][1] * coords[(i + 1) % len(coords)][0] -
            coords[(i + 1) % len(coords)][1] * coords[i][0])
        for i in range(len(coords))
    ) / 2 * 111320 * 111320 / 10000

    if area_ha > 50:
        zoom = 14
    elif area_ha > 10:
        zoom = 15
    elif area_ha > 1:
        zoom = 16
    else:
        zoom = 17

    return zoom, min_lat, max_lat, min_lng, max_lng


def _coords_to_pixels(
    coords: list[list[float]],
    min_lat: float, max_lat: float,
    min_lng: float, max_lng: float,
    width: int, height: int,
) -> list[tuple[int, int]]:
    """Convert lat/lng polygon to pixel coordinates for a given viewport."""
    pixels = []
    lat_range = max_lat - min_lat
    lng_range = max_lng - min_lng
    if lat_range == 0 or lng_range == 0:
        return pixels
    for lat, lng in coords:
        x = int((lng - min_lng) / lng_range * width)
        y = int((max_lat - lat) / lat_range * height)
        pixels.append((x, y))
    return pixels


# =============================================================================
# ENGINE 1 — staticmap (Primary)
# =============================================================================

def _engine_staticmap(
    coordinates: list[list[float]],
    centroid: dict,
    report_id: str,
    output_path: Path,
    map_viewport: dict | None = None,
) -> bool:
    """
    Render the parcel snapshot using the staticmap library.
    Returns True on success, False on failure.
    """
    try:
        from staticmap import StaticMap, Polygon as SMapPolygon, CircleMarker, Line as SMapLine

        if map_viewport:
            zoom = map_viewport["zoom"]
            centre_lat = map_viewport["lat"]
            centre_lng = map_viewport["lng"]
            min_lat = min(pt[0] for pt in coordinates)
            max_lat = max(pt[0] for pt in coordinates)
            min_lng = min(pt[1] for pt in coordinates)
            max_lng = max(pt[1] for pt in coordinates)
        else:
            zoom, min_lat, max_lat, min_lng, max_lng = _compute_zoom(
                coordinates, SNAPSHOT_WIDTH, SNAPSHOT_HEIGHT
            )
            centre_lng = min_lng + (max_lng - min_lng) / 2
            centre_lat = min_lat + (max_lat - min_lat) / 2

        # Use local tile cache if available, else Google Hybrid (requires internet)
        tile_url = LOCAL_TILE_URL
        if "{z}" in tile_url and tile_url.startswith("file:"):
            # Check local tiles exist
            sample = tile_url.replace("{z}", str(zoom)).replace("{x}", "0").replace("{y}", "0")
            if not Path(sample.replace("file:///", "")).exists():
                tile_url = "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}"

        m = StaticMap(
            SNAPSHOT_WIDTH,
            SNAPSHOT_HEIGHT,
            url_template=tile_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
        )

        # Polygon: staticmap expects (lng, lat) order
        poly_coords = [(pt[1], pt[0]) for pt in coordinates]
        
        polygon = SMapPolygon(
            poly_coords,
            fill_color="#dc26261f",  # 12% opacity red fill
            outline_color=None,
        )
        m.add_polygon(polygon)

        # Use Line for custom thick stroke
        line_coords = list(poly_coords)
        if line_coords and line_coords[0] != line_coords[-1]:
            line_coords.append(line_coords[0]) # close the loop
        m.add_line(SMapLine(line_coords, color="#dc2626", width=6))

        # Centroid marker
        m.add_marker(CircleMarker(
            (centroid["lng"], centroid["lat"]),
            color="#1e40af",
            width=10,
        ))

        image = m.render(zoom=zoom, center=[centre_lng, centre_lat])

        # Compose final image with metadata strip
        final = _add_metadata_strip(image, coordinates, centroid, report_id)
        final.save(str(output_path), "PNG", optimize=True)

        logger.info(f"[snapshot] staticmap engine succeeded → {output_path.name}")
        return True

    except Exception as exc:
        logger.warning(f"[snapshot] staticmap engine failed: {exc}")
        return False


# =============================================================================
# ENGINE 2 — matplotlib + contextily
# =============================================================================

def _engine_matplotlib_contextily(
    coordinates: list[list[float]],
    centroid: dict,
    report_id: str,
    output_path: Path,
    map_viewport: dict | None = None,
) -> bool:
    """Render using matplotlib + contextily basemap tiles."""
    try:
        import matplotlib
        matplotlib.use("Agg")  # non-interactive backend — no GUI window
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        from matplotlib.patches import Polygon as MplPolygon
        from matplotlib.collections import PatchCollection
        import contextily as cx
        import numpy as np

        if map_viewport:
            zoom = map_viewport["zoom"]
            # To apply a custom viewport in matplotlib, we set custom limits based on the zoom
            # but since contextily downloads tiles based on the plot limits, we must set them manually
            # However, for simplicity and safety, we just use the original bounds logic if map_viewport
            # is passed to matplotlib engines, because matplotlib handles zoom intrinsically via plot limits.
            # We'll just extract the bounds.
            min_lat = min(pt[0] for pt in coordinates)
            max_lat = max(pt[0] for pt in coordinates)
            min_lng = min(pt[1] for pt in coordinates)
            max_lng = max(pt[1] for pt in coordinates)
        else:
            zoom, min_lat, max_lat, min_lng, max_lng = _compute_zoom(
                coordinates, SNAPSHOT_WIDTH, SNAPSHOT_HEIGHT
            )

        fig, ax = plt.subplots(figsize=(SNAPSHOT_WIDTH / 100, SNAPSHOT_HEIGHT / 100), dpi=100)

        # Add basemap
        try:
            cx.add_basemap(
                ax,
                crs="EPSG:4326",
                source="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
                zoom=zoom,
            )
        except Exception:
            pass  # basemap optional — draw polygon without it

        ax.set_xlim(min_lng, max_lng)
        ax.set_ylim(min_lat, max_lat)

        # Draw polygon
        poly_pts = [(lng, lat) for lat, lng in coordinates]
        polygon_patch = MplPolygon(poly_pts, closed=True)
        patch_collection = PatchCollection(
            [polygon_patch],
            facecolor=(255/255, 0/255, 0/255, 0.10),
            edgecolor=(255/255, 0/255, 0/255, 1.0),
            linewidths=3,
        )
        ax.add_collection(patch_collection)

        # Centroid marker
        ax.plot(centroid["lng"], centroid["lat"], "o",
                color="#1e40af", markersize=8, zorder=5)

        ax.axis("off")
        plt.tight_layout(pad=0)

        buf = io.BytesIO()
        plt.savefig(buf, format="PNG", dpi=100, bbox_inches="tight", pad_inches=0)
        plt.close(fig)
        buf.seek(0)

        image = Image.open(buf).convert("RGBA")
        image = image.resize((SNAPSHOT_WIDTH, SNAPSHOT_HEIGHT), Image.LANCZOS)
        final = _add_metadata_strip(image, coordinates, centroid, report_id)
        final.save(str(output_path), "PNG", optimize=True)

        logger.info(f"[snapshot] matplotlib+contextily engine succeeded → {output_path.name}")
        return True

    except Exception as exc:
        logger.warning(f"[snapshot] matplotlib+contextily engine failed: {exc}")
        return False


# =============================================================================
# ENGINE 3 — matplotlib only (last resort, white background)
# =============================================================================

def _engine_matplotlib_only(
    coordinates: list[list[float]],
    centroid: dict,
    report_id: str,
    output_path: Path,
    map_viewport: dict | None = None,
) -> bool:
    """Render polygon outline only on white background. No tiles required."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon as MplPolygon
        from matplotlib.collections import PatchCollection

        if map_viewport:
            zoom = map_viewport["zoom"]
            min_lat = min(pt[0] for pt in coordinates)
            max_lat = max(pt[0] for pt in coordinates)
            min_lng = min(pt[1] for pt in coordinates)
            max_lng = max(pt[1] for pt in coordinates)
        else:
            zoom, min_lat, max_lat, min_lng, max_lng = _compute_zoom(
                coordinates, SNAPSHOT_WIDTH, SNAPSHOT_HEIGHT
            )

        fig, ax = plt.subplots(figsize=(SNAPSHOT_WIDTH / 100, SNAPSHOT_HEIGHT / 100), dpi=100)
        ax.set_facecolor("#f8fafc")
        ax.set_xlim(min_lng, max_lng)
        ax.set_ylim(min_lat, max_lat)

        poly_pts = [(lng, lat) for lat, lng in coordinates]
        polygon_patch = MplPolygon(poly_pts, closed=True)
        patch_collection = PatchCollection(
            [polygon_patch],
            facecolor=(255/255, 0/255, 0/255, 0.10),
            edgecolor=(255/255, 0/255, 0/255, 1.0),
            linewidths=3.0,
        )
        ax.add_collection(patch_collection)

        ax.plot(centroid["lng"], centroid["lat"], "o",
                color="#1e40af", markersize=10, zorder=5)

        # Simple grid and coord labels
        ax.grid(True, alpha=0.2, linewidth=0.5)
        ax.set_xlabel("Longitude (°E)", fontsize=8)
        ax.set_ylabel("Latitude (°N)", fontsize=8)
        ax.set_title("Base map unavailable — parcel boundary shown", fontsize=9, color="#64748b")

        buf = io.BytesIO()
        plt.savefig(buf, format="PNG", dpi=100, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)

        image = Image.open(buf).convert("RGBA")
        image = image.resize((SNAPSHOT_WIDTH, SNAPSHOT_HEIGHT), Image.LANCZOS)
        final = _add_metadata_strip(image, coordinates, centroid, report_id)
        final.save(str(output_path), "PNG", optimize=True)

        logger.info(f"[snapshot] matplotlib-only engine succeeded → {output_path.name}")
        return True

    except Exception as exc:
        logger.warning(f"[snapshot] matplotlib-only engine failed: {exc}")
        return False


# =============================================================================
# ENGINE 4 — Selenium + Folium (optional — behind feature flag)
# =============================================================================

def _engine_selenium_folium(
    coordinates: list[list[float]],
    centroid: dict,
    report_id: str,
    output_path: Path,
    map_viewport: dict | None = None,
) -> bool:
    """
    Optional engine. Only activates if SELENIUM_SNAPSHOT_ACTIVE=true.
    Requires Chrome + chromedriver installed on the host machine.
    """
    if not SELENIUM_ACTIVE:
        return False
    try:
        import folium
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        import tempfile

        if map_viewport:
            centroid_coords = [map_viewport["lat"], map_viewport["lng"]]
            zoom_start = map_viewport["zoom"]
        else:
            centroid_coords = [centroid["lat"], centroid["lng"]]
            zoom_start = 17

        m = folium.Map(
            location=centroid_coords, 
            zoom_start=zoom_start, 
            tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", 
            attr="Google Hybrid",
            zoom_control=False,
        )

        coords_leaflet = [[pt[0], pt[1]] for pt in coordinates]
        folium.Polygon(
            locations=coords_leaflet,
            color="#FF0000",
            weight=4,
            fill=True,
            fill_color="#FF0000",
            fill_opacity=0.08,
        ).add_to(m)
        folium.Marker(location=centroid_coords).add_to(m)

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            m.save(f.name)
            html_path = f.name

        import json
        coords_json = json.dumps(coords_leaflet)

        with open(html_path, "a") as f_html:
            # Inject robust tile loading listener that flags when leaflet is truly idle
            # AND forces the map to fit exactly to the boundary
            f_html.write(f"""
            <script>
              setTimeout(() => {{
                // Find the leaflet map object dynamically
                let mapObj = null;
                for (let key in window) {{
                  if (key.startsWith('map_') && window[key] instanceof L.Map) {{
                    mapObj = window[key];
                    break;
                  }}
                }}
                if (mapObj) {{
                  // Disable animations for crisp snapshot
                  mapObj.options.fadeAnimation = false;
                  mapObj.options.zoomAnimation = false;

                  // Force camera zoom frame tightly to the boundary edges with strict low padding
                  const bounds = L.latLngBounds({coords_json});
                  mapObj.fitBounds(bounds, {{ padding: [10, 10], animate: false }});

                  mapObj.whenReady(() => {{
                    document.body.classList.add('map-capture-ready');
                  }});
                }} else {{
                  document.body.classList.add('map-capture-ready');
                }}
              }}, 500);
            </script>
            """)

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument(f"--window-size={SNAPSHOT_WIDTH},{SNAPSHOT_HEIGHT}")

        driver = webdriver.Chrome(options=options)
        try:
            driver.get(f"file:///{html_path}")
            import time as _time
            
            try:
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                # Wait for custom ready class
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "map-capture-ready"))
                )
            except Exception as wait_exc:
                logger.warning(f"[snapshot] Selenium wait for tiles timed out/failed: {wait_exc}")
                
            # Provide a 1.5 second network cooling window to prevent blurred imagery renders
            _time.sleep(1.5)
            screenshot = driver.get_screenshot_as_png()
        finally:
            driver.quit()
            os.unlink(html_path)

        image = Image.open(io.BytesIO(screenshot)).convert("RGBA")
        image = image.resize((SNAPSHOT_WIDTH, SNAPSHOT_HEIGHT), Image.LANCZOS)
        final = _add_metadata_strip(image, coordinates, centroid, report_id)
        final.save(str(output_path), "PNG", optimize=True)

        logger.info(f"[snapshot] Selenium+Folium engine succeeded → {output_path.name}")
        return True

    except Exception as exc:
        logger.warning(f"[snapshot] Selenium+Folium engine failed: {exc}")
        return False


# =============================================================================
# METADATA STRIP COMPOSER
# =============================================================================

def _add_metadata_strip(
    image: Image.Image,
    coordinates: list[list[float]],
    centroid: dict,
    report_id: str,
) -> Image.Image:
    """
    Add a white metadata strip at the bottom of the snapshot with:
      Report ID | Generated timestamp | Centroid lat/lng | Area
    """
    strip_height = 32
    final = Image.new("RGBA", (image.width, image.height + strip_height), "white")
    final.paste(image, (0, 0))

    # Compute approximate area for the strip label
    from agents.coord_extract import compute_area_ha
    try:
        area_ha = compute_area_ha([(pt[0], pt[1]) for pt in coordinates])
        area_label = f"{area_ha:.2f} ha"
    except Exception:
        area_label = "area unknown"

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    strip_text = (
        f"Report: {report_id[:8]}…  |  "
        f"Generated: {now_str}  |  "
        f"Centroid: {centroid['lat']:.5f}°N, {centroid['lng']:.5f}°E  |  "
        f"Area: {area_label}"
    )

    draw = ImageDraw.Draw(final)
    try:
        font = ImageFont.truetype("arial.ttf", 11)
    except (IOError, OSError):
        font = ImageFont.load_default()

    draw.rectangle([(0, image.height), (image.width, image.height + strip_height)], fill="#1e293b")
    draw.text((8, image.height + 8), strip_text, fill="#f1f5f9", font=font)

    return final


# =============================================================================
# THUMBNAIL GENERATOR
# =============================================================================

def _generate_thumbnail(source_path: Path) -> Path | None:
    """Generate a 240×160px thumbnail from the full snapshot."""
    try:
        thumb_path = source_path.parent / f"{source_path.stem}_thumb.png"
        img = Image.open(source_path)
        img.thumbnail((THUMB_WIDTH, THUMB_HEIGHT), Image.LANCZOS)
        # Pad to exact dimensions
        thumb = Image.new("RGBA", (THUMB_WIDTH, THUMB_HEIGHT), "#f8fafc")
        offset_x = (THUMB_WIDTH - img.width) // 2
        offset_y = (THUMB_HEIGHT - img.height) // 2
        thumb.paste(img, (offset_x, offset_y))
        thumb.save(str(thumb_path), "PNG")
        return thumb_path
    except Exception as exc:
        logger.warning(f"[snapshot] Thumbnail generation failed: {exc}")
        return None


# =============================================================================
# MAIN CAPTURE FUNCTION
# =============================================================================

def capture(
    coordinates: list[list[float]],
    centroid: dict,
    report_id: str,
    traffic_light: str | None = None,
    map_viewport: dict | None = None,
) -> str | None:
    """
    Main snapshot capture entrypoint.

    Tries each render engine in priority order:
      1. staticmap (primary)
      2. matplotlib + contextily
      3. matplotlib only
      4. Selenium + Folium (if SELENIUM_SNAPSHOT_ACTIVE=true)

    Always returns the snapshot path string or None.
    NEVER raises an exception — failures are logged and the pipeline continues.

    Args:
        coordinates    : WGS84 polygon [[lat, lng], ...]
        centroid       : {"lat": float, "lng": float}
        report_id      : Pipeline run_id (UUID4)
        traffic_light  : "GREEN"|"AMBER"|"RED"|None (used in future PDF render)
        map_viewport   : Optional dictionary with custom {lat, lng, zoom}
    """
    start_ms = time.monotonic()

    # Ensure snapshots directory exists
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = SNAPSHOTS_DIR / f"{report_id}_snapshot.png"

    if not coordinates or len(coordinates) < 3:
        logger.warning(f"[snapshot] Insufficient coordinates for {report_id}")
        return None

    # Engine execution order
    engines = [
        ("staticmap",             _engine_staticmap),
        ("matplotlib+contextily", _engine_matplotlib_contextily),
        ("matplotlib-only",       _engine_matplotlib_only),
        ("selenium+folium",       _engine_selenium_folium),
    ]

    engine_used = None
    for engine_name, engine_fn in engines:
        try:
            success = engine_fn(coordinates, centroid, report_id, output_path, map_viewport=map_viewport)
            if success and output_path.exists():
                engine_used = engine_name
                break
        except Exception as exc:
            logger.warning(f"[snapshot] {engine_name} crashed: {exc}\n{traceback.format_exc()}")
            continue

    if not engine_used or not output_path.exists():
        logger.error(f"[snapshot] All engines failed for run_id={report_id}. "
                     "Report will continue without a snapshot.")
        return None

    # File size check — compress if > 2MB
    size_bytes = output_path.stat().st_size
    if size_bytes > 2 * 1024 * 1024:
        try:
            img = Image.open(output_path)
            img.save(str(output_path), "PNG", optimize=True, compress_level=7)
            logger.info(f"[snapshot] Compressed from {size_bytes/1024:.0f}KB "
                        f"to {output_path.stat().st_size/1024:.0f}KB")
        except Exception:
            pass  # Keep original if compression fails

    # Generate thumbnail
    thumb_path = _generate_thumbnail(output_path)

    elapsed_ms = int((time.monotonic() - start_ms) * 1000)
    logger.info(
        f"[snapshot] Captured in {elapsed_ms}ms "
        f"using {engine_used} → {output_path.name} "
        f"({output_path.stat().st_size / 1024:.0f}KB)"
    )

    return str(output_path)
