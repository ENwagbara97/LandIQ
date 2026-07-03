import pytest
import math
from agents.cadastral_engine import _run_track_b, _BearingDistance

def test_cogo_closure_classification_and_bowditch():
    anchor = (1000.0, 1000.0)
    
    # 100m square, but the last leg is 99.6m instead of 100m.
    # We fall short by 0.40m West. So the final coordinate is (1000.4, 1000.0).
    # Misclosure error = 0.40m. This should be classified as "GOOD" (0.10 - 0.50m)
    # and Bowditch should be applied.
    vectors = [
        _BearingDistance(bearing_decimal_deg=0.0, distance_m=100.0),   # N to (1000, 1100)
        _BearingDistance(bearing_decimal_deg=90.0, distance_m=100.0),  # E to (1100, 1100)
        _BearingDistance(bearing_decimal_deg=180.0, distance_m=100.0), # S to (1100, 1000)
        _BearingDistance(bearing_decimal_deg=270.0, distance_m=99.6),  # W to (1000.4, 1000)
    ]
    
    stations, misclosure, classification, warning_msg = _run_track_b(anchor, vectors)
    
    assert math.isclose(misclosure, 0.40, abs_tol=0.01)
    assert classification == "GOOD"
    assert warning_msg == "" # GOOD doesn't have a warning, just an info note (handled by UI)
    
    # Check Bowditch Adjustment
    # Station 4 is the final point. Before Bowditch, Easting is 1000.4.
    # After Bowditch, it should be adjusted exactly to the anchor point (1000.0) to close the polygon.
    assert math.isclose(stations[4].calculated_easting, 1000.0, abs_tol=0.01)
    assert math.isclose(stations[4].calculated_northing, 1000.0, abs_tol=0.01)

def test_cogo_closure_poor_no_adjustment():
    anchor = (1000.0, 1000.0)
    
    # 100m square, but last leg is 97m. 3m error!
    vectors = [
        _BearingDistance(bearing_decimal_deg=0.0, distance_m=100.0),
        _BearingDistance(bearing_decimal_deg=90.0, distance_m=100.0),
        _BearingDistance(bearing_decimal_deg=180.0, distance_m=100.0),
        _BearingDistance(bearing_decimal_deg=270.0, distance_m=97.0),
    ]
    
    stations, misclosure, classification, warning_msg = _run_track_b(anchor, vectors)
    
    assert math.isclose(misclosure, 3.00, abs_tol=0.01)
    assert classification == "POOR"
    assert "exceeds normal survey tolerance" in warning_msg
    
    # Bowditch MUST NOT be applied for POOR classification.
    # Final coordinate should remain unadjusted at 1003.0
    assert math.isclose(stations[4].calculated_easting, 1003.0, abs_tol=0.01)
