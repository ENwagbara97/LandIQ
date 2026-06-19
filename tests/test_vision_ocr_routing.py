"""
LandIQ — tests/test_vision_ocr_routing.py

Tests for the multi-provider Vision OCR routing layer in coord_extract.py.
These tests are fully offline — they mock all HTTP calls and verify:
  1. _vision_result_to_text() converts JSON correctly to text
  2. ocr_file() routes to the correct provider function
  3. ocr_file() falls back to Tesseract when no provider is set
  4. ocr_file() falls back to Tesseract when the Cloud API raises an exception
  5. run() accepts and passes through vision_provider / vision_api_key
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# The module under test
from agents.coord_extract import (
    _ocr_via_gemini,
    _ocr_via_openai,
    _ocr_via_anthropic,
    _vision_result_to_text,
    ocr_file,
    run,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

SAMPLE_TYPE_A_JSON = {
    "origin": {"easting": 387223.007, "northing": 550821.575},
    "crs_hint": "Minna",
    "datum": "UTM Zone 32",
    "raw_coordinates": [
        [387804.297, 550821.575],
        [387798.928, 550820.648],
        [387791.342, 550834.219],
        [387804.297, 550821.575],   # closed
    ],
    "boundaries": [],
    "confidence": 90,
    "warnings": [],
}

SAMPLE_TYPE_B_JSON = {
    "origin": {"easting": 387223.007, "northing": 552487.540},
    "crs_hint": "Minna",
    "datum": "UTM(ZONE32)",
    "raw_coordinates": [],
    "boundaries": [
        {"bearing": "93° 02'", "distance_m": 9.73, "to_easting": None, "to_northing": None},
        {"bearing": "342° 27'", "distance_m": 11.02, "to_easting": None, "to_northing": None},
    ],
    "confidence": 75,
    "warnings": [],
}

NO_COORDS_JSON = {
    "error": "NO_COORDINATES_FOUND",
    "warnings": ["Could not locate any numeric coordinate data"],
}

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32  # fake PNG header bytes


# ─── _vision_result_to_text() ─────────────────────────────────────────────────

class TestVisionResultToText:
    def test_type_a_plan_produces_easting_northing_lines(self):
        text = _vision_result_to_text(SAMPLE_TYPE_A_JSON)
        assert "UTM Zone 32" in text          # datum line
        assert "387223.007mE" in text         # origin easting
        assert "550821.575mN" in text         # origin northing
        assert "E: 387804.297" in text        # raw coordinate pair
        assert "N: 550821.575" in text

    def test_type_b_plan_produces_bearing_distance_lines(self):
        text = _vision_result_to_text(SAMPLE_TYPE_B_JSON)
        assert "93° 02'" in text
        assert "9.730m" in text
        assert "342° 27'" in text
        assert "11.020m" in text

    def test_empty_json_returns_empty_string(self):
        text = _vision_result_to_text({})
        assert text == ""

    def test_datum_from_crs_hint_fallback(self):
        data = {"crs_hint": "Minna", "raw_coordinates": [], "boundaries": []}
        text = _vision_result_to_text(data)
        assert "Minna" in text


# ─── _ocr_via_gemini() ────────────────────────────────────────────────────────

# Env patch applied to all Gemini tests so the proxy route is taken
_PROXY_ENV = {
    "MODEL_PROXY_URL": "https://mp-staging.kaggle.net/models",
    "MODEL_PROXY_API_KEY": "kaggle:fakekey",
    "GEMINI_API_KEY": "AQ.fakekey",
}

class TestOcrViaGemini:
    def _make_mock_response(self, payload: dict):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]
        }
        return mock_resp

    def test_successful_extraction(self):
        with patch.dict("os.environ", _PROXY_ENV):
            with patch("requests.post", return_value=self._make_mock_response(SAMPLE_TYPE_A_JSON)):
                result = _ocr_via_gemini(FAKE_PNG, "fake-api-key")
        assert "387223.007mE" in result

    def test_no_coordinates_raises_runtime_error(self):
        with patch.dict("os.environ", _PROXY_ENV):
            with patch("requests.post", return_value=self._make_mock_response(NO_COORDS_JSON)):
                with pytest.raises(RuntimeError, match="Gemini Vision"):
                    _ocr_via_gemini(FAKE_PNG, "fake-api-key")

    def test_strips_markdown_fences(self):
        """Model sometimes wraps JSON in ```json ... ``` — should be stripped."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": f"```json\n{json.dumps(SAMPLE_TYPE_B_JSON)}\n```"}]}}]
        }
        with patch.dict("os.environ", _PROXY_ENV):
            with patch("requests.post", return_value=mock_resp):
                result = _ocr_via_gemini(FAKE_PNG, "fake-api-key")
        assert "93° 02'" in result


# ─── _ocr_via_openai() ────────────────────────────────────────────────────────

