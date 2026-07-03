"""
LandIQ — core/data_loader.py
Single entry point for ALL raster and vector file reads.

No agent reads data files directly. Everything goes through here.
Provides graceful degradation: if a file is missing (setup.py hasn't run),
returns None with a structured warning — never crashes the pipeline.

Caches open rasterio datasets to avoid re-opening on repeated calls.
"""

from __future__ import annotations

import json
import logging
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("landiq.data_loader")

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT_DIR    = Path(__file__).resolve().parent.parent
DATA_DIR    = ROOT_DIR / "data"
CONFIG_PATH = ROOT_DIR / "config" / "feed_flags.json"

SRTM_DIR     = DATA_DIR / "rasters"
HYDRO_DIR    = DATA_DIR / "hydro"
OSM_DIR      = DATA_DIR / "osm"
SENTINEL_DIR = DATA_DIR / "sentinel"

# ── Thread-safe raster cache ──────────────────────────────────────────────────
_raster_cache: dict[str, Any] = {}
_cache_lock = threading.Lock()


# =============================================================================
# CONFIG
# =============================================================================

@lru_cache(maxsize=1)
def load_flags() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_sentinel_zones() -> list[dict]:
    return load_flags().get("SENTINEL_ZONES", [])


# =============================================================================
# RASTER READER (rasterio)
# =============================================================================

def _open_raster(path: Path):
    """Return a cached rasterio DatasetReader for the given path."""
    key = str(path)
    with _cache_lock:
        if key in _raster_cache:
            return _raster_cache[key]
        try:
            import rasterio
            ds = rasterio.open(str(path))
            _raster_cache[key] = ds
            return ds
        except Exception as exc:
            logger.warning(f"[data_loader] Cannot open raster {path.name}: {exc}")
            return None


def sample_raster_at_point(raster_path: Path, lat: float, lng: float) -> float | None:
    """
    Sample a single raster band at the given WGS84 lat/lng.
    Returns the float value at that pixel, or None if unavailable.
    """
    if not raster_path.exists():
        logger.debug(f"[data_loader] Raster not found: {raster_path.name}")
        return None
    ds = _open_raster(raster_path)
    if ds is None:
        return None
    try:
        row, col = ds.index(lng, lat)
        data = ds.read(1)
        if 0 <= row < data.shape[0] and 0 <= col < data.shape[1]:
            value = float(data[row, col])
            # Treat SRTM nodata (−32768) as missing
            if value <= -9999 or value == ds.nodata:
                return None
            return value
    except Exception as exc:
        logger.debug(f"[data_loader] Raster sample error at ({lat},{lng}): {exc}")
    return None


def compute_slope_from_dem(dem_path: Path, lat: float, lng: float, radius_m: float = 90) -> float | None:
    """
    Approximate slope (%) around a point by sampling a 3×3 neighbourhood
    on the SRTM DEM and computing the maximum gradient.
    radius_m: half-width of the sampling window in metres (default 90m ≈ 3 SRTM pixels).
    """
    if not dem_path.exists():
        return None
    ds = _open_raster(dem_path)
    if ds is None:
        return None

    try:
        import numpy as np

        # Convert radius_m to degrees (approx)
        deg_step = radius_m / 111_320.0
        elevations = []
        for dlat in [-deg_step, 0, deg_step]:
            for dlng in [-deg_step, 0, deg_step]:
                val = sample_raster_at_point(dem_path, lat + dlat, lng + dlng)
                if val is not None:
                    elevations.append((dlat, dlng, val))

        if len(elevations) < 4:
            return None

        # Find max rise over run between any two opposite corners
        max_slope = 0.0
        for i, (dlat_a, dlng_a, elev_a) in enumerate(elevations):
            for dlat_b, dlng_b, elev_b in elevations[i + 1:]:
                rise = abs(elev_a - elev_b)
                run_m = (
                    ((dlat_a - dlat_b) * 111_320) ** 2 +
                    ((dlng_a - dlng_b) * 111_320) ** 2
                ) ** 0.5
                if run_m > 0:
                    slope = (rise / run_m) * 100
                    max_slope = max(max_slope, slope)

        return round(max_slope, 2)
    except Exception as exc:
        logger.debug(f"[data_loader] Slope computation error: {exc}")
        return None


