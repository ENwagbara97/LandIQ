"""
LandIQ — agents/coord_extract.py
Step 1: Coordinate Extraction & Validation Agent

Handles ALL input formats:
  - Manual text strings (Decimal Degrees, DMS, UTM)
  - KML / KMZ files
  - Shapefiles (.shp)
  - PDF / image (via Tesseract OCR)

CRS detection, Minna Datum transforms, polygon closure validation,
Nigeria bounding box checks, auto-flip failsafe, and dialog trigger
evaluation are all deterministic Python — zero LLM calls.

Output: CoordExtractOutput (valid) | MCPErrorResponse (on failure)
"""

from __future__ import annotations

import json
import re
import uuid
import zipfile
from pathlib import Path
from typing import Union

import numpy as np

# ── Lazy imports (not all environments have all deps) ────────────────────────
try:
    from pyproj import Transformer, CRS as ProjCRS
    _PYPROJ_AVAILABLE = True
except ImportError:
    _PYPROJ_AVAILABLE = False

try:
    from shapely.geometry import Polygon as ShapelyPolygon, Point as ShapelyPoint
    _SHAPELY_AVAILABLE = True
except ImportError:
    _SHAPELY_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image
    # Hardcoded path for Windows install via winget (UB-Mannheim)
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    _TESSERACT_AVAILABLE = True
except ImportError:
    _TESSERACT_AVAILABLE = False

# Poppler binary path (installed via winget oschwartz10612.Poppler)
_POPPLER_PATH = r"C:\Users\Admin\AppData\Local\Microsoft\WinGet\Packages\oschwartz10612.Poppler_Microsoft.Winget.Source_8wekyb3d8bbwe\poppler-25.07.0\Library\bin"

try:
    import geopandas as gpd
    _GEOPANDAS_AVAILABLE = True
except ImportError:
    _GEOPANDAS_AVAILABLE = False

from core.schemas import (
    CoordExtractOutput,
    Coordinate,
    CRSName,
    MCPErrorResponse,
    PipelineStage,
)

# =============================================================================
# NIGERIA BOUNDING BOX
# =============================================================================
NIGERIA_BBOX = {
    "lon_min": 2.676932,
    "lon_max": 14.680073,
    "lat_min": 4.240594,
    "lat_max": 13.885645,
}

# =============================================================================
# REGEX PATTERNS
# =============================================================================

