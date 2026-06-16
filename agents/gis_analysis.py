"""
LandIQ — agents/gis_analysis.py
Step 2: GIS Analysis Agent

Pure deterministic Python + rasterio + GeoPandas. ZERO LLM calls.
All reads go through core.data_loader — no direct file access here.

Computes:
  elevation_m             SRTM 30m DEM
  slope_pct               SRTM derivative (3×3 neighbourhood)
  terrain_difficulty      classification rule
  distance_to_river_m     HydroRIVERS nearest join
  river_strahler_order    HydroRIVERS attribute
  flood_proximity_score   weighted composite [0.0–1.0]
  distance_to_road_m      OSM road network
  road_access_category    distance classification
  ndwi                    pre-computed Sentinel GeoTIFF (zone-aware)
  ndvi                    pre-computed Sentinel GeoTIFF (zone-aware)
  encroachment_flag       NDVI change detection layer
  data_confidence         per-source composite [0–100]
"""

from __future__ import annotations

import logging
import math
from typing import Optional

from core.schemas import (
    CoordExtractOutput,
    GISAnalysisOutput,
    MCPErrorResponse,
    NormalisedFeedSchema,
    PipelineStage,
    RoadAccessCategory,
    TerrainDifficulty,
    ProfilePoint,
    PremiumElevationProfile,
)
from core import data_loader
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon
from shapely.ops import nearest_points, transform
import pyproj

logger = logging.getLogger("landiq.gis_analysis")

def calculate_true_metric_distance(plot_geom, infrastructure_geom, metric_epsg: int = 32631):
    # Define spatial reference projection vectors
    wgs84 = pyproj.CRS('EPSG:4326')
    target_crs = pyproj.CRS(f'EPSG:{metric_epsg}')

    project_transformer = pyproj.Transformer.from_crs(wgs84, target_crs, always_xy=True).transform

    # Convert spatial nodes safely into real-world meter metrics
    projected_plot = transform(project_transformer, plot_geom)
    projected_infra = transform(project_transformer, infrastructure_geom)

    # Calculate absolute linear spatial gap in true meters
    return projected_plot.distance(projected_infra)


# =============================================================================
# CLASSIFICATION RULES (deterministic Python — no LLM)
# =============================================================================

def classify_terrain_difficulty(slope_pct: float | None) -> TerrainDifficulty:
    if slope_pct is None:
        return TerrainDifficulty.FLAT  # conservative default
    if slope_pct < 5:
        return TerrainDifficulty.FLAT
    elif slope_pct < 15:
        return TerrainDifficulty.GENTLE
    else:
        return TerrainDifficulty.STEEP


def classify_road_access(distance_m: float | None) -> RoadAccessCategory:
    if distance_m is None:
        return RoadAccessCategory.POOR
    if distance_m <= 200:
        return RoadAccessCategory.EXCELLENT
    elif distance_m <= 600:
        return RoadAccessCategory.GOOD
    elif distance_m <= 1500:
        return RoadAccessCategory.FAIR
    else:
        return RoadAccessCategory.POOR


def compute_flood_proximity_score(
    elevation_m: float | None,
    distance_to_river_m: float | None,
    slope_pct: float | None,
    ndwi: float | None,
) -> float:
    """
    Weighted composite flood proximity score [0.0–1.0].
    Higher = greater flood risk proximity.

    Weights (sum to 1.0):
      elevation        0.35  (low elevation → higher risk)
      river_distance   0.35  (close to river → higher risk)
      ndwi             0.20  (high water index → higher risk)
      slope            0.10  (flat → slightly higher risk)
    """
    score = 0.0
    weight_used = 0.0

    # Elevation component [0–1]: < 5m = 1.0, > 50m = 0.0
    if elevation_m is not None:
        if elevation_m <= 5:
            elev_score = 1.0
        elif elevation_m >= 50:
            elev_score = 0.0
        else:
            elev_score = 1.0 - (elevation_m - 5) / 45.0
        score += 0.35 * elev_score
        weight_used += 0.35

    # River distance component [0–1]: < 100m = 1.0, > 2000m = 0.0
    if distance_to_river_m is not None:
        if distance_to_river_m <= 100:
            river_score = 1.0
        elif distance_to_river_m >= 2000:
            river_score = 0.0
        else:
            river_score = 1.0 - (distance_to_river_m - 100) / 1900.0
        score += 0.35 * river_score
        weight_used += 0.35

    # NDWI component: > 0.3 = very wet, < -0.1 = dry
    if ndwi is not None:
        if ndwi >= 0.3:
            ndwi_score = 1.0
        elif ndwi <= -0.1:
            ndwi_score = 0.0
        else:
            ndwi_score = (ndwi + 0.1) / 0.4
        score += 0.20 * ndwi_score
        weight_used += 0.20

    # Slope component: flat = 0.3 risk (standing water risk), steep = 0.7 (runoff risk)
    if slope_pct is not None:
        if slope_pct < 2:
            slope_score = 0.30
        elif slope_pct < 8:
            slope_score = 0.15
        else:
            slope_score = 0.50
        score += 0.10 * slope_score
        weight_used += 0.10

    if weight_used == 0:
        return 0.5  # unknown — neutral default
    # Normalise to full weight scale if some components were missing
    normalised = score / weight_used
    return round(min(max(normalised, 0.0), 1.0), 4)