# =============================================================================
# SRTM DEM
# =============================================================================

def get_srtm_tile_path(lat: float, lng: float) -> Path:
    """
    Return the path to the SRTM .tif tile covering the given lat/lng.
    SRTM tiles are named by the SW corner: N06E003.tif, N04E007.tif etc.
    """
    tile_lat = int(lat)
    tile_lng = int(lng)
    lat_str = f"N{tile_lat:02d}" if lat >= 0 else f"S{abs(tile_lat):02d}"
    lng_str = f"E{tile_lng:03d}" if lng >= 0 else f"W{abs(tile_lng):03d}"
    return SRTM_DIR / f"{lat_str}{lng_str}.tif"


def load_elevation(lat: float, lng: float) -> float | None:
    """Load elevation in metres at a WGS84 point from the SRTM DEM or API fallback."""
    tile = get_srtm_tile_path(lat, lng)
    val = sample_raster_at_point(tile, lat, lng)
    if val is not None:
        return val
    # API Fallback
    elev, _ = _fallback_open_elevation_and_slope(lat, lng)
    return elev


def load_slope(lat: float, lng: float) -> float | None:
    """Compute slope (%) at a WGS84 point from the SRTM DEM or API fallback."""
    tile = get_srtm_tile_path(lat, lng)
    val = compute_slope_from_dem(tile, lat, lng)
    if val is not None:
        return val
    # API Fallback
    _, slope = _fallback_open_elevation_and_slope(lat, lng)
    return slope

def _fallback_open_elevation_and_slope(lat: float, lng: float) -> tuple[float | None, float | None]:
    """Fetch elevation and compute slope via Open-Elevation API."""
    import requests
    import math
    deg_step = 90.0 / 111320.0
    locations = [
        f"{lat},{lng}",
        f"{lat+deg_step},{lng}",
        f"{lat-deg_step},{lng}",
        f"{lat},{lng+deg_step}",
        f"{lat},{lng-deg_step}",
    ]
    try:
        url = f"https://api.open-elevation.com/api/v1/lookup?locations={'|'.join(locations)}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            res = resp.json().get("results", [])
            if not res:
                return None, None
            center_elev = res[0]["elevation"]
            elevs = [r["elevation"] for r in res]
            
            # Simple slope estimate (max rise over 90m run)
            max_rise = max(abs(e - center_elev) for e in elevs[1:])
            slope_pct = round((max_rise / 90.0) * 100, 2)
            
            return center_elev, slope_pct
    except Exception as e:
        logger.warning(f"[data_loader] Open-Elevation API fallback failed: {e}")
    return None, None


# =============================================================================
# SENTINEL-2 (pre-computed NDWI / NDVI)
# =============================================================================

def _find_sentinel_zone(lat: float, lng: float) -> dict | None:
    """Return the matching Sentinel zone config for a lat/lng, or None."""
    for zone in get_sentinel_zones():
        if (zone["lat_min"] <= lat <= zone["lat_max"] and
                zone["lon_min"] <= lng <= zone["lon_max"]):
            return zone
    return None


def load_ndwi(lat: float, lng: float) -> tuple[float | None, bool]:
    """
    Load NDWI at a point from the nearest pre-clipped Sentinel GeoTIFF.
    Returns (ndwi_value, out_of_zone). out_of_zone=True if no zone matched.
    """
    zone = _find_sentinel_zone(lat, lng)
    if zone is None:
        ndwi, _ = _fallback_gee_ndvi_ndwi(lat, lng)
        return ndwi, True
    path = ROOT_DIR / zone["ndwi_path"]
    val = sample_raster_at_point(path, lat, lng)
    if val is None:
        ndwi, _ = _fallback_gee_ndvi_ndwi(lat, lng)
        return ndwi, False
    return val, False


