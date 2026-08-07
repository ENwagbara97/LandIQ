"""
LandIQ — core/reverse_geocode.py
Master 4-Tier Reverse Geocoding Cascade for Nigerian Land Parcels.

Cascade Tiers:
  1. OpenStreetMap Nominatim API (free, precise administrative levels, LRU cached)
  2. OpenCage Geocoding API (secondary online fallback if OPENCAGE_API_KEY set)
  3. Local State Bounding Box Lookup (100% offline Python dictionary for all 36 States + FCT)
  4. Formatted Coordinates Fallback (last-resort, formatted coordinates string)

Guarantees:
  - NEVER returns None.
  - NEVER returns "Unknown" or "—, —".
  - Always populates "display_location".
"""

from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from functools import lru_cache
from typing import Optional, Any

logger = logging.getLogger("landiq.reverse_geocode")

# Nigeria bounding box sanity check
NIGERIA_BOUNDS = {
    "lat_min": 4.0, "lat_max": 14.0,
    "lon_min": 2.5, "lon_max": 15.5,
}

# Nigerian state bounding boxes for offline fallback (pure Python dictionary lookup)
NIGERIA_STATE_BOXES: dict[str, dict[str, tuple[float, float]]] = {
    "Lagos":       {"lat": (6.35, 6.70),  "lon": (3.10, 3.95)},
    "Rivers":      {"lat": (4.55, 5.10),  "lon": (6.65, 7.40)},
    "FCT Abuja":   {"lat": (8.75, 9.30),  "lon": (7.10, 7.80)},
    "Akwa Ibom":   {"lat": (4.50, 5.35),  "lon": (7.50, 8.55)},
    "Cross River": {"lat": (5.40, 6.85),  "lon": (7.80, 9.45)},
    "Ogun":        {"lat": (6.40, 7.35),  "lon": (2.90, 4.00)},
    "Oyo":         {"lat": (7.05, 9.05),  "lon": (3.00, 4.60)},
    "Kano":        {"lat": (11.4, 13.2),  "lon": (7.60, 9.60)},
    "Enugu":       {"lat": (6.10, 7.10),  "lon": (7.00, 7.90)},
    "Anambra":     {"lat": (5.85, 6.70),  "lon": (6.65, 7.35)},
    "Imo":         {"lat": (5.05, 5.85),  "lon": (6.85, 7.50)},
    "Delta":       {"lat": (5.00, 6.35),  "lon": (5.55, 6.85)},
    "Edo":         {"lat": (5.70, 7.35),  "lon": (5.30, 6.90)},
    "Kaduna":      {"lat": (9.00, 11.4),  "lon": (6.70, 8.75)},
    "Katsina":     {"lat": (11.3, 13.3),  "lon": (6.75, 9.15)},
    "Borno":       {"lat": (10.3, 13.9),  "lon": (11.0, 15.5)},
    "Plateau":     {"lat": (8.20, 10.6),  "lon": (8.20, 10.4)},
    "Benue":       {"lat": (6.10, 8.20),  "lon": (7.50, 10.1)},
    "Niger":       {"lat": (8.25, 12.4),  "lon": (3.55, 7.75)},
    "Kwara":       {"lat": (7.70, 9.75),  "lon": (3.10, 5.85)},
    "Osun":        {"lat": (7.10, 7.95),  "lon": (4.10, 4.90)},
    "Ekiti":       {"lat": (7.45, 7.85),  "lon": (4.75, 5.55)},
    "Ondo":        {"lat": (5.80, 7.90),  "lon": (4.50, 6.05)},
    "Abia":        {"lat": (5.00, 5.95),  "lon": (7.20, 7.80)},
    "Ebonyi":      {"lat": (5.85, 6.85),  "lon": (7.75, 8.50)},
    "Bayelsa":     {"lat": (4.15, 5.10),  "lon": (5.80, 6.90)},
    "Nasarawa":    {"lat": (7.65, 9.35),  "lon": (7.60, 9.30)},
    "Taraba":      {"lat": (6.50, 9.35),  "lon": (9.55, 12.4)},
    "Adamawa":     {"lat": (8.05, 11.0),  "lon": (11.4, 13.9)},
    "Gombe":       {"lat": (9.45, 11.0),  "lon": (10.0, 12.0)},
    "Bauchi":      {"lat": (9.50, 12.3),  "lon": (9.00, 11.2)},
    "Sokoto":      {"lat": (12.0, 13.9),  "lon": (4.00, 6.75)},
    "Zamfara":     {"lat": (11.2, 13.3),  "lon": (5.85, 7.70)},
    "Kebbi":       {"lat": (10.6, 13.3),  "lon": (3.00, 5.50)},
    "Yobe":        {"lat": (10.6, 13.8),  "lon": (10.2, 14.7)},
    "Jigawa":      {"lat": (11.6, 13.4),  "lon": (8.10, 10.3)},
    "Kogi":        {"lat": (6.75, 8.65),  "lon": (5.65, 7.65)},
}


