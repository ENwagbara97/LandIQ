"""
LandIQ — agents/cadastral_engine.py
Lead Cadastral Computation & Spatial Data Normalization Engine

Accepts four input vectors:
  1. Raw OCR / Pasted Text String  — fragmented legacy survey sheet text
  2. CSV / XLSX Tabular bytes      — uploaded spreadsheet data
  3. Google Sheets URL             — public sheet fetched as CSV
  4. COGO Text                     — tie-point + bearing-distance traverse sequence

Routes through one of two mathematical tracks:
  Track A (TABULAR)      — explicit Easting/Northing coordinate columns
  Track B (COGO_TRAVERSE) — anchor point + bearing-distance forward computation

Returns a CadastralResult JSON with:
  • user_summary   — plain-English status, area comparison, accuracy flag
  • technical_audit — datum, misclosure, area variance, per-station WGS84 ledger

Zero LLM calls. Zero gate/session/pipeline interaction.
"""

from __future__ import annotations

import logging
import math
import re
import uuid
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("landiq.cadastral_engine")

# ── Lazy imports ──────────────────────────────────────────────────────────────
try:
    from pyproj import Transformer
    _PYPROJ_AVAILABLE = True
except ImportError:
    _PYPROJ_AVAILABLE = False

from core.schemas import (
    AreaMatchStatus,
    CadastralResult,
    CadastralStationEntry,
    ComputationTrack,
    MCPErrorResponse,
    PipelineStage,
    ExtractionMeta,
    PlanDetails,
    TraverseData,
    TraverseLeg,
    PolygonData,
    ExtractionConfidence,
)

# ── Internal dataclasses (not exposed via Pydantic — engine-internal only) ────

@dataclass
class _Station:
    """Internal representation of a computed boundary station."""
    station_id          : str
    stated_easting      : Optional[float] = None
    stated_northing     : Optional[float] = None
    calculated_easting  : Optional[float] = None
    calculated_northing : Optional[float] = None
    wgs84_lng           : Optional[float] = None
    wgs84_lat           : Optional[float] = None


@dataclass
class _BearingDistance:
    """One leg of a COGO traverse sequence."""
    bearing_decimal_deg : float   # Decimal degrees (converted from DMS)
    distance_m          : float
    label               : str = ""   # e.g. "L1", "LINE 1", or empty


# =============================================================================
# § 1 · DATUM DETECTION
# =============================================================================

# Regex patterns for datum text scanning
_MINNA_RE    = re.compile(r"\bminna\b|clarke\s*1880|nigerian\s+datum", re.IGNORECASE)
_WGS84_RE    = re.compile(r"\bwgs\s*84\b|\bwgs84\b|\bepa:4326\b", re.IGNORECASE)
_UTM_ZONE_RE = re.compile(r"\butm\s*zone\s*(\d+)\b", re.IGNORECASE)


def _detect_datum(raw_text: str) -> tuple[str, Optional[int]]:
    """
    Scan raw text for datum and UTM zone labels.
    Returns (datum_label, utm_zone_number).
    Returns None for zone if not explicitly stated.
    """
    text = raw_text or ""

    # UTM zone extraction
    zone_match = _UTM_ZONE_RE.search(text)
    utm_zone = int(zone_match.group(1)) if zone_match else None

    if _MINNA_RE.search(text):
        return "MINNA", utm_zone
    if _WGS84_RE.search(text):
        return "WGS84", utm_zone

    # Default: legacy Nigerian plan → Minna
    return "MINNA", utm_zone


# =============================================================================
# § 2 · NUMERIC CORRUPTION REMEDIATION (reusable helper)
# =============================================================================

def _cleanse_number(raw: str) -> Optional[float]:
    """
    Apply OCR corruption remediation and return a float.
    Handles: thousands commas, hyphen-as-decimal, European decimal comma,
    internal spaces.
    Returns None if value is not parseable.
    """
    if not raw:
        return None
    s = raw.strip()

    # Remove internal spaces within numbers
    s = re.sub(r"(\d)\s+(\d)", r"\1\2", s)

    # Thousands-comma removal (iterative for multi-group numbers)
    prev = None
    while s != prev:
        prev = s
        s = re.sub(r"(\d),(\d{3})(?!\d)", r"\1\2", s)

    # Trailing hyphen → decimal point (e.g. "550852-254" → "550852.254")
    s = re.sub(r"^(-?\d+)-(\d+)$", r"\1.\2", s)

    # European decimal comma (single comma, no decimal yet)
    if "." not in s and s.count(",") == 1:
        s = s.replace(",", ".")

    try:
        return float(s)
    except ValueError:
        return None