def load_ndvi(lat: float, lng: float) -> tuple[float | None, bool]:
    """Load NDVI at a point from the nearest pre-clipped Sentinel GeoTIFF."""
    zone = _find_sentinel_zone(lat, lng)
    if zone is None:
        _, ndvi = _fallback_gee_ndvi_ndwi(lat, lng)
        return ndvi, True
    path = ROOT_DIR / zone["ndvi_path"]
    val = sample_raster_at_point(path, lat, lng)
    if val is None:
        _, ndvi = _fallback_gee_ndvi_ndwi(lat, lng)
        return ndvi, False
    return val, False


# =============================================================================
# HYDROSHEDS (river network)
# =============================================================================

def load_rivers_geodataframe(state: str | None = None):
    """
    Load HydroRIVERS shapefile for Nigeria (or a specific state area).
    Returns a GeoDataFrame or None.
    """
    try:
        import geopandas as gpd
        # Try state-specific file first, fall back to full Nigeria
        if state:
            state_path = HYDRO_DIR / f"hydrorivers_{state.lower()}.gpkg"
            if state_path.exists():
                return gpd.read_file(str(state_path))
        full_path = HYDRO_DIR / "hydrorivers_nigeria.gpkg"
        if full_path.exists():
            return gpd.read_file(str(full_path))
        # Try shapefile fallback
        shp_path = HYDRO_DIR / "HydroRIVERS_v10_af.shp"
        if shp_path.exists():
            return gpd.read_file(str(shp_path))
        logger.warning("[data_loader] HydroRIVERS file not found. Regional river network data is currently unavailable.")
        return None
    except Exception as exc:
        logger.warning(f"[data_loader] HydroRIVERS load failed: {exc}")
        return None


def nearest_river_distance_and_order(
    lat: float, lng: float, state: str | None = None
) -> tuple[float | None, int | None]:
    """
    Find distance (m) to the nearest HydroRIVERS segment and its Strahler order.
    Returns (distance_m, strahler_order).
    """
    try:
        import geopandas as gpd
        from shapely.geometry import Point

        gdf = load_rivers_geodataframe(state)
        if gdf is None or gdf.empty:
            # API Fallback
            dist, _ = _fallback_overpass_nearest_feature(lat, lng, 'waterway')
            return dist, None

        point = gpd.GeoDataFrame(
            {"geometry": [Point(lng, lat)]}, crs="EPSG:4326"
        )
        # Project to a local metric CRS for accurate distance
        utm_epsg = _utm_epsg_for_lng(lng)
        gdf_proj = gdf.to_crs(epsg=utm_epsg)
        point_proj = point.to_crs(epsg=utm_epsg)

        distances = gdf_proj.geometry.distance(point_proj.geometry.iloc[0])
        nearest_idx = distances.idxmin()
        dist_m = float(distances.loc[nearest_idx])

        # Strahler order column varies by HydroSHEDS version
        order = None
        for col in ["ORDER", "STRAHLER", "ORD_FLOW", "ORD_STRA"]:
            if col in gdf.columns:
                raw = gdf.loc[nearest_idx, col]
                try:
                    order = int(raw)
                except (TypeError, ValueError):
                    pass
                break

        return round(dist_m, 1), order

    except Exception as exc:
        logger.warning(f"[data_loader] River distance computation failed: {exc}")
        return None, None


# =============================================================================
# OSM (roads, settlements, land use)
# =============================================================================

def load_osm_roads(state: str | None = None):
    """Load OSM road network GeoDataFrame for nearest_road_distance computation."""
    try:
        import geopandas as gpd
        if state:
            path = OSM_DIR / f"roads_{state.lower()}.gpkg"
            if path.exists():
                return gpd.read_file(str(path))
        path = OSM_DIR / "roads_nigeria.gpkg"
        if path.exists():
            return gpd.read_file(str(path))
        path = OSM_DIR / "gis_osm_roads_free_1.shp"
        if path.exists():
            return gpd.read_file(str(path))
        logger.warning("[data_loader] OSM roads file not found. Regional road network data is currently unavailable.")
        return None
    except Exception as exc:
        logger.warning(f"[data_loader] OSM roads load failed: {exc}")
        return None