class TestOcrViaOpenAI:
    def _make_mock_response(self, payload: dict):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": json.dumps(payload)}}]
        }
        return mock_resp

    def test_successful_extraction(self):
        with patch("requests.post", return_value=self._make_mock_response(SAMPLE_TYPE_A_JSON)):
            result = _ocr_via_openai(FAKE_PNG, "fake-api-key")
        assert "387223.007mE" in result

    def test_no_coordinates_raises_runtime_error(self):
        with patch("requests.post", return_value=self._make_mock_response(NO_COORDS_JSON)):
            with pytest.raises(RuntimeError, match="GPT-4o Vision"):
                _ocr_via_openai(FAKE_PNG, "fake-api-key")


# ─── _ocr_via_anthropic() ────────────────────────────────────────────────────

class TestOcrViaAnthropic:
    def _make_mock_response(self, payload: dict):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "content": [{"text": json.dumps(payload)}]
        }
        return mock_resp

    def test_successful_extraction(self):
        with patch("requests.post", return_value=self._make_mock_response(SAMPLE_TYPE_A_JSON)):
            result = _ocr_via_anthropic(FAKE_PNG, "fake-api-key")
        assert "387223.007mE" in result

    def test_no_coordinates_raises_runtime_error(self):
        with patch("requests.post", return_value=self._make_mock_response(NO_COORDS_JSON)):
            with pytest.raises(RuntimeError, match="Claude Vision"):
                _ocr_via_anthropic(FAKE_PNG, "fake-api-key")


# ─── ocr_file() routing ───────────────────────────────────────────────────────

class TestOcrFileRouting:
    """Tests that ocr_file() dispatches to the correct backend."""

    def _gemini_success(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps(SAMPLE_TYPE_A_JSON)}]}}]
        }
        return mock_resp

    def test_routes_to_gemini_when_provider_gemini(self):
        with patch("requests.post", return_value=self._gemini_success()) as mock_post:
            result = ocr_file(FAKE_PNG, "survey.png", vision_provider="gemini", vision_api_key="key123")
        assert mock_post.called
        url_called = mock_post.call_args[0][0]
        assert "gemini" in url_called
        assert "387223.007mE" in result

    def test_routes_to_openai_when_provider_openai(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": json.dumps(SAMPLE_TYPE_A_JSON)}}]
        }
        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = ocr_file(FAKE_PNG, "survey.png", vision_provider="openai", vision_api_key="key123")
        url_called = mock_post.call_args[0][0]
        assert "openai" in url_called

    def test_routes_to_anthropic_when_provider_anthropic(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "content": [{"text": json.dumps(SAMPLE_TYPE_A_JSON)}]
        }
        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = ocr_file(FAKE_PNG, "survey.png", vision_provider="anthropic", vision_api_key="key123")
        url_called = mock_post.call_args[0][0]
        assert "anthropic" in url_called

    def test_falls_back_to_gemini_inline_when_no_provider(self):
        """With no provider set, ocr_file should NOT call requests.post at all, but fall back to inline Gemini."""
        with patch("requests.post") as mock_post:
            with patch("os.getenv", return_value=None):
                with pytest.raises(RuntimeError, match="Image parsing requires a Gemini API key"):
                    ocr_file(FAKE_PNG, "survey.png")
        assert not mock_post.called

    def test_fails_gracefully_on_cloud_failure(self):
        """If the Cloud API raises, we fall back gracefully to the inline Gemini block or fail with RuntimeError."""
        with patch("requests.post", side_effect=Exception("Network error")):
            with patch("os.getenv", return_value=None):
                with pytest.raises(RuntimeError, match="Image parsing requires a Gemini API key"):
                    ocr_file(FAKE_PNG, "survey.png", vision_provider="gemini", vision_api_key="key")

    def test_unknown_provider_fails_gracefully(self):
        """An unrecognised provider string should fall through to inline Gemini fallback, not crash."""
        with patch("requests.post") as mock_post:
            with patch("os.getenv", return_value=None):
                with pytest.raises(RuntimeError, match="Image parsing requires a Gemini API key"):
                    ocr_file(FAKE_PNG, "survey.png", vision_provider="banana", vision_api_key="key")
        assert not mock_post.called


# ─── run() integration ───────────────────────────────────────────────────────

class TestRunVisionParams:
    """Verify that run() accepts and passes through vision params."""

    def test_run_accepts_vision_provider_kwarg(self):
        """run() should not raise a TypeError when vision params are passed."""
        try:
            run(
                raw_input="6.6018N 3.5062E; 6.6025N 3.5075E; 6.6010N 3.5080E; 6.6003N 3.5067E; 6.6018N 3.5062E",
                vision_provider="gemini",
                vision_api_key="fake-key-no-call-expected",
            )
        except TypeError as e:
            pytest.fail(f"run() raised TypeError with vision params: {e}")
        except Exception:
            pass  # Any other error (network, Tesseract, etc.) is acceptable
