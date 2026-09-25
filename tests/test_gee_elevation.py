import unittest.mock as mock
import pytest
from fastapi.testclient import TestClient
from main import app
from core.elevation_contour import get_nice_interval, get_gee_elevation_contours
from core.schemas import PersonaMode

client = TestClient(app)

def test_get_nice_interval():
    # Test different ranges to verify nice interval selection
    assert get_nice_interval(10.0, 12.0) == 0.5
    assert get_nice_interval(10.0, 25.0) == 2.0
    assert get_nice_interval(10.0, 80.0) == 5.0
    assert get_nice_interval(10.0, 200.0) == 10.0
    assert get_nice_interval(10.0, 10.0) == 1.0


@mock.patch("core.elevation_contour._conn")
def test_gee_elevation_cache_hit(mock_conn):
    # Test cache hit path
    mock_cursor = mock.MagicMock()
    mock_cursor.fetchone.return_value = {
        "response_json": '{"elevation_available": true, "cached": true}',
        "fetched_at": "2026-07-03T12:00:00+00:00"
    }
    mock_conn.return_value.execute.return_value = mock_cursor

    res = get_gee_elevation_contours("test-report-id", [[6.43, 3.41], [6.44, 3.42]])
    assert res.get("cached") is True


@mock.patch("core.elevation_contour._conn")
@mock.patch("core.elevation_contour.ee")
def test_gee_elevation_live_mocked(mock_ee, mock_conn):
    # Test standard fetch path with GEE mocked out
    mock_cursor = mock.MagicMock()
    mock_cursor.fetchone.return_value = None # Cache miss
    mock_conn.return_value.execute.return_value = mock_cursor

    mock_ee.ImageCollection.return_value.select.return_value.mosaic.return_value.resample.return_value.reproject.return_value.sampleRectangle.return_value.getInfo.return_value = {
        "properties": {
            "DEM": [[10.0, 12.0], [11.0, 13.0]]
        }
    }

    res = get_gee_elevation_contours("test-report-id", [[6.43, 3.41], [6.44, 3.42]])
    assert res.get("elevation_available") is True
    assert res.get("grid") == [[10.0, 12.0], [11.0, 13.0]]
    assert res.get("min_elevation") == 10.0
    assert res.get("max_elevation") == 13.0


@mock.patch("core.history_manager.get_report")
def test_api_gee_elevation_gates(mock_get_report):
    # Test non-existent report
    mock_get_report.return_value = None
    response = client.get("/api/report/non-existent-report/gee-elevation")
    assert response.status_code == 404

    # Test non-expert persona (should succeed)
    mock_report = mock.MagicMock()
    mock_report.persona_mode = PersonaMode.EVERYDAY_BUYER
    mock_report.parcel_geometry.coordinates = [[6.43, 3.41], [6.44, 3.42]]
    mock_get_report.return_value = mock_report
    
    with mock.patch("core.elevation_contour.get_gee_elevation_contours") as mock_get_contours:
        mock_get_contours.return_value = {"elevation_available": True, "grid": [[10]]}
        response = client.get("/api/report/test-report/gee-elevation")
        assert response.status_code == 200
        assert "elevation_available" in response.json()

    # Test expert persona access
    mock_report.persona_mode = PersonaMode.SURVEYOR
    mock_report.parcel_geometry.coordinates = [[6.43, 3.41], [6.44, 3.42]]
    
    with mock.patch("core.elevation_contour.get_gee_elevation_contours") as mock_get_contours:
        mock_get_contours.return_value = {"elevation_available": True, "grid": [[10]]}
        response = client.get("/api/report/test-report/gee-elevation")
        assert response.status_code == 200
        assert response.json()["grid"] == [[10]]