def load_osm_buildings(state: str | None = None):
    """Load OSM building footprints for urban density computation."""
    try:
        import geopandas as gpd
        path = OSM_DIR / f"buildings_{(state or 'nigeria').lower()}.gpkg"
        if path.exists():
            return gpd.read_file(str(path))
        path = OSM_DIR / "gis_osm_buildings_a_free_1.shp"
        if path.exists():
            return gpd.read_file(str(path))
        return None
    except Exception as exc:
        logger.warning(f"[data_loader] OSM buildings load failed: {exc}")
        return None


def load_osm_landuse(state: str | None = None):
    """Load OSM land use polygons for conflict detection."""
    try:
        import geopandas as gpd
        path = OSM_DIR / f"landuse_{(state or 'nigeria').lower()}.gpkg"
        if path.exists():
            return gpd.read_file(str(path))
        path = OSM_DIR / "gis_osm_landuse_a_free_1.shp"
        if path.exists():
            return gpd.read_file(str(path))
        return None
    except Exception as exc:
        logger.warning(f"[data_loader] OSM land use load failed: {exc}")
        return None


def nearest_road_distance(
    lat: float, lng: float, state: str | None = None
) -> float | None:
    """Return distance in metres to the nearest classified road."""
    try:
        import geopandas as gpd
        from shapely.geometry import Point

        gdf = load_osm_roads(state)
        if gdf is None or gdf.empty:
            # API Fallback
            dist, _ = _fallback_overpass_nearest_feature(lat, lng, 'highway')
            return dist

        point = gpd.GeoDataFrame({"geometry": [Point(lng, lat)]}, crs="EPSG:4326")
        utm_epsg = _utm_epsg_for_lng(lng)
        gdf_proj = gdf.to_crs(epsg=utm_epsg)
        point_proj = point.to_crs(epsg=utm_epsg)

        distances = gdf_proj.geometry.distance(point_proj.geometry.iloc[0])
        return round(float(distances.min()), 1)
    except Exception as exc:
        logger.warning(f"[data_loader] Road distance computation failed: {exc}")
        return None


def building_density_in_buffer(
    lat: float, lng: float, buffer_m: float, state: str | None = None
) -> int | None:
    """Count OSM building footprints within buffer_m of the centroid."""
    try:
        import geopandas as gpd
        from shapely.geometry import Point

        gdf = load_osm_buildings(state)
        if gdf is None or gdf.empty:
            # API Fallback
            return _fallback_overpass_building_density(lat, lng, buffer_m)

        utm_epsg = _utm_epsg_for_lng(lng)
        point_proj = Point(lng, lat)
        point_gdf = gpd.GeoDataFrame({"geometry": [point_proj]}, crs="EPSG:4326")
        point_proj_gdf = point_gdf.to_crs(epsg=utm_epsg)
        buffer_geom = point_proj_gdf.geometry.iloc[0].buffer(buffer_m)

        gdf_proj = gdf.to_crs(epsg=utm_epsg)
        count = int(gdf_proj.geometry.intersects(buffer_geom).sum())
        return count
    except Exception as exc:
        logger.warning(f"[data_loader] Building density computation failed: {exc}")
        return None


def land_use_conflicts_at_point(
    lat: float, lng: float, radius_m: float = 200, state: str | None = None
) -> list[str]:
    """
    Return a list of land use tags (e.g. 'wetland', 'forest', 'protected')
    that overlap with the given point's buffer.
    """
    try:
        import geopandas as gpd
        from shapely.geometry import Point

        gdf = load_osm_landuse(state)
        if gdf is None or gdf.empty:
            return _fallback_overpass_landuse(lat, lng, radius_m)

        utm_epsg = _utm_epsg_for_lng(lng)
        point_gdf = gpd.GeoDataFrame({"geometry": [Point(lng, lat)]}, crs="EPSG:4326")
        point_proj = point_gdf.to_crs(epsg=utm_epsg).geometry.iloc[0]
        buffer_geom = point_proj.buffer(radius_m)

        gdf_proj = gdf.to_crs(epsg=utm_epsg)
        overlapping = gdf_proj[gdf_proj.geometry.intersects(buffer_geom)]

        conflict_tags = set()
        for col in ["fclass", "type", "landuse", "natural"]:
            if col in overlapping.columns:
                for val in overlapping[col].dropna().unique():
                    tag = str(val).lower().strip()
                    if tag in {
                        "wetland", "marsh", "water", "reservoir", "forest",
                        "wood", "nature_reserve", "protected_area",
                        "military", "cemetery", "landfill",
                    }:
                        conflict_tags.add(tag)

        return sorted(conflict_tags)
    except Exception as exc:
        logger.warning(f"[data_loader] Land use conflict check failed: {exc}")
        return []