# Decimal Degrees: 6.4281 or -6.4281
_DD_PATTERN = re.compile(
    r"""
    (?P<lat>-?\d{1,2}\.\d{2,8})[°\s,;]*[NS]?[,;\s]+
    (?P<lng>-?\d{1,3}\.\d{2,8})[°\s,;]*[EW]?
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Decimal Degrees with cardinal: 6.4281N 3.4219E
_DD_CARDINAL_PATTERN = re.compile(
    r"""
    (?P<lat_val>\d{1,2}\.\d{2,8})\s*(?P<lat_dir>[NS])[,;\s]+
    (?P<lng_val>\d{1,3}\.\d{2,8})\s*(?P<lng_dir>[EW])
    """,
    re.VERBOSE | re.IGNORECASE,
)

# DMS: 6°36'6.5"N 3°30'22.3"E  or  6 36 6.5 N 3 30 22.3 E
_DMS_PATTERN = re.compile(
    r"""
    (?P<lat_d>\d{1,2})[°\s]+(?P<lat_m>\d{1,2})['\s]+(?P<lat_s>[\d.]+)[\"'\s]*(?P<lat_dir>[NS])[,;\s]*
    (?P<lng_d>\d{1,3})[°\s]+(?P<lng_m>\d{1,2})['\s]+(?P<lng_s>[\d.]+)[\"'\s]*(?P<lng_dir>[EW])
    """,
    re.VERBOSE | re.IGNORECASE,
)

# UTM: Northing Easting  or  Easting Northing (bare numbers)
_UTM_PATTERN = re.compile(
    r"""
    (?P<a>\d{6,7}(?:\.\d+)?)[,;\s]+
    (?P<b>\d{6,7}(?:\.\d+)?)
    """,
    re.VERBOSE,
)

# UTM with E/N suffixes: 387804.297E 550821.575N  or  550821.575N 387804.297E
# Easting has E suffix (300_000–900_000 for Nigeria); Northing has N suffix (>1_000_000 or large 6-digit)
_UTM_SUFFIX_PATTERN = re.compile(
    r"""
    (?P<first>\d{6,7}(?:\.\d+)?)\s*(?P<first_dir>[ENen])\s*[,;\s]+
    (?P<second>\d{6,7}(?:\.\d+)?)\s*(?P<second_dir>[NSns])
    """,
    re.VERBOSE,
)

# Minna datum label detection
_MINNA_LABELS = re.compile(r"minna|clarke\s*1880|nigerian\s*datum", re.IGNORECASE)
_UTM_ZONE_PATTERN = re.compile(r"utm\s*zone\s*(\d+)\s*([NS])", re.IGNORECASE)


# =============================================================================
# DMS → DECIMAL DEGREES
# =============================================================================

def dms_to_dd(degrees: float, minutes: float, seconds: float, direction: str) -> float:
    """Convert Degrees-Minutes-Seconds to Decimal Degrees."""
    dd = degrees + minutes / 60.0 + seconds / 3600.0
    if direction.upper() in ("S", "W"):
        dd = -dd
    return dd


# =============================================================================
# CRS HEURISTIC DETECTION
# =============================================================================

def discover_zone_from_raw_metrics(easting: float, northing: float) -> tuple[CRSName, float]:
    """
    Projects a single coordinate through all 3 Nigerian UTM zones to 
    discover which zone correctly positions the property within Nigeria's borders.
    """
    test_zones = {
        CRSName.UTM_31N: 32631,
        CRSName.UTM_32N: 32632,
        CRSName.UTM_33N: 32633
    }
    valid_zones = []
    
    # Sovereign bounding box envelope for mainland Nigeria
    for crs_name, epsg in test_zones.items():
        try:
            transformer = pyproj.Transformer.from_crs(epsg, 4326, always_xy=True)
            lng, lat = transformer.transform(easting, northing)
            
            # Check if this specific zone projection places the coordinates inside Nigeria
            if (NIGERIA_BBOX["lat_min"] <= lat <= NIGERIA_BBOX["lat_max"]) and (NIGERIA_BBOX["lon_min"] <= lng <= NIGERIA_BBOX["lon_max"]):
                valid_zones.append(crs_name)
        except Exception:
            continue
            
    if len(valid_zones) == 1:
        return valid_zones[0], 80.0
    elif len(valid_zones) > 1:
        # Ambiguous (falls in Nigeria in multiple zones)
        # Default to the most central zone (Zone 32N) if valid, else pick the first one.
        if CRSName.UTM_32N in valid_zones:
            return CRSName.UTM_32N, 60.0
        return valid_zones[0], 60.0
    
    # Outside all zones
    return CRSName.UNKNOWN, 50.0

def detect_crs(
    points: list[tuple[float, float]],
    raw_text: str = "",
    coordinate_hint: str | None = None,
    datum_label: str | None = None,
) -> tuple[CRSName, float, str]:
    """
    Detect the most likely CRS from coordinate values and text cues.
    Returns (CRSName, confidence_score 0–100, discovery_method).
    """
    # Override via explicit hint (from test cases or user selection)
    if coordinate_hint == "MINNA_DATUM":
        return CRSName.MINNA, 95.0, "Explicit Hint"
    if coordinate_hint == "UTM_SWAPPED":
        # Treat as UTM — caller handles swapped axes
        return CRSName.UTM_31N, 70.0, "Explicit Hint"

    # Check text labels for Minna Datum
    combined_text = f"{raw_text} {datum_label or ''}"
    if _MINNA_LABELS.search(combined_text):
        return CRSName.MINNA, 95.0, "Datum Label Match"

    # Extract UTM zone hint from text
    utm_zone_match = _UTM_ZONE_PATTERN.search(combined_text)
    if utm_zone_match:
        zone = int(utm_zone_match.group(1))
        if zone == 31:
            return CRSName.UTM_31N, 90.0, "Text Zone Parsing"
        elif zone == 32:
            return CRSName.UTM_32N, 90.0, "Text Zone Parsing"
        elif zone == 33:
            return CRSName.UTM_33N, 90.0, "Text Zone Parsing"

    if not points:
        return CRSName.UNKNOWN, 0.0, "None"

    # Sample first point
    a, b = points[0]

    # WGS84 Lat/Lng heuristic: values in Nigeria lat/lng range
    if (NIGERIA_BBOX["lat_min"] - 5 <= a <= NIGERIA_BBOX["lat_max"] + 5 and
            NIGERIA_BBOX["lon_min"] - 5 <= b <= NIGERIA_BBOX["lon_max"] + 5):
        # Strong WGS84 confidence
        confidence = 90.0
        # Slight boost if all points are within an even tighter range
        all_in_bbox = all(
            NIGERIA_BBOX["lat_min"] <= p[0] <= NIGERIA_BBOX["lat_max"] and
            NIGERIA_BBOX["lon_min"] <= p[1] <= NIGERIA_BBOX["lon_max"]
            for p in points
        )
        if all_in_bbox:
            confidence = 95.0
        return CRSName.WGS84, confidence, "Lat/Lng Bounds Check"

    # UTM Northing/Easting heuristic for Nigeria
    # Northing: 400,000–1,600,000 for Nigeria latitude range
    # Easting: 100,000–900,000 for UTM Zones 31–33
    if (400_000 <= a <= 1_600_000 and 100_000 <= b <= 900_000):
        # 1. COMPREHENSIVE NATIONWIDE STATE-TO-ZONE MAPPER
        zone_31_indicators = ["/LA/", "/OG/", "/OY/", "/OS/", "/EK/", "/ON/", "/ED/"]
        zone_33_indicators = ["/BO/", "/AD/", "/TA/", "/YO/", "/GO/"]
        zone_32_indicators = ["/AK/", "/CR/", "/AB/", "/IM/", "/RI/", "/AN/", "/KA/", "/KD/"]

        if any(marker in combined_text.upper() for marker in zone_33_indicators):
            return CRSName.UTM_33N, 85.0, "State Prefix Detection"
        elif any(marker in combined_text.upper() for marker in zone_31_indicators):
            return CRSName.UTM_31N, 85.0, "State Prefix Detection"
        elif any(marker in combined_text.upper() for marker in zone_32_indicators):
            return CRSName.UTM_32N, 85.0, "State Prefix Detection"
            
        # STEP 2: PREFIX-LESS GEOGRAPHIC TRIAL COMPUTATION FALLBACK (SMART PATH)
        discovered_zone, conf = discover_zone_from_raw_metrics(b, a)
        return discovered_zone, conf, "Algorithmic Boundary Spatial Analysis"

    # Swapped? (b is northing, a is easting)
    if (400_000 <= b <= 1_600_000 and 100_000 <= a <= 900_000):
        discovered_zone, conf = discover_zone_from_raw_metrics(a, b)
        return discovered_zone, 60.0, "Algorithmic Boundary Spatial Analysis (Swapped axes)"

    return CRSName.UNKNOWN, 30.0, "Unknown"


# =============================================================================
# COORDINATE PARSING
# =============================================================================

def parse_dd_with_cardinal(text: str) -> list[tuple[float, float]]:
    """Parse decimal degrees with cardinal directions: 6.6018N 3.5062E"""
    points = []
    for m in _DD_CARDINAL_PATTERN.finditer(text):
        lat = float(m.group("lat_val"))
        lng = float(m.group("lng_val"))
        if m.group("lat_dir").upper() == "S":
            lat = -lat
        if m.group("lng_dir").upper() == "W":
            lng = -lng
        points.append((lat, lng))
    return points


def parse_dd_plain(text: str) -> list[tuple[float, float]]:
    """Parse plain decimal degree pairs: 6.4281, 3.4219"""
    points = []
    for m in _DD_PATTERN.finditer(text):
        lat = float(m.group("lat"))
        lng = float(m.group("lng"))
        points.append((lat, lng))
    return points


def parse_dms(text: str) -> list[tuple[float, float]]:
    """Parse Degrees-Minutes-Seconds strings."""
    points = []
    for m in _DMS_PATTERN.finditer(text):
        lat = dms_to_dd(
            float(m.group("lat_d")),
            float(m.group("lat_m")),
            float(m.group("lat_s")),
            m.group("lat_dir"),
        )
        lng = dms_to_dd(
            float(m.group("lng_d")),
            float(m.group("lng_m")),
            float(m.group("lng_s")),
            m.group("lng_dir"),
        )
        points.append((lat, lng))
    return points


def _strip_thousands_commas(text: str) -> str:
    r"""
    Remove commas used as thousands separators in large numbers.
    e.g. '378,829.13E' -> '378829.13E',  '500,331.23N' -> '500331.23N'
    Runs in a loop to handle multi-group numbers like 1,440,000.
    Safe for DD/DMS text -- those numbers are too small to match \d,\d{3}.
    """
    prev = None
    result = text
    while result != prev:
        prev = result
        # Match digit + comma + exactly 3 digits NOT followed by another digit
        result = re.sub(r'(\d),(\d{3})(?!\d)', r'\1\2', result)
    return result


def parse_utm_suffix_pairs(text: str) -> list[tuple[float, float]]:
    """
    Parse UTM coordinates with explicit E/N direction suffixes.
    e.g. '387804.297E 550821.575N'  or  '550821.575N 387804.297E'
    Returns list of (northing, easting) tuples ready for utm_to_wgs84.
    """
    points = []
    for m in _UTM_SUFFIX_PATTERN.finditer(text):
        first_val = float(m.group("first"))
        first_dir = m.group("first_dir").upper()
        second_val = float(m.group("second"))
        second_dir = m.group("second_dir").upper()

        if first_dir == "E" and second_dir == "N":
            easting, northing = first_val, second_val
        elif first_dir == "N" and second_dir == "E":
            northing, easting = first_val, second_val
        else:
            # Fallback: larger value is typically northing in Nigeria
            if first_val > second_val:
                northing, easting = first_val, second_val
            else:
                northing, easting = second_val, first_val

        # Store as (northing, easting) — same convention as parse_utm_pairs
        points.append((northing, easting))
    return points


def parse_utm_pairs(text: str) -> list[tuple[float, float]]:
    """Parse UTM Northing/Easting bare number pairs.

    Returns tuples in (northing, easting) order as expected by transform_to_wgs84.

    Ordering heuristic: for Nigerian UTM (zones 31-33N), northing values are
    always larger than easting values:
      - Easting:  ~100,000 – 900,000 m  (false easting 500,000m)
      - Northing: ~400,000 – 1,600,000 m (from equator)
    When both a, b are in the UTM scale, the larger one is northing.
    This corrects survey plans that list easting before northing in the text.
    """
    points = []
    for m in _UTM_PATTERN.finditer(text):
        a = float(m.group("a"))
        b = float(m.group("b"))
        # Apply northing/easting heuristic: larger value = northing
        if a >= b:
            points.append((a, b))   # (northing=a, easting=b)
        else:
            points.append((b, a))   # (northing=b, easting=a)
    return points


def parse_text_input(
    raw_text: str,
    coordinate_hint: str | None = None,
    datum_label: str | None = None,
) -> tuple[list[tuple[float, float]], bool, bool]:
    """
    Auto-detect format and parse coordinates from raw text.
    Returns: (points, is_dms, is_utm)
    """
    # Pre-process: strip thousands-separator commas (e.g. 378,829.13 -> 378829.13)
    # Safe to apply globally — DD/DMS values are too small to have thousands commas.
    raw_text = _strip_thousands_commas(raw_text)

    # 1. Try DMS first (most specific pattern)
    dms_points = parse_dms(raw_text)
    if dms_points and len(dms_points) >= 3:
        return dms_points, True, False

    # 2. Try DD with cardinal directions
    dd_cardinal = parse_dd_with_cardinal(raw_text)
    if dd_cardinal and len(dd_cardinal) >= 3:
        return dd_cardinal, False, False

    # 3. Try plain DD
    dd_plain = parse_dd_plain(raw_text)
    if dd_plain and len(dd_plain) >= 3:
        return dd_plain, False, False

    # 4. Try UTM with explicit E/N suffixes (e.g. Nigerian survey plan format: 387804.297E 550821.575N)
    utm_suffix = parse_utm_suffix_pairs(raw_text)
    if utm_suffix and len(utm_suffix) >= 3:
        return utm_suffix, False, True

    # 5. Try bare UTM number pairs
    utm_pairs = parse_utm_pairs(raw_text)
    if utm_pairs and len(utm_pairs) >= 3:
        return utm_pairs, False, True

    return [], False, False


# =============================================================================
# CRS TRANSFORMS
# =============================================================================

def utm_to_wgs84(
    northing: float,
    easting: float,
    crs_name: CRSName,
) -> tuple[float, float]:
    """Transform a UTM coordinate to WGS84 lat/lng."""
    if not _PYPROJ_AVAILABLE:
        raise RuntimeError("pyproj not available — cannot perform CRS transform")

    epsg_map = {
        CRSName.UTM_31N: 32631,
        CRSName.UTM_32N: 32632,
        CRSName.UTM_33N: 32633,
    }
    epsg = epsg_map.get(crs_name, 32632)  # default to 32N if ambiguous
    transformer = Transformer.from_crs(epsg, 4326, always_xy=True)
    lng, lat = transformer.transform(easting, northing)
    return lat, lng


def minna_to_wgs84(lat_minna: float, lng_minna: float) -> tuple[float, float]:
    """
    Transform Minna Datum (EPSG:4263) to WGS84 (EPSG:4326) with explicit towgs84 parameters.
    Accuracy: approximately ±5 metres.
    """
    if not _PYPROJ_AVAILABLE:
        raise RuntimeError("pyproj not available — cannot perform Minna Datum transform")
    minna_proj = "+proj=longlat +ellps=clrk80 +towgs84=-92,-93,272,0,0,0,0 +no_defs"
    transformer = Transformer.from_proj(minna_proj, "EPSG:4326", always_xy=True)
    lng_wgs, lat_wgs = transformer.transform(lng_minna, lat_minna)
    return lat_wgs, lng_wgs


def transform_to_wgs84(
    points: list[tuple[float, float]],
    crs_name: CRSName,
    is_utm: bool,
    raw_text: str = "",
) -> list[tuple[float, float]]:
    """Transform all points to WGS84 based on detected CRS."""
    if crs_name == CRSName.WGS84:
        return points  # Already WGS84

    transformed = []
    if crs_name == CRSName.MINNA:
        if is_utm:
            # Minna UTM: Determine zone (31, 32, or 33) using smart heuristic
            zone = detect_minna_utm_zone(points, raw_text)
            minna_proj_str = (
                f"+proj=utm +zone={zone} +ellps=clrk80 "
                f"+towgs84=-92,-93,272,0,0,0,0 +units=m +no_defs"
            )
            transformer = Transformer.from_proj(minna_proj_str, "EPSG:4326", always_xy=True)
            for northing, easting in points:
                lng_wgs, lat_wgs = transformer.transform(easting, northing)
                transformed.append((lat_wgs, lng_wgs))
        else:
            # Minna Geographic (Decimal Degrees)
            for lat, lng in points:
                lat_wgs, lng_wgs = minna_to_wgs84(lat, lng)
                transformed.append((lat_wgs, lng_wgs))
    elif is_utm:
        fallback_crs = crs_name if crs_name in (CRSName.UTM_31N, CRSName.UTM_32N, CRSName.UTM_33N) else CRSName.UTM_32N
        for northing, easting in points:
            lat, lng = utm_to_wgs84(northing, easting, fallback_crs)
            transformed.append((lat, lng))
    else:
        # Unknown CRS — return as-is, let downstream flag it
        return points

    return transformed


# =============================================================================
# GEOMETRY UTILITIES
# =============================================================================

def compute_centroid(points: list[tuple[float, float]]) -> Coordinate:
    """Compute the arithmetic centroid of a polygon."""
    lats = [p[0] for p in points]
    lngs = [p[1] for p in points]
    return Coordinate(lat=round(sum(lats) / len(lats), 6), lng=round(sum(lngs) / len(lngs), 6))


def is_closed_polygon(points: list[tuple[float, float]], tolerance: float = 1e-6) -> bool:
    """Check if first and last points are the same (closed polygon)."""
    if len(points) < 4:
        return False
    first, last = points[0], points[-1]
    return (abs(first[0] - last[0]) < tolerance and abs(first[1] - last[1]) < tolerance)


def compute_area_ha(points: list[tuple[float, float]]) -> float:
    """
    Compute polygon area in hectares using the Shoelace formula.
    Uses an approximate metres-per-degree conversion centred on the polygon centroid.
    Accurate to ~1% for small parcels (< 100 ha).
    """
    try:
        if not _SHAPELY_AVAILABLE:
            # Fallback: rough Shoelace in degrees, then convert
            n = len(points)
            area_deg = 0.0
            for i in range(n):
                j = (i + 1) % n
                area_deg += points[i][1] * points[j][0]
                area_deg -= points[j][1] * points[i][0]
            area_deg = abs(area_deg) / 2.0
            # 1 degree lat ≈ 111,320m, 1 degree lng ≈ 111,320 * cos(lat)
            mid_lat = sum(p[0] for p in points) / len(points)
            m_per_deg_lat = 111_320.0
            m_per_deg_lng = 111_320.0 * abs(np.cos(np.radians(mid_lat)))
            area_m2 = area_deg * m_per_deg_lat * m_per_deg_lng
            return round(area_m2 / 10_000, 4)

        # Use Shapely with a local azimuthal equidistant projection for accuracy
        from shapely.geometry import Polygon
        import pyproj

        mid_lat = sum(p[0] for p in points) / len(points)
        mid_lng = sum(p[1] for p in points) / len(points)

        # Check if coordinates look like valid WGS84 lat/lng before building proj
        if not (-90 <= mid_lat <= 90 and -180 <= mid_lng <= 180):
            # If coordinates are in meters (UTM/Minna), compute raw area using Shapely directly
            poly = Polygon([(lng, lat) for lat, lng in points])
            return round(poly.area / 10_000, 4)

        proj_str = f"+proj=aeqd +lat_0={mid_lat} +lon_0={mid_lng} +datum=WGS84 +units=m"
        transformer = Transformer.from_crs("EPSG:4326", proj_str, always_xy=True)
        projected = [transformer.transform(lng, lat) for lat, lng in points]
        poly = Polygon(projected)
        area_ha = poly.area / 10_000
        return round(area_ha, 4)
    except Exception:
        return 0.0


def is_inside_nigeria(centroid: Coordinate) -> bool:
    """Check if centroid falls within Nigeria's bounding box."""
    return (
        NIGERIA_BBOX["lat_min"] <= centroid.lat <= NIGERIA_BBOX["lat_max"] and
        NIGERIA_BBOX["lon_min"] <= centroid.lng <= NIGERIA_BBOX["lon_max"]
    )


def detect_minna_utm_zone(points: list[tuple[float, float]], raw_text: str = "") -> int:
    """
    Detect Minna UTM zone (31, 32, or 33) based on text hints or centroid overlap with Nigeria.
    """
    utm_zone_match = _UTM_ZONE_PATTERN.search(raw_text)
    if utm_zone_match:
        return int(utm_zone_match.group(1))

    # Test which zone places the centroid inside Nigeria
    valid_zones = []
    for z in (31, 32, 33):
        minna_proj_str = (
            f"+proj=utm +zone={z} +ellps=clrk80 "
            f"+towgs84=-92,-93,272,0,0,0,0 +units=m +no_defs"
        )
        try:
            transformer = Transformer.from_proj(minna_proj_str, "EPSG:4326", always_xy=True)
            pts = []
            for northing, easting in points:
                lng_wgs, lat_wgs = transformer.transform(easting, northing)
                pts.append((lat_wgs, lng_wgs))
            centroid_tmp = compute_centroid(pts)
            if is_inside_nigeria(centroid_tmp):
                valid_zones.append(z)
        except Exception:
            pass

    # Inferred zone from Easting values
    easting_guess = 32
    if points:
        _, easting = points[0]
        if 100_000 <= easting <= 400_000:
            easting_guess = 31
        elif 400_000 <= easting <= 700_000:
            easting_guess = 32
        elif 700_000 <= easting <= 900_000:
            easting_guess = 33

    if len(valid_zones) == 1:
        return valid_zones[0]
    elif len(valid_zones) > 1:
        if easting_guess in valid_zones:
            return easting_guess
        return min(valid_zones, key=lambda z: abs(z - easting_guess))

    return easting_guess  # Default fallback


def test_flipped_axes(
    points: list[tuple[float, float]],
    crs_name: CRSName,
    is_utm: bool = False,
    raw_text: str = "",
) -> tuple[list[tuple[float, float]], bool]:
    """
    Auto-flip failsafe: if centroid is outside Nigeria, test swapping
    Easting/Northing axes and re-check.
    Returns (flipped_points, was_successful).
    """
    flipped = [(b, a) for a, b in points]
    try:
        if crs_name in (CRSName.UTM_31N, CRSName.UTM_32N, CRSName.UTM_33N):
            # Treat flipped[i] as (northing, easting) → already correct order after flip
            wgs_flipped = [utm_to_wgs84(lat, lng, crs_name) for lat, lng in flipped]
        elif crs_name == CRSName.MINNA:
            if is_utm:
                zone = detect_minna_utm_zone(flipped, raw_text)
                minna_proj_str = (
                    f"+proj=utm +zone={zone} +ellps=clrk80 "
                    f"+towgs84=-92,-93,272,0,0,0,0 +units=m +no_defs"
                )
                transformer = Transformer.from_proj(minna_proj_str, "EPSG:4326", always_xy=True)
                wgs_flipped = []
                for northing, easting in flipped:
                    lng_wgs, lat_wgs = transformer.transform(easting, northing)
                    wgs_flipped.append((lat_wgs, lng_wgs))
            else:
                wgs_flipped = [minna_to_wgs84(lat, lng) for lat, lng in flipped]
        else:
            wgs_flipped = flipped

        centroid_flipped = compute_centroid(wgs_flipped)
        if is_inside_nigeria(centroid_flipped):
            return wgs_flipped, True
    except Exception:
        pass
    return points, False


# =============================================================================
# DIALOG TRIGGER EVALUATION (T1–T5)
# =============================================================================

def evaluate_dialog_triggers(
    crs_confidence: float,
    crs_name: CRSName,
    inside_nigeria: bool,
    area_discrepancy_pct: float | None,
    minna_detected: bool,
    dms_converted: bool,
) -> list[str]:
    """
    Evaluate which CRS dialogs must fire before analysis proceeds.
    T1: CRS confidence < 60
    T2: is_inside_nigeria = false (after auto-flip)
    T3: Area discrepancy > 10%
    T4: Minna Datum detected
    T5: DMS format detected
    """
    triggers = []
    if crs_confidence < 60:
        triggers.append("T1")
    if not inside_nigeria:
        triggers.append("T2")
    if area_discrepancy_pct is not None and abs(area_discrepancy_pct) > 10:
        triggers.append("T3")
    if minna_detected:
        triggers.append("T4")
    if dms_converted:
        triggers.append("T5")
    return triggers


# =============================================================================
# KML / KMZ PARSING
# =============================================================================

def parse_kml_coordinates(kml_text: str) -> list[tuple[float, float]]:
    """Extract coordinates from KML <coordinates> block."""
    coord_block = re.search(r"<coordinates>(.*?)</coordinates>", kml_text, re.DOTALL | re.IGNORECASE)
    if not coord_block:
        return []
    raw = coord_block.group(1).strip()
    points = []
    for token in re.split(r"[\s\n]+", raw):
        token = token.strip()
        if not token:
            continue
        parts = token.split(",")
        if len(parts) >= 2:
            try:
                lng = float(parts[0])
                lat = float(parts[1])
                points.append((lat, lng))
            except ValueError:
                continue
    return points


def parse_kml_file(file_bytes: bytes) -> list[tuple[float, float]]:
    """Parse KML file bytes and extract polygon coordinates."""
    text = file_bytes.decode("utf-8", errors="ignore")
    return parse_kml_coordinates(text)


def parse_kmz_file(file_bytes: bytes) -> list[tuple[float, float]]:
    """Extract and parse the KML inside a KMZ archive."""
    import io
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
        for name in z.namelist():
            if name.endswith(".kml"):
                kml_bytes = z.read(name)
                return parse_kml_file(kml_bytes)
    return []


# =============================================================================
# SHAPEFILE PARSING
# =============================================================================

def parse_shapefile(file_bytes: bytes, filename: str = "upload.zip") -> list[tuple[float, float]]:
    """
    Parse a zipped shapefile and extract the first polygon's exterior ring.
    Requires geopandas + fiona.
    """
    if not _GEOPANDAS_AVAILABLE:
        raise RuntimeError("geopandas not available — cannot parse shapefiles")
    import io
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = Path(tmpdir) / "upload.zip"
        zip_path.write_bytes(file_bytes)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmpdir)

        shp_files = list(Path(tmpdir).glob("**/*.shp"))
        if not shp_files:
            return []

        gdf = gpd.read_file(shp_files[0])
        if gdf.empty:
            return []

        # Re-project to WGS84 if needed
        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)

        geom = gdf.geometry.iloc[0]
        if geom.geom_type == "Polygon":
            coords = list(geom.exterior.coords)
            return [(lat, lng) for lng, lat in coords]
        elif geom.geom_type == "MultiPolygon":
            coords = list(geom.geoms[0].exterior.coords)
            return [(lat, lng) for lng, lat in coords]
    return []


