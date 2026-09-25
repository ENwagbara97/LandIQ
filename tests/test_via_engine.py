"""
LandIQ — tests/test_via_engine.py
Comprehensive unit and integration tests for the VIA (Visual Site Scan) module.
"""

import io
import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from agents.via_engine import (
    FLAG_CONFLICT_WITH_MATH,
    FLAG_GULLY_EROSION,
    FLAG_INFORMAL_SETTLEMENT,
    FLAG_LOW_CONFIDENCE,
    FLAG_POOR_ROAD,
    FLAG_WATER_FEATURE,
    VIACallAResult,
    _resize_snapshot,
    _check_conflict_guardrail,
    _detect_advisory_flags,
    run_via,
)
from core.schemas import (
    FloodRiskLevel,
    PersonaMode,
    ReportSchema,
    TrafficLight,
    ReportMeta,
    ReportSummary,
    ParcelGeometry,
    CoordinateValidation,
    TerrainAssessment,
    FloodRiskMetrics,
    AccessibilityDevelopment,
    EncroachmentRecord,
    GrowthPotentialRecord,
    TitleRecord,
    Coordinate,
    LocationContext,
    DevelopmentSuitability,
    InfrastructureProximity,
    VIAResult,
)

from main import app


# ─── Mock Data Helpers ────────────────────────────────────────────────────────

def make_dummy_report(
    flood_level: FloodRiskLevel = FloodRiskLevel.LOW,
    traffic_light: TrafficLight = TrafficLight.GREEN,
) -> ReportSchema:
    return ReportSchema(
        meta=ReportMeta(report_id="test-report-123", version="2.0", generated_at="2026-07-13T12:00:00Z"),
        parcel_geometry=ParcelGeometry(
            coordinates=[[6.5, 3.3], [6.6, 3.3], [6.6, 3.4], [6.5, 3.4], [6.5, 3.3]],
            centroid=Coordinate(lat=6.55, lng=3.35),
            computed_area_ha=1.5,
            location_context=LocationContext(lga="Ikorodu", state="Lagos"),
        ),
        coordinate_validation=CoordinateValidation(
            detected_crs="UTM_32N",
            crs_confidence=95.0,
            is_inside_nigeria=True,
        ),
        terrain_assessment=TerrainAssessment(suitability="SUITABLE", steepness_of_land=1.5),
        flood_risk_metrics=FloodRiskMetrics(
            level=flood_level,
            water_presence_index=0.1,
            distance_to_nearest_river=500.0,
            reason_in_plain_english="Elevated and dry.",
        ),
        accessibility_development=AccessibilityDevelopment(
            distance_to_road_m=50.0,
            suitability_matrix=DevelopmentSuitability(
                residential=True,
                commercial=True,
                agricultural=True,
                industrial=False,
            ),
        ),
        encroachment=EncroachmentRecord(flag=False),
        growth_potential=GrowthPotentialRecord(
            level="HIGH",
            infrastructure_proximity=InfrastructureProximity(road_km=0.05),
        ),
        title_record=TitleRecord(title_status="Not verified", source_verified=False),
        summary=ReportSummary(
            traffic_light=traffic_light,
            executive_summary="Summary text.",
            ai_recommendation="Rec text.",
            overall_risk_score=20.0,
        ),
        persona_mode=PersonaMode.EVERYDAY_BUYER,
    )



def make_dummy_call_a(
    overall_confidence: str = "high",
    flooding_evidence: bool = False,
    erosion_visible: bool = False,
    informal_settlement: bool = False,
    road_visible: bool = True,
    water_visible: bool = False,
) -> VIACallAResult:
    raw_json = {
        "image_quality": {
            "satellite_clarity": "clear",
            "estimated_image_age": "recent (<2yr)",
            "cloud_cover_pct": 0,
        },
        "parcel_interior": {
            "current_use_observed": "vacant",
            "structures_visible_inside": False,
            "structure_count_estimate": 0,
            "vegetation_cover": "sparse",
            "surface_condition": "dry and stable",
        },
        "immediate_surroundings_250m": {
            "road_access": {
                "road_visible": road_visible,
                "road_type": "paved" if road_visible else "none",
                "road_proximity": "adjacent" if road_visible else "none visible",
                "named_road_if_visible": None,
            },
            "water_features": {
                "water_body_visible": water_visible,
                "type": "creek" if water_visible else "none",
                "proximity_to_parcel": "within 50m" if water_visible else "none",
                "direction_from_parcel": "north" if water_visible else None,
            },
            "settlement_pattern": {
                "settlement_type": "informal settlement" if informal_settlement else "formal residential",
                "density": "medium",
                "commercial_activity_visible": False,
            },
            "risk_observations": {
                "erosion_visible": erosion_visible,
                "erosion_severity": "moderate" if erosion_visible else None,
                "marshy_terrain_visible": False,
                "industrial_activity_visible": False,
                "industrial_type": None,
                "encroachment_risk_visual": False,
                "encroachment_detail": None,
                "flooding_evidence_visible": flooding_evidence,
                "flooding_evidence_detail": "Wet patch" if flooding_evidence else None,
            },
            "development_context": {
                "area_development_trend": "growing",
                "infrastructure_quality_visual": "fair",
                "notable_landmarks_visible": [],
            },
        },
        "confidence": {
            "overall_confidence": overall_confidence,
            "low_confidence_reasons": [],
        },
    }
    return VIACallAResult.model_validate(raw_json)


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_resize_snapshot_reduces_size(tmp_path):
    """Test PIL resize logic maintains Lanczos constraints and outputs valid bytes."""
    # Create dummy 1200x800 test image
    img = Image.new("RGB", (1200, 800), color="blue")
    img_path = tmp_path / "test_snapshot.png"
    img.save(img_path)

    resized_bytes = _resize_snapshot(str(img_path))
    assert isinstance(resized_bytes, bytes)

    # Read back image constraints
    resized_img = Image.open(io.BytesIO(resized_bytes))
    w, h = resized_img.size
    assert w <= 800
    assert h <= 533


