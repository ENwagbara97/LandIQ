import pytest
from agents.coord_extract import reverse_geocode

def test_reverse_geocode_lagos():
    """
    Test that reverse_geocode correctly hits Nominatim OSM
    and extracts the State and LGA (county/city) for a known coordinate in Lagos.
    Coordinate: 6.45, 3.4 (Lagos Island area)
    """
    # 6.45 N, 3.4 E is in Lagos State.
    state, lga = reverse_geocode(6.45, 3.4)
    
    assert state == "Lagos", f"Expected 'Lagos' State, got {state}"
    assert lga != "Unresolved — confirm LGA", "LGA was not resolved"
    
def test_reverse_geocode_abuja():
    """
    Test coordinate in Abuja (FCT).
    Coordinate: 9.076, 7.399 (Abuja)
    """
    state, lga = reverse_geocode(9.076, 7.399)
    
    assert state == "Federal Capital Territory", f"Expected 'Federal Capital Territory', got {state}"
    assert lga != "Unresolved — confirm LGA", "LGA was not resolved"
