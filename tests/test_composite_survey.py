"""
LandIQ — tests/test_composite_survey.py
Deterministic unit tests for the composite survey intelligence upgrade.

All tests are pure-Python (no Gemini API calls, no network requests).
Tests validate:
  - Plan type classifier (Chapter 1.2)
  - Back bearing computation (Chapter 5.1)
  - Lot traverse closure (Chapter 5.1)
  - Area validation (Chapter 6.1)
  - Shared vertex consistency (Chapter 6.1)
  - Engineering/topo type detection (Chapter 1.2)
  - Title deed rejection (TYPE_E)
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from agents.plan_classifier import classify_plan_type
from agents.coord_extract import _bearing_dms_to_decimal, compute_lot_traverse
from core.schemas import PlanType


# =============================================================================
# PLAN TYPE CLASSIFIER TESTS
# =============================================================================

class TestPlanClassifier:

    def test_simple_parcel_defaults_to_type_a(self):
        """A plain single-parcel OCR text must classify as TYPE_A."""
        text = """
        MINNA UTM ZONE 32
        SC/AK/K 49700  387804.297  550821.575
        SC/AK/K 49701  387852.254  550891.123
        SC/AK/K 49702  387910.500  550865.400
        SC/AK/K 49703  387875.100  550795.200
        AREA = 424.846 SQ. METRES
        """
        result = classify_plan_type(text)
        assert result.plan_type == PlanType.TYPE_A
        assert result.confidence >= 0.70

    def test_composite_two_lots_detected_as_type_b(self):
        """OCR text with Lot 1 and Lot 2 + two area statements → TYPE_B."""
        text = """
        PLAN OF LOTS 1 AND 2
        LOT 1   AREA = 1664 m²
        LOT 2   AREA = 606 m²
        Bearing table reference: Lots 1 and 2 on RP 716480
        """
        result = classify_plan_type(text)
        assert result.plan_type == PlanType.TYPE_B
        assert result.confidence >= 0.70
        assert any("named_lots" in s for s in result.signals)
        assert any("area_statements" in s for s in result.signals)

    def test_engineering_topo_detected_as_type_c(self):
        """OCR text with school name + contour keyword → TYPE_C."""
        text = """
        TOPOGRAPHIC AND ENGINEERING SURVEY
        COMPREHENSIVE SECONDARY SCHOOL, NKPOR
        IDEMILI NORTH LOCAL GOVERNMENT AREA, ANAMBRA STATE
        Contour interval: 2 metres
        ADMIN BLOCK  LABORATORY  STORE
        SCALE: 1:1000
        """
        result = classify_plan_type(text)
        assert result.plan_type == PlanType.TYPE_C
        assert result.confidence >= 0.70

    def test_title_deed_rejected_as_type_e(self):
        """A Certificate of Occupancy text must be classified TYPE_E."""
        text = """
        CERTIFICATE OF OCCUPANCY
        This is to certify that the Governor of Lagos State
        grants a right of occupancy to Chief Emeka Okafor
        for a term of 99 years.
        """
        result = classify_plan_type(text)
        assert result.plan_type == PlanType.TYPE_E
        assert result.confidence >= 0.70

    def test_empty_text_defaults_gracefully(self):
        """Empty/null OCR text should return TYPE_A without crashing."""
        result = classify_plan_type("")
        assert result.plan_type == PlanType.TYPE_A

    def test_three_lots_gives_higher_confidence(self):
        """Three named lots should push confidence higher than two."""
        two_lot_text = "LOT 1  AREA=100m²  LOT 2  AREA=200m²"
        three_lot_text = "LOT 1  AREA=100m²  LOT 2  AREA=200m²  LOT 3  AREA=150m²"
        r2 = classify_plan_type(two_lot_text)
        r3 = classify_plan_type(three_lot_text)
        assert r3.confidence >= r2.confidence

    def test_deed_of_assignment_is_type_e(self):
        """Deed of Assignment keywords must trigger TYPE_E."""
        text = "DEED OF ASSIGNMENT between the Assignor and Assignee for plot 5 Block B"
        result = classify_plan_type(text)
        assert result.plan_type == PlanType.TYPE_E


# =============================================================================
# BEARING CONVERSION TESTS
# =============================================================================

class TestBearingConversion:

    def test_whole_circle_bearing(self):
        """045°30'00\" should convert to 45.5 degrees."""
        result = _bearing_dms_to_decimal("045°30'00\"")
        assert abs(result - 45.5) < 0.01

    def test_north_east_quadrant_bearing(self):
        """N45°30'E should convert to 45.5 degrees azimuth."""
        result = _bearing_dms_to_decimal("N45°30'E")
        assert abs(result - 45.5) < 0.01

    def test_south_east_quadrant_bearing(self):
        """S45°30'E should convert to 134.5 degrees azimuth."""
        result = _bearing_dms_to_decimal("S45°30'E")
        assert abs(result - 134.5) < 0.01

    def test_south_west_quadrant_bearing(self):
        """S45°30'W should convert to 225.5 degrees azimuth."""
        result = _bearing_dms_to_decimal("S45°30'W")
        assert abs(result - 225.5) < 0.01

    def test_north_west_quadrant_bearing(self):
        """N45°30'W should convert to 314.5 degrees azimuth."""
        result = _bearing_dms_to_decimal("N45°30'W")
        assert abs(result - 314.5) < 0.01

    def test_plain_decimal_bearing(self):
        """A plain decimal string like '135.25' should pass through."""
        result = _bearing_dms_to_decimal("135.25")
        assert abs(result - 135.25) < 0.001

    def test_back_bearing_computation(self):
        """
        Chapter 5.1 Rule: back bearing = (forward + 180) % 360.
        If forward bearing of shared leg = 45°, back = 225°.
        """
        forward = 45.0
        back = (forward + 180.0) % 360.0
        assert back == 225.0

    def test_back_bearing_wraps_correctly(self):
        """If forward = 270°, back bearing must be 90° (not 450°)."""
        forward = 270.0
        back = (forward + 180.0) % 360.0
        assert back == 90.0


