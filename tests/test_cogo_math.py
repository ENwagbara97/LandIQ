import pytest
import math
from agents.cadastral_engine import parse_cogo_bearing, _run_track_b, _BearingDistance, _Station

def test_parse_cogo_bearing_azimuth():
    assert math.isclose(parse_cogo_bearing("45 30 00"), 45.5, rel_tol=1e-5)
    assert math.isclose(parse_cogo_bearing("134.5"), 134.5, rel_tol=1e-5)
    assert math.isclose(parse_cogo_bearing("045°30'00\""), 45.5, rel_tol=1e-5)
    assert math.isclose(parse_cogo_bearing("135-30-15"), 135.5041666, rel_tol=1e-5)

def test_parse_cogo_bearing_quadrant():
    assert math.isclose(parse_cogo_bearing("N45°30'00\"E"), 45.5, rel_tol=1e-5)
    assert math.isclose(parse_cogo_bearing("S45°30'E"), 134.5, rel_tol=1e-5)
    assert math.isclose(parse_cogo_bearing("S30°15'W"), 210.25, rel_tol=1e-5)
    assert math.isclose(parse_cogo_bearing("N 45 30 W"), 314.5, rel_tol=1e-5)
    assert parse_cogo_bearing("S-45-30-E") == pytest.approx(134.5, rel=1e-5)

def test_cogo_deltas_canonical():
    anchor = (1000.0, 1000.0)
    # L=100
    # North (0) -> dE=0, dN=+100 -> (1000, 1100)
    # East (90) -> dE=+100, dN=0 -> (1100, 1100)
    # South (180) -> dE=0, dN=-100 -> (1100, 1000)
    # West (270) -> dE=-100, dN=0 -> (1000, 1000)
    
    vectors = [
        _BearingDistance(bearing_decimal_deg=0.0, distance_m=100.0),
        _BearingDistance(bearing_decimal_deg=90.0, distance_m=100.0),
        _BearingDistance(bearing_decimal_deg=180.0, distance_m=100.0),
        _BearingDistance(bearing_decimal_deg=270.0, distance_m=100.0),
    ]
    
    stations, misclosure, cls, msg = _run_track_b(anchor, vectors)
    
    # Station 0 is anchor
    assert stations[0].calculated_easting == 1000.0
    assert stations[0].calculated_northing == 1000.0
    
    # Station 1 (North 100m)
    assert math.isclose(stations[1].calculated_easting, 1000.0, abs_tol=0.01)
    assert math.isclose(stations[1].calculated_northing, 1100.0, abs_tol=0.01)
    
    # Station 2 (East 100m)
    assert math.isclose(stations[2].calculated_easting, 1100.0, abs_tol=0.01)
    assert math.isclose(stations[2].calculated_northing, 1100.0, abs_tol=0.01)
    
    # Station 3 (South 100m)
    assert math.isclose(stations[3].calculated_easting, 1100.0, abs_tol=0.01)
    assert math.isclose(stations[3].calculated_northing, 1000.0, abs_tol=0.01)
    
    # Station 4 (West 100m -> back to anchor)
    assert math.isclose(stations[4].calculated_easting, 1000.0, abs_tol=0.01)
    assert math.isclose(stations[4].calculated_northing, 1000.0, abs_tol=0.01)
    
    assert math.isclose(misclosure, 0.0, abs_tol=0.01)
