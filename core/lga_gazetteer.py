"""
LGA Gazetteer Module for Nigeria Land Intelligence Agent
Provides ultra-fast (<1ms) in-memory lookup of Nigerian States and LGAs
mapped to primary UTM zones (31N, 32N, 33N) and official Minna EPSG codes.

Extended: loads all Nigerian LGAs from data/nigeria_lgas.json at startup
for Layer 2.5 Geo-Resolution Verification in the News Intelligence Feed.
"""
from __future__ import annotations

import json
import logging
import pathlib as _pathlib
from typing import Any, Dict, Optional

logger = logging.getLogger("landiq.gazetteer")

STATE_UTM_ZONE_MAP: Dict[str, int] = {
    "lagos": 31, "ogun": 31, "oyo": 31, "osun": 31, "ondo": 31,
    "ekiti": 31, "kwara": 31, "sokoto": 31, "kebbi": 31,
    "akwa ibom": 32, "cross river": 32, "rivers": 32, "bayelsa": 32,
    "delta": 32, "edo": 32, "imo": 32, "abia": 32, "enugu": 32,
    "anambra": 32, "ebonyi": 32, "kogi": 32, "fct": 32,
    "fct abuja": 32, "abuja": 32, "kaduna": 32, "kano": 32,
    "niger": 32, "benue": 32, "nasarawa": 32, "plateau": 32,
    "jigawa": 32, "katsina": 32, "zamfara": 32,
    "borno": 33, "yobe": 33, "adamawa": 33, "taraba": 33,
    "bauchi": 33, "gombe": 33,
}

LGA_GAZETTEER: Dict[str, Dict[str, Any]] = {
    "uyo":           {"state": "Akwa Ibom",  "zone": 32, "epsg": "EPSG:26332", "bbox": [4.95, 5.08, 7.85, 7.98]},
    "eket":          {"state": "Akwa Ibom",  "zone": 32, "epsg": "EPSG:26332", "bbox": [4.58, 4.70, 7.88, 8.00]},
    "ikot ekpene":   {"state": "Akwa Ibom",  "zone": 32, "epsg": "EPSG:26332", "bbox": [5.15, 5.25, 7.68, 7.78]},
    "port harcourt": {"state": "Rivers",     "zone": 32, "epsg": "EPSG:26332", "bbox": [4.70, 4.90, 6.95, 7.10]},
    "calabar":       {"state": "Cross River","zone": 32, "epsg": "EPSG:26332", "bbox": [4.90, 5.05, 8.30, 8.42]},
    "benin city":    {"state": "Edo",        "zone": 32, "epsg": "EPSG:26332", "bbox": [6.25, 6.42, 5.55, 5.70]},
    "warri":         {"state": "Delta",      "zone": 32, "epsg": "EPSG:26332", "bbox": [5.48, 5.60, 5.70, 5.82]},
    "enugu":         {"state": "Enugu",      "zone": 32, "epsg": "EPSG:26332", "bbox": [6.38, 6.50, 7.45, 7.58]},
    "owerri":        {"state": "Imo",        "zone": 32, "epsg": "EPSG:26332", "bbox": [5.42, 5.54, 6.98, 7.10]},
    "abuja":         {"state": "FCT",        "zone": 32, "epsg": "EPSG:26332", "bbox": [8.90, 9.15, 7.30, 7.55]},
    "ikeja":         {"state": "Lagos",      "zone": 31, "epsg": "EPSG:26331", "bbox": [6.57, 6.64, 3.32, 3.37]},
    "eti-osa":       {"state": "Lagos",      "zone": 31, "epsg": "EPSG:26331", "bbox": [6.40, 6.48, 3.42, 3.65]},
    "lekki":         {"state": "Lagos",      "zone": 31, "epsg": "EPSG:26331", "bbox": [6.42, 6.49, 3.50, 3.80]},
    "ibadan":        {"state": "Oyo",        "zone": 31, "epsg": "EPSG:26331", "bbox": [7.30, 7.48, 3.82, 3.98]},
    "abeokuta":      {"state": "Ogun",       "zone": 31, "epsg": "EPSG:26331", "bbox": [7.10, 7.22, 3.30, 3.42]},
    "maiduguri":     {"state": "Borno",      "zone": 33, "epsg": "EPSG:26333", "bbox": [11.78, 11.90, 13.10, 13.22]},
}

