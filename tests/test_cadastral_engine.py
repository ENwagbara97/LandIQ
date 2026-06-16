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