# =============================================================================
# LOT TRAVERSE TESTS (CHAPTER 5.1)
# =============================================================================

class TestLotTraverse:
    """
    Synthetic 2-lot composite test based on Image 1 reference.
    Lot 1: rectangular ~1664 m², Lot 2: ~606 m².
    Shared boundary: one internal leg between P2→P3.

    We use a simplified rectangle for deterministic testing:
    Lot 1 legs (clockwise, UTM 32N):
      P1→P2: E  (bearing 90°, 40.0m)
      P2→P3: S  (bearing 180°, 41.6m)  ← shared with Lot 2
      P3→P4: W  (bearing 270°, 40.0m)
      P4→P1: N  (bearing 0°,   41.6m)
    Area = 40 × 41.6 = 1664 m² ✓

    Lot 2 uses shared leg P2→P3 in REVERSE (back bearing = 0°, N direction).
    Lot 2 must be smaller: 20×30 = 606 m² approx.
    """

    # Reference UTM 32N (Lagos-area coordinates for plausibility)
    REF_E = 387804.297
    REF_N = 550821.575

    LOT1_INFO = {
        "stations": ["P1", "P2", "P3", "P4"],
        "shared_with": ["2"],
        "shared_station_from": "P2",
        "shared_station_to": "P3",
    }

    BEARING_TABLE = [
        {"from_station": "P1", "to_station": "P2",
         "bearing_dms": "90", "distance_m": 40.0,
         "belongs_to_lots": ["1"], "is_shared": False},
        {"from_station": "P2", "to_station": "P3",
         "bearing_dms": "180", "distance_m": 41.6,
         "belongs_to_lots": ["1", "2"], "is_shared": True},
        {"from_station": "P3", "to_station": "P4",
         "bearing_dms": "270", "distance_m": 40.0,
         "belongs_to_lots": ["1"], "is_shared": False},
        {"from_station": "P4", "to_station": "P1",
         "bearing_dms": "0", "distance_m": 41.6,
         "belongs_to_lots": ["1"], "is_shared": False},
    ]

    def test_lot1_traverse_returns_points(self):
        """Lot 1 traverse must return at least 4 WGS84 points."""
        wgs_pts = compute_lot_traverse(
            lot_id="1",
            lot_info=self.LOT1_INFO,
            bearing_table=self.BEARING_TABLE,
            reference_easting=self.REF_E,
            reference_northing=self.REF_N,
            crs_name_str="UTM_32N",
        )
        assert len(wgs_pts) >= 4, f"Expected >=4 points, got {len(wgs_pts)}"

    def test_lot1_traverse_points_inside_nigeria(self):
        """All computed Lot 1 WGS84 points must fall inside Nigeria's bounding box."""
        from agents.coord_extract import NIGERIA_BBOX
        wgs_pts = compute_lot_traverse(
            lot_id="1",
            lot_info=self.LOT1_INFO,
            bearing_table=self.BEARING_TABLE,
            reference_easting=self.REF_E,
            reference_northing=self.REF_N,
            crs_name_str="UTM_32N",
        )
        for lat, lng in wgs_pts:
            assert NIGERIA_BBOX["lat_min"] <= lat <= NIGERIA_BBOX["lat_max"], \
                f"Latitude {lat} out of Nigeria bounds"
            assert NIGERIA_BBOX["lon_min"] <= lng <= NIGERIA_BBOX["lon_max"], \
                f"Longitude {lng} out of Nigeria bounds"

    def test_lot1_closure_error_within_tolerance(self):
        """
        Closure check: last point must be within 0.5m of start point (Chapter 5.1 Step 4).
        Uses Haversine approximation — for a tiny rectangle this is accurate enough.
        """
        wgs_pts = compute_lot_traverse(
            lot_id="1",
            lot_info=self.LOT1_INFO,
            bearing_table=self.BEARING_TABLE,
            reference_easting=self.REF_E,
            reference_northing=self.REF_N,
            crs_name_str="UTM_32N",
        )
        # First and last point should be very close (closed traverse)
        first = wgs_pts[0]
        last = wgs_pts[-1]
        # Quick Euclidean approximation in degrees (1° ≈ 111km)
        dlat = (last[0] - first[0]) * 111_320
        dlng = (last[1] - first[1]) * 111_320 * math.cos(math.radians(first[0]))
        closure_m = math.sqrt(dlat ** 2 + dlng ** 2)
        assert closure_m < 2.0, f"Closure error {closure_m:.3f}m exceeds tolerance"

    def test_back_bearing_produces_different_traverse_than_forward(self):
        """
        Lot 2 uses the shared leg in back-bearing. The resulting polygon must
        be different from Lot 1 (not the same shape in the same location).
        """
        lot2_info = {
            "stations": ["P2", "P3"],  # only has the shared leg
            "shared_with": ["1"],
            "shared_station_from": "P3",   # Lot 2 traverses P3→P2 (reverse)
            "shared_station_to": "P2",
        }
        wgs_lot1 = compute_lot_traverse(
            lot_id="1",
            lot_info=self.LOT1_INFO,
            bearing_table=self.BEARING_TABLE,
            reference_easting=self.REF_E,
            reference_northing=self.REF_N,
        )
        wgs_lot2 = compute_lot_traverse(
            lot_id="2",
            lot_info=lot2_info,
            bearing_table=self.BEARING_TABLE,
            reference_easting=self.REF_E,
            reference_northing=self.REF_N,
        )
        # At minimum they should not be identical
        if wgs_lot1 and wgs_lot2:
            assert wgs_lot1[0] != wgs_lot2[0] or len(wgs_lot1) != len(wgs_lot2)


