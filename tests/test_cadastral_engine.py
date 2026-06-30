"""
LandIQ — tests/test_cadastral_engine.py
Unit + integration tests for the Cadastral Computation Engine.

Tests both tracks:
  Track A: OCR tabular text → explicit Easting/Northing stations
  Track B: COGO traverse    → anchor + bearing-distance sequence
"""

from __future__ import annotations

import sys
import json
import math
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.cadastral_engine import run as cadastral_run
from core.schemas import CadastralResult, MCPErrorResponse

TRACK_A_TEXT = """
MINNA UTM ZONE 32

SC/AK/K 49700  387804.297  550821.575
SC/AK/K 49701  387852.254  550891.123
SC/AK/K 49702  387910.500  550865.400
SC/AK/K 49703  387875.100  550795.200
SC/AK/K 49700  387804.297  550821.575
"""

CORRUPT_TEXT = """
MINNA UTM ZONE 32

S1  387,804.297  550,821.575
S2  387,852-254  550,891-123
S3  387,910.500  550,865.400
S1  387,804.297  550,821.575
"""

COGO_TEXT = """
MINNA UTM ZONE 32

Tie-Point: E 387500.000 N 550600.000

L1: N 62°15'30"E  120.50m
L2: S 27°44'30"E   95.75m
L3: S 62°15'30"W  120.50m
L4: N 27°44'30"W   95.75m
"""

BASE_TEXT = """
MINNA UTM ZONE 32
SC1  387804.0  550821.0
SC2  387900.0  550900.0
SC3  387950.0  550820.0
SC1  387804.0  550821.0
"""


def test_track_a_ocr_tabular():
    result = cadastral_run(
        raw_text=TRACK_A_TEXT,
        stated_area_ha=0.558,
        property_owner="Alhaji Musa Ibrahim",
        location_context="Minna, Niger State",
    )
    
    assert not isinstance(result, MCPErrorResponse)
    
    meta = result.extraction_meta
    polygon = result.polygon
    beacons = result.beacons
    
    assert meta.extraction_method == "OCR_TABLE"
    assert "MINNA" in meta.datum_detected
    assert len(beacons) >= 4
    assert polygon.computed_area_ha > 0
    assert polygon.computed_area_sqm > 0
    assert polygon.area_discrepancy_pct is not None
    assert polygon.area_discrepancy_pct <= 10.0
    assert beacons[0].latitude_wgs84 is not None
    assert 4.0 <= (beacons[0].latitude_wgs84 or 0) <= 14.0
    assert result.plan_details.owner_name == "Alhaji Musa Ibrahim"


def test_track_a_ocr_corruption_remediation():
    result = cadastral_run(raw_text=CORRUPT_TEXT)
    assert not isinstance(result, MCPErrorResponse)
    assert len(result.beacons) >= 3
    assert result.polygon.computed_area_ha > 0


def test_track_b_cogo_traverse():
    result = cadastral_run(
        raw_text=COGO_TEXT,
        property_owner="Chief Emeka Okonkwo",
        location_context="Asaba, Delta State",
    )
    
    assert not isinstance(result, MCPErrorResponse)
    
    meta = result.extraction_meta
    polygon = result.polygon
    beacons = result.beacons
    traverse = result.traverse_data
    
    assert meta.extraction_method == "OCR_TRAVERSE"
    assert len(beacons) >= 5
    assert traverse.closure_error_m < 1.0
    assert polygon.computed_area_ha > 0
    
    expected_area_m2 = 120.5 * 95.75
    actual_area_m2 = polygon.computed_area_sqm
    area_diff_pct = abs(actual_area_m2 - expected_area_m2) / expected_area_m2 * 100
    
    assert area_diff_pct < 1.0
    assert 4.0 <= (beacons[0].latitude_wgs84 or 0) <= 14.0


def test_area_accuracy_flag_thresholds():
    # GREEN
    r_green = cadastral_run(raw_text=BASE_TEXT, stated_area_ha=0.00001)
    assert not isinstance(r_green, MCPErrorResponse)
    
    # RED
    r_red = cadastral_run(raw_text=BASE_TEXT, stated_area_ha=999.0)
    assert not isinstance(r_red, MCPErrorResponse)
    assert r_red.polygon.area_discrepancy_pct > 10.0


