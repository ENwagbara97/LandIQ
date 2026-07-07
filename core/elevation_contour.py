"""
LandIQ — core/elevation_contour.py
Google Earth Engine NASADEM bridge & Matplotlib Static Contour Generator.
Caches 2D height grid responses in SQLite for 30 days.
"""

from __future__ import annotations

import io
import json
import logging
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import ee

logger = logging.getLogger("landiq.elevation")

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = ROOT_DIR / "db" / "landiq.db"

def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL;")
    c.execute("PRAGMA foreign_keys=ON;")
    return c

def get_nice_interval(min_val: float, max_val: float) -> float:
    diff = max_val - min_val
    if diff <= 0:
        return 1.0
    if diff <= 5:
        return 0.5
    elif diff <= 20:
        return 2.0
    elif diff <= 100:
        return 5.0
    else:
        return 10.0

def get_gee_elevation_contours(report_id: str, coordinates: list[list[float]]) -> dict:
    """
    Fetch a structured 2D grid of resampled elevations from GEE NASADEM inside
    the parcel bounding box (buffered by 50m).
    Uses a 30-day SQLite cache layer.
    """
    # 1. Cache Lookup
    try:
        conn = _conn()
        row = conn.execute(
            "SELECT response_json, fetched_at FROM gee_elevation_cache WHERE report_id = ?",
            (report_id,)
        ).fetchone()
        if row:
            fetched_at = datetime.fromisoformat(row["fetched_at"])
            age = datetime.now(timezone.utc) - fetched_at
            if age.days < 30:
                logger.info(f"[elevation] Cache hit for report {report_id}")
                return json.loads(row["response_json"])
    except Exception as e:
        logger.warning(f"[elevation] Cache lookup failed: {e}")
    finally:
        conn.close()

    # 2. GEE Fetch
    try:
        # Initialize GEE
        ee.Initialize()

        min_lat = min(pt[0] for pt in coordinates)
        max_lat = max(pt[0] for pt in coordinates)
        min_lng = min(pt[1] for pt in coordinates)
        max_lng = max(pt[1] for pt in coordinates)

        # Estimate grid scale dynamically so we always have ~50 pixels along max dim
        lat_avg = (min_lat + max_lat) / 2.0
        width_m = (max_lng - min_lng) * 111000.0 * math.cos(math.radians(lat_avg))
        height_m = (max_lat - min_lat) * 111000.0
        max_dim_m = max(width_m, height_m)

        target_cells = 50.0
        dynamic_scale = max_dim_m / target_cells
        scale_m = max(5.0, min(50.0, dynamic_scale))

        # Bounding box buffered by 50m
        buffer_deg = 50.0 / 111000.0
        buffered_min_lat = min_lat - buffer_deg
        buffered_max_lat = max_lat + buffer_deg
        buffered_min_lng = min_lng - buffer_deg
        buffered_max_lng = max_lng + buffer_deg

        bbox = ee.Geometry.Rectangle([
            buffered_min_lng,
            buffered_min_lat,
            buffered_max_lng,
            buffered_max_lat
        ])

        image = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM").mosaic()
        resampled = image.resample('bilinear')
        proj = ee.Projection('EPSG:4326').atScale(scale_m)
        reprojected = resampled.reproject(crs=proj)

        pixel_data = reprojected.sampleRectangle(region=bbox, defaultValue=-9999).getInfo()
        elevations = pixel_data['properties']['elevation']

        rows = len(elevations)
        cols = len(elevations[0]) if rows > 0 else 0

        if rows == 0 or cols == 0:
            raise ValueError("Empty grid returned from GEE")

        # Flat values check (ignore defaults)
        flat_elevations = [float(v) for r in elevations for v in r if v != -9999 and v is not None]
        if not flat_elevations:
            raise ValueError("No valid elevation values returned")

        # Replace any -9999 or None values with the mean value to prevent contour errors
        mean_val = np.mean(flat_elevations)
        clean_grid = []
        for r in elevations:
            clean_row = []
            for v in r:
                if v == -9999 or v is None:
                    clean_row.append(float(mean_val))
                else:
                    clean_row.append(float(v))
            clean_grid.append(clean_row)

        min_elev = min(flat_elevations)
        max_elev = max(flat_elevations)
        interval_m = get_nice_interval(min_elev, max_elev)

        response_data = {
            "elevation_available": True,
            "grid": clean_grid,
            "bounds": [
                [buffered_min_lat, buffered_min_lng],
                [buffered_max_lat, buffered_max_lng]
            ],
            "scale_m": round(scale_m, 1),
            "interval_m": interval_m,
            "min_elevation": round(min_elev, 1),
            "max_elevation": round(max_elev, 1),
            "dimensions": [rows, cols]
        }

        # 3. Save to Cache
        conn = _conn()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO gee_elevation_cache
                (report_id, fetched_at, scale_m, interval_m, response_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    datetime.now(timezone.utc).isoformat(),
                    scale_m,
                    interval_m,
                    json.dumps(response_data)
                )
            )
            conn.commit()
        except Exception as cache_err:
            logger.warning(f"[elevation] Failed to cache response: {cache_err}")
        finally:
            conn.close()

        return response_data

    except Exception as e:
        logger.error(f"[elevation] GEE extraction failed: {e}")
        return {
            "elevation_available": False,
            "message": f"Topographic dataset unavailable: {str(e)}"
        }