# =============================================================================
# UTILITY
# =============================================================================

def _utm_epsg_for_lng(lng: float) -> int:
    """Return the most appropriate UTM EPSG code for a Nigerian longitude."""
    if lng < 6.0:
        return 32631  # UTM Zone 31N
    elif lng < 12.0:
        return 32632  # UTM Zone 32N
    else:
        return 32633  # UTM Zone 33N


def data_availability_report() -> dict:
    """
    Check which data files are present on disk.
    Used by setup.py and the diagnostics endpoint to show what needs downloading.
    """
    checks = {
        "srtm_tiles": list(SRTM_DIR.glob("*.tif")),
        "hydrorivers": list(HYDRO_DIR.glob("*.gpkg")) + list(HYDRO_DIR.glob("*.shp")),
        "osm_roads":    list(OSM_DIR.glob("roads_*.gpkg")) + list(OSM_DIR.glob("*roads*.shp")),
        "osm_buildings":list(OSM_DIR.glob("buildings_*.gpkg")) + list(OSM_DIR.glob("*buildings*.shp")),
        "osm_landuse":  list(OSM_DIR.glob("landuse_*.gpkg")) + list(OSM_DIR.glob("*landuse*.shp")),
        "sentinel_ndwi":list(SENTINEL_DIR.glob("*ndwi*.tif")),
        "sentinel_ndvi":list(SENTINEL_DIR.glob("*ndvi*.tif")),
    }
    return {
        key: {"count": len(files), "files": [f.name for f in files]}
        for key, files in checks.items()
    }

# =============================================================================
# OVERPASS API FALLBACKS
# =============================================================================

