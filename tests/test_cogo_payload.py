import pytest
from pydantic import ValidationError
from core.schemas import COGOTraversePayload

def test_cogo_payload_valid():
    payload_dict = {
        "input_mode": "cogo_traverse",
        "starting_point": {
            "easting": 387223.007,
            "northing": 552487.540,
            "crs": "EPSG:32632",
            "confidence": "confirmed"
        },
        "stations": [
            {
                "station_id": "S1",
                "easting_raw": 387223.007,
                "northing_raw": 552487.540,
                "easting_adjusted": 387223.007,
                "northing_adjusted": 552487.540,
                "source": "cogo_computed"
            }
        ],
        "closure": {
            "error_m": 0.18,
            "classification": "GOOD",
            "adjustment_applied": "bowditch"
        },
        "is_closed_traverse": True,
        "computed_area_sqm": 424.91,
        "stated_area_sqm": 424.846,
        "area_discrepancy_pct": 0.015,
        "crs": "EPSG:32632"
    }
    
    payload = COGOTraversePayload(**payload_dict)
    assert payload.crs == "EPSG:32632"
    assert payload.closure.classification == "GOOD"
    assert payload.is_closed_traverse is True

def test_cogo_payload_missing_crs():
    payload_dict = {
        "input_mode": "cogo_traverse",
        "starting_point": {
            "easting": 387223.007,
            "northing": 552487.540,
            "crs": "EPSG:32632",
            "confidence": "confirmed"
        },
        "stations": [],
        "closure": {
            "error_m": 0.18,
            "classification": "GOOD",
            "adjustment_applied": "bowditch"
        },
        "is_closed_traverse": True,
        "computed_area_sqm": 424.91,
        "stated_area_sqm": 424.846,
        "area_discrepancy_pct": 0.015,
        "crs": "" # Empty CRS should trigger validation error
    }
    
    with pytest.raises(ValidationError) as exc_info:
        COGOTraversePayload(**payload_dict)
    
    assert "CRS is explicitly required and cannot be empty" in str(exc_info.value)