def generate_static_contour_map(
    coordinates: list[list[float]],
    grid_data: list[list[float]],
    bounds: list[list[float]],
    interval_m: float,
    output_path: Path
) -> bool:
    """
    Generate a fused satellite/contour map using matplotlib + contextily.
    Saves the static map to output_path.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon as MplPolygon
        from matplotlib.collections import PatchCollection
        import contextily as cx

        elevations = np.array(grid_data, dtype=float)
        rows, cols = elevations.shape

        buffered_min_lat, buffered_min_lng = bounds[0]
        buffered_max_lat, buffered_max_lng = bounds[1]

        # Define meshgrid
        lats = np.linspace(buffered_max_lat, buffered_min_lat, rows)
        lngs = np.linspace(buffered_min_lng, buffered_max_lng, cols)
        X, Y = np.meshgrid(lngs, lats)

        fig, ax = plt.subplots(figsize=(10, 8), dpi=150)

        # Draw fast CartoDB Positron basemap
        try:
            cx.add_basemap(
                ax,
                crs="EPSG:4326",
                source=cx.providers.CartoDB.Positron
            )
        except Exception as basemap_err:
            logger.warning(f"[elevation] Basemap loading skipped: {basemap_err}")

        ax.set_xlim(buffered_min_lng, buffered_max_lng)
        ax.set_ylim(buffered_min_lat, buffered_max_lat)

        min_z, max_z = np.min(elevations), np.max(elevations)
        index_interval = interval_m * 5.0

        all_levels = np.arange(math.floor(min_z / interval_m) * interval_m, max_z + interval_m, interval_m)
        index_levels = np.arange(math.floor(min_z / index_interval) * index_interval, max_z + index_interval, index_interval)
        normal_levels = [lvl for lvl in all_levels if lvl not in index_levels]

        # Thin contours (normal)
        if len(normal_levels) > 0:
            ax.contour(X, Y, elevations, levels=normal_levels, colors='#475569', alpha=0.25, linewidths=0.6)

        # Thick contours (index)
        if len(index_levels) > 0:
            thick = ax.contour(X, Y, elevations, levels=index_levels, colors='#0f172a', alpha=0.55, linewidths=1.2)
            ax.clabel(thick, inline=True, fontsize=7, fmt="%g m", colors='#0f172a')

        # Draw brand blue boundary
        poly_pts = [(lng, lat) for lat, lng in coordinates]
        polygon_patch = MplPolygon(poly_pts, closed=True)
        patch_collection = PatchCollection(
            [polygon_patch],
            facecolor=(0/255, 88/255, 189/255, 0.12),  # 12% brand blue
            edgecolor=(0/255, 88/255, 189/255, 1.0),   # solid brand blue
            linewidths=2.5,
            zorder=4
        )
        ax.add_collection(patch_collection)

        ax.axis("off")
        plt.tight_layout(pad=0)
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(str(output_path), dpi=150, bbox_inches="tight", pad_inches=0.1)
        plt.close(fig)

        logger.info(f"[elevation] Saved static contour map to {output_path.name}")
        return True
    except Exception as e:
        logger.error(f"[elevation] Failed to generate static contour map: {e}")
        return False