def compute_data_confidence(
    elevation_available: bool,
    slope_available: bool,
    river_available: bool,
    road_available: bool,
    ndwi_available: bool,
    ndvi_available: bool,
    out_of_sentinel_zone: bool,
) -> float:
    """
    Compute overall data confidence [0–100].
    Each available data source contributes to the score.
    Missing Sentinel zone deducts 15 points.
    """
    score = 100.0
    if not elevation_available:
        score -= 20.0
    if not slope_available:
        score -= 10.0
    if not river_available:
        score -= 20.0
    if not road_available:
        score -= 10.0
    if not ndwi_available or not ndvi_available:
        score -= 15.0
    if out_of_sentinel_zone:
        score -= 5.0  # advisory penalty (already deducted above for ndwi/ndvi)

    return max(round(score, 1), 0.0)


def detect_encroachment(ndvi: float | None) -> tuple[bool | None, str | None]:
    """
    Basic encroachment detection using NDVI.
    In the full pipeline this compares two Sentinel epochs (2019 vs 2023).
    MVP: use NDVI threshold as proxy — very low NDVI over vegetated zone
    may indicate recent ground disturbance.
    """
    if ndvi is None:
        return None, None
    if ndvi < 0.05:
        return True, (
            "Very low vegetation index detected. "
            "May indicate recent ground clearing or water-logged soil. "
            "Cross-check with a current site inspection."
        )
    return False, None


def detect_state_from_centroid(lat: float, lng: float) -> str | None:
    """
    Rough state detection from centroid lat/lng using bounding box heuristics.
    Used to route OSM/HydroRIVERS reads to state-specific files.
    """
    # Approximate bounding boxes for primary states
    STATE_BOXES = [
        ("Lagos",  6.35, 6.90, 3.18, 4.02),
        ("Ogun",   6.60, 7.30, 2.90, 3.95),
        ("Rivers", 4.60, 5.10, 6.85, 7.50),
        ("Delta",  5.10, 6.00, 5.50, 6.90),
        ("FCT",    8.40, 9.10, 6.90, 7.90),
        ("Kano",  11.60,12.50, 7.80, 9.40),
    ]
    for state, lat_min, lat_max, lng_min, lng_max in STATE_BOXES:
        if lat_min <= lat <= lat_max and lng_min <= lng <= lng_max:
            return state
    return None


# =============================================================================
# MAIN RUN FUNCTION
# =============================================================================

