"""
LandIQ — core/schemas.py
All Pydantic v2 inter-agent data contracts.

Every agent output passes through one of these schemas before the next
agent receives it. Schema validation is mandatory at every pipeline boundary.
A validation failure produces an MCPErrorResponse — never a raw Python exception.

Canonical reference: LandIQ Unified Operational Plan v2.0 Section 13
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


# =============================================================================
# ENUMERATIONS
# =============================================================================

class CRSName(str, Enum):
    WGS84   = "WGS84"
    MINNA   = "MINNA"
    UTM_31N = "UTM_31N"
    UTM_32N = "UTM_32N"
    UTM_33N = "UTM_33N"
    UNKNOWN = "UNKNOWN"


class FloodRiskLevel(str, Enum):
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"


class TerrainSuitability(str, Enum):
    SUITABLE   = "SUITABLE"
    MARGINAL   = "MARGINAL"
    UNSUITABLE = "UNSUITABLE"


class GrowthPotential(str, Enum):
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"


class TrafficLight(str, Enum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED   = "RED"


class PersonaMode(str, Enum):
    EVERYDAY_BUYER      = "EVERYDAY_BUYER"
    SURVEYOR            = "SURVEYOR"
    REALTOR             = "REALTOR"
    ARCHITECT           = "ARCHITECT"
    INSTITUTIONAL_DEV   = "INSTITUTIONAL_DEV"


class AdapterID(str, Enum):
    OFFLINE_RASTER = "offline_raster"
    NLIR           = "nlir"
    STATE_LIS      = "state_lis"
    WORLD_BANK     = "world_bank"
    MOCK_REGISTRY  = "mock_registry"


class TitleType(str, Enum):
    C_OF_O    = "C_OF_O"
    DEED      = "DEED"
    CUSTOMARY = "CUSTOMARY"
    UNKNOWN   = "UNKNOWN"


class TitleStatus(str, Enum):
    ACTIVE   = "ACTIVE"
    DISPUTED = "DISPUTED"
    REVOKED  = "REVOKED"
    UNKNOWN  = "UNKNOWN"


class TerrainDifficulty(str, Enum):
    FLAT   = "flat"
    GENTLE = "gentle"
    STEEP  = "steep"


class RoadAccessCategory(str, Enum):
    EXCELLENT = "Excellent"
    GOOD      = "Good"
    FAIR      = "Fair"
    POOR      = "Poor"


class PipelineStage(str, Enum):
    INIT          = "INIT"
    COORD_EXTRACT = "COORD_EXTRACT"
    GATE          = "GATE"
    ADAPTER_FETCH = "ADAPTER_FETCH"
    GIS_ANALYSIS  = "GIS_ANALYSIS"
    RISK_ASSESS   = "RISK_ASSESS"
    SUITABILITY   = "SUITABILITY"
    REPORT_GEN    = "REPORT_GEN"
    PDF_RENDER    = "PDF_RENDER"
    COMPLETE      = "COMPLETE"
    ERROR         = "ERROR"


# =============================================================================
# MCP ERROR RESPONSE
# Returned by any agent on failure — never a raw Python exception.
# =============================================================================

class MCPErrorResponse(BaseModel):
    """Structured error returned at any pipeline boundary failure."""
    status      : str = "error"
    error_code  : str                       # e.g. "POLYGON_OPEN", "CRS_UNDETECTABLE"
    instruction : str                       # plain-English correction tip for the caller
    run_id      : Optional[str] = None
    stage       : Optional[PipelineStage] = None
    detail      : Optional[str] = None     # optional technical detail (scrubbed before user delivery)


# =============================================================================
# STEP 1 — COORD EXTRACT OUTPUT
# =============================================================================

class Coordinate(BaseModel):
    lat: float
    lng: float


class CoordExtractOutput(BaseModel):
    """Output contract for the CoordExtract agent (Step 1)."""
    run_id              : str
    coordinates         : list[list[float]]         # [[lat, lng], ...]
    centroid            : Coordinate
    detected_crs        : CRSName
    crs_confidence      : float = Field(ge=0.0, le=100.0)
    metric_analysis_epsg: int = 32631
    is_inside_nigeria   : bool
    computed_area_ha    : float
    state               : Optional[str] = None
    lga                 : Optional[str] = None
    health_check_stats  : Optional[dict] = None
    stated_area_ha      : Optional[float] = None
    area_discrepancy_pct: Optional[float] = None    # null if stated_area_ha not provided
    minna_datum_detected: bool = False
    dms_converted       : bool = False              # true if input was DMS → converted
    flip_tested         : bool = False              # true if auto-flip was attempted
    warnings            : list[str] = []
    crs_dialog_triggers : list[str] = []            # which dialogs (T1–T5) should fire
    discovery_method    : str = "Unknown"           # How the CRS was discovered

    @field_validator("coordinates")
    @classmethod
    def must_have_at_least_three_points(cls, v: list) -> list:
        if len(v) < 3:
            raise ValueError("A valid polygon requires at least 3 coordinate pairs.")
        return v

    @field_validator("computed_area_ha")
    @classmethod
    def area_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Computed parcel area must be greater than zero.")
        return v


# =============================================================================
# ADAPTER LAYER — NORMALISED FEED SCHEMA
# All adapters output this exact schema. No adapter may add or remove fields.
# =============================================================================

class FeedMeta(BaseModel):
    adapter_id      : AdapterID
    source_name     : str
    feed_active     : bool
    fetched_at      : Optional[str] = None          # ISO8601 or null
    data_vintage    : str = "unknown"               # "2024-Q1" | "live" | "unknown"
    confidence_score: float = Field(ge=0.0, le=1.0)
    fallback_used   : bool = False


class TitleData(BaseModel):
    title_exists        : Optional[bool] = None
    title_type          : Optional[TitleType] = None
    title_number        : Optional[str] = None
    title_status        : Optional[TitleStatus] = None
    acquisition_flag    : Optional[bool] = None
    acquisition_detail  : Optional[str] = None
    source_verified     : bool = False              # false until NLIR is live


class ZoningData(BaseModel):
    zoning_class     : Optional[str] = None         # "RESIDENTIAL" | "COMMERCIAL" etc
    permitted_uses   : Optional[list[str]] = None
    restrictions     : Optional[list[str]] = None
    gazette_reference: Optional[str] = None
    source_verified  : bool = False


class EncumbranceData(BaseModel):
    encumbrance_flag  : Optional[bool] = None
    encumbrance_detail: Optional[str] = None
    source_verified   : bool = False


class SupplementalGIS(BaseModel):
    official_plot_number: Optional[str] = None
    survey_plan_ref     : Optional[str] = None
    lga_confirmed       : Optional[str] = None
    state_confirmed     : Optional[str] = None
    source_verified     : bool = False


class NormalisedFeedSchema(BaseModel):
    """Universal output contract for all adapters."""
    feed_meta       : FeedMeta
    title_data      : TitleData
    zoning_data     : ZoningData
    encumbrance_data: EncumbranceData
    supplemental_gis: SupplementalGIS


# =============================================================================
# STEP 2 — GIS ANALYSIS OUTPUT
# =============================================================================

class GISAnalysisOutput(BaseModel):
    """Output contract for the GISAnalysis agent (Step 2)."""
    run_id                  : str
    elevation_m             : Optional[float] = None
    slope_pct               : Optional[float] = None
    terrain_difficulty      : Optional[TerrainDifficulty] = None
    distance_to_river_m     : Optional[float] = None
    river_strahler_order    : Optional[int] = None
    flood_proximity_score   : Optional[float] = Field(None, ge=0.0, le=1.0)
    distance_to_road_m      : Optional[float] = None
    road_access_category    : Optional[RoadAccessCategory] = None
    distance_to_town_m      : Optional[float] = None
    encroachment_flag       : Optional[bool] = None
    encroachment_detail     : Optional[str] = None
    ndwi                    : Optional[float] = None    # null if out of Sentinel zone
    ndvi                    : Optional[float] = None    # null if out of Sentinel zone
    data_confidence         : float = Field(ge=0.0, le=100.0)
    out_of_sentinel_zone    : bool = False
    data_sources_used       : list[str] = []            # adapter IDs consulted
    warnings                : list[str] = []
    drainage_block_warning  : Optional[bool] = None
    outfall_connected       : Optional[bool] = None
    outfall_distance_m      : Optional[float] = None
    outfall_asset_type      : Optional[str] = None
    premium_elevation_profile: Optional[PremiumElevationProfile] = None


# =============================================================================
# STEP 3 — RISK ASSESS OUTPUT
# =============================================================================

class DevelopmentSuitability(BaseModel):
    residential: bool
    commercial : bool
    agricultural: bool
    industrial : bool


class RiskAssessOutput(BaseModel):
    """Output contract for the RiskAssess agent (Step 3). Deterministic Python only."""
    run_id                  : str
    flood_risk              : FloodRiskLevel
    flood_risk_reason       : str                   # plain-English trigger reason
    flood_confidence        : float = Field(ge=0.0, le=100.0)
    terrain_suitability     : TerrainSuitability
    development_suitability : DevelopmentSuitability
    advisory_flags          : list[str] = []
    overall_risk_score      : float = Field(ge=0.0, le=100.0)
    traffic_light           : TrafficLight          # deterministic — Python assigns
    low_data_fields         : list[str] = []        # fields flagged [LOW DATA]
    null_fields             : list[str] = []        # fields returning null (conf < 30)
    drainage_block_warning  : Optional[bool] = None


# =============================================================================
# STEP 4 — SUITABILITY & GROWTH OUTPUT
# =============================================================================

class InfrastructureProximity(BaseModel):
    road_km   : Optional[float] = None
    airport_km: Optional[float] = None
    rail_km   : Optional[float] = None
    port_km   : Optional[float] = None


class SuitabilityGrowthOutput(BaseModel):
    """Output contract for the SuitabilityGrowth agent (Step 4)."""
    run_id                 : str
    land_use_conflicts     : list[str] = []
    urban_expansion_score  : Optional[float] = Field(None, ge=0.0, le=1.0)
    infrastructure_proximity: InfrastructureProximity
    growth_potential       : GrowthPotential
    growth_notes           : Optional[str] = None   # filled by Ollama in ReportGen
    # LGA benchmark comparisons (Layer 3 depth)
    lga_avg_flood_score    : Optional[float] = None
    lga_avg_growth_score   : Optional[float] = None
    lga_report_count       : Optional[int] = None
    parcel_flood_percentile: Optional[float] = None # e.g. 71 → "higher than 71% of parcels"
    parcel_growth_percentile: Optional[float] = None


# =============================================================================
# STEP 5 — FINAL REPORT SCHEMA (v2.0 Authoritative Contract)
# =============================================================================

class ReportMeta(BaseModel):
    report_id  : str
    generated_at: str                               # ISO8601
    version    : str = "2.0"
    disclaimer : str = (
        "This report is advisory only. It does not constitute a legal survey, "
        "title opinion, or professional engineering assessment. Always engage a "
        "SURCON-registered surveyor and a qualified property lawyer before "
        "committing funds to any land transaction."
    )


class LocationContext(BaseModel):
    lga       : Optional[str] = None
    state     : Optional[str] = None
    community : Optional[str] = None


class ParcelGeometry(BaseModel):
    centroid        : Coordinate
    coordinates     : list[list[float]]
    computed_area_ha: float
    stated_area_ha  : Optional[float] = None
    location_context: LocationContext
    health_check_stats: Optional[dict] = None


class CoordinateValidation(BaseModel):
    detected_crs       : str
    crs_confidence     : float
    is_inside_nigeria  : bool
    area_discrepancy_pct: Optional[float] = None
    warnings           : list[str] = []


class TerrainAssessment(BaseModel):
    elevation_m      : Optional[float] = None
    steepness_of_land: Optional[float] = None       # user-facing label (= slope_pct)
    terrain_difficulty: Optional[str] = None
    suitability      : Optional[str] = None
    drainage_block_warning: Optional[bool] = None
    outfall_connected: Optional[bool] = None
    outfall_distance_m: Optional[float] = None
    outfall_asset_type: Optional[str] = None


class ProfilePoint(BaseModel):
    distance_m: float
    elevation_m: Optional[float] = None
    label: Optional[str] = None


class PremiumElevationProfile(BaseModel):
    user_demanded_export: bool = False
    internal_profile_points: list[ProfilePoint] = []
    outfall_profile_points: list[ProfilePoint] = []


class FloodRiskMetrics(BaseModel):
    level                  : FloodRiskLevel
    score                  : Optional[float] = None
    reason_in_plain_english: str
    distance_to_nearest_river: Optional[float] = None
    water_presence_index   : Optional[float] = None  # user-facing label (= ndwi)


class AccessibilityDevelopment(BaseModel):
    distance_to_road_m: Optional[float] = None
    road_category     : Optional[str] = None
    suitability_matrix: DevelopmentSuitability


class EncroachmentRecord(BaseModel):
    flag                    : Optional[bool] = None
    detail                  : Optional[str] = None
    satellite_epoch_comparison: Optional[str] = None


class GrowthPotentialRecord(BaseModel):
    level                : GrowthPotential
    urban_expansion_score: Optional[float] = None
    infrastructure_proximity: InfrastructureProximity
    summary_notes        : Optional[str] = None


class TitleRecord(BaseModel):
    """Registry verification status — source_verified = false until NLIR live."""
    title_status    : str = "Not verified via live registry."
    title_type      : Optional[str] = None
    acquisition_flag: Optional[bool] = None
    source_verified : bool = False
    advisory_text   : str = (
        "Title Status: Not verified via live registry. "
        "Advisory only — confirm at your State Land Registry "
        "or Surveyor-General's office before transacting."
    )


class ReportSummary(BaseModel):
    traffic_light    : TrafficLight
    executive_summary: str                          # max 3 sentences, Ollama-written
    ai_recommendation: str                          # ends with mandatory disclaimer
    overall_risk_score: float = Field(ge=0.0, le=100.0)


class ReportSchema(BaseModel):
    """
    v2.0 Authoritative Report Contract.
    All agents fill fields — they do not invent new fields.
    WeasyPrint reads this schema directly for PDF rendering.
    """
    meta                   : ReportMeta
    parcel_geometry        : ParcelGeometry
    coordinate_validation  : CoordinateValidation
    terrain_assessment     : TerrainAssessment
    flood_risk_metrics     : FloodRiskMetrics
    accessibility_development: AccessibilityDevelopment
    encroachment           : EncroachmentRecord
    growth_potential       : GrowthPotentialRecord
    title_record           : TitleRecord
    advisory_flags         : list[str] = []
    summary                : ReportSummary
    premium_elevation_profile: Optional[PremiumElevationProfile] = None
    # Pipeline metadata (not rendered to user)
    pipeline_version       : str = "2.0"
    persona_mode           : PersonaMode = PersonaMode.EVERYDAY_BUYER
    ollama_model_used      : Optional[str] = None
    llm_timeout_fired      : bool = False
    feed_context           : Optional[dict[str, Any]] = None  # NormalisedFeedSchema


# =============================================================================
# COMPARISON DELTA SCHEMA
# =============================================================================

class DeltaField(BaseModel):
    field_name       : str
    value_a          : Any                          # earlier report
    value_b          : Any                          # later report
    direction        : str                          # "improved" | "worsened" | "unchanged"
    plain_english    : str                          # human-readable change description


class ComparisonDelta(BaseModel):
    comparison_id    : str
    report_id_a      : str
    report_id_b      : str
    generated_at_a   : str
    generated_at_b   : str
    parcel_match     : bool
    fields           : list[DeltaField]
    plain_english_delta: Optional[str] = None       # Ollama summary of overall change


# =============================================================================
# SESSION STATE
# =============================================================================

class SessionState(BaseModel):
    run_id          : str
    user_id         : str
    created_at      : str
    confirmed       : bool = False
    confirmed_at    : Optional[str] = None
    status          : str = "pending"
    persona_mode    : PersonaMode = PersonaMode.EVERYDAY_BUYER
    pipeline_stage  : PipelineStage = PipelineStage.INIT
    coord_extract   : Optional[CoordExtractOutput] = None
    feed_context    : Optional[NormalisedFeedSchema] = None
    snapshot_path   : Optional[str] = None
    error_detail    : Optional[str] = None


# =============================================================================
# CADASTRAL ENGINE SCHEMAS
# Output contract for the standalone /api/cadastral computation engine.
# No pipeline session required — pure deterministic math output.
# =============================================================================

class AreaMatchStatus(str, Enum):
    GREEN = "GREEN"   # Delta ≤ 0.005 ha  — Optimal
    AMBER = "AMBER"   # Delta ≤ 0.050 ha  — Review Required
    RED   = "RED"     # Delta  > 0.050 ha — Critical Error


class ComputationTrack(str, Enum):
    TABULAR      = "TABULAR"        # Track A: explicit Easting/Northing columns
    COGO_TRAVERSE = "COGO_TRAVERSE" # Track B: anchor + bearing-distance sequence


class ExtractionMeta(BaseModel):
    source_file: str
    extraction_method: str
    plan_type: str
    datum_detected: str
    datum_epsg: Optional[int] = None
    ocr_engine: str
    pre_processing: list[str] = []
    rotation_corrected: float = 0.0
    multi_plot_detected: bool = False
    plot_index: Optional[int] = None


class PlanDetails(BaseModel):
    owner_name: Optional[str] = None
    plan_number: Optional[str] = None
    location: Optional[str] = None
    lga: Optional[str] = None
    state: Optional[str] = None
    surveyor_name: Optional[str] = None
    certification_date: Optional[str] = None
    stated_area_sqm: Optional[float] = None
    datum: Optional[str] = None
    scale: Optional[str] = None


class TraverseLeg(BaseModel):
    from_beacon: str
    to_beacon: str
    bearing_dms: str
    bearing_dd: float
    distance_m: float
    ocr_confidence: int = 100


class TraverseData(BaseModel):
    starting_beacon: str
    starting_easting: float
    starting_northing: float
    legs: list[TraverseLeg] = []
    closure_error_m: float = 0.0
    adjustment_method: str = "none"


class CadastralStationEntry(BaseModel):
    station_id: str
    easting_utm: float
    northing_utm: float
    latitude_wgs84: float
    longitude_wgs84: float
    source: str
    ocr_confidence: int = 100


class PolygonData(BaseModel):
    wgs84_coordinates: list[list[float]] = []
    utm_coordinates: list[list[float]] = []
    computed_area_sqm: float
    computed_area_ha: float
    stated_area_sqm: Optional[float] = None
    area_discrepancy_pct: Optional[float] = None
    is_closed: bool
    is_valid: bool
    has_self_intersection: bool
    vertex_count: int
    closure_error_m: float = 0.0
    crs_input: str
    crs_output: str = "EPSG:4326"


class ExtractionConfidence(BaseModel):
    owner_name: int = 100
    plan_number: int = 100
    coordinates_overall: int = 100
    datum: int = 100
    area: int = 100
    overall: int = 100


class CadastralResult(BaseModel):
    """Top-level output of the new Cadastral Computation Engine."""
    extraction_meta: ExtractionMeta
    plan_details: PlanDetails
    traverse_data: Optional[TraverseData] = None
    beacons: list[CadastralStationEntry] = []
    polygon: Optional[PolygonData] = None
    extraction_confidence: ExtractionConfidence