# =============================================================================
# CLOUD VISION CADASTRAL EXTRACTION METAPROMPT
# Sent to Gemini / GPT-4o / Claude when a vision API key is configured.
# =============================================================================

_CADASTRAL_VISION_PROMPT = """You are a specialist coordinate extraction agent for Nigerian survey plans.

You will receive an image of a Nigerian cadastral survey plan.

Your job:
1. Locate ALL boundary coordinates — they may be in a table, written along boundary lines, or printed vertically on the page margin.
2. Extract ALL tie-point or origin coordinates (usually labeled mE / mN, or Easting / Northing).
3. Extract ALL bearings and distances along boundary legs.
4. Ignore: red certification stamps, surveyor signatures, title blocks, north arrows.

Nigerian survey plans use these formats — recognise all of them:
- Eastings: 6-digit number followed by mE or .000mE (e.g. 387223.007mE)
- Northings: 6-digit number followed by mN or .000mN
- Bearings: Whole Circle (93° 02') or Quadrant (N62°15'E)
- Distances: decimal metres (e.g. 9.73m or 9.730m)
- Station IDs: SC/AK/K 5946, Beacon 12, etc.

Return ONLY this JSON — no explanation, no preamble, no markdown fences:
{
  "origin": {"easting": number_or_null, "northing": number_or_null},
  "crs_hint": "Minna / WGS84 / unknown",
  "datum": "UTM Zone 32 / ZONE32 / etc or null",
  "boundaries": [
    {
      "bearing": "string as written on plan",
      "distance_m": number,
      "to_easting": number_or_null,
      "to_northing": number_or_null
    }
  ],
  "raw_coordinates": [[easting, northing]],
  "confidence": 0_to_100,
  "warnings": ["list any text you could not read clearly"]
}

If you cannot find coordinates, return:
{"error": "NO_COORDINATES_FOUND", "warnings": ["reason"]}"""