@lru_cache(maxsize=500)
def reverse_geocode_centroid(lat: float, lng: float) -> dict[str, Any]:
    """
    Master reverse geocoding function.
    Tries 4 sources in cascade. Always returns a valid dictionary.
    NEVER returns None. NEVER returns "Unknown".
    """
    # Round coordinates to 4 decimal places for caching consistency
    rounded_lat = round(lat, 4)
    rounded_lng = round(lng, 4)

    # Sanity check: must be inside Nigeria
    if not (NIGERIA_BOUNDS["lat_min"] <= rounded_lat <= NIGERIA_BOUNDS["lat_max"]
            and NIGERIA_BOUNDS["lon_min"] <= rounded_lng <= NIGERIA_BOUNDS["lon_max"]):
        return {
            "lga": None,
            "state": None,
            "community": None,
            "country": "Outside Nigeria",
            "display_location": "Outside Nigeria",
            "source": "bounds_check",
            "confidence": 95,
        }

    # SOURCE 1: OSM Nominatim (Primary online source)
    res_nominatim = _nominatim_reverse(rounded_lat, rounded_lng)
    if res_nominatim:
        return res_nominatim

    # SOURCE 2: OpenCage Geocoding API (Secondary online fallback if API key configured)
    res_opencage = _opencage_reverse(rounded_lat, rounded_lng)
    if res_opencage:
        return res_opencage

    # SOURCE 3: Local state bounding box lookup (100% offline, zero internet)
    res_local = _local_state_lookup(rounded_lat, rounded_lng)
    if res_local and isinstance(res_local, dict):
        return res_local

    # SOURCE 4: Coordinate-based fallback (Absolute last resort)
    state_name = _local_state_lookup(rounded_lat, rounded_lng, state_only=True)
    state_str = str(state_name) if state_name else "Nigeria"
    display_str = _format_coordinate_location(rounded_lat, rounded_lng)

    return {
        "lga": None,
        "state": state_str if "State" in state_str else f"{state_str} State" if state_str != "Nigeria" else None,
        "community": None,
        "country": "Nigeria",
        "display_location": display_str,
        "source": "coordinate_fallback",
        "confidence": 20,
    }


