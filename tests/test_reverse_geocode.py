"""
Tests for core/reverse_geocode.py
Verifies 4-tier reverse geocoding cascade across all location scenarios.
"""

from core.reverse_geocode import reverse_geocode_centroid, _local_state_lookup


def test_reverse_geocode_lagos_centroid():
    """Lagos coordinates should resolve to Lagos State."""
    res = reverse_geocode_centroid(6.5244, 3.3792)
    assert res is not None
    assert res["country"] == "Nigeria"
    assert "Lagos" in res["display_location"]
    assert res["confidence"] > 0


def test_reverse_geocode_abuja_centroid():
    """Abuja coordinates should resolve to FCT Abuja or Federal Capital Territory."""
    res = reverse_geocode_centroid(9.0765, 7.4988)
    assert res is not None
    assert res["country"] == "Nigeria"
    assert any(term in res["display_location"] for term in ["Abuja", "FCT", "Federal Capital Territory"])


def test_reverse_geocode_uyo_centroid():
    """Uyo coordinates should resolve to Akwa Ibom State."""
    res = reverse_geocode_centroid(5.0002, 7.9820)
    assert res is not None
    assert res["country"] == "Nigeria"
    assert "Akwa Ibom" in res["display_location"] or "Uyo" in res["display_location"]


def test_reverse_geocode_offline_fallback():
    """Local state bounding box lookup should work offline without errors."""
    res = _local_state_lookup(5.0002, 7.9820)
    assert res is not None
    assert res["state"] == "Akwa Ibom State"
    assert res["source"] == "local_state_box"


def test_reverse_geocode_out_of_nigeria():
    """Coordinates outside Nigeria should be flagged cleanly."""
    res = reverse_geocode_centroid(43.6532, -79.3832)  # Toronto
    assert res["country"] == "Outside Nigeria"
    assert res["display_location"] == "Outside Nigeria"
    assert res["source"] == "bounds_check"
