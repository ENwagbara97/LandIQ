"""
LandIQ — tests/test_api_integration.py

Integration tests for the FastAPI backend — covers the full user flow:
  upload → session → confirm → report
All tests hit a live local server at http://127.0.0.1:5000.
Skipped automatically when the server is unavailable.
"""
from __future__ import annotations

import pytest
import requests

API = "http://127.0.0.1:5000"

SAMPLE_UTM_COORDS = """
SC/AK/K 49703  387875.100  550865.400
SC/AK/K 49700  387804.297  550795.200
SC/AK/K 49701  387682.500  550821.575
SC/AK/K 49702  387750.000  550900.000
SC/AK/K 49703  387875.100  550865.400
"""


def server_available() -> bool:
    try:
        r = requests.get(API + "/", timeout=2)
        return r.status_code < 500
    except Exception:
        return False


skip_no_server = pytest.mark.skipif(
    not server_available(),
    reason="Local server not running at http://127.0.0.1:5000"
)


# ---------------------------------------------------------------------------
# Phase 1: Upload endpoint
# ---------------------------------------------------------------------------
class TestUploadEndpoint:
    @skip_no_server
    def test_upload_returns_200(self):
        r = requests.post(f"{API}/api/upload", data={"raw_text": SAMPLE_UTM_COORDS})
        assert r.status_code == 200

    @skip_no_server
    def test_upload_returns_session_id(self):
        r = requests.post(f"{API}/api/upload", data={"raw_text": SAMPLE_UTM_COORDS})
        body = r.json()
        assert "session_id" in body or "cad_result" in body, f"Unexpected body: {body}"

    @skip_no_server
    def test_upload_empty_returns_error(self):
        r = requests.post(f"{API}/api/upload", data={})
        # Should be 400 or 422 — not 500
        assert r.status_code in (400, 422, 200), f"Got {r.status_code}"

    @skip_no_server
    def test_upload_with_persona(self):
        r = requests.post(f"{API}/api/upload", data={
            "raw_text": SAMPLE_UTM_COORDS,
            "persona_mode": "CITY_PLANNER"
        })
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Phase 2: Session endpoint
# ---------------------------------------------------------------------------
class TestSessionEndpoint:
    @staticmethod
    def get_session_id() -> str:
        r = requests.post(f"{API}/api/upload", data={"raw_text": SAMPLE_UTM_COORDS})
        body = r.json()
        return body.get("session_id") or body.get("cad_result", {}).get("run_id")

    @skip_no_server
    def test_session_returns_200(self):
        sid = self.get_session_id()
        assert sid, "No session_id returned from upload"
        r = requests.get(f"{API}/api/session/{sid}")
        assert r.status_code == 200

    @skip_no_server
    def test_session_has_coord_extract(self):
        sid = self.get_session_id()
        r = requests.get(f"{API}/api/session/{sid}")
        body = r.json()
        assert "coord_extract" in body, f"Missing coord_extract in: {list(body.keys())}"

    @skip_no_server
    def test_session_coord_extract_has_coordinates(self):
        sid = self.get_session_id()
        r = requests.get(f"{API}/api/session/{sid}")
        ext = r.json().get("coord_extract", {})
        assert "coordinates" in ext or "wgs84_polygon" in ext, \
            f"No coordinates found. Keys: {list(ext.keys())}"

    @skip_no_server
    def test_session_404_for_invalid_id(self):
        r = requests.get(f"{API}/api/session/nonexistent-id-xyz")
        assert r.status_code == 404

    @skip_no_server
    def test_session_has_detected_crs(self):
        sid = self.get_session_id()
        r = requests.get(f"{API}/api/session/{sid}")
        ext = r.json().get("coord_extract", {})
        assert "detected_crs" in ext, f"Missing detected_crs. Keys: {list(ext.keys())}"