def test_error_handling_no_input():
    r_err = cadastral_run()
    assert isinstance(r_err, MCPErrorResponse)
    assert r_err.error_code in ("NO_INPUT_PROVIDED", "INSUFFICIENT_SPATIAL_DATA")


def test_json_schema_compliance():
    result = cadastral_run(
        raw_text=TRACK_A_TEXT,
        stated_area_ha=0.558,
        property_owner="Alhaji Musa Ibrahim",
        location_context="Minna, Niger State",
    )
    assert not isinstance(result, MCPErrorResponse)
    
    payload = json.loads(result.model_dump_json())
    
    assert "extraction_meta" in payload
    assert "polygon" in payload
    assert "beacons" in payload
    assert "area_discrepancy_pct" in payload["polygon"]
    assert isinstance(payload["beacons"], list)
    assert all("longitude_wgs84" in s and "latitude_wgs84" in s for s in payload["beacons"])
    assert "datum_detected" in payload["extraction_meta"]
    assert "extraction_method" in payload["extraction_meta"]


def test_pre_plot_sanity_check():
    from agents.cadastral_engine import pre_plot_sanity_check

    # 1. Successful pass
    passed, msg = pre_plot_sanity_check(
        computed_area_sqm=424.0,
        stated_area_sqm=424.0,
        polygon_bbox_m=25.0,
        wgs84_coords=[(6.5, 3.5), (6.5, 3.6), (6.6, 3.6), (6.6, 3.5), (6.5, 3.5)],
        has_self_intersection=False
    )
    assert passed
    assert "Sanity checks passed" in msg

    # 2. Area ratio fail (ratio > 5)
    passed, msg = pre_plot_sanity_check(
        computed_area_sqm=2500.0,
        stated_area_sqm=424.0,
        polygon_bbox_m=25.0,
        wgs84_coords=[(6.5, 3.5), (6.5, 3.6), (6.6, 3.6), (6.6, 3.5), (6.5, 3.5)],
        has_self_intersection=False
    )
    assert not passed
    assert "ratio" in msg.lower() or "area" in msg.lower()

    # 3. Area ratio fail (ratio < 0.1)
    passed, msg = pre_plot_sanity_check(
        computed_area_sqm=30.0,
        stated_area_sqm=424.0,
        polygon_bbox_m=25.0,
        wgs84_coords=[(6.5, 3.5), (6.5, 3.6), (6.6, 3.6), (6.6, 3.5), (6.5, 3.5)],
        has_self_intersection=False
    )
    assert not passed
    assert "ratio" in msg.lower() or "area" in msg.lower()

    # 4. Bounding box plausibility fail
    passed, msg = pre_plot_sanity_check(
        computed_area_sqm=424.0,
        stated_area_sqm=424.0,
        polygon_bbox_m=500.0, # too large for 424 sqm
        wgs84_coords=[(6.5, 3.5), (6.5, 3.6), (6.6, 3.6), (6.6, 3.5), (6.5, 3.5)],
        has_self_intersection=False
    )
    assert not passed
    assert "spans" in msg.lower() or "bounding box" in msg.lower() or "wrong" in msg.lower()

    # 5. Outside Nigeria bounds
    passed, msg = pre_plot_sanity_check(
        computed_area_sqm=424.0,
        stated_area_sqm=424.0,
        polygon_bbox_m=25.0,
        wgs84_coords=[(51.5, -0.12), (51.5, -0.11), (51.6, -0.11), (51.6, -0.12)], # London
        has_self_intersection=False
    )
    assert not passed
    assert "nigeria" in msg.lower()

    # 6. Self-intersection pass (no longer a hard block per surveyor instructions)
    passed, msg = pre_plot_sanity_check(
        computed_area_sqm=424.0,
        stated_area_sqm=424.0,
        polygon_bbox_m=25.0,
        wgs84_coords=[(6.5, 3.5), (6.5, 3.6), (6.6, 3.6), (6.6, 3.5), (6.5, 3.5)],
        has_self_intersection=True
    )
    assert passed
    assert "Sanity checks passed" in msg