def test_guardrail_conflict_detected():
    """LOW math flood risk but high-confidence visual evidence of flooding -> conflict True."""
    report = make_dummy_report(flood_level=FloodRiskLevel.LOW)
    call_a = make_dummy_call_a(overall_confidence="high", flooding_evidence=True)
    assert _check_conflict_guardrail(call_a, report) is True


def test_guardrail_no_conflict_medium():
    """MEDIUM math flood risk + visual evidence of flooding -> conflict False (corroborates math)."""
    report = make_dummy_report(flood_level=FloodRiskLevel.MEDIUM)
    call_a = make_dummy_call_a(overall_confidence="high", flooding_evidence=True)
    assert _check_conflict_guardrail(call_a, report) is False


def test_flag_low_confidence_suppresses_others():
    """Low overall confidence must suppress all detailed observations, returning only low-confidence flag."""
    report = make_dummy_report()
    call_a = make_dummy_call_a(
        overall_confidence="low",
        erosion_visible=True,
        informal_settlement=True,
    )
    flags = _detect_advisory_flags(call_a, report, conflict=False)
    assert len(flags) == 1
    assert flags[0] == FLAG_LOW_CONFIDENCE


def test_flag_water_feature():
    """Water feature visible within 250m -> adds water feature flag."""
    report = make_dummy_report()
    call_a = make_dummy_call_a(water_visible=True)
    flags = _detect_advisory_flags(call_a, report, conflict=False)
    assert any(FLAG_WATER_FEATURE in f for f in flags)


def test_flag_gully_erosion():
    """Erosion visible -> adds gully erosion flag."""
    report = make_dummy_report()
    call_a = make_dummy_call_a(erosion_visible=True)
    flags = _detect_advisory_flags(call_a, report, conflict=False)
    assert any(FLAG_GULLY_EROSION in f for f in flags)


def test_flag_informal_settlement():
    """Informal settlement pattern observed -> adds informal settlement flag."""
    report = make_dummy_report()
    call_a = make_dummy_call_a(informal_settlement=True)
    flags = _detect_advisory_flags(call_a, report, conflict=False)
    assert any(FLAG_INFORMAL_SETTLEMENT in f for f in flags)


@patch("agents.via_engine._gemini_vision_call")
@patch("agents.via_engine._gemini_text_call")
def test_run_via_flow(mock_text_call, mock_vision_call, tmp_path):
    """Test full run_via pipeline completes successfully and returns VIAResult."""
    # Create test image
    img = Image.new("RGB", (1200, 800), color="teal")
    img_path = tmp_path / "snap.png"
    img.save(img_path)

    # Mock Vision Call A (returns JSON string)
    mock_a_json = {
        "image_quality": {"satellite_clarity": "clear", "estimated_image_age": "recent (<2yr)", "cloud_cover_pct": 0},
        "parcel_interior": {"current_use_observed": "vacant", "structures_visible_inside": False, "structure_count_estimate": 0, "vegetation_cover": "sparse", "surface_condition": "dry and stable"},
        "immediate_surroundings_250m": {
            "road_access": {"road_visible": True, "road_type": "paved", "road_proximity": "adjacent", "named_road_if_visible": None},
            "water_features": {"water_body_visible": False, "type": "none", "proximity_to_parcel": "none", "direction_from_parcel": None},
            "settlement_pattern": {"settlement_type": "formal residential", "density": "medium", "commercial_activity_visible": False},
            "risk_observations": {"erosion_visible": False, "erosion_severity": None, "marshy_terrain_visible": False, "industrial_activity_visible": False, "industrial_type": None, "encroachment_risk_visual": False, "encroachment_detail": None, "flooding_evidence_visible": False, "flooding_evidence_detail": None},
            "development_context": {"area_development_trend": "growing", "infrastructure_quality_visual": "fair", "notable_landmarks_visible": []}
        },
        "confidence": {"overall_confidence": "high", "low_confidence_reasons": []}
    }
    mock_vision_call.return_value = (json.dumps(mock_a_json), {"promptTokenCount": 100, "candidatesTokenCount": 200})

    # Mock Text Call B (returns plain text summary)
    mock_text_call.return_value = ("Visual scan text summary.", {"promptTokenCount": 50, "candidatesTokenCount": 100})

    report = make_dummy_report()
    result = run_via(
        report_id="test-id",
        snapshot_path=str(img_path),
        report=report,
        api_key="AIzaSyDummyKey123",
    )

    assert result.status.value == "complete"
    assert result.call_b_text == "Visual scan text summary."
    assert result.usage_meta.input_tokens_a == 100
    assert result.usage_meta.output_tokens_b == 100
    assert len(result.advisory_flags) == 0  # no risks or poor road access