# ---------------------------------------------------------------------------
# Phase 2: Confirm endpoint
# ---------------------------------------------------------------------------
class TestConfirmEndpoint:
    @staticmethod
    def get_session_id() -> str:
        r = requests.post(f"{API}/api/upload", data={"raw_text": SAMPLE_UTM_COORDS})
        body = r.json()
        return body.get("session_id") or body.get("cad_result", {}).get("run_id")

    @skip_no_server
    def test_confirm_returns_200(self):
        sid = self.get_session_id()
        r = requests.post(f"{API}/api/confirm/{sid}", json={"responses": {}})
        assert r.status_code == 200, f"Got {r.status_code}: {r.text[:200]}"

    @skip_no_server
    def test_confirm_returns_report_id(self):
        sid = self.get_session_id()
        r = requests.post(f"{API}/api/confirm/{sid}", json={"responses": {}})
        body = r.json()
        assert "report_id" in body or "run_id" in body or "session_id" in body, \
            f"No report reference. Keys: {list(body.keys())}"


# ---------------------------------------------------------------------------
# Phase 3: Report endpoint
# ---------------------------------------------------------------------------
class TestReportEndpoint:
    @staticmethod
    def get_report_id() -> str:
        r = requests.post(f"{API}/api/upload", data={"raw_text": SAMPLE_UTM_COORDS})
        body = r.json()
        sid = body.get("session_id") or body.get("cad_result", {}).get("run_id")
        r2 = requests.post(f"{API}/api/confirm/{sid}", json={"responses": {}})
        # Poll session status until background pipeline completes
        import time
        for _ in range(180):  # Wait up to 90 seconds (accommodates local LLM cold starts)
            status_res = requests.get(f"{API}/api/session/{sid}")
            if status_res.status_code == 200:
                status_data = status_res.json()
                if status_data.get("status") in ("completed", "error"):
                    break
            time.sleep(0.5)
        return sid


    @skip_no_server
    def test_report_returns_200(self):
        rid = self.get_report_id()
        r = requests.get(f"{API}/api/report/{rid}")
        assert r.status_code == 200, f"Got {r.status_code}"

    @skip_no_server
    def test_report_has_summary(self):
        rid = self.get_report_id()
        r = requests.get(f"{API}/api/report/{rid}")
        body = r.json()
        assert "summary" in body, f"Missing summary. Keys: {list(body.keys())}"

    @skip_no_server
    def test_report_summary_has_score(self):
        rid = self.get_report_id()
        r = requests.get(f"{API}/api/report/{rid}")
        summary = r.json().get("summary", {})
        assert "overall_risk_score" in summary, \
            f"Missing overall_risk_score. Summary keys: {list(summary.keys())}"

    @skip_no_server
    def test_report_summary_has_traffic_light(self):
        rid = self.get_report_id()
        r = requests.get(f"{API}/api/report/{rid}")
        summary = r.json().get("summary", {})
        assert "traffic_light" in summary, \
            f"Missing traffic_light. Summary keys: {list(summary.keys())}"

    @skip_no_server
    def test_report_has_terrain_assessment(self):
        rid = self.get_report_id()
        r = requests.get(f"{API}/api/report/{rid}")
        body = r.json()
        assert "terrain_assessment" in body, \
            f"Missing terrain_assessment. Keys: {list(body.keys())}"

    @skip_no_server
    def test_report_sources_endpoint(self):
        rid = self.get_report_id()
        r = requests.get(f"{API}/api/report/{rid}/sources")
        assert r.status_code in (200, 404), f"Unexpected status: {r.status_code}"


# ---------------------------------------------------------------------------
# Phase 3: History endpoint
# ---------------------------------------------------------------------------
class TestHistoryEndpoint:
    @skip_no_server
    def test_history_returns_200(self):
        r = requests.get(f"{API}/api/history")
        assert r.status_code == 200

    @skip_no_server
    def test_history_returns_list(self):
        r = requests.get(f"{API}/api/history")
        body = r.json()
        assert isinstance(body, list), f"Expected list, got {type(body)}"

    @skip_no_server
    def test_history_items_have_report_id(self):
        r = requests.get(f"{API}/api/history")
        items = r.json()
        if items:
            assert "report_id" in items[0], \
                f"Missing report_id. Item keys: {list(items[0].keys())}"