def test_linear_ring_self_intersection_check():
    from agents.cadastral_engine import _enforce_simple_polygon_sequence, _Station
    # Create a bowtie polygon sequence of stations:
    # (0, 0), (2, 2), (2, 0), (0, 2)
    # The edges (0,0)-(2,2) and (2,0)-(0,2) cross at (1,1).
    
    stations = [
        _Station(station_id="S1", wgs84_lng=0.0, wgs84_lat=0.0),
        _Station(station_id="S2", wgs84_lng=2.0, wgs84_lat=2.0),
        _Station(station_id="S3", wgs84_lng=2.0, wgs84_lat=0.0),
        _Station(station_id="S4", wgs84_lng=0.0, wgs84_lat=2.0),
        _Station(station_id="S1 (close)", wgs84_lng=0.0, wgs84_lat=0.0),
    ]
    
    unfixed_stations, has_self_intersection = _enforce_simple_polygon_sequence(stations)
    assert has_self_intersection
    assert len(unfixed_stations) == 5
    
    # Assert sequence order is exactly unchanged
    assert unfixed_stations[0].station_id == "S1"
    assert unfixed_stations[1].station_id == "S2"
    assert unfixed_stations[2].station_id == "S3"
    assert unfixed_stations[3].station_id == "S4"


def test_surveyor_intelligence_beacons():
    # Track B: COGO traverse with authentic beacon names
    cogo_text = """
    MINNA UTM ZONE 32
    Tie-Point: E 387500.000 N 550600.000
    
    SC/AK/K 5948 to SC/AK/K 5949: N 62°15'30"E 120.50m
    SC/AK/K 5949 to SC/AK/K 5950: S 27°44'30"E 95.75m
    SC/AK/K 5950 to SC/AK/K 5951: S 62°15'30"W 120.50m
    SC/AK/K 5951 to SC/AK/K 5948: N 27°44'30"W 95.75m
    """
    result = cadastral_run(raw_text=cogo_text)
    assert not isinstance(result, MCPErrorResponse)
    
    beacons = result.beacons
    assert len(beacons) == 5
    assert beacons[0].station_id == "SC/AK/K 5948"
    assert beacons[1].station_id == "SC/AK/K 5949"
    assert beacons[2].station_id == "SC/AK/K 5950"
    assert beacons[3].station_id == "SC/AK/K 5951"
    assert beacons[4].station_id == "SC/AK/K 5948" # closed station ID (since vec[-1].to_station is SC/AK/K 5948)
    
    # Assert clipboard copy string is populated
    for b in beacons:
        assert b.ui_clipboard_copy_string is not None
        assert "," in b.ui_clipboard_copy_string
        e_str, n_str = b.ui_clipboard_copy_string.split(",")
        # Should be float strings
        float(e_str.strip())
        float(n_str.strip())


def test_unclosed_traverse_misclosure():
    # Misclosure error is large because final leg is way too short (10.0m instead of 95.75m)
    cogo_text_unclosed = """
    MINNA UTM ZONE 32
    Tie-Point: E 387500.000 N 550600.000
    
    SC/AK/K 5948 to SC/AK/K 5949: N 62°15'30"E 120.50m
    SC/AK/K 5949 to SC/AK/K 5950: S 27°44'30"E 95.75m
    SC/AK/K 5950 to SC/AK/K 5951: S 62°15'30"W 120.50m
    SC/AK/K 5951 to SC/AK/K 5948: N 27°44'30"W 10.00m
    """
    result = cadastral_run(raw_text=cogo_text_unclosed)
    assert not isinstance(result, MCPErrorResponse)
    
    polygon = result.polygon
    assert polygon is not None
    assert polygon.is_closed is False
    assert polygon.is_valid is False
    assert polygon.closure_status == "UNCLOSED"
    assert polygon.closure_error_meters > 2.0
    
    # Verify open coordinates sequence is still constructed and returned
    assert len(polygon.wgs84_coordinates) == 5
    assert len(polygon.utm_coordinates) == 5
    assert polygon.wgs84_coordinates[0] != [0.0, 0.0]


def test_clipboard_copy_string_tabular():
    result = cadastral_run(raw_text=TRACK_A_TEXT)
    assert not isinstance(result, MCPErrorResponse)
    
    beacons = result.beacons
    assert len(beacons) >= 4
    for b in beacons:
        assert b.ui_clipboard_copy_string is not None
        assert "," in b.ui_clipboard_copy_string