def _nominatim_reverse(lat: float, lng: float) -> Optional[dict[str, Any]]:
    """OpenStreetMap Nominatim reverse geocode lookup."""
    try:
        url = (
            f"https://nominatim.openstreetmap.org/reverse?"
            f"lat={lat}&lon={lng}&format=json&addressdetails=1&zoom=14&accept-language=en"
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "LandIQ/1.0 (landiq.ng; info@landiq.ng)"}
        )
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode('utf-8'))

        addr = data.get("address", {})

        state = (addr.get("state") or addr.get("region") or addr.get("province"))
        lga = (
            addr.get("county") or
            addr.get("state_district") or
            addr.get("district") or
            addr.get("city_district") or
            addr.get("municipality")
        )
        community = (
            addr.get("suburb") or
            addr.get("neighbourhood") or
            addr.get("quarter") or
            addr.get("village") or
            addr.get("town") or
            addr.get("city")
        )

        # Clean "Local Government Area" suffix from LGA
        if lga:
            lga = lga.replace("Local Government Area", "").replace("Local Government", "").strip()
        if state and "State" not in state and state != "Federal Capital Territory":
            state = f"{state} State"

        if not state and not lga:
            return None

        display = _build_display_location(lga, state, community)

        return {
            "lga": lga or None,
            "state": state or None,
            "community": community or None,
            "country": "Nigeria",
            "display_location": display,
            "source": "nominatim",
            "confidence": 88,
        }

    except Exception as exc:
        logger.debug(f"[reverse_geocode] Nominatim lookup skipped: {exc}")
        return None


def _opencage_reverse(lat: float, lng: float) -> Optional[dict[str, Any]]:
    """OpenCage API reverse geocode lookup."""
    api_key = os.getenv("OPENCAGE_API_KEY")
    if not api_key:
        return None

    try:
        url = (
            f"https://api.opencagedata.com/geocode/v1/json?"
            f"q={lat}+{lng}&key={api_key}&language=en&no_annotations=1&countrycode=ng"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "LandIQ/1.0"})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode('utf-8'))

        results = data.get("results", [])
        if not results:
            return None

        comp = results[0].get("components", {})
        state = comp.get("state", "")
        lga = comp.get("county") or comp.get("state_district") or comp.get("city_district", "")
        community = comp.get("suburb") or comp.get("neighbourhood") or comp.get("town") or comp.get("village", "")

        if lga:
            lga = lga.replace("Local Government Area", "").replace("Local Government", "").strip()
        if state and "State" not in state and state != "Federal Capital Territory":
            state = f"{state} State"

        if not state:
            return None

        display = _build_display_location(lga, state, community)
        return {
            "lga": lga or None,
            "state": state or None,
            "community": community or None,
            "country": "Nigeria",
            "display_location": display,
            "source": "opencage",
            "confidence": 85,
        }

    except Exception as exc:
        logger.debug(f"[reverse_geocode] OpenCage lookup skipped: {exc}")
        return None


def _local_state_lookup(lat: float, lng: float, state_only: bool = False) -> Optional[dict[str, Any]] | Optional[str]:
    """Pure Python offline fallback matching bounding boxes for 36 States + FCT Abuja."""
    for state_name, bounds in NIGERIA_STATE_BOXES.items():
        lat_min, lat_max = bounds["lat"]
        lon_min, lon_max = bounds["lon"]
        if lat_min <= lat <= lat_max and lon_min <= lng <= lon_max:
            full_state = state_name if "FCT" in state_name or "State" in state_name else f"{state_name} State"
            if state_only:
                return full_state
            return {
                "lga": None,
                "state": full_state,
                "community": None,
                "country": "Nigeria",
                "display_location": f"{full_state}, Nigeria",
                "source": "local_state_box",
                "confidence": 55,
            }
    return None


def _build_display_location(lga: Optional[str], state: Optional[str], community: Optional[str]) -> str:
    """Builds human-readable location string. Always returns clean location."""
    parts = []
    if community and community != lga:
        parts.append(community)
    if lga:
        parts.append(f"{lga} LGA" if "LGA" not in lga else lga)
    if state:
        parts.append(state)

    if not parts:
        return "Nigeria"
    return ", ".join(parts)


def _format_coordinate_location(lat: float, lng: float) -> str:
    """Last resort fallback formatting coordinates."""
    lat_dir = "N" if lat >= 0 else "S"
    lng_dir = "E" if lng >= 0 else "W"
    return f"{abs(lat):.4f}°{lat_dir}, {abs(lng):.4f}°{lng_dir} (Nigeria)"