def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def _fallback_overpass_nearest_feature(lat: float, lng: float, tag_key: str, search_radius_m: int = 5000) -> tuple[float | None, dict | None]:
    """Queries Overpass API for nearest feature matching tag_key."""
    import requests
    query = f'''
    [out:json];
    way(around:{search_radius_m},{lat},{lng})["{tag_key}"];
    out center;
    '''
    try:
        resp = requests.post("http://overpass-api.de/api/interpreter", data={"data": query}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            min_dist = float('inf')
            best_element = None
            for element in data.get("elements", []):
                if "center" in element:
                    d = _haversine_m(lat, lng, element["center"]["lat"], element["center"]["lon"])
                    if d < min_dist:
                        min_dist = d
                        best_element = element
            if best_element:
                return round(min_dist, 1), best_element
    except Exception as e:
        logger.warning(f"[data_loader] Overpass API fallback failed for {tag_key}: {e}")
    return None, None

def _fallback_overpass_building_density(lat: float, lng: float, radius_m: float) -> int | None:
    """Queries Overpass API for count of buildings in radius."""
    import requests
    query = f'''
    [out:json];
    way(around:{radius_m},{lat},{lng})["building"];
    out count;
    '''
    try:
        resp = requests.post("http://overpass-api.de/api/interpreter", data={"data": query}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if "elements" in data and len(data["elements"]) > 0:
                tags = data["elements"][0].get("tags", {})
                return int(tags.get("ways", 0)) + int(tags.get("relations", 0))
    except Exception as e:
        logger.warning(f"[data_loader] Overpass API fallback failed for buildings: {e}")
    return None

def _fallback_overpass_landuse(lat: float, lng: float, radius_m: float) -> list[str]:
    """Queries Overpass API for overlapping landuse tags."""
    import requests
    query = f'''
    [out:json];
    way(around:{radius_m},{lat},{lng})["landuse"];
    out tags;
    '''
    try:
        resp = requests.post("http://overpass-api.de/api/interpreter", data={"data": query}, timeout=10)
        if resp.status_code == 200:
            tags_found = set()
            for el in resp.json().get("elements", []):
                t = el.get("tags", {}).get("landuse")
                if t:
                    tags_found.add(t)
            return list(tags_found)
    except Exception as e:
        logger.warning(f"[data_loader] Overpass API fallback failed for landuse: {e}")
    return []

# =============================================================================
# GOOGLE EARTH ENGINE (GEE) API FALLBACKS
# =============================================================================

def _fallback_gee_ndvi_ndwi(lat: float, lng: float) -> tuple[float | None, float | None]:
    """
    Fetches NDVI and NDWI from Google Earth Engine's Sentinel-2 collection.
    Requires earthengine-api to be installed and authenticated on the server.
    Returns (ndwi, ndvi).
    """
    try:
        import ee
        # Initialize without prompting. Server must be pre-authenticated.
        if not ee.data._credentials:
            ee.Initialize()
        
        point = ee.Geometry.Point([lng, lat])
        
        # Get the least cloudy Sentinel-2 image in the last 6 months
        collection = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                      .filterBounds(point)
                      .filterDate(ee.Date(ee.Date.now()).advance(-6, 'month'), ee.Date.now())
                      .sort("CLOUDY_PIXEL_PERCENTAGE")
                      .first())
        
        if not collection:
            return None, None
            
        # Calculate NDVI: (NIR - Red) / (NIR + Red) -> (B8 - B4) / (B8 + B4)
        ndvi = collection.normalizedDifference(['B8', 'B4'])
        # Calculate NDWI: (Green - NIR) / (Green + NIR) -> (B3 - B8) / (B3 + B8)
        ndwi = collection.normalizedDifference(['B3', 'B8'])
        
        # Sample the point
        ndvi_val = ndvi.reduceRegion(reducer=ee.Reducer.mean(), geometry=point, scale=10).get('nd').getInfo()
        ndwi_val = ndwi.reduceRegion(reducer=ee.Reducer.mean(), geometry=point, scale=10).get('nd').getInfo()
        
        return (
            round(float(ndwi_val), 2) if ndwi_val is not None else None,
            round(float(ndvi_val), 2) if ndvi_val is not None else None
        )
        
    except ImportError:
        logger.warning("[data_loader] earthengine-api package not installed. Skipping GEE fallback.")
    except Exception as e:
        logger.warning(f"[data_loader] GEE fallback failed (ensure server is authenticated): {e}")
    return None, None

# =============================================================================
# ISRIC SOILGRIDS REST API
# =============================================================================

def fetch_isric_soil_properties(lat: float, lng: float) -> dict | None:
    """
    Queries the public ISRIC SoilGrids REST API for soil properties at 0-5cm depth.
    Returns a dict with clay, sand, and bulk_density (bdod) values.
    """
    import requests
    url = f"https://rest.isric.org/soilgrids/v2.0/properties/query"
    params = {
        "lon": lng,
        "lat": lat,
        "property": ["clay", "sand", "bdod"],
        "depth": "0-5cm",
        "value": "mean"
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            layers = data.get("properties", {}).get("layers", [])
            result = {}
            for layer in layers:
                name = layer.get("name")
                depths = layer.get("depths", [])
                if depths:
                    # Convert to actual values (ISRIC stores them scaled)
                    val = depths[0].get("values", {}).get("mean")
                    if val is not None:
                        if name == "clay":
                            result["clay_pct"] = val / 10.0  # scaled by 10
                        elif name == "sand":
                            result["sand_pct"] = val / 10.0  # scaled by 10
                        elif name == "bdod":
                            result["bulk_density"] = val / 100.0  # scaled by 100 (cg/cm3 -> g/cm3)
            
            if result:
                return result
    except Exception as e:
        logger.warning(f"[data_loader] ISRIC SoilGrids API failed: {e}")
    return None
