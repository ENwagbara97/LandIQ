"""
LandIQ — tests/test_phase2_hardened_checks.py
Verification tests for the Phase 2 security and concurrency fixes:
1. 15MB file size limit validation check (expecting 413)
2. Coordinate edge-case mapping validation between UTM Zone 31N and Zone 32N
"""
from __future__ import annotations

import pytest
import requests
import io

API = "http://127.0.0.1:8000"

def server_available() -> bool:
    try:
        r = requests.get(API + "/", timeout=2)
        return r.status_code < 500
    except Exception:
        return False

skip_no_server = pytest.mark.skipif(
    not server_available(),
    reason="Local server not running at http://127.0.0.1:8000"
)

@skip_no_server
def test_upload_file_size_limit_enforced():
    """Verify that uploading a file larger than 15MB returns a 413 Payload Too Large error."""
    # Construct a dummy 16MB file payload
    file_content = b"a" * (16 * 1024 * 1024)
    files = {"file": ("large_dummy.txt", io.BytesIO(file_content), "text/plain")}
    
    r = requests.post(f"{API}/api/upload", files=files, data={"persona_mode": "EVERYDAY_BUYER"})
    assert r.status_code == 413
    assert r.json()["detail"]["error_code"] == "FILE_TOO_LARGE"

@skip_no_server
def test_coordinate_edge_case_zone_32_boundary():
    """
    Verify that coordinate inputs right on the Zone 31N / Zone 32N boundary (around 6°E)
    are parsed and transformed to coordinates within Nigeria borders.
    Coordinate: 6.0°N, 6.0001°E (Zone 32N, Easting ~167000, Northing ~663833)
    """
    raw_text = """
    MINNA UTM ZONE 32
    SC/AK/K 49700 167000.000 663833.000
    SC/AK/K 49701 167100.000 663833.000
    SC/AK/K 49702 167100.000 663933.000
    SC/AK/K 49703 167000.000 663933.000
    SC/AK/K 49700 167000.000 663833.000
    """
    
    r = requests.post(f"{API}/api/upload", data={"raw_text": raw_text})
    assert r.status_code == 200
    body = r.json()
    assert "session_id" in body
    sid = body["session_id"]
    
    # Query session state to get coord_extract
    r_sess = requests.get(f"{API}/api/session/{sid}")
    assert r_sess.status_code == 200
    sess_body = r_sess.json()
    assert "coord_extract" in sess_body
    ext = sess_body["coord_extract"]
    
    assert ext["detected_crs"] in ("MINNA_UTM_32N", "UTM_32N", "MINNA")
    assert ext["is_inside_nigeria"] is True
    
    # Check that transformed coordinates reside in Nigeria
    for coord in ext["coordinates"]:
        lat, lng = coord
        assert 4.0 <= lat <= 14.0, f"Lat {lat} out of Nigeria bounds"
        assert 2.5 <= lng <= 15.0, f"Lng {lng} out of Nigeria bounds"
        # Validate that the transform positioned it near the 6°E boundary
        assert 5.9 <= lng <= 6.1, f"Expected longitude near 6°E, got {lng}"
        assert 5.9 <= lat <= 6.1, f"Expected latitude near 6.0°N, got {lat}"
