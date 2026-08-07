import pytest
from agents.coord_extract import detect_crs, discover_zone_from_raw_metrics, validate_wgs84_result, CRSName

def test_explicit_crs_header_parsing():
    """Verify # CRS: header comments are parsed with 99% confidence."""
    text_32n = "# CRS: UTM Zone 32N (EPSG:32632)\n# Source: COGO Forward Traverse\nS1-S2 377821.067 553849.531\nS2-S3 377854.843 553853.205"
    crs, conf, method = detect_crs([], raw_text=text_32n)
    assert crs == CRSName.UTM_32N
    assert conf == 99.0
    assert method == "Header CRS Declared"

    text_31n = "# CRS: UTM Zone 31N (EPSG:32631)\nS1-S2 377821.067 553849.531"
    crs31, conf31, _ = detect_crs([], raw_text=text_31n)
    assert crs31 == CRSName.UTM_31N
    assert conf31 == 99.0

def test_northing_aware_zone_disambiguation():
    """Verify Eastings [300k, 500k] with High Northing (>480k N) infer Zone 32N (SE Nigeria)."""
    # Uyo coordinates: 377821.067 E, 553849.531 N
    zone, conf = discover_zone_from_raw_metrics(377821.067, 553849.531)
    assert zone == CRSName.UTM_32N
    assert conf >= 80.0

def test_wgs84_validation_bounds():
    """Verify validate_wgs84_result catches points outside Nigeria."""
    valid_coords = [(6.500, 3.300), (6.501, 3.301)]
    res = validate_wgs84_result(valid_coords)
    assert res["valid"] is True

    out_coords = [(51.507, -0.127)] # London
    res_out = validate_wgs84_result(out_coords)
    assert res_out["valid"] is False
    assert res_out["error"] == "CRS_MISMATCH_SUSPECTED"
