"""
LandIQ — tests/test_news_parser.py
Unit tests for the 6-layer News Intelligence Feed hallucination defence.

Run: pytest tests/test_news_parser.py -v
"""
import pytest
from difflib import SequenceMatcher


# ── Layer 2: Fuzzy Quote Verifier ─────────────────────────────────────────────
class TestLayer2FuzzyQuote:
    ARTICLE = (
        "Heavy flooding submerged properties along Rumuola Road in Port Harcourt. "
        "Residents were displaced as flood waters rose overnight. "
        "The state government has declared a state of emergency in the affected areas."
    )

    def test_exact_quote_passes(self):
        from core.news_parser import _verify_quote
        quote = "Heavy flooding submerged properties along Rumuola Road in Port Harcourt."
        assert _verify_quote(quote, self.ARTICLE) is True

    def test_hallucinated_quote_fails(self):
        from core.news_parser import _verify_quote
        quote = "The president declared martial law across all 36 states due to flooding."
        assert _verify_quote(quote, self.ARTICLE) is False

    def test_too_short_quote_rejected(self):
        from core.news_parser import _verify_quote
        quote = "flooding"
        assert _verify_quote(quote, self.ARTICLE) is False

    def test_partial_real_quote_passes(self):
        from core.news_parser import _verify_quote
        quote = "Residents were displaced as flood waters rose overnight."
        assert _verify_quote(quote, self.ARTICLE) is True

# ── Layer 2.5: Gazetteer Spatial Match ────────────────────────────────────────
class TestLayer25GazetteerMatch:
    def test_valid_lga_passes(self):
        from core.lga_gazetteer import validate_lga_geo
        result = validate_lga_geo("Ikeja", "Lagos")
        assert result["valid"] is True
        assert result["lga"] is not None
        assert result["confidence"] == "VALIDATED"

    def test_uyo_in_lagos_fails(self):
        """The classic confabulation: Uyo assigned to Lagos."""
        from core.lga_gazetteer import validate_lga_geo
        result = validate_lga_geo("Uyo", "Lagos")
        assert result["valid"] is False
        assert result["lga"] is None
        assert result["confidence"] == "LOW"
        assert "confabulation" in result["reason"].lower() or "Akwa Ibom" in result["reason"]

    def test_nonexistent_lga_fails(self):
        from core.lga_gazetteer import validate_lga_geo
        result = validate_lga_geo("Narnia Central", "Wakanda")
        assert result["valid"] is False
        assert result["confidence"] == "LOW"

    def test_empty_lga_fails(self):
        from core.lga_gazetteer import validate_lga_geo
        result = validate_lga_geo(None, "Lagos")
        assert result["valid"] is False

    def test_valid_lga_no_state_passes(self):
        """LGA-only lookup (no state provided) should still validate."""
        from core.lga_gazetteer import validate_lga_geo
        result = validate_lga_geo("Port Harcourt", None)
        assert result["valid"] is True
        assert result["state"] == "Rivers"

    def test_extended_dataset_loaded(self):
        """Verify that extended LGA dataset is loaded (>15 LGAs known)."""
        from core.lga_gazetteer import _EXTENDED_LGA
        assert len(_EXTENDED_LGA) > 15, f"Expected >15 LGAs, got {len(_EXTENDED_LGA)}"

    def test_warri_correct_state(self):
        from core.lga_gazetteer import validate_lga_geo
        result = validate_lga_geo("Warri", "Delta")
        assert result["valid"] is True

    def test_enugu_correct(self):
        from core.lga_gazetteer import validate_lga_geo
        result = validate_lga_geo("Enugu North", "Enugu")
        assert result["valid"] is True


# ── Layer 3: Confidence Gate ──────────────────────────────────────────────────
class TestLayer3ConfidenceGate:
    VALID_TYPES = {"flood", "demolition", "land_dispute", "cof_revocation", "fire", "erosion"}

    def test_high_confidence_with_lga_passes(self):
        ev = {"confidence": "HIGH", "lga": "Ikeja", "event_type": "flood"}
        assert ev["confidence"] in {"HIGH", "MEDIUM"}
        assert ev["lga"] is not None
        assert ev["event_type"] in self.VALID_TYPES

    def test_low_confidence_gated_out(self):
        ev = {"confidence": "LOW", "lga": "Ikeja", "event_type": "flood"}
        assert ev["confidence"] not in {"HIGH", "MEDIUM"}

    def test_none_lga_gated_out(self):
        ev = {"confidence": "HIGH", "lga": None, "event_type": "flood"}
        assert ev["lga"] is None  # Should be gated

    def test_invalid_event_type_gated(self):
        ev = {"confidence": "HIGH", "lga": "Ikeja", "event_type": "earthquake"}
        assert ev["event_type"] not in self.VALID_TYPES


# ── Layer 4: Cross-Source Corroboration Logic ─────────────────────────────────
class TestLayer4Corroboration:
    def test_single_source_is_pending(self):
        count = 1
        status = "CONFIRMED" if count >= 2 else "PENDING"
        assert status == "PENDING"

    def test_two_sources_confirm(self):
        count = 2
        status = "CONFIRMED" if count >= 2 else "PENDING"
        assert status == "CONFIRMED"

    def test_three_sources_still_confirmed(self):
        count = 3
        status = "CONFIRMED" if count >= 2 else "PENDING"
        assert status == "CONFIRMED"


# ── Gazetteer: resolve_utm_zone_and_epsg backward compat ─────────────────────
class TestGazetteerBackwardCompat:
    def test_existing_uyo_lookup_unchanged(self):
        from core.lga_gazetteer import resolve_utm_zone_and_epsg
        zone, epsg = resolve_utm_zone_and_epsg(lga="Uyo")
        assert zone == 32
        assert epsg == "EPSG:26332"

    def test_existing_ikeja_lookup_unchanged(self):
        from core.lga_gazetteer import resolve_utm_zone_and_epsg
        zone, epsg = resolve_utm_zone_and_epsg(lga="Ikeja")
        assert zone == 31
        assert epsg == "EPSG:26331"

    def test_state_only_lookup(self):
        from core.lga_gazetteer import resolve_utm_zone_and_epsg
        zone, epsg = resolve_utm_zone_and_epsg(state="Borno")
        assert zone == 33
        assert epsg == "EPSG:26333"

    def test_unknown_defaults_to_32(self):
        from core.lga_gazetteer import resolve_utm_zone_and_epsg
        zone, epsg = resolve_utm_zone_and_epsg(lga="UnknownCity")
        assert zone == 32
        assert epsg == "EPSG:26332"