def _vision_result_to_text(vision_json: dict) -> str:
    """
    Convert the structured JSON from a Cloud Vision API into the flat text
    format that the Cadastral Engine and parse_text_input() already understand.

    This means the rest of the pipeline is completely unchanged —
    Cloud Vision simply replaces Tesseract, not the entire parse chain.
    """
    lines = []

    # Datum / CRS hint
    datum = vision_json.get("datum") or vision_json.get("crs_hint", "")
    if datum:
        lines.append(f"DATUM: {datum}")

    # Origin / tie-point
    origin = vision_json.get("origin") or {}
    e = origin.get("easting")
    n = origin.get("northing")
    if e and n:
        lines.append(f"{e:.3f}mE")
        lines.append(f"{n:.3f}mN")

    # Explicit raw coordinate table (Type A plans)
    for pair in vision_json.get("raw_coordinates", []):
        if len(pair) == 2:
            lines.append(f"E: {pair[0]:.3f}  N: {pair[1]:.3f}")

    # Boundary traverse lines (Type B plans)
    for leg in vision_json.get("boundaries", []):
        bearing = leg.get("bearing", "")
        dist = leg.get("distance_m")
        to_e = leg.get("to_easting")
        to_n = leg.get("to_northing")
        if bearing and dist is not None:
            lines.append(f"{bearing}  {dist:.3f}m")
        if to_e and to_n:
            lines.append(f"E: {to_e:.3f}  N: {to_n:.3f}")

    return "\n".join(lines)