def test_run_via_no_snapshot():
    """No snapshot path -> returns status ERROR."""
    report = make_dummy_report()
    result = run_via(
        report_id="test-id",
        snapshot_path="non_existent_file.png",
        report=report,
        api_key="dummy_key",
    )
    assert result.status.value == "error"
    assert "file not found" in result.error_detail.lower()


@patch("agents.via_engine._gemini_vision_call")
def test_run_via_timeout(mock_vision_call, tmp_path):
    """If call raises TimeoutError, pipeline catches it and returns timeout status."""
    img = Image.new("RGB", (1200, 800), color="red")
    img_path = tmp_path / "snap2.png"
    img.save(img_path)

    mock_vision_call.side_effect = TimeoutError("Gemini timed out.")

    report = make_dummy_report()
    result = run_via(
        report_id="test-id-2",
        snapshot_path=str(img_path),
        report=report,
        api_key="dummy_key",
    )
    assert result.status.value == "timeout"


# ─── FastAPI Endpoints Tests ──────────────────────────────────────────────────

def test_via_endpoints_flow(tmp_path):
    """Test POST /api/via/trigger and GET /api/via/status/{report_id} with SQLite DB."""
    import sqlite3
    import core.history_manager as history_manager

    # Setup database file
    db_file = tmp_path / "test_landiq.db"
    if db_file.exists():
        db_file.unlink()

    # Re-run migrations on test db
    from db.migrate import run_migrations
    run_migrations(db_file)

    # Patch connection DB path in history_manager
    with patch("core.history_manager.DB_PATH", db_file), \
         patch("main.load_dotenv"), \
         patch("agents.via_engine.os.getenv", return_value="AIzaSyDummyKey"):

        # Insert a dummy report into reports table
        report = make_dummy_report()
        snap_file = tmp_path / "snap3.png"
        Image.new("RGB", (1200, 800), color="green").save(snap_file)

        # Mock the run_via task execution
        mock_result = VIAResult(
            status="complete",
            call_b_text="Test description text.",
            completed_at="2026-07-13T12:00:00Z",
            advisory_flags=["VIA_WATER_FEATURE_OBSERVED: Nearby creek."],
            call_a=make_dummy_call_a(water_visible=True),
        )

        # Insert a dummy session row before saving the report to satisfy foreign key constraints
        conn = sqlite3.connect(str(db_file))
        conn.execute(
            "INSERT INTO sessions (run_id, user_id, created_at, status) VALUES (?, ?, datetime('now'), 'completed')",
            (report.meta.report_id, "test-user")
        )
        conn.commit()
        conn.close()

        history_manager.save_report(
            report=report,

            snapshot_path=str(snap_file),
            snapshot_thumb_path=None,
            total_generation_ms=1000,
            user_id="test-user",
        )

        client = TestClient(app)

        # 1. Poll status initially (should be pending)
        status_resp = client.get(f"/api/via/status/{report.meta.report_id}")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "pending"

        # 2. Trigger VIA background task (mock the background worker to execute synchronously)
        with patch("agents.via_engine.run_via", return_value=mock_result):
            # Call background task directly to avoid async timing issues in test
            from main import _run_via_background_task
            _run_via_background_task(report.meta.report_id)


        # 3. Poll status again (should be complete with via_result populated)
        status_resp = client.get(f"/api/via/status/{report.meta.report_id}")
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["status"] == "complete"
        assert data["via_result"]["call_b_text"] == "Test description text."
        assert len(data["via_result"]["advisory_flags"]) == 1

        # 4. Trigger again (should be idempotent and return already_complete)
        trigger_resp = client.post(
            "/api/via/trigger",
            json={"report_id": report.meta.report_id},
        )
        assert trigger_resp.status_code == 200
        assert trigger_resp.json()["status"] == "already_complete"