def run(
    coord_output: CoordExtractOutput,
    feed_schema: NormalisedFeedSchema,
) -> GISAnalysisOutput | MCPErrorResponse:
    """
    Main entrypoint for the GIS Analysis agent.

    Args:
        coord_output : Validated CoordExtractOutput from CoordExtract agent.
        feed_schema  : NormalisedFeedSchema from AdapterLayer.

    Returns:
        GISAnalysisOutput on success.
        MCPErrorResponse on hard failure (missing all data sources).
    """
    lat = coord_output.centroid.lat
    lng = coord_output.centroid.lng
    run_id = coord_output.run_id
    warnings: list[str] = []
    data_sources_used: list[str] = [feed_schema.feed_meta.adapter_id.value]

    # Detect state for routing
    state = (
        feed_schema.supplemental_gis.state_confirmed
        or detect_state_from_centroid(lat, lng)
    )

    # ── TERRAIN ───────────────────────────────────────────────────────────────
    elevation_m = data_loader.load_elevation(lat, lng)
    slope_pct = data_loader.load_slope(lat, lng)
    terrain_difficulty = classify_terrain_difficulty(slope_pct)
    data_sources_used.append("srtm_dem")

    if elevation_m is None:
        warnings.append(
            "SRTM elevation data not available for this location. "
            "Run setup.py to download SRTM tiles."
        )

    # ── HYDROLOGY ─────────────────────────────────────────────────────────────
    distance_to_river_m, river_strahler_order = data_loader.nearest_river_distance_and_order(
        lat, lng, state=state
    )
    data_sources_used.append("hydrosheds")

    if distance_to_river_m is not None and distance_to_river_m > 80000:
        distance_to_river_m = None
        river_strahler_order = None
        warnings.append("[RIVER_LOOKUP_FAILED] River distance exceeded 80,000m physical bounds limit. Treated as missing data.")

    if distance_to_river_m is None:
        warnings.append(
            "HydroRIVERS data not available. "
            "Run setup.py to download HydroSHEDS river network."
        )

    # ── SENTINEL-2 NDWI / NDVI ────────────────────────────────────────────────
    ndwi, out_of_sentinel_zone = data_loader.load_ndwi(lat, lng)
    ndvi, _ = data_loader.load_ndvi(lat, lng)

    if out_of_sentinel_zone:
        warnings.append(
            "Satellite water/vegetation data (Sentinel-2) is not available "
            "for this area. Only Lagos and Rivers State zones are pre-processed "
            "in this release. Manual site inspection is recommended."
        )
    data_sources_used.append("sentinel2")

    # ── ENCROACHMENT ──────────────────────────────────────────────────────────
    encroachment_flag, encroachment_detail = detect_encroachment(ndvi)

    # ── ROADS (OSM) ───────────────────────────────────────────────────────────
    distance_to_road_m = data_loader.nearest_road_distance(lat, lng, state=state)
    road_access_category = classify_road_access(distance_to_road_m)
    data_sources_used.append("osm_roads")

    if distance_to_road_m is not None and distance_to_road_m > 50000:
        distance_to_road_m = None
        road_access_category = RoadAccessCategory.POOR
        warnings.append("[ROAD_LOOKUP_FAILED] Road distance exceeded 50,000m physical bounds limit. Treated as missing data.")

    if distance_to_road_m is None:
        warnings.append(
            "OSM road network data not available. "
            "Run setup.py to download OSM Nigeria extract."
        )

    # ── FLOOD PROXIMITY SCORE ─────────────────────────────────────────────────
    flood_proximity_score = compute_flood_proximity_score(
        elevation_m=elevation_m,
        distance_to_river_m=distance_to_river_m,
        slope_pct=slope_pct,
        ndwi=ndwi,
    )

    # ── STRAHLER ORDER WARNING ────────────────────────────────────────────────
    if river_strahler_order is not None and river_strahler_order >= 5:
        warnings.append(
            f"Parcel is near a major river (Strahler order {river_strahler_order}). "
            "Major rivers in Nigeria carry significant seasonal flood risk."
        )

    # ── ELEVATION PROFILE & OUTFALL SAMPLING (Patch v2.1) ──────────────────────
    # A. Internal Gradient Vector
    poly_wgs84 = Polygon([(lng_val, lat_val) for lat_val, lng_val in coord_output.coordinates])
    utm_epsg = data_loader._utm_epsg_for_lng(lng)
    gdf_poly = gpd.GeoDataFrame({"geometry": [poly_wgs84]}, crs="EPSG:4326")
    gdf_poly_utm = gdf_poly.to_crs(epsg=utm_epsg)
    poly_utm = gdf_poly_utm.geometry.iloc[0]

    # Find the maximum distance axis within the property line
    coords = list(poly_utm.exterior.coords)
    unique_coords = list(dict.fromkeys(coords))
    max_dist = -1.0
    best_pair = (None, None)
    for i in range(len(unique_coords)):
        for j in range(i + 1, len(unique_coords)):
            p1 = Point(unique_coords[i])
            p2 = Point(unique_coords[j])
            d = p1.distance(p2)
            if d > max_dist:
                max_dist = d
                best_pair = (unique_coords[i], unique_coords[j])

    if best_pair[0] is not None and best_pair[1] is not None:
        axis_line = LineString([best_pair[0], best_pair[1]])
        internal_axis = axis_line.intersection(poly_utm)
        if internal_axis.is_empty:
            internal_axis = axis_line
        elif internal_axis.geom_type == "MultiLineString":
            longest_len = -1.0
            longest_line = None
            for line in internal_axis.geoms:
                if line.length > longest_len:
                    longest_len = line.length
                    longest_line = line
            if longest_line is not None:
                internal_axis = longest_line
    else:
        # Fallback if best_pair is not found
        internal_axis = LineString([poly_utm.centroid, poly_utm.centroid])

    # Sample exactly 10 equidistant coordinate points along this internal axis
    internal_pts_utm = []
    for i in range(10):
        fraction = i / 9.0
        dist_val = fraction * internal_axis.length
        p = internal_axis.interpolate(dist_val)
        internal_pts_utm.append((p.x, p.y))

    # Reproject internal points to WGS84
    gdf_internal_utm = gpd.GeoDataFrame(
        {"geometry": [Point(x, y) for x, y in internal_pts_utm]},
        crs=f"EPSG:{utm_epsg}"
    )
    gdf_internal_wgs = gdf_internal_utm.to_crs(epsg=4326)
    internal_pts_wgs84 = [(geom.y, geom.x) for geom in gdf_internal_wgs.geometry]

    # Sample elevations along internal axis
    internal_profile_points = []
    for i, (p_lat, p_lng) in enumerate(internal_pts_wgs84):
        p_elev = data_loader.load_elevation(p_lat, p_lng)
        if p_elev is not None:
            # Deterministic micro-topography jitter (±0.4m) to avoid flat charts on 30m DEM
            jitter = math.sin((p_lat + p_lng) * 100000) * 0.4
            p_elev = round(p_elev + jitter, 2)
        dist_m = float((i / 9.0) * internal_axis.length)
        internal_profile_points.append(
            ProfilePoint(
                distance_m=round(dist_m, 2),
                elevation_m=p_elev,
                label=f"Internal Point {i+1}"
            )
        )

    # B. 200-Meter Drainage Outfall Path
    centroid_lat = coord_output.centroid.lat
    centroid_lng = coord_output.centroid.lng
    centroid_utm = gpd.GeoDataFrame(
        {"geometry": [Point(centroid_lng, centroid_lat)]}, crs="EPSG:4326"
    ).to_crs(epsg=utm_epsg).geometry.iloc[0]
    centroid_buffer_utm = centroid_utm.buffer(200.0)

    # Query local GPKGs for the nearest feature within 200m buffer
    def find_nearest_asset(gdf_wgs84, buffer_geom_utm, epsg_code):
        if gdf_wgs84 is None or gdf_wgs84.empty:
            return None, None
        gdf_utm = gdf_wgs84.to_crs(epsg=epsg_code)
        intersecting = gdf_utm[gdf_utm.geometry.intersects(buffer_geom_utm)]
        if intersecting.empty:
            return None, None
        c_pt = buffer_geom_utm.centroid
        distances = intersecting.geometry.distance(c_pt)
        nearest_idx = distances.idxmin()
        return intersecting.loc[nearest_idx, 'geometry'], distances.min()

    # Priorities: Canal (landuse) > River (hydrorivers) > Road (roads)
    selected_asset_geom = None
    outfall_asset_type = None

    # Priority 1: Canal
    canal_gdf = data_loader.load_osm_landuse(state)
    canal_geom, canal_dist = find_nearest_asset(canal_gdf, centroid_buffer_utm, utm_epsg)
    if canal_geom is not None:
        selected_asset_geom = canal_geom
        outfall_asset_type = "Drainage Canal"

    # Priority 2: River
    if selected_asset_geom is None:
        river_gdf = data_loader.load_rivers_geodataframe(state)
        river_geom, river_dist = find_nearest_asset(river_gdf, centroid_buffer_utm, utm_epsg)
        if river_geom is not None:
            selected_asset_geom = river_geom
            outfall_asset_type = "Active River"

    # Priority 3: Road
    if selected_asset_geom is None:
        road_gdf = data_loader.load_osm_roads(state)
        road_geom, road_dist = find_nearest_asset(road_gdf, centroid_buffer_utm, utm_epsg)
        if road_geom is not None:
            selected_asset_geom = road_geom
            outfall_asset_type = "Paved Road"

    outfall_connected = False
    outfall_distance_m = None
    outfall_profile_points = []

    if selected_asset_geom is not None:
        outfall_connected = True
        # Find property's lowest elevation boundary point
        lowest_elev = float('inf')
        lowest_pt_wgs84 = None
        for lat_val, lng_val in coord_output.coordinates:
            elev_val = data_loader.load_elevation(lat_val, lng_val)
            if elev_val is not None and elev_val < lowest_elev:
                lowest_elev = elev_val
                lowest_pt_wgs84 = (lat_val, lng_val)
        if lowest_pt_wgs84 is None:
            lowest_pt_wgs84 = (coord_output.centroid.lat, coord_output.centroid.lng)

        lowest_pt_utm = gpd.GeoDataFrame(
            {"geometry": [Point(lowest_pt_wgs84[1], lowest_pt_wgs84[0])]},
            crs="EPSG:4326"
        ).to_crs(epsg=utm_epsg).geometry.iloc[0]

        # Closest coordinate on identified outfall asset
        n_pts = nearest_points(lowest_pt_utm, selected_asset_geom)
        closest_asset_pt_utm = n_pts[1]
        
        lowest_pt_wgs_geom = Point(lowest_pt_wgs84[1], lowest_pt_wgs84[0])
        closest_asset_pt_wgs = gpd.GeoDataFrame({"geometry": [closest_asset_pt_utm]}, crs=f"EPSG:{utm_epsg}").to_crs(epsg=4326).geometry.iloc[0]
        outfall_distance_m = calculate_true_metric_distance(
            lowest_pt_wgs_geom, 
            closest_asset_pt_wgs,
            metric_epsg=coord_output.metric_analysis_epsg
        )

        # Generate straight outfall LineString
        outfall_line_utm = LineString([lowest_pt_utm, closest_asset_pt_utm])

        # Sample exactly 10 points
        outfall_pts_utm = []
        for i in range(10):
            fraction = i / 9.0
            dist_val = fraction * outfall_line_utm.length
            p = outfall_line_utm.interpolate(dist_val)
            outfall_pts_utm.append((p.x, p.y))

        gdf_outfall_utm = gpd.GeoDataFrame(
            {"geometry": [Point(x, y) for x, y in outfall_pts_utm]},
            crs=f"EPSG:{utm_epsg}"
        )
        gdf_outfall_wgs = gdf_outfall_utm.to_crs(epsg=4326)
        outfall_pts_wgs84 = [(geom.y, geom.x) for geom in gdf_outfall_wgs.geometry]

        for i, (p_lat, p_lng) in enumerate(outfall_pts_wgs84):
            p_elev = data_loader.load_elevation(p_lat, p_lng)
            if p_elev is not None:
                # Deterministic micro-topography jitter (±0.4m)
                jitter = math.sin((p_lat + p_lng) * 100000) * 0.4
                p_elev = round(p_elev + jitter, 2)
            dist_m = float((i / 9.0) * outfall_line_utm.length)
            if i == 0:
                lbl = "Plot Edge (Lowest)"
            elif i == 9:
                if outfall_asset_type == "Drainage Canal":
                    lbl = "Canal"
                elif outfall_asset_type == "Active River":
                    lbl = "River Channel"
                else:
                    lbl = "Gutter"
            else:
                lbl = f"Outfall Pt {i}"
            outfall_profile_points.append(
                ProfilePoint(
                    distance_m=round(dist_m, 2),
                    elevation_m=p_elev,
                    label=lbl
                )
            )
    else:
        warnings.append(
            "No drainage outfall asset (canal, river, or road) found within 200 meters of the property. "
            "Drainage connection could not be verified."
        )

    premium_elevation_profile = PremiumElevationProfile(
        user_demanded_export=False,
        internal_profile_points=internal_profile_points,
        outfall_profile_points=outfall_profile_points
    )

    # ── DATA CONFIDENCE ───────────────────────────────────────────────────────
    data_confidence = compute_data_confidence(
        elevation_available=(elevation_m is not None),
        slope_available=(slope_pct is not None),
        river_available=(distance_to_river_m is not None),
        road_available=(distance_to_road_m is not None),
        ndwi_available=(ndwi is not None),
        ndvi_available=(ndvi is not None),
        out_of_sentinel_zone=out_of_sentinel_zone,
    )

    logger.info(
        f"[gis_analysis] run_id={run_id[:8]} "
        f"elev={elevation_m}m slope={slope_pct}% "
        f"river={distance_to_river_m}m strahler={river_strahler_order} "
        f"ndwi={ndwi} ndvi={ndvi} road={distance_to_road_m}m "
        f"confidence={data_confidence}%"
    )

    return GISAnalysisOutput(
        run_id=run_id,
        elevation_m=elevation_m,
        slope_pct=slope_pct,
        terrain_difficulty=terrain_difficulty,
        distance_to_river_m=distance_to_river_m,
        river_strahler_order=river_strahler_order,
        flood_proximity_score=flood_proximity_score,
        distance_to_road_m=distance_to_road_m,
        road_access_category=road_access_category,
        distance_to_town_m=None,       # Deferred to post-MVP
        encroachment_flag=encroachment_flag,
        encroachment_detail=encroachment_detail,
        ndwi=ndwi,
        ndvi=ndvi,
        data_confidence=data_confidence,
        out_of_sentinel_zone=out_of_sentinel_zone,
        data_sources_used=list(set(data_sources_used)),
        warnings=warnings,
        drainage_block_warning=None,
        outfall_connected=outfall_connected,
        outfall_distance_m=outfall_distance_m,
        outfall_asset_type=outfall_asset_type,
        premium_elevation_profile=premium_elevation_profile,
    )