MINNA_EPSG_MAP = {31: "EPSG:26331", 32: "EPSG:26332", 33: "EPSG:26333"}

_EXTENDED_LGA: Dict[str, Dict[str, Any]] = {}


def _load_extended_lgas() -> None:
    global _EXTENDED_LGA
    data_path = _pathlib.Path(__file__).parent.parent / "data" / "nigeria_lgas.json"
    if not data_path.exists():
        logger.warning("[gazetteer] data/nigeria_lgas.json not found — extended LGA lookup disabled")
        return
    try:
        records = json.loads(data_path.read_text(encoding="utf-8"))
        for r in records:
            key = r["lga"].strip().lower()
            _EXTENDED_LGA[key] = {
                "state":     r["state"],
                "zone":      r["zone"],
                "epsg":      r["epsg"],
                "canonical": r["lga"],
            }
        logger.info(f"[gazetteer] Loaded {len(_EXTENDED_LGA)} LGAs from nigeria_lgas.json")
    except Exception as exc:
        logger.error(f"[gazetteer] Failed to load nigeria_lgas.json: {exc}")


_load_extended_lgas()


def resolve_utm_zone_and_epsg(lga: Optional[str] = None, state: Optional[str] = None) -> tuple:
    """
    Resolve primary UTM Zone (31, 32, or 33) and Minna EPSG code from state/LGA names.
    Defaults to Zone 32N (EPSG:26332) if unmapped.
    """
    if lga:
        lga_clean = lga.strip().lower()
        if lga_clean in LGA_GAZETTEER:
            info = LGA_GAZETTEER[lga_clean]
            return info["zone"], info["epsg"]
        for k, v in LGA_GAZETTEER.items():
            if k in lga_clean or lga_clean in k:
                return v["zone"], v["epsg"]
        if lga_clean in _EXTENDED_LGA:
            info = _EXTENDED_LGA[lga_clean]
            return info["zone"], info["epsg"]
        for k, v in _EXTENDED_LGA.items():
            if k in lga_clean or lga_clean in k:
                return v["zone"], v["epsg"]
    if state:
        state_clean = state.strip().lower()
        for k, zone in STATE_UTM_ZONE_MAP.items():
            if k in state_clean or state_clean in k:
                return zone, MINNA_EPSG_MAP[zone]
    return 32, "EPSG:26332"


def validate_lga_geo(extracted_lga: Optional[str], extracted_state: Optional[str]) -> dict:
    """
    Layer 2.5 Geo-Resolution Verification for the News Intelligence Feed.

    Verifies that:
      1. The extracted LGA name exists in the Nigerian gazetteer.
      2. The associated state matches the extracted state (if provided).

    Returns dict with keys: lga, state, valid, confidence, reason.
    """
    if not extracted_lga or not extracted_lga.strip():
        return {"lga": None, "state": None, "valid": False,
                "confidence": "LOW", "reason": "No LGA extracted"}

    lga_clean = extracted_lga.strip().lower()

    match = LGA_GAZETTEER.get(lga_clean)
    if not match:
        for k, v in LGA_GAZETTEER.items():
            if k in lga_clean or lga_clean in k:
                match = v
                break
    if not match:
        match = _EXTENDED_LGA.get(lga_clean)
    if not match:
        for k, v in _EXTENDED_LGA.items():
            if k in lga_clean or lga_clean in k:
                match = v
                break

    if not match:
        return {
            "lga": None, "state": None, "valid": False,
            "confidence": "LOW",
            "reason": f"'{extracted_lga}' not found in Nigerian LGA gazetteer",
        }

    canonical_lga   = match.get("canonical", extracted_lga)
    canonical_state = match["state"]

    if extracted_state and extracted_state.strip():
        s = extracted_state.strip().lower()
        if canonical_state.lower() not in s and s not in canonical_state.lower():
            return {
                "lga": None, "state": None, "valid": False,
                "confidence": "LOW",
                "reason": (
                    f"'{extracted_lga}' belongs to {canonical_state}, "
                    f"not '{extracted_state}' — likely confabulation error"
                ),
            }

    return {
        "lga":        canonical_lga,
        "state":      canonical_state,
        "valid":      True,
        "confidence": "VALIDATED",
        "reason":     "LGA and state verified against Nigerian gazetteer",
    }