def _ocr_via_gemini(image_bytes: bytes, api_key: str) -> str:
    """Call Gemini 1.5 Flash Vision API and return extracted text."""
    import base64
    import json as _json
    import requests as _req

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-1.5-flash:generateContent?key={api_key}"
    )
    b64 = base64.b64encode(image_bytes).decode()
    payload = {
        "contents": [{
            "parts": [
                {"text": _CADASTRAL_VISION_PROMPT},
                {"inline_data": {"mime_type": "image/png", "data": b64}},
            ]
        }]
    }
    resp = _req.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    # Strip markdown fences if model adds them
    raw = raw.strip("```json").strip("```").strip()
    result = _json.loads(raw)
    if "error" in result:
        raise RuntimeError(f"Gemini Vision: {result.get('warnings', result['error'])}")
    return _vision_result_to_text(result)


def _ocr_via_openai(image_bytes: bytes, api_key: str) -> str:
    """Call GPT-4o Vision API and return extracted text."""
    import base64
    import json as _json
    import requests as _req

    b64 = base64.b64encode(image_bytes).decode()
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": _CADASTRAL_VISION_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]
        }],
        "max_tokens": 1000,
    }
    resp = _req.post("https://api.openai.com/v1/chat/completions",
                     headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"].strip()
    raw = raw.strip("```json").strip("```").strip()
    result = _json.loads(raw)
    if "error" in result:
        raise RuntimeError(f"GPT-4o Vision: {result.get('warnings', result['error'])}")
    return _vision_result_to_text(result)


def _ocr_via_anthropic(image_bytes: bytes, api_key: str) -> str:
    """Call Claude 3.5 Sonnet Vision API and return extracted text."""
    import base64
    import json as _json
    import requests as _req

    b64 = base64.b64encode(image_bytes).decode()
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "claude-3-5-sonnet-20241022",
        "max_tokens": 1000,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/png", "data": b64
                }},
                {"type": "text", "text": _CADASTRAL_VISION_PROMPT},
            ]
        }]
    }
    resp = _req.post("https://api.anthropic.com/v1/messages",
                     headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    raw = resp.json()["content"][0]["text"].strip()
    raw = raw.strip("```json").strip("```").strip()
    result = _json.loads(raw)
    if "error" in result:
        raise RuntimeError(f"Claude Vision: {result.get('warnings', result['error'])}")
    return _vision_result_to_text(result)


# =============================================================================
# OCR PARSING (PDF / IMAGE)
# =============================================================================

def ocr_file(
    file_bytes: bytes,
    filename: str,
    vision_provider: str | None = None,
    vision_api_key: str | None = None,
) -> str:
    """
    Extract text from a PDF or image file.

    If vision_provider and vision_api_key are supplied, the appropriate
    Cloud Vision API is called and Tesseract is bypassed entirely.

    Supported vision_provider values:
      "gemini"    → Google Gemini 1.5 Flash Vision
      "openai"    → OpenAI GPT-4o Vision
      "anthropic" → Anthropic Claude 3.5 Sonnet Vision

    Falls back to local Tesseract OCR when no provider is configured.

    Returns raw text string.
    """
    import io
    import logging
    _logger = logging.getLogger("landiq.vision_ocr")

    ext = Path(filename).suffix.lower()

    # ── CLOUD VISION PATH ────────────────────────────────────────────────────
    if vision_provider and vision_api_key:
        # For PDFs, convert first page to PNG bytes for the Vision API
        if ext == ".pdf":
            try:
                from pdf2image import convert_from_bytes
                pages = convert_from_bytes(file_bytes, dpi=200, first_page=1, last_page=1)
                img_buf = io.BytesIO()
                pages[0].save(img_buf, format="PNG")
                image_bytes_for_api = img_buf.getvalue()
            except Exception:
                # If pdf2image fails, try pypdf text first
                try:
                    import pypdf
                    reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text() or ""
                    text = text.strip()
                    if len(text) > 50 and any(c.isdigit() for c in text):
                        return text
                except Exception:
                    pass
                # Fall through to local OCR
                image_bytes_for_api = None
        else:
            image_bytes_for_api = file_bytes

        if image_bytes_for_api:
            provider = vision_provider.lower()
            try:
                if provider == "gemini":
                    _logger.info("[vision_ocr] Using Gemini 1.5 Flash Vision")
                    return _ocr_via_gemini(image_bytes_for_api, vision_api_key)
                elif provider == "openai":
                    _logger.info("[vision_ocr] Using GPT-4o Vision")
                    return _ocr_via_openai(image_bytes_for_api, vision_api_key)
                elif provider == "anthropic":
                    _logger.info("[vision_ocr] Using Claude 3.5 Sonnet Vision")
                    return _ocr_via_anthropic(image_bytes_for_api, vision_api_key)
                else:
                    _logger.warning(f"[vision_ocr] Unknown provider '{provider}', falling back to Tesseract")
            except Exception as exc:
                _logger.warning(f"[vision_ocr] Cloud Vision call failed ({exc}). Falling back to Tesseract.")
                # Fall through to Tesseract below

    # ── LOCAL TESSERACT PATH (default / fallback) ───────────────────────────
    if ext == ".pdf":
        # 1. Try direct text extraction via pypdf (for digital/vector PDFs)
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""
            text = text.strip()
            if len(text) > 50 and any(char.isdigit() for char in text):
                return text
        except Exception:
            pass

        # 2. Fall back to Tesseract OCR (for scanned image PDFs)
        if not _TESSERACT_AVAILABLE:
            raise RuntimeError(
                "pytesseract not available on this server. "
                "Unable to read scanned PDFs. Please use a digital PDF or paste the text directly."
            )

        try:
            try:
                from pdf2image import convert_from_bytes
                from pdf2image.exceptions import PDFInfoNotInstalledError
                from agents.vision_preprocessor import preprocess_image_for_ocr
                try:
                    pages = convert_from_bytes(file_bytes, dpi=300, poppler_path=_POPPLER_PATH)
                except PDFInfoNotInstalledError:
                    raise ImportError("Poppler is missing")

                texts = []
                for page in pages:
                    img_byte_arr = io.BytesIO()
                    page.save(img_byte_arr, format='PNG')
                    img_bytes = img_byte_arr.getvalue()
                    processed_bytes = preprocess_image_for_ocr(img_bytes)
                    processed_img = Image.open(io.BytesIO(processed_bytes))
                    text = pytesseract.image_to_string(processed_img, lang="eng", config="--psm 6")
                    texts.append(text)
                return "\n".join(texts)
            except ImportError:
                raise RuntimeError(
                    "PDF/image processing tools are not configured correctly. "
                    "Please paste coordinate text directly instead."
                )
        except Exception as exc:
            if "TesseractNotFoundError" in type(exc).__name__ or "tesseract is not installed" in str(exc).lower():
                raise RuntimeError(
                    "Tesseract OCR could not be found. "
                    "Please paste coordinate text directly."
                ) from exc
            raise

    elif ext in (".jpg", ".jpeg", ".png", ".tiff", ".bmp"):
        if not _TESSERACT_AVAILABLE:
            raise RuntimeError(
                "pytesseract not available on this server. "
                "Image parsing is unavailable. Please paste coordinate text directly."
            )

        try:
            from agents.vision_preprocessor import preprocess_image_for_ocr
            processed_bytes = preprocess_image_for_ocr(file_bytes)
            img = Image.open(io.BytesIO(processed_bytes))
            return pytesseract.image_to_string(img, lang="eng", config="--psm 6")
        except Exception as exc:
            if "TesseractNotFoundError" in type(exc).__name__ or "tesseract is not installed" in str(exc).lower():
                raise RuntimeError(
                    "Tesseract OCR is not installed on this system. "
                    "Image parsing is unavailable. Please paste coordinate text directly."
                ) from exc
            raise
    else:
        raise RuntimeError(f"Unsupported file extension for text extraction: {ext}")

    """
    Extract text from a PDF or image file.
    Returns raw text string.
    """
    import io

    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        # 1. Try direct text extraction via pypdf (for digital/vector PDFs)
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""
            text = text.strip()
            if len(text) > 50 and any(char.isdigit() for char in text):
                return text
        except Exception as exc:
            pass

        # 2. Fall back to Tesseract OCR (for scanned image PDFs)
        if not _TESSERACT_AVAILABLE:
            raise RuntimeError(
                "pytesseract not available on this server. "
                "Unable to read scanned PDFs. Please use a digital PDF or paste the text directly."
            )

        try:
            # Try pdf2image if available
            try:
                from pdf2image import convert_from_bytes
                from pdf2image.exceptions import PDFInfoNotInstalledError
                from agents.vision_preprocessor import preprocess_image_for_ocr
                try:
                    pages = convert_from_bytes(file_bytes, dpi=300, poppler_path=_POPPLER_PATH)
                except PDFInfoNotInstalledError:
                    raise ImportError("Poppler is missing")
                
                texts = []
                for page in pages:
                    # Convert PIL Image back to bytes for preprocessor
                    img_byte_arr = io.BytesIO()
                    page.save(img_byte_arr, format='PNG')
                    img_bytes = img_byte_arr.getvalue()
                    
                    processed_bytes = preprocess_image_for_ocr(img_bytes)
                    processed_img = Image.open(io.BytesIO(processed_bytes))
                    
                    # Try PSM 6 (uniform block) which is best for coordinate tables
                    text = pytesseract.image_to_string(processed_img, lang="eng", config="--psm 6")
                    texts.append(text)
                    
                return "\n".join(texts)
            except ImportError:
                raise RuntimeError(
                    "PDF/image processing tools are not configured correctly. "
                    "Please paste coordinate text directly instead."
                )
        except Exception as exc:
            if "TesseractNotFoundError" in type(exc).__name__ or "tesseract is not installed" in str(exc).lower():
                raise RuntimeError(
                    "Tesseract OCR could not be found. "
                    "Please paste coordinate text directly."
                ) from exc
            raise

    elif ext in (".jpg", ".jpeg", ".png", ".tiff", ".bmp"):
        if not _TESSERACT_AVAILABLE:
            raise RuntimeError(
                "pytesseract not available on this server. "
                "Image parsing is unavailable. Please paste coordinate text directly."
            )

        try:
            from agents.vision_preprocessor import preprocess_image_for_ocr
            processed_bytes = preprocess_image_for_ocr(file_bytes)
            img = Image.open(io.BytesIO(processed_bytes))
            return pytesseract.image_to_string(img, lang="eng", config="--psm 6")
        except Exception as exc:
            if "TesseractNotFoundError" in type(exc).__name__ or "tesseract is not installed" in str(exc).lower():
                raise RuntimeError(
                    "Tesseract OCR is not installed on this system. "
                    "Image parsing is unavailable. Please paste coordinate text directly."
                ) from exc
            raise
    else:
        raise RuntimeError(f"Unsupported file extension for text extraction: {ext}")


# =============================================================================
# MAIN RUN FUNCTION
# =============================================================================

def reverse_geocode(lat: float, lng: float) -> tuple[str, str]:
    import requests
    import logging
    state = "Unresolved — confirm State"
    lga = "Unresolved — confirm LGA"
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lng}&format=json&zoom=10"
        headers = {"User-Agent": "LandIQ-Pipeline"}
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            addr = data.get("address", {})
            if "state" in addr:
                state = addr["state"].replace(" State", "")
            if "county" in addr:
                lga = addr["county"]
            elif "city" in addr:
                lga = addr["city"]
    except Exception as e:
        logging.getLogger("landiq.coord_extract").warning(f"Nominatim lookup failed: {e}")
    return state, lga