# =============================================================================
# § 3 · OCR TEXT SCANNER (Track A — Tabular Pathway from raw text)
# =============================================================================

# Station ID patterns seen in Nigerian survey plans
_STATION_LABEL_RE = re.compile(
    r"""
    (?P<id>
        (?:SC|SG|SK|BP|TP|BM|NR|S)[/\-\s]*[A-Z0-9]+(?:[/\-\s][A-Z0-9]+)*  # SC/AK/K 49700 style
        | [A-Z]{1,4}\d{4,7}                                                  # condensed: BP12345
        | (?:STATION|BEACON|PILLAR|CORNER)\s*\d+                             # STATION 1, BEACON 3
        | [A-Z]\d+                                                            # A1, B2 etc.
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Match UTM-scale numbers (6-7 digits) — rejects 5-digit station IDs like 49700
# Easting: 100,000–900,000; Northing: 400,000–1,600,000  →  both are 6-7 digits
_UTM_SCALE_RE = re.compile(r"\b(\d{6,7}(?:\.\d+)?)\b")

# Legacy anchor-line pair scanner (kept for _scan_cogo_text anchor detection)
_COORD_PAIR_RE = re.compile(
    r"(?P<a>\d{3,7}(?:[.,\-]\d+)?)\s*[,;\s]+\s*(?P<b>\d{3,7}(?:[.,\-]\d+)?)"
)


def _preprocess_line(line: str) -> str:
    """
    Apply OCR corruption remediation to an entire line before number extraction.
    Only corrects well-defined OCR artefacts that do NOT collapse column gaps:
      1. Thousands-separator commas:  "387,804.297" → "387804.297"
      2. Hyphen-as-decimal:           "387852-254"  → "387852.254"

    NOTE: Internal-space removal (e.g. "550 821" → "550821") is intentionally
    omitted because tabular data has multi-space column gaps that must be
    preserved for _UTM_SCALE_RE to find separate easting/northing values.
    """
    # Step 1: Thousands-comma removal (iterative for multi-group numbers)
    prev = None
    while line != prev:
        prev = line
        line = re.sub(r"(\d),(\d{3})(?!\d)", r"\1\2", line)
    # Step 2: Hyphen-as-decimal between digit groups (3-7 digits each side)
    line = re.sub(r"(\d{3,7})-(\d{3})", r"\1.\2", line)
    return line


def _scan_ocr_text_for_stations(raw_text: str) -> list[_Station]:
    """
    Scan raw OCR text for station-ID + coordinate pairs.

    Strategy:
      1. Split text into lines and apply full-line corruption remediation.
      2. Extract all UTM-scale numbers (6-7 digits) from the cleaned line.
         This rejects 5-digit station IDs (e.g. 49700) and keeps 6-digit
         Easting/Northing values (e.g. 387804.297, 550821.575).
      3. Use the first pair of UTM-scale numbers as (Easting, Northing).
      4. Detect station label from non-numeric prefix text.

    Returns list of _Station (stated == calculated for Track A).
    """
    stations: list[_Station] = []
    lines = raw_text.splitlines()
    auto_idx = 1

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Apply full-line corruption remediation
        clean_line = _preprocess_line(line)

        # Extract UTM-scale numbers (6-7 digits with optional decimal)
        utm_matches = _UTM_SCALE_RE.findall(clean_line)
        if len(utm_matches) < 2:
            continue  # Need at least 2 UTM-scale values

        a_raw, b_raw = utm_matches[0], utm_matches[1]
        a = _cleanse_number(a_raw)
        b = _cleanse_number(b_raw)

        if a is None or b is None:
            continue

        # Validate UTM range: Easting 100,000–900,000, Northing 400,000–1,600,000
        # Both must be at least 100,000
        if a < 100_000 or b < 100_000:
            continue

        # Attempt station label detection — look in original line before clean
        id_match = _STATION_LABEL_RE.search(line)
        if id_match:
            sid = re.sub(r"\s+", " ", id_match.group("id").strip())
        else:
            sid = f"S{auto_idx}"
            auto_idx += 1

        # Heuristic: larger value is Northing for Nigerian UTM
        if a > b:
            northing, easting = a, b
        else:
            northing, easting = b, a

        stations.append(_Station(
            station_id=sid,
            stated_easting=easting,
            stated_northing=northing,
            calculated_easting=easting,
            calculated_northing=northing,
        ))

    # If row-by-row failed, try global column matching (Tesseract often reads tables by column)
    if len(stations) < 3:
        clean_text = _preprocess_line(raw_text.replace("\n", " "))
        all_utms = [float(v) for v in _UTM_SCALE_RE.findall(clean_text) if float(v) >= 100_000]
        if len(all_utms) >= 6 and len(all_utms) % 2 == 0:
            # Check if it's grouped EEEEE NNNNN
            mid = len(all_utms) // 2
            first_half = all_utms[:mid]
            second_half = all_utms[mid:]
            
            # Usually E < N in Nigeria
            if abs(sum(first_half)/mid - sum(second_half)/mid) > 50000:
                # Yes, they are grouped!
                if sum(first_half) < sum(second_half):
                    eastings, northings = first_half, second_half
                else:
                    eastings, northings = second_half, first_half
                
                stations = []
                for i in range(mid):
                    stations.append(_Station(
                        station_id=f"S{i+1}",
                        stated_easting=eastings[i],
                        stated_northing=northings[i],
                        calculated_easting=eastings[i],
                        calculated_northing=northings[i]
                    ))

    return stations


# =============================================================================
# § 4 · COGO TEXT SCANNER (Track B — Traverse pathway from raw text)
# =============================================================================

# Anchor / tie-point extraction (first explicit easting/northing pair)
_ANCHOR_RE = re.compile(
    r"""
    (?:tie[\-\s]*point|anchor|origin|start(?:ing)?\s*point|reference)[:\s]*
    (?:E(?:asting)?[:\s]*)?(?P<e>\d{3,7}(?:\.\d+)?)\s*[mM]?\s*[,;\s]+\s*
    (?:N(?:orthing)?[:\s]*)?(?P<n>\d{3,7}(?:\.\d+)?)
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Bearing: DMS quadrant format (N62°15'30"E) OR Whole Circle format (293°02'15")
_BEARING_RE = re.compile(
    r"""
    (?:(?P<dir1>[NSns])\s*)?
    (?P<deg>\d{1,3})[\u00b0\s]+(?P<min>\d{1,2})['\u2032\s]*(?:(?P<sec>[\d.]+)[\"″\s]*)?
    (?:(?P<dir2>[EWew]))?
    """,
    re.VERBOSE,
)

# Distance: "250.50m" or "250.50 m" or "250.50"
_DIST_RE = re.compile(r"(?P<dist>\d{1,6}(?:\.\d+)?)\s*[mM]?\b")

# Line/leg label: "L1", "LINE 1", "LEG 1", "1."
_LEG_LABEL_RE = re.compile(r"(?:line|leg|l)\s*(\d+)|^(\d+)[.):]", re.IGNORECASE)


def _bearing_dms_to_dd(direction1: Optional[str], deg: float, mins: float, sec: float, direction2: Optional[str]) -> float:
    """
    Convert a whole-circle quadrant bearing (e.g. N45°30'15"E) to decimal degrees.
    North = 0°, East = 90°, South = 180°, West = 270°.
    If direction1 and direction2 are missing, treat as Whole Circle Bearing.
    """
    dd = deg + mins / 60.0 + sec / 3600.0
    if not direction1 and not direction2:
        return dd  # Already Whole Circle
    
    d1 = direction1.upper() if direction1 else ""
    d2 = direction2.upper() if direction2 else ""
    if d1 == "N" and d2 == "E":
        return dd
    elif d1 == "S" and d2 == "E":
        return 180.0 - dd
    elif d1 == "S" and d2 == "W":
        return 180.0 + dd
    elif d1 == "N" and d2 == "W":
        return 360.0 - dd
    return dd  # fallback


def _scan_cogo_text(raw_text: str) -> tuple[Optional[tuple[float, float]], list[_BearingDistance]]:
    """
    Parse COGO traverse text into (anchor_E_N, list of bearing-distance vectors).
    Returns (None, []) if insufficient data found.

    Safety guards:
      - Lines containing UTM-scale coordinates (≥100,000) are skipped for
        bearing extraction to avoid treating coordinate values as bearings.
      - Plain decimal bearings must be in [0, 360] to be accepted.
    """
    anchor: Optional[tuple[float, float]] = None
    vectors: list[_BearingDistance] = []

    # ── Anchor detection ─────────────────────────────────────────────────────
    anchor_match = _ANCHOR_RE.search(raw_text)
    if anchor_match:
        e = _cleanse_number(anchor_match.group("e"))
        n = _cleanse_number(anchor_match.group("n"))
        if e is not None and n is not None:
            anchor = (e, n)

    # If no explicit anchor label, use _UTM_SCALE_RE to find the first
    # pair of 6-7 digit numbers in the text.
    if anchor is None:
        full_clean = _preprocess_line(raw_text.replace("\n", " "))
        utm_vals = [float(v) for v in _UTM_SCALE_RE.findall(full_clean) if float(v) >= 100_000]
        if len(utm_vals) >= 2:
            # Smaller = Easting, Larger = Northing (Nigerian UTM convention)
            e_guess = min(utm_vals[0], utm_vals[1])
            n_guess = max(utm_vals[0], utm_vals[1])
            anchor = (e_guess, n_guess)

    # ── Bearing-Distance extraction ───────────────────────────────────────────
    lines = raw_text.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # ⚠️ SAFETY GUARD: skip lines that contain UTM-scale coordinates.
        # These are anchor/coordinate lines — not bearing lines.
        clean_for_check = _preprocess_line(line)
        utm_in_line = [float(v) for v in _UTM_SCALE_RE.findall(clean_for_check)
                       if float(v) >= 100_000]
        if utm_in_line:
            continue  # Coordinate line — skip for bearing extraction

        # Try to find a bearing
        b_match = _BEARING_RE.search(line)
        if not b_match:
            continue

        if True:
            # We accept both DMS quadrant and Whole Circle bearings
            try:
                matched_str = b_match.group(0)
                d1 = b_match.group("dir1")
                d2 = b_match.group("dir2")
                if not d1 and not d2:
                    # To prevent false positives on plain numbers, require degree or minute symbol
                    if "°" not in matched_str and "'" not in matched_str and "″" not in matched_str:
                        continue
                        
                deg  = float(b_match.group("deg"))
                mins = float(b_match.group("min"))
                sec  = float(b_match.group("sec")) if b_match.group("sec") else 0.0
                bearing_dd = _bearing_dms_to_dd(d1, deg, mins, sec, d2)
            except (TypeError, ValueError):
                continue

        # Find distance in the same line (search after the bearing match)
        d_match = _DIST_RE.search(line[b_match.end():])
        if not d_match:
            d_match = _DIST_RE.search(line)  # Try full line as fallback
        if not d_match:
            continue

        try:
            distance = float(d_match.group("dist"))
        except ValueError:
            continue

        if distance <= 0:
            continue

        # Leg label
        lbl_match = _LEG_LABEL_RE.search(line)
        label = lbl_match.group(0).strip() if lbl_match else ""

        vectors.append(_BearingDistance(
            bearing_decimal_deg=bearing_dd,
            distance_m=distance,
            label=label,
        ))

    return anchor, vectors


# =============================================================================
# § 5 · TRACK ROUTER
# =============================================================================

def _detect_track(
    ocr_stations: list[_Station],
    anchor: Optional[tuple[float, float]],
    vectors: list[_BearingDistance],
    tabular_stations: list,
) -> str:
    """
    Route to TABULAR or COGO_TRAVERSE.
    Priority: if ≥3 explicit coordinate stations found → Track A.
    Otherwise if anchor + ≥3 bearing vectors → Track B.
    """
    n_tab = len(tabular_stations) if tabular_stations else 0
    n_ocr = len(ocr_stations)
    n_vec = len(vectors)

    if n_tab >= 3:
        return "TABULAR"
    if n_ocr >= 3:
        return "TABULAR"
    if n_vec >= 3:
        return "COGO_TRAVERSE"
    # Not enough data for either track
    return "INSUFFICIENT"


# =============================================================================
# § 6 · TRACK A — TABULAR ENGINE
# =============================================================================

def _run_track_a(stations: list[_Station]) -> tuple[list[_Station], str]:
    """
    Track A: stated coordinates are the calculated coordinates.
    Validates polygon closure (last ≈ first within 0.01 m).
    Returns (stations, closure_warning or "").
    """
    # Ensure polygon closure: if last point doesn't match first, note it
    if len(stations) >= 3:
        first = stations[0]
        last  = stations[-1]
        delta_e = abs((first.stated_easting or 0) - (last.stated_easting or 0))
        delta_n = abs((first.stated_northing or 0) - (last.stated_northing or 0))
        if delta_e > 0.01 or delta_n > 0.01:
            # Auto-close: append a copy of the first station as the closing vertex
            close_station = _Station(
                station_id=f"{first.station_id} (close)",
                stated_easting=first.stated_easting,
                stated_northing=first.stated_northing,
                calculated_easting=first.stated_easting,
                calculated_northing=first.stated_northing,
            )
            stations = stations + [close_station]
            return stations, (
                f"Polygon auto-closed: last station and first station differ by "
                f"({delta_e:.3f}m E, {delta_n:.3f}m N). A closing vertex was appended."
            )

    return stations, ""


# =============================================================================
# § 7 · TRACK B — COGO TRAVERSE ENGINE
# =============================================================================

def _run_track_b(
    anchor: tuple[float, float],
    vectors: list[_BearingDistance],
) -> tuple[list[_Station], float]:
    """
    Execute a forward cadastral traverse from anchor + bearing-distance sequence.
    Returns (stations, linear_misclosure_m).

    Forward traverse formulas (plane surveying, bearing measured clockwise from North):
        E_next = E_curr + distance * sin(bearing_radians)
        N_next = N_curr + distance * cos(bearing_radians)
    """
    stations: list[_Station] = []
    E_curr, N_curr = anchor

    # Station 0 — tie-point / anchor
    stations.append(_Station(
        station_id="TP0 (Tie-Point)",
        stated_easting=E_curr,
        stated_northing=N_curr,
        calculated_easting=E_curr,
        calculated_northing=N_curr,
    ))

    for i, vec in enumerate(vectors):
        bearing_rad = math.radians(vec.bearing_decimal_deg)
        E_next = E_curr + vec.distance_m * math.sin(bearing_rad)
        N_next = N_curr + vec.distance_m * math.cos(bearing_rad)

        label = vec.label if vec.label else f"S{i + 1}"
        stations.append(_Station(
            station_id=label,
            stated_easting=None,        # COGO: no stated coords
            stated_northing=None,
            calculated_easting=round(E_next, 3),
            calculated_northing=round(N_next, 3),
        ))
        E_curr, N_curr = E_next, N_next

    # Linear misclosure: distance from final position back to anchor
    E_0, N_0 = anchor
    misclosure_e = E_curr - E_0
    misclosure_n = N_curr - N_0
    misclosure = math.sqrt(misclosure_e ** 2 + misclosure_n ** 2)

    # Apply Bowditch Adjustment if closure error <= 2.0m
    if misclosure > 0.0 and misclosure <= 2.0:
        total_length = sum(v.distance_m for v in vectors)
        if total_length > 0:
            cum_dist = 0.0
            for i in range(1, len(stations)):
                cum_dist += vectors[i-1].distance_m
                corr_e = -(misclosure_e * (cum_dist / total_length))
                corr_n = -(misclosure_n * (cum_dist / total_length))
                if stations[i].calculated_easting is not None and stations[i].calculated_northing is not None:
                    stations[i].calculated_easting = round(stations[i].calculated_easting + corr_e, 3)
                    stations[i].calculated_northing = round(stations[i].calculated_northing + corr_n, 3)

    return stations, round(misclosure, 4)


# =============================================================================
# § 8 · AREA COMPUTATION — METRIC SHOELACE
# =============================================================================

def _shoelace_area_m2(stations: list[_Station]) -> float:
    """
    Compute polygon area in square metres using the Shoelace formula.
    Operates directly on projected metre coordinates (E, N) — no degree conversion needed.
    Uses calculated_easting/northing where available, falls back to stated.
    """
    coords = []
    for s in stations:
        e = s.calculated_easting if s.calculated_easting is not None else s.stated_easting
        n = s.calculated_northing if s.calculated_northing is not None else s.stated_northing
        if e is not None and n is not None:
            coords.append((e, n))

    n = len(coords)
    if n < 3:
        return 0.0

    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += coords[i][0] * coords[j][1]
        area -= coords[j][0] * coords[i][1]

    return abs(area) / 2.0


# =============================================================================
# § 9 · WGS84 REPROJECTION
# =============================================================================

def _reproject_stations(stations: list[_Station], datum_label: str, stated_zone: Optional[int], raw_text: str = "", location_context: str = "") -> None:
    """
    Transform calculated (E, N) metre coordinates to WGS84 (lng, lat).
    Modifies stations in-place.
    """
    if not _PYPROJ_AVAILABLE:
        logger.warning("[cadastral] pyproj not available — skipping WGS84 reprojection.")
        return

    # Find the first valid Easting to infer zone if needed
    first_easting = None
    for s in stations:
        e = s.calculated_easting if s.calculated_easting is not None else s.stated_easting
        if e is not None:
            first_easting = e
            break
            
    if first_easting is None:
        return

    # Infer UTM Zone for Nigeria based on Easting range
    utm_zone = stated_zone
    if not utm_zone:
        loc = ((raw_text or "") + " " + (location_context or "")).lower()
        if any(s in loc for s in ["lagos", "ogun", "oyo", "osun", "kwara", "ekiti", "sokoto", "kebbi", "niger state"]):
            utm_zone = 31
        elif any(s in loc for s in ["borno", "yobe", "taraba", "adamawa"]):
            utm_zone = 33
        else:
            utm_zone = 32

    is_minna = "MINNA" in datum_label.upper()

    if is_minna:
        proj_str = (
            f"+proj=utm +zone={utm_zone} +ellps=clrk80 "
            f"+towgs84=-92,-93,272,0,0,0,0 +units=m +no_defs"
        )
        transformer = Transformer.from_proj(proj_str, "EPSG:4326", always_xy=True)
    else:
        # WGS84 UTM
        epsg_map = {31: 32631, 32: 32632, 33: 32633}
        epsg = epsg_map.get(utm_zone, 32632)
        transformer = Transformer.from_crs(epsg, 4326, always_xy=True)

    for s in stations:
        e = s.calculated_easting if s.calculated_easting is not None else s.stated_easting
        n = s.calculated_northing if s.calculated_northing is not None else s.stated_northing
        if e is not None and n is not None:
            try:
                lng, lat = transformer.transform(e, n)
                s.wgs84_lng = round(lng, 6)
                s.wgs84_lat = round(lat, 6)
            except Exception as exc:
                logger.warning(f"[cadastral] WGS84 transform failed for station {s.station_id}: {exc}")


# =============================================================================
# § 10 · AREA ACCURACY FLAG
# =============================================================================

def _flag_area_accuracy(
    stated_ha: Optional[float],
    calculated_ha: float,
) -> tuple[AreaMatchStatus, float, str]:
    """
    Returns (status, delta_ha, message).
    Thresholds per spec:
      GREEN: delta ≤ 0.005 ha
      AMBER: delta ≤ 0.050 ha
      RED:   delta  > 0.050 ha
    """
    if stated_ha is None or stated_ha <= 0:
        return AreaMatchStatus.GREEN, 0.0, (
            f"No stated area provided. Computed area is {calculated_ha:.4f} ha "
            f"({calculated_ha * 10_000:,.1f} m²). No comparison possible."
        )

    delta = abs(stated_ha - calculated_ha)

    if delta <= 0.005:
        status = AreaMatchStatus.GREEN
        msg = (
            f"Excellent match. Computed area ({calculated_ha:.4f} ha) is within "
            f"0.005 ha of the stated area ({stated_ha:.4f} ha). "
            f"Boundary data is geometrically consistent."
        )
    elif delta <= 0.050:
        status = AreaMatchStatus.AMBER
        msg = (
            f"Review required. Computed area ({calculated_ha:.4f} ha) differs from "
            f"the stated area ({stated_ha:.4f} ha) by {delta:.4f} ha. "
            f"Minor data-entry errors or legacy plan rounding may be the cause."
        )
    else:
        status = AreaMatchStatus.RED
        msg = (
            f"Critical error. Computed area ({calculated_ha:.4f} ha) differs from "
            f"the stated area ({stated_ha:.4f} ha) by {delta:.4f} ha — exceeding the "
            f"0.05 ha threshold. This suggests a broken boundary, missing station, "
            f"or unclosed polygon. Engage a SURCON-registered surveyor for re-verification."
        )

    return status, delta, msg


# =============================================================================
# § 11 · MAIN run() ENTRYPOINT
# =============================================================================

def run(
    raw_text: Optional[str] = None,
    file_bytes: Optional[bytes] = None,
    filename: Optional[str] = None,
    sheet_url: Optional[str] = None,
    stated_area_ha: Optional[float] = None,
    property_owner: Optional[str] = None,
    location_context: Optional[str] = None,
) -> CadastralResult | MCPErrorResponse:
    """
    Main entrypoint for the Cadastral Computation Engine.

    Input vectors (at least one must be provided):
      raw_text     : Pasted OCR text or COGO sequence string.
      file_bytes   : CSV or XLSX file bytes from upload.
      filename     : Original filename (determines CSV vs XLSX).
      sheet_url    : Public Google Sheets URL (fetched as CSV).
      stated_area_ha: Area printed on survey plan (for accuracy comparison).
      property_owner: Name from plan header (user-facing label).
      location_context: LGA/State/community description.

    Returns:
      CadastralResult on success.
      MCPErrorResponse on any input or computation failure.
    """
    # ── Collect all station data from available inputs ─────────────────────────
    tabular_stations_raw: list = []   # from tabular_parser
    parse_warnings: list[str] = []

    # Vector 1: CSV / XLSX file bytes
    if file_bytes and filename:
        from pathlib import Path
        ext = Path(filename).suffix.lower()
        try:
            if ext == ".csv":
                from agents.tabular_parser import parse_csv_bytes
                tabular_stations_raw, pw = parse_csv_bytes(file_bytes)
                parse_warnings.extend(pw)
            elif ext in (".xlsx", ".xls"):
                from agents.tabular_parser import parse_xlsx_bytes
                tabular_stations_raw, pw = parse_xlsx_bytes(file_bytes)
                parse_warnings.extend(pw)
            else:
                return MCPErrorResponse(
                    error_code="UNSUPPORTED_FORMAT",
                    instruction=(
                        f"File format '{ext}' is not supported by the cadastral engine. "
                        "Upload a .csv or .xlsx file, or paste raw coordinate text."
                    ),
                    stage=PipelineStage.COORD_EXTRACT,
                )
        except Exception as exc:
            return MCPErrorResponse(
                error_code="FILE_PARSE_ERROR",
                instruction=f"Could not parse uploaded file: {exc}",
                stage=PipelineStage.COORD_EXTRACT,
                detail=str(exc),
            )

    # Vector 2: Google Sheets URL
    if sheet_url:
        try:
            from agents.tabular_parser import parse_sheet_url
            url_stations, pw = parse_sheet_url(sheet_url)
            parse_warnings.extend(pw)
            if not tabular_stations_raw:
                tabular_stations_raw = url_stations
        except Exception as exc:
            parse_warnings.append(f"[sheet_url] Failed: {exc}")

    # Convert RawStation dataclasses → _Station dataclasses
    tabular_stations: list[_Station] = [
        _Station(
            station_id=rs.station_id,
            stated_easting=rs.easting,
            stated_northing=rs.northing,
            calculated_easting=rs.easting,
            calculated_northing=rs.northing,
        )
        for rs in tabular_stations_raw
    ]

    # Vector 3 & 4: Raw text (OCR tabular OR COGO)
    raw_text = (raw_text or "").strip()
    ocr_stations: list[_Station] = []
    anchor: Optional[tuple[float, float]] = None
    cogo_vectors: list[_BearingDistance] = []

    if raw_text:
        # Try OCR tabular scan first
        ocr_stations = _scan_ocr_text_for_stations(raw_text)
        # Also scan for COGO (may coexist in the same text)
        anchor, cogo_vectors = _scan_cogo_text(raw_text)

    # ── Detect datum from all text sources ────────────────────────────────────
    combined_text = f"{raw_text}"
    datum_label, utm_zone = _detect_datum(combined_text)
    logger.info(f"[cadastral] Datum detected: {datum_label}, UTM Zone: {utm_zone}")

    # ── Route to Track A or Track B ───────────────────────────────────────────
    track = _detect_track(ocr_stations, anchor, cogo_vectors, tabular_stations)

    if track == "INSUFFICIENT":
        hint_parts = []
        if not tabular_stations and not ocr_stations:
            hint_parts.append("no coordinate pairs found")
        if anchor is None:
            hint_parts.append("no tie-point anchor found for COGO")
        if len(cogo_vectors) < 3:
            hint_parts.append(f"only {len(cogo_vectors)} bearing-distance vectors detected (need ≥3)")
        hint = "; ".join(hint_parts) or "insufficient spatial data"
        return MCPErrorResponse(
            error_code="INSUFFICIENT_SPATIAL_DATA",
            instruction=(
                f"Could not determine computation track: {hint}. "
                "For Track A (tabular): provide a CSV/XLSX with Easting and Northing columns, "
                "or paste coordinate pairs. "
                "For Track B (COGO): provide a tie-point coordinate and a sequence of "
                "bearing (DMS or decimal) + distance (metres) vectors."
            ),
            stage=PipelineStage.COORD_EXTRACT,
        )

    # ── Execute computation track ──────────────────────────────────────────────
    misclosure_m = 0.0
    closure_warning = ""

    if track == "TABULAR":
        # Prefer file/URL stations over OCR-scanned stations
        active_stations = tabular_stations if tabular_stations else ocr_stations
        active_stations, closure_warning = _run_track_a(active_stations)
        comp_track = ComputationTrack.TABULAR
        logger.info(f"[cadastral] Track A: {len(active_stations)} stations")
    else:
        # Track B: COGO traverse
        # If anchor is missing, default to a safe Nigerian UTM coordinate (e.g. Minna, Niger State)
        # so that the polygon shape and area can still be computed.
        if anchor is None:
            anchor = (250000.0, 1000000.0)
            closure_warning += " No Tie-Point found. Polygon placed at arbitrary coordinates. "
            
        active_stations, misclosure_m = _run_track_b(anchor, cogo_vectors)
        comp_track = ComputationTrack.COGO_TRAVERSE
        logger.info(f"[cadastral] Track B: {len(active_stations)} computed stations, misclosure={misclosure_m}m")

    if len(active_stations) < 3:
        # Partial extraction: do not throw error. Return partial data so UI can show the degraded mode.
        closure_warning += f" Only {len(active_stations)} valid station(s) resolved. Needs at least 3 to close."
        # Keep going to build the partial ledger

    # ── WGS84 reprojection ─────────────────────────────────────────────────────
    _reproject_stations(active_stations, datum_label, utm_zone, raw_text, location_context)

    # ── Area computation ───────────────────────────────────────────────────────
    area_m2 = _shoelace_area_m2(active_stations)
    area_ha = round(area_m2 / 10_000, 6)

    # ── Area accuracy flag ─────────────────────────────────────────────────────
    area_status, delta_ha, simple_msg = _flag_area_accuracy(stated_area_ha, area_ha)
    area_variance_m2 = round(delta_ha * 10_000, 4)

    # Append any parse warnings / closure notes to the simple message
    extra_notes = []
    if closure_warning:
        extra_notes.append(closure_warning)
    if parse_warnings:
        extra_notes.extend(parse_warnings)
    if extra_notes:
        simple_msg += " | Notes: " + " | ".join(extra_notes)

    # ── Build station ledger ───────────────────────────────────────────────────
    ledger = [
        CadastralStationEntry(
            station_id=s.station_id,
            easting_utm=s.calculated_easting if s.calculated_easting is not None else (s.stated_easting or 0.0),
            northing_utm=s.calculated_northing if s.calculated_northing is not None else (s.stated_northing or 0.0),
            latitude_wgs84=s.wgs84_lat or 0.0,
            longitude_wgs84=s.wgs84_lng or 0.0,
            source="computed" if comp_track == ComputationTrack.COGO_TRAVERSE else "table",
            ocr_confidence=100
        )
        for s in active_stations
    ]

    extraction_meta = ExtractionMeta(
        source_file=filename or "manual_entry",
        extraction_method="OCR_TRAVERSE" if comp_track == ComputationTrack.COGO_TRAVERSE else "OCR_TABLE",
        plan_type="TYPE_B" if comp_track == ComputationTrack.COGO_TRAVERSE else "TYPE_A",
        datum_detected=datum_label or "MINNA",
        datum_epsg=32632 if not utm_zone else int(f"326{utm_zone}"),
        ocr_engine="tesseract_cv2",
    )

    plan_details = PlanDetails(
        owner_name=property_owner,
        stated_area_sqm=stated_area_ha * 10000 if stated_area_ha else None,
        location=location_context,
        datum=datum_label,
    )

    traverse_data = None
    if comp_track == ComputationTrack.COGO_TRAVERSE and anchor:
        traverse_data = TraverseData(
            starting_beacon="TP0",
            starting_easting=anchor[0],
            starting_northing=anchor[1],
            closure_error_m=misclosure_m,
            adjustment_method="bowditch" if misclosure_m <= 2.0 else "none"
        )

    is_closed_poly = len(active_stations) >= 3

    polygon_data = PolygonData(
        wgs84_coordinates=[[s.wgs84_lat or 0.0, s.wgs84_lng or 0.0] for s in active_stations] if is_closed_poly else [],
        utm_coordinates=[[s.calculated_easting or 0.0, s.calculated_northing or 0.0] for s in active_stations] if is_closed_poly else [],
        computed_area_sqm=area_m2 if is_closed_poly else 0.0,
        computed_area_ha=area_ha if is_closed_poly else 0.0,
        stated_area_sqm=stated_area_ha * 10000 if stated_area_ha else None,
        area_discrepancy_pct=(area_variance_m2 / (stated_area_ha * 10000) * 100) if stated_area_ha and stated_area_ha > 0 else None,
        is_closed=is_closed_poly,
        is_valid=is_closed_poly,
        has_self_intersection=False,
        vertex_count=(len(active_stations) - 1) if is_closed_poly else len(active_stations),
        closure_error_m=misclosure_m,
        crs_input=datum_label or "MINNA",
    )

    # ── Assemble output ────────────────────────────────────────────────────────
    return CadastralResult(
        extraction_meta=extraction_meta,
        plan_details=plan_details,
        traverse_data=traverse_data,
        beacons=ledger,
        polygon=polygon_data,
        extraction_confidence=ExtractionConfidence()
    )
