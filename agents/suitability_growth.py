"""
LandIQ — agents/suitability_growth.py
Step 4: Suitability & Growth Agent

Pure Python + local OSM cache. ZERO LLM calls.
LGA benchmark comparisons pulled from accumulated SQLite history.

Computes:
  urban_expansion_score    OSM building density in 1km, 5km, 10km rings
  infrastructure_proximity road/airport/rail/port distances
  land_use_conflicts       OSM land use overlaps
  growth_potential         HIGH | MEDIUM | LOW (deterministic thresholds)
  lga_benchmark_*          comparison data from SQLite (Layer 3 depth)
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional

from core.schemas import (
    GISAnalysisOutput,
    GrowthPotential,
    InfrastructureProximity,
    RiskAssessOutput,
    SuitabilityGrowthOutput,
    MCPErrorResponse,
    NormalisedFeedSchema,
    CoordExtractOutput,
)
from core import data_loader

logger = logging.getLogger("landiq.suitability_growth")

# ── DB Path ───────────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = ROOT_DIR / "db" / "landiq.db"

# =============================================================================
# INFRASTRUCTURE PROXIMITY — STATIC DATASETS (hardcoded major facilities)
# Replaces full OSM POI query for MVP — accurate within 10km for major facilities.
# =============================================================================

# (name, lat, lng, type)
MAJOR_AIRPORTS = [
    ("Murtala Muhammed International Airport", 6.5774, 3.3214, "airport"),
    ("Nnamdi Azikiwe International Airport",   9.0069, 7.2625, "airport"),
    ("Port Harcourt International Airport",    4.9008, 6.9497, "airport"),
    ("Mallam Aminu Kano International Airport",12.0476, 8.5246, "airport"),
    ("Margaret Ekpo International Airport",    5.0030, 8.3472, "airport"),
    ("Akanu Ibiam International Airport",      6.4736, 7.5618, "airport"),
    ("Benin Airport",                          6.3170, 5.5995, "airport"),
]

MAJOR_PORTS = [
    ("Apapa Port Lagos",            6.4398, 3.3667, "port"),
    ("Tin Can Island Port Lagos",   6.4378, 3.3052, "port"),
    ("Port Harcourt Port",          4.7769, 7.0358, "port"),
    ("Onne Port",                   4.7167, 7.1500, "port"),
    ("Warri Port",                  5.5167, 5.7500, "port"),
]

MAJOR_RAIL_STATIONS = [
    ("Lagos Terminus (Blue Line Phase 1)", 6.4531, 3.3958, "rail"),
    ("Agbado Station (Lagos-Ibadan Rail)", 6.6597, 3.2977, "rail"),
    ("Ibadan Station",                    7.3776, 3.9470, "rail"),
    ("Warri Station",                     5.5167, 5.7500, "rail"),
    ("Port Harcourt Station",             4.8156, 7.0498, "rail"),
    ("Abuja (Idu) Station",               9.0337, 7.2822, "rail"),
    ("Kaduna Station",                    10.5167, 7.4333, "rail"),
]


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def compute_infrastructure_proximity(lat: float, lng: float) -> InfrastructureProximity:
    """Compute distances to nearest airport, port, and rail station."""
    def nearest_km(facilities: list) -> float | None:
        if not facilities:
            return None
        dists = [_haversine_km(lat, lng, f[1], f[2]) for f in facilities]
        return round(min(dists), 2)

    road_m = data_loader.nearest_road_distance(lat, lng)
    road_km = round(road_m / 1000, 2) if road_m is not None else None

    return InfrastructureProximity(
        road_km=road_km,
        airport_km=nearest_km(MAJOR_AIRPORTS),
        rail_km=nearest_km(MAJOR_RAIL_STATIONS),
        port_km=nearest_km(MAJOR_PORTS),
    )


# =============================================================================
# URBAN EXPANSION SCORE
# =============================================================================

def compute_urban_expansion_score(
    lat: float, lng: float, state: str | None
) -> float | None:
    """
    Score urban expansion potential [0.0–1.0] using OSM building density
    in concentric rings: 1km, 5km, 10km.

    Weighting:
      1km ring  (immediate context)  weight 0.50
      5km ring  (neighbourhood)      weight 0.30
      10km ring (urban fringe)       weight 0.20

    Thresholds for normalisation:
      1km:  > 200 buildings → score 1.0,  0 → score 0.0
      5km:  > 1000 buildings → 1.0
      10km: > 5000 buildings → 1.0
    """
    try:
        count_1km  = data_loader.building_density_in_buffer(lat, lng, 1000, state) or 0
        count_5km  = data_loader.building_density_in_buffer(lat, lng, 5000, state) or 0
        count_10km = data_loader.building_density_in_buffer(lat, lng, 10000, state) or 0

        norm_1km  = min(count_1km  / 200.0,  1.0)
        norm_5km  = min(count_5km  / 1000.0, 1.0)
        norm_10km = min(count_10km / 5000.0, 1.0)

        score = (0.50 * norm_1km) + (0.30 * norm_5km) + (0.20 * norm_10km)
        return round(score, 4)
    except Exception as exc:
        logger.warning(f"[suitability_growth] Urban expansion score failed: {exc}")
        return None


# =============================================================================
# GROWTH POTENTIAL CLASSIFICATION
# =============================================================================

def classify_growth_potential(
    urban_expansion_score: float | None,
    infra: InfrastructureProximity,
    flood_risk_level: str,
    terrain_suitability: str,
) -> GrowthPotential:
    """
    HIGH: expansion_score > 0.55 AND airport < 30km AND road < 2km AND not HIGH flood
    MEDIUM: expansion_score 0.25–0.55 OR good infra with MEDIUM flood
    LOW: otherwise
    """
    if urban_expansion_score is None:
        # No building data — use infra proximity as proxy
        if infra.airport_km and infra.airport_km < 30 and infra.road_km and infra.road_km < 2:
            return GrowthPotential.MEDIUM
        return GrowthPotential.LOW

    good_infra = (
        (infra.road_km is not None and infra.road_km < 2) and
        (infra.airport_km is not None and infra.airport_km < 50)
    )

    if flood_risk_level == "HIGH" or terrain_suitability == "UNSUITABLE":
        # High risk caps growth at LOW regardless of expansion score
        if urban_expansion_score > 0.55:
            return GrowthPotential.MEDIUM  # potential exists but risk limits it
        return GrowthPotential.LOW

    if urban_expansion_score > 0.55 and good_infra:
        return GrowthPotential.HIGH
    elif urban_expansion_score > 0.25 or good_infra:
        return GrowthPotential.MEDIUM
    else:
        return GrowthPotential.LOW


# =============================================================================
# LGA BENCHMARK QUERIES (from accumulated SQLite reports)
# =============================================================================

def _get_lga_benchmarks(lga: str | None, state: str | None) -> dict:
    """Pull average metrics for the LGA from the lga_benchmarks SQLite table."""
    defaults = {
        "lga_avg_flood_score": None,
        "lga_avg_growth_score": None,
        "lga_report_count": None,
    }
    if not lga or not DB_PATH.exists():
        return defaults
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT avg_flood_score, avg_growth_score, report_count "
            "FROM lga_benchmarks WHERE lga = ? AND state = ?",
            (lga, state or ""),
        ).fetchone()
        conn.close()
        if not row:
            return defaults
        return {
            "lga_avg_flood_score":  float(row["avg_flood_score"])  if row["avg_flood_score"]  is not None else None,
            "lga_avg_growth_score": float(row["avg_growth_score"]) if row["avg_growth_score"] is not None else None,
            "lga_report_count":     int(row["report_count"]),
        }
    except Exception as exc:
        logger.debug(f"[suitability_growth] LGA benchmark query failed: {exc}")
        return defaults


def _compute_percentile(
    this_score: float | None,
    avg_score: float | None,
) -> float | None:
    """
    Rough percentile estimate from a single average value.
    This is a heuristic — a proper percentile requires all individual scores.
    """
    if this_score is None or avg_score is None or avg_score == 0:
        return None
    ratio = this_score / (avg_score * 2)
    return round(min(max(ratio * 100, 0), 99), 1)


# =============================================================================
# BENCHMARK UPDATER — called after each report to keep LGA aggregates fresh
# =============================================================================

def update_lga_benchmark(
    lga: str,
    state: str,
    flood_proximity_score: float | None,
    growth_score: float | None,
    elevation_m: float | None,
    data_confidence: float,
) -> None:
    """
    Upsert the lga_benchmarks table with data from this report.
    Uses incremental average: new_avg = ((count * old_avg) + new_val) / (count + 1)
    """
    if not DB_PATH.exists():
        return
    if not lga or not state:
        return
    try:
        from datetime import datetime, timezone
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        existing = conn.execute(
            "SELECT * FROM lga_benchmarks WHERE lga = ? AND state = ?",
            (lga, state),
        ).fetchone()

        now = datetime.now(timezone.utc).isoformat()

        if existing is None:
            conn.execute(
                """
                INSERT INTO lga_benchmarks
                  (benchmark_id, lga, state, report_count,
                   avg_flood_score, avg_growth_score, avg_elevation_m,
                   avg_data_confidence, last_updated)
                VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?)
                """,
                (
                    __import__("uuid").uuid4().hex,
                    lga, state,
                    flood_proximity_score, growth_score,
                    elevation_m, data_confidence, now,
                ),
            )
        else:
            count = int(existing["report_count"])

            def incr_avg(old_avg, new_val, count):
                if old_avg is None and new_val is None:
                    return None
                old = old_avg or 0.0
                nv  = new_val or 0.0
                return (old * count + nv) / (count + 1)

            conn.execute(
                """
                UPDATE lga_benchmarks SET
                  report_count     = ?,
                  avg_flood_score  = ?,
                  avg_growth_score = ?,
                  avg_elevation_m  = ?,
                  avg_data_confidence = ?,
                  last_updated     = ?
                WHERE lga = ? AND state = ?
                """,
                (
                    count + 1,
                    incr_avg(existing["avg_flood_score"],  flood_proximity_score, count),
                    incr_avg(existing["avg_growth_score"], growth_score, count),
                    incr_avg(existing["avg_elevation_m"],  elevation_m, count),
                    incr_avg(existing["avg_data_confidence"], data_confidence, count),
                    now,
                    lga, state,
                ),
            )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.warning(f"[suitability_growth] LGA benchmark update failed: {exc}")


# =============================================================================
# MAIN RUN FUNCTION
# =============================================================================

def run(
    coord_output: CoordExtractOutput,
    gis_output: GISAnalysisOutput,
    risk_output: RiskAssessOutput,
    feed_schema: NormalisedFeedSchema,
) -> SuitabilityGrowthOutput | MCPErrorResponse:
    """
    Main entrypoint for the SuitabilityGrowth agent.
    """
    run_id = coord_output.run_id
    lat = coord_output.centroid.lat
    lng = coord_output.centroid.lng

    # State and LGA from adapter or heuristic
    state = (
        feed_schema.supplemental_gis.state_confirmed
        or data_loader.detect_state_from_centroid(lat, lng)
        if hasattr(data_loader, "detect_state_from_centroid")
        else None
    )
    lga = feed_schema.supplemental_gis.lga_confirmed

    # ── URBAN EXPANSION SCORE ─────────────────────────────────────────────────
    urban_expansion_score = compute_urban_expansion_score(lat, lng, state)

    # ── INFRASTRUCTURE PROXIMITY ──────────────────────────────────────────────
    infra = compute_infrastructure_proximity(lat, lng)

    # ── LAND USE CONFLICTS ────────────────────────────────────────────────────
    land_use_conflicts = data_loader.land_use_conflicts_at_point(lat, lng, state=state)

    # ── GROWTH POTENTIAL ──────────────────────────────────────────────────────
    growth_potential = classify_growth_potential(
        urban_expansion_score=urban_expansion_score,
        infra=infra,
        flood_risk_level=risk_output.flood_risk.value,
        terrain_suitability=risk_output.terrain_suitability.value,
    )

    # ── LGA BENCHMARKS ────────────────────────────────────────────────────────
    benchmarks = _get_lga_benchmarks(lga, state)
    growth_score_float = float(urban_expansion_score) if urban_expansion_score is not None else None

    parcel_flood_percentile = _compute_percentile(
        gis_output.flood_proximity_score,
        benchmarks["lga_avg_flood_score"],
    )
    parcel_growth_percentile = _compute_percentile(
        growth_score_float,
        benchmarks["lga_avg_growth_score"],
    )

    # ── UPDATE LGA BENCHMARK ──────────────────────────────────────────────────
    if lga and state:
        update_lga_benchmark(
            lga=lga,
            state=state,
            flood_proximity_score=gis_output.flood_proximity_score,
            growth_score=growth_score_float,
            elevation_m=gis_output.elevation_m,
            data_confidence=gis_output.data_confidence,
        )

    # ── LAND USE CONFLICT NOTES ───────────────────────────────────────────────
    conflict_notes = None
    if land_use_conflicts:
        conflict_notes = (
            f"Land use conflicts detected near this parcel: "
            f"{', '.join(land_use_conflicts)}. "
            "Verify that the intended use is compatible with surrounding land designations."
        )

    logger.info(
        f"[suitability_growth] run_id={run_id[:8]} "
        f"urban_score={urban_expansion_score} growth={growth_potential.value} "
        f"conflicts={land_use_conflicts} "
        f"airport={infra.airport_km}km road={infra.road_km}km"
    )

    return SuitabilityGrowthOutput(
        run_id=run_id,
        land_use_conflicts=land_use_conflicts,
        urban_expansion_score=urban_expansion_score,
        infrastructure_proximity=infra,
        growth_potential=growth_potential,
        growth_notes=conflict_notes,
        lga_avg_flood_score=benchmarks["lga_avg_flood_score"],
        lga_avg_growth_score=benchmarks["lga_avg_growth_score"],
        lga_report_count=benchmarks["lga_report_count"],
        parcel_flood_percentile=parcel_flood_percentile,
        parcel_growth_percentile=parcel_growth_percentile,
    )