def run(
    raw_input: str | None = None,
    file_bytes: bytes | None = None,
    filename: str | None = None,
    run_id: str | None = None,
    coordinate_hint: str | None = None,
    datum_label: str | None = None,
    stated_area_ha: float | None = None,
    vision_provider: str | None = None,
    vision_api_key: str | None = None,
) -> CoordExtractOutput | MCPErrorResponse:
    """
    Main entrypoint for the CoordExtract agent.

    Args:
        raw_input      : Raw text string of coordinates (manual entry).
        file_bytes     : Raw bytes of uploaded file (PDF, image, KML, KMZ, SHP).
        filename       : Original filename (used to detect file type).
        run_id         : Pipeline run ID. Generated if not provided.
        coordinate_hint: Override hint ("MINNA_DATUM", "UTM_SWAPPED", etc.)
        datum_label    : Text from survey plan indicating datum.
        stated_area_ha : User-stated area in hectares (for discrepancy check).
        vision_provider: Cloud Vision provider: "gemini" | "openai" | "anthropic"
        vision_api_key : API key for the chosen vision provider.

    Returns:
        CoordExtractOutput on success.
        MCPErrorResponse on any validation failure.
    """
    if run_id is None:
        run_id = str(uuid.uuid4())

    warnings: list[str] = []
    raw_text = raw_input or ""
    is_dms = False
    is_utm = False
    points: list[tuple[float, float]] = []

    # ── STEP A: Extract raw text from file if provided ────────────────────
    if file_bytes and filename:
        ext = Path(filename).suffix.lower()
        try:
            if ext == ".kml":
                points = parse_kml_file(file_bytes)
            elif ext == ".kmz":
                points = parse_kmz_file(file_bytes)
            elif ext == ".zip":
                points = parse_shapefile(file_bytes, filename)
            elif ext in (".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".bmp"):
                raw_text = ocr_file(
                    file_bytes, filename,
                    vision_provider=vision_provider,
                    vision_api_key=vision_api_key,
                )
            else:
                return MCPErrorResponse(
                    error_code="UNSUPPORTED_FORMAT",
                    instruction=f"File format '{ext}' is not supported. "
                                "Upload a PDF, image, KML, KMZ, or zipped shapefile.",
                    run_id=run_id,
                    stage=PipelineStage.COORD_EXTRACT,
                )
        except Exception as exc:
            return MCPErrorResponse(
                error_code="FILE_PARSE_ERROR",
                instruction=str(exc) if isinstance(exc, RuntimeError) else (
                    "Could not read the uploaded file. "
                    "Ensure the file is not password-protected or corrupted."
                ),
                run_id=run_id,
                stage=PipelineStage.COORD_EXTRACT,
                detail=str(exc),
            )


    # ── STEP B: Parse text → coordinate list ─────────────────────────────
    if not points and raw_text:
        points, is_dms, is_utm = parse_text_input(raw_text, coordinate_hint, datum_label)

    # ── STEP B-FALLBACK: Cadastral Tabular OCR Scanner ───────────────────
    # Standard format parsers (DD, DMS, UTM suffix/pairs) could not detect any
    # coordinates. This is common with scanned Nigerian survey plans that use a
    # Station-ID | Easting | Northing tabular column layout.
    # Try the cadastral engine's UTM-scale tabular scanner as a last resort.
    if not points and raw_text:
        try:
            from agents.cadastral_engine import _scan_ocr_text_for_stations
            cad_stations = _scan_ocr_text_for_stations(raw_text)
            if len(cad_stations) >= 3:
                # Convert to (northing, easting) tuples — transform_to_wgs84
                # line 427 unpacks each point as: for northing, easting in points
                points = [
                    (s.stated_northing, s.stated_easting)
                    for s in cad_stations
                    if s.stated_northing is not None and s.stated_easting is not None
                ]
                if len(points) >= 3:
                    is_utm = True
                    warnings.append(
                        "TABULAR_OCR_FALLBACK: Coordinates were extracted from a "
                        "Station-ID/Easting/Northing tabular layout. "
                        "For full cadastral audit (misclosure, area variance, per-station ledger) "
                        "use the dedicated POST /api/cadastral endpoint."
                    )
                else:
                    points = []
        except Exception:
            pass  # Fallback failure is silent — handled by the error below

    if not points:
        return MCPErrorResponse(
            error_code="NO_COORDINATES_DETECTED",
            instruction=(
                "We could not find any coordinates in this document. "
                "This may be a scanned plan — try uploading a "
                "clearer scan. Or enter your coordinates manually "
                "below."
            ),
            run_id=run_id,
            stage=PipelineStage.COORD_EXTRACT,
        )


    if is_dms:
        warnings.append("DMS_CONVERTED")

    # ── STEP C: Detect CRS ────────────────────────────────────────────────
    crs_name, crs_confidence, discovery_method = detect_crs(points, raw_text, coordinate_hint, datum_label)
    minna_detected = (crs_name == CRSName.MINNA) or bool(_MINNA_LABELS.search(f"{raw_text} {datum_label or ''}"))

    # ── STEP D: Transform to WGS84 ────────────────────────────────────────
    try:
        wgs84_points = transform_to_wgs84(points, crs_name, is_utm, raw_text)
    except RuntimeError as exc:
        return MCPErrorResponse(
            error_code="CRS_TRANSFORM_FAILED",
            instruction="Could not transform coordinates to WGS84. "
                        "Ensure pyproj is installed and the coordinate system is specified correctly.",
            run_id=run_id,
            stage=PipelineStage.COORD_EXTRACT,
            detail=str(exc),
        )

    if minna_detected:
        warnings.append("[POS_ACCURACY: ±5 METRES] — Minna Datum transform applied. "
                        "Positional accuracy is approximately ±5 metres.")

    # ── STEP E: Validate polygon closure ──────────────────────────────────
    if not is_closed_polygon(wgs84_points):
        return MCPErrorResponse(
            error_code="POLYGON_OPEN",
            instruction="The extracted points do not form a closed loop. "
                        "A valid polygon requires the last coordinate to match the first. "
                        "Check for a missing terminal node or a typo in the point sequence.",
            run_id=run_id,
            stage=PipelineStage.COORD_EXTRACT,
        )

    # ── STEP F: Compute centroid and area ────────────────────────────────
    centroid = compute_centroid(wgs84_points)
    computed_area_ha = compute_area_ha(wgs84_points)

    # ── STEP G: Nigeria bounding box check ───────────────────────────────
    inside_nigeria = is_inside_nigeria(centroid)
    flip_tested = False

    if coordinate_hint == "UTM_SWAPPED":
        inside_nigeria = False

    if not inside_nigeria:
        warnings.append("OUTSIDE_NIGERIA")
        # Auto-flip failsafe for UTM or Minna inputs
        if is_utm or crs_name in (CRSName.UTM_31N, CRSName.UTM_32N, CRSName.UTM_33N, CRSName.MINNA):
            _, flip_worked = test_flipped_axes(points, crs_name, is_utm, raw_text)
            if flip_worked:
                flip_tested = True
                # Log flip_tested = True, but do NOT automatically apply the flip to the returned coordinates inside coord_extract.py.
                # Keep is_inside_nigeria as False so that the coordinate user gate's T2 dialog fires.

    # ── STEP H: Coordinate Health Check (FIX 2.3) ─────────────────────────
    import math
    segment_lengths = []
    health_check_stats = None
    
    valid_wgs84 = all(-90 <= p[0] <= 90 and -180 <= p[1] <= 180 for p in wgs84_points)
    if valid_wgs84:
        for i in range(len(wgs84_points) - 1):
            lat1, lon1 = wgs84_points[i]
            lat2, lon2 = wgs84_points[i+1]
            R = 6371000
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a_h = math.sin(dlat/2) * math.sin(dlat/2) + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2) * math.sin(dlon/2)
            c_h = 2 * math.atan2(math.sqrt(a_h), math.sqrt(1-a_h))
            segment_lengths.append(R * c_h)
            
        mean_dist = sum(segment_lengths) / len(segment_lengths) if segment_lengths else 0
        variance = sum((d - mean_dist)**2 for d in segment_lengths) / len(segment_lengths) if segment_lengths else 0
        std_dev = math.sqrt(variance)
        
        health_check_stats = {
            "mean_segment_m": round(mean_dist, 2),
            "max_segment_m": round(max(segment_lengths), 2) if segment_lengths else 0,
            "std_dev_m": round(std_dev, 2)
        }
        
        if std_dev > 5000:
            return MCPErrorResponse(
                error_code="POLYGON_TOO_LARGE",
                instruction="[POLYGON_TOO_LARGE] Health Check failed: The standard deviation of coordinate distances exceeds 5km. This usually indicates an erroneous bounding box or massive coordinate typo.",
                run_id=run_id,
                stage=PipelineStage.COORD_EXTRACT,
            )

    # ── STEP I: Area discrepancy check ────────────────────────────────────
    area_discrepancy_pct: float | None = None
    if stated_area_ha is not None and stated_area_ha > 0:
        area_discrepancy_pct = round(
            ((computed_area_ha - stated_area_ha) / stated_area_ha) * 100, 2
        )
        if abs(area_discrepancy_pct) > 10:
            warnings.append(
                f"AREA_DISCREPANCY: Computed area ({computed_area_ha:.2f} ha) differs "
                f"from stated area ({stated_area_ha:.2f} ha) by {area_discrepancy_pct:+.1f}%."
            )

    # ── STEP I: Dialog trigger evaluation ────────────────────────────────
    dialog_triggers = evaluate_dialog_triggers(
        crs_confidence=crs_confidence,
        crs_name=crs_name,
        inside_nigeria=inside_nigeria,
        area_discrepancy_pct=area_discrepancy_pct,
        minna_detected=minna_detected,
        dms_converted=is_dms,
    )

    # ── OUTPUT ────────────────────────────────────────────────────────────
    coord_pairs = [[lat, lng] for lat, lng in wgs84_points]

    # Determine dynamic metric EPSG for distance calculations
    combined_text = f"{raw_text} {datum_label or ''}".upper()
    zone_31_indicators = ["/LA/", "/OG/", "/OY/", "/OS/", "/EK/", "/ON/", "/ED/"]
    zone_33_indicators = ["/BO/", "/AD/", "/TA/", "/YO/", "/GO/"] 

    if any(marker in combined_text for marker in zone_33_indicators):
        metric_analysis_epsg = 32633
    elif any(marker in combined_text for marker in zone_31_indicators):
        metric_analysis_epsg = 32631
    else:
        metric_analysis_epsg = 32632  # Default fallback to central Nigeria (Zone 32)

    # ── REVERSE GEOCODE CENTROID (FIX 1.4) ────────────────────────────────────
    # Calling module-level reverse_geocode

    state, lga = reverse_geocode(centroid.lat, centroid.lng)

    return CoordExtractOutput(
        run_id=run_id,
        coordinates=coord_pairs,
        centroid=centroid,
        detected_crs=crs_name,
        crs_confidence=crs_confidence,
        metric_analysis_epsg=metric_analysis_epsg,
        is_inside_nigeria=inside_nigeria,
        computed_area_ha=computed_area_ha,
        state=state,
        lga=lga,
        health_check_stats=health_check_stats,
        stated_area_ha=stated_area_ha,
        area_discrepancy_pct=area_discrepancy_pct,
        minna_datum_detected=minna_detected,
        dms_converted=is_dms,
        flip_tested=flip_tested,
        warnings=warnings,
        crs_dialog_triggers=dialog_triggers,
        discovery_method=discovery_method,
    )