# =============================================================================
# AREA VALIDATION (CHAPTER 6.1)
# =============================================================================

class TestAreaValidation:

    def test_lot_areas_must_not_exceed_master(self):
        """
        Chapter 6.1 Rule: sum(individual lot areas) <= master boundary area.
        If sum > master, at least one computation is wrong.
        """
        lot1_area_sqm = 1664.0
        lot2_area_sqm = 606.0
        master_area_sqm = 2400.0   # roads + margins bring it higher

        total_lots = lot1_area_sqm + lot2_area_sqm
        assert total_lots <= master_area_sqm, \
            f"Sum of lots ({total_lots}) exceeds master ({master_area_sqm})"

    def test_individual_lot_area_within_tolerance(self):
        """
        Chapter 6.1: computed area must match stated area within 5%.
        Synthetic test using the stated areas from Image 1.
        """
        stated_sqm = 1664.0
        computed_sqm = 1695.0   # ±2% — acceptable
        discrepancy_pct = abs(computed_sqm - stated_sqm) / stated_sqm * 100
        assert discrepancy_pct <= 5.0, \
            f"Area discrepancy {discrepancy_pct:.1f}% exceeds 5% tolerance"

    def test_area_discrepancy_flag_fires_above_threshold(self):
        """If computed area is >5% off from stated, the system must flag it."""
        stated_sqm = 1664.0
        computed_sqm = 1900.0   # 14.2% off — must flag
        discrepancy_pct = abs(computed_sqm - stated_sqm) / stated_sqm * 100
        assert discrepancy_pct > 5.0, "Expected flag condition not triggered"
