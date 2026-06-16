"""
LandIQ — core/adapters.py
External Registry Feed Adapter Layer

All adapters output the same NormalisedFeedSchema.
The pipeline never knows which adapter fired.
AdapterLayer.fetch() reads feed_flags.json on every call (hot-reloadable).

Adapter priority (MVP):
  1. OfflineRasterAdapter   — always active, never fails
  2. MockRegistryAdapter    — active for testing (MOCK_REGISTRY_ACTIVE=true)
  3. StateLISAdapter        — dormant stub (STATE_LIS_ACTIVE=false)
  4. NLIRAdapter            — dormant stub (NLIR_FEED_ACTIVE=false)

Failure rules (all live adapters):
  - Timeout > FEED_TIMEOUT_SECONDS  → fallback, log [FEED_TIMEOUT]
  - HTTP 4xx / 5xx                  → fallback, log error_code
  - Schema mismatch                 → reject payload, fallback, log [SCHEMA_MISMATCH]
  - All fields null                 → source_verified=false on every field
  - Report is NEVER blocked by a missing feed
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from pathlib import Path
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from core.schemas import (
    AdapterID,
    EncumbranceData,
    FeedMeta,
    NormalisedFeedSchema,
    SupplementalGIS,
    TitleData,
    TitleStatus,
    TitleType,
    ZoningData,
)

logger = logging.getLogger("landiq.adapters")

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT_DIR    = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config" / "feed_flags.json"
STATE_LIS_CONFIG_PATH = ROOT_DIR / "config" / "state_lis_config.json"
MOCK_REGISTRY_DIR = ROOT_DIR / "config" / "mock_registry"


def _load_flags() -> dict:
    """Reload feed flags from disk on every call (hot-reload — no restart needed)."""
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_state_lis_config() -> dict:
    try:
        return json.loads(STATE_LIS_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"states": []}


# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================

class FeedTimeoutError(Exception):
    pass

class FeedHTTPError(Exception):
    def __init__(self, status_code: int, detail: str = ""):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")

class FeedSchemaMismatchError(Exception):
    pass


# =============================================================================
# NULL (EMPTY) FEED — returned when all live adapters fail
# =============================================================================

def _null_feed(adapter_id: AdapterID = AdapterID.OFFLINE_RASTER) -> NormalisedFeedSchema:
    """Return a fully-null NormalisedFeedSchema with source_verified=false everywhere."""
    return NormalisedFeedSchema(
        feed_meta=FeedMeta(
            adapter_id=adapter_id,
            source_name="No registry data available",
            feed_active=False,
            confidence_score=0.0,
            fallback_used=True,
        ),
        title_data=TitleData(source_verified=False),
        zoning_data=ZoningData(source_verified=False),
        encumbrance_data=EncumbranceData(source_verified=False),
        supplemental_gis=SupplementalGIS(source_verified=False),
    )


# =============================================================================
# HAVERSINE DISTANCE (for centroid matching)
# =============================================================================

def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return distance in metres between two WGS84 lat/lng points."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# =============================================================================
# ADAPTER 1 — OfflineRasterAdapter (always active)
# =============================================================================

class OfflineRasterAdapter:
    """
    Reads all GIS data from local raster/vector files.
    Always active. Never fails unless setup.py has not been run.
    Provides non-title fields only (elevation, rivers, etc. are in GISAnalysis).
    This adapter provides the structural metadata frame for the pipeline.
    """
    adapter_id = AdapterID.OFFLINE_RASTER

    def fetch(self, centroid: dict, bbox: dict) -> NormalisedFeedSchema:
        return NormalisedFeedSchema(
            feed_meta=FeedMeta(
                adapter_id=self.adapter_id,
                source_name="Local Raster + Vector Data (SRTM, HydroSHEDS, OSM)",
                feed_active=True,
                fetched_at=_iso_now(),
                data_vintage="2020–2024",
                confidence_score=0.85,
                fallback_used=False,
            ),
            title_data=TitleData(source_verified=False),
            zoning_data=ZoningData(source_verified=False),
            encumbrance_data=EncumbranceData(source_verified=False),
            supplemental_gis=SupplementalGIS(source_verified=False),
        )


# =============================================================================
# ADAPTER 2 — MockRegistryAdapter (active when MOCK_REGISTRY_ACTIVE=true)
# =============================================================================

class MockRegistryAdapter:
    """
    Reads from local JSON files in /config/mock_registry/.
    Matches by centroid proximity (≤100m).
    Controlled by MOCK_REGISTRY_ACTIVE flag + MOCK_SCENARIO override.

    Scenarios (set via MOCK_SCENARIO in feed_flags.json):
      clean_title   → Active C of O, no disputes
      disputed      → DISPUTED title + encumbrance
      revoked       → REVOKED + government acquisition
      govt_acquisition → acquisition flag set
      timeout       → sleeps 6s to trigger FeedTimeoutError
      http_error    → raises FeedHTTPError(500)
      schema_mismatch → raises FeedSchemaMismatchError
      partial_data  → returns title_type only
      no_record     → returns null feed
    """
    adapter_id = AdapterID.MOCK_REGISTRY

    def fetch(self, centroid: dict, bbox: dict) -> NormalisedFeedSchema:
        flags = _load_flags()
        scenario = flags.get("MOCK_SCENARIO", "clean_title")
        timeout_s = flags.get("FEED_TIMEOUT_SECONDS", 5)

        # Simulate failure scenarios
        if scenario == "timeout":
            logger.info("[mock_registry] Simulating timeout...")
            time.sleep(timeout_s + 1)
            raise FeedTimeoutError("Mock timeout scenario")

        if scenario == "http_error":
            raise FeedHTTPError(500, "Mock HTTP 500 scenario")

        if scenario == "schema_mismatch":
            raise FeedSchemaMismatchError("Mock schema mismatch scenario")

        if scenario == "no_record":
            return _null_feed(self.adapter_id)

        # Load all mock registry JSON files
        all_records = self._load_all_records()

        # Match by centroid proximity
        lat, lng = centroid["lat"], centroid["lng"]
        match = None
        for record in all_records:
            rec_lat = record["centroid"]["lat"]
            rec_lng = record["centroid"]["lng"]
            radius = record.get("match_radius_m", 100)
            dist = _haversine_m(lat, lng, rec_lat, rec_lng)
            if dist <= radius:
                match = record
                break

        if match is None:
            logger.info(f"[mock_registry] No match found within radius for ({lat:.5f}, {lng:.5f})")
            return _null_feed(self.adapter_id)

        # Handle partial data scenario
        if scenario == "partial_data":
            return NormalisedFeedSchema(
                feed_meta=FeedMeta(
                    adapter_id=self.adapter_id,
                    source_name="Mock Registry (partial data)",
                    feed_active=True,
                    fetched_at=_iso_now(),
                    data_vintage="2024",
                    confidence_score=0.35,
                    fallback_used=True,
                ),
                title_data=TitleData(
                    title_type=TitleType(match.get("title_type", "UNKNOWN")),
                    source_verified=False,
                ),
                zoning_data=ZoningData(source_verified=False),
                encumbrance_data=EncumbranceData(source_verified=False),
                supplemental_gis=SupplementalGIS(source_verified=False),
            )

        # Full record
        return self._record_to_schema(match)

    def _load_all_records(self) -> list[dict]:
        records = []
        for json_file in MOCK_REGISTRY_DIR.glob("*.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    records.extend(data)
                elif isinstance(data, dict):
                    records.append(data)
            except Exception as exc:
                logger.warning(f"[mock_registry] Failed to load {json_file.name}: {exc}")
        return records

    def _record_to_schema(self, record: dict) -> NormalisedFeedSchema:
        """Convert a mock registry JSON record to NormalisedFeedSchema."""
        def _safe_enum(cls, val, default=None):
            if val is None:
                return default
            try:
                return cls(val)
            except ValueError:
                return default

        return NormalisedFeedSchema(
            feed_meta=FeedMeta(
                adapter_id=self.adapter_id,
                source_name="Mock Registry (local JSON)",
                feed_active=True,
                fetched_at=_iso_now(),
                data_vintage="2024",
                confidence_score=0.70,
                fallback_used=False,
            ),
            title_data=TitleData(
                title_exists=record.get("title_type") is not None,
                title_type=_safe_enum(TitleType, record.get("title_type")),
                title_number=record.get("id"),
                title_status=_safe_enum(TitleStatus, record.get("title_status")),
                acquisition_flag=record.get("acquisition_flag"),
                acquisition_detail=record.get("acquisition_detail"),
                source_verified=True,  # Mock data is "verified" for testing
            ),
            zoning_data=ZoningData(
                zoning_class=record.get("zoning_class"),
                permitted_uses=record.get("permitted_uses"),
                restrictions=record.get("restrictions"),
                gazette_reference=record.get("gazette_reference"),
                source_verified=True,
            ),
            encumbrance_data=EncumbranceData(
                encumbrance_flag=record.get("encumbrance_flag"),
                encumbrance_detail=record.get("encumbrance_detail"),
                source_verified=True,
            ),
            supplemental_gis=SupplementalGIS(
                official_plot_number=record.get("official_plot_number"),
                survey_plan_ref=record.get("survey_plan_ref"),
                lga_confirmed=record.get("lga_confirmed"),
                state_confirmed=record.get("state_confirmed"),
                source_verified=True,
            ),
        )


# =============================================================================
# ADAPTER 3 — NLIRAdapter (dormant stub)
# =============================================================================

class NLIRAdapter:
    """
    National Land Information Repository feed adapter.
    DORMANT — activate when NLIR_FEED_ACTIVE=true in feed_flags.json.

    Endpoint: https://nlir.gov.ng/api/v1/parcel (placeholder)
    Auth: Bearer token from NLIR_API_TOKEN environment variable.
    """
    adapter_id = AdapterID.NLIR
    BASE_URL   = "https://nlir.gov.ng/api/v1"

    def fetch(self, centroid: dict, bbox: dict, timeout_s: int = 5) -> NormalisedFeedSchema:
        token = os.environ.get("NLIR_API_TOKEN", "")
        if not token:
            logger.warning("[nlir] NLIR_API_TOKEN not set — cannot authenticate")
            raise FeedHTTPError(401, "No NLIR API token configured")

        params = {
            "lat": centroid["lat"],
            "lng": centroid["lng"],
            "format": "json",
        }
        try:
            with httpx.Client(timeout=timeout_s) as client:
                resp = client.get(
                    f"{self.BASE_URL}/parcel",
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                )
            if resp.status_code == 404:
                return _null_feed(self.adapter_id)
            if resp.status_code != 200:
                raise FeedHTTPError(resp.status_code, resp.text[:200])

            data = resp.json()
            return self._map_response(data)

        except httpx.TimeoutException:
            raise FeedTimeoutError(f"NLIR timed out after {timeout_s}s")
        except (KeyError, ValueError) as exc:
            raise FeedSchemaMismatchError(f"NLIR response schema mismatch: {exc}")

    def _map_response(self, data: dict) -> NormalisedFeedSchema:
        """Map NLIR JSON response → NormalisedFeedSchema (schema TBD — placeholder mapping)."""
        return NormalisedFeedSchema(
            feed_meta=FeedMeta(
                adapter_id=self.adapter_id,
                source_name="National Land Information Repository (NLIR)",
                feed_active=True,
                fetched_at=_iso_now(),
                data_vintage="live",
                confidence_score=0.90,
                fallback_used=False,
            ),
            title_data=TitleData(
                title_exists=data.get("title_exists"),
                title_type=_safe_title_type(data.get("title_type")),
                title_number=data.get("file_number"),
                title_status=_safe_title_status(data.get("status")),
                acquisition_flag=data.get("govt_acquisition"),
                acquisition_detail=data.get("acquisition_details"),
                source_verified=True,
            ),
            zoning_data=ZoningData(
                zoning_class=data.get("zoning"),
                permitted_uses=data.get("permitted_uses"),
                restrictions=data.get("restrictions"),
                gazette_reference=data.get("gazette_ref"),
                source_verified=True,
            ),
            encumbrance_data=EncumbranceData(
                encumbrance_flag=data.get("encumbrance"),
                encumbrance_detail=data.get("encumbrance_detail"),
                source_verified=True,
            ),
            supplemental_gis=SupplementalGIS(
                official_plot_number=data.get("plot_number"),
                survey_plan_ref=data.get("survey_plan"),
                lga_confirmed=data.get("lga"),
                state_confirmed=data.get("state"),
                source_verified=True,
            ),
        )


# =============================================================================
# ADAPTER 4 — StateLISAdapter (dormant stub)
# =============================================================================

class StateLISAdapter:
    """
    State Land Information System adapter.
    DORMANT — activate when STATE_LIS_ACTIVE=true.
    Endpoint and auth per state read from state_lis_config.json.
    """
    adapter_id = AdapterID.STATE_LIS

    def fetch(
        self, centroid: dict, bbox: dict, state: str | None, timeout_s: int = 5
    ) -> NormalisedFeedSchema:
        config = _load_state_lis_config()
        state_cfg = next(
            (s for s in config.get("states", [])
             if s.get("name", "").lower() == (state or "").lower()),
            None,
        )
        if not state_cfg or not state_cfg.get("active", False):
            return _null_feed(self.adapter_id)

        token = os.environ.get(state_cfg.get("token_env_var", ""), "")
        if not token:
            raise FeedHTTPError(401, f"No token for {state_cfg['name']} LIS")

        params = {"lat": centroid["lat"], "lng": centroid["lng"], "format": "json"}
        try:
            with httpx.Client(timeout=timeout_s) as client:
                resp = client.get(
                    state_cfg["endpoint"],
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                )
            if resp.status_code == 404:
                return _null_feed(self.adapter_id)
            if resp.status_code != 200:
                raise FeedHTTPError(resp.status_code, resp.text[:200])

            data = resp.json()
            # Map using same logic as NLIR (schema v1.0 assumed compatible)
            return NLIRAdapter()._map_response(data)

        except httpx.TimeoutException:
            raise FeedTimeoutError(f"{state_cfg['name']} LIS timed out after {timeout_s}s")
        except (KeyError, ValueError) as exc:
            raise FeedSchemaMismatchError(f"State LIS schema mismatch: {exc}")


# =============================================================================
# ADAPTER LAYER — Orchestrator
# =============================================================================

class AdapterLayer:
    """
    Orchestrates all adapters. Reads feed_flags.json on every call (hot-reloadable).
    Returns a merged NormalisedFeedSchema regardless of which adapters fired.

    Merge priority (last write wins for non-null fields):
      OfflineRaster (structural base) → MockRegistry → StateLIS → NLIR

    fallback_used=True is set in feed_meta if any live adapter failed or timed out.
    source_verified=True is only set on title/zoning fields if a live feed confirmed them.
    """

    def fetch(
        self,
        centroid: dict,
        bbox: dict,
        state: str | None = None,
    ) -> NormalisedFeedSchema:
        """
        Main fetch entrypoint. Called once per pipeline run after confirmation.
        Args:
            centroid: {"lat": float, "lng": float}
            bbox:     {"min_lat":…, "max_lat":…, "min_lng":…, "max_lng":…}
            state:    Nigerian state name for StateLIS routing
        """
        flags = _load_flags()
        timeout_s = int(flags.get("FEED_TIMEOUT_SECONDS", 5))
        fallback_used = False
        active_adapters: list[str] = ["offline_raster"]

        # Always start with the offline structural base
        result = OfflineRasterAdapter().fetch(centroid, bbox)

        # MockRegistry
        if flags.get("MOCK_REGISTRY_ACTIVE", False):
            active_adapters.append("mock_registry")
            try:
                mock_result = _run_with_timeout(
                    MockRegistryAdapter().fetch,
                    args=(centroid, bbox),
                    timeout_s=timeout_s,
                )
                result = _merge(result, mock_result, "mock_registry")
                logger.info("[adapters] MockRegistry fetch succeeded")
            except FeedTimeoutError as exc:
                fallback_used = True
                logger.warning(f"[FEED_TIMEOUT] mock_registry: {exc}")
            except FeedHTTPError as exc:
                fallback_used = True
                logger.warning(f"[FEED_HTTP_ERROR] mock_registry: HTTP {exc.status_code}")
            except FeedSchemaMismatchError as exc:
                fallback_used = True
                logger.warning(f"[SCHEMA_MISMATCH] mock_registry: {exc}")
            except Exception as exc:
                fallback_used = True
                logger.warning(f"[FEED_ERROR] mock_registry: {exc}")

        # StateLIS
        if flags.get("STATE_LIS_ACTIVE", False):
            active_adapters.append("state_lis")
            try:
                lis_result = _run_with_timeout(
                    StateLISAdapter().fetch,
                    args=(centroid, bbox, state),
                    timeout_s=timeout_s,
                )
                result = _merge(result, lis_result, "state_lis")
                logger.info(f"[adapters] StateLIS ({state}) fetch succeeded")
            except FeedTimeoutError as exc:
                fallback_used = True
                logger.warning(f"[FEED_TIMEOUT] state_lis: {exc}")
            except Exception as exc:
                fallback_used = True
                logger.warning(f"[FEED_ERROR] state_lis: {exc}")

        # NLIR
        if flags.get("NLIR_FEED_ACTIVE", False):
            active_adapters.append("nlir")
            try:
                nlir_result = _run_with_timeout(
                    NLIRAdapter().fetch,
                    args=(centroid, bbox, timeout_s),
                    timeout_s=timeout_s,
                )
                result = _merge(result, nlir_result, "nlir")
                logger.info("[adapters] NLIR fetch succeeded")
            except FeedTimeoutError as exc:
                fallback_used = True
                logger.warning(f"[FEED_TIMEOUT] nlir: {exc}")
            except Exception as exc:
                fallback_used = True
                logger.warning(f"[FEED_ERROR] nlir: {exc}")

        # Apply fallback flag to feed_meta
        if fallback_used:
            result = result.model_copy(
                update={
                    "feed_meta": result.feed_meta.model_copy(
                        update={"fallback_used": True}
                    )
                }
            )

        logger.info(
            f"[adapters] Fetch complete. "
            f"Adapters active: {active_adapters}. "
            f"fallback_used={fallback_used}. "
            f"title.source_verified={result.title_data.source_verified}"
        )
        return result


# =============================================================================
# MERGE LOGIC
# =============================================================================

def _merge(
    base: NormalisedFeedSchema,
    override: NormalisedFeedSchema,
    source: str,
) -> NormalisedFeedSchema:
    """
    Merge override schema into base. Non-null fields in override win.
    Preserves base values where override is null.
    """
    def _merge_model(base_model, override_model):
        base_dict = base_model.model_dump()
        override_dict = override_model.model_dump()
        merged = {}
        for key in base_dict:
            override_val = override_dict.get(key)
            if override_val is not None and override_val != [] and override_val != {}:
                merged[key] = override_val
            else:
                merged[key] = base_dict[key]
        return merged

    try:
        return NormalisedFeedSchema(
            feed_meta=override.feed_meta,  # Always take the latest adapter's meta
            title_data=TitleData(**_merge_model(base.title_data, override.title_data)),
            zoning_data=ZoningData(**_merge_model(base.zoning_data, override.zoning_data)),
            encumbrance_data=EncumbranceData(**_merge_model(base.encumbrance_data, override.encumbrance_data)),
            supplemental_gis=SupplementalGIS(**_merge_model(base.supplemental_gis, override.supplemental_gis)),
        )
    except Exception as exc:
        logger.warning(f"[adapters] Merge failed for {source}: {exc} — keeping base")
        return base


# =============================================================================
# UTILITIES
# =============================================================================

def _run_with_timeout(fn, args: tuple, timeout_s: int):
    """Run fn(*args) with a wall-clock timeout. Raises FeedTimeoutError on expiry."""
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn, *args)
        try:
            return future.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError:
            raise FeedTimeoutError(f"Adapter timed out after {timeout_s}s")


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _safe_title_type(val: str | None) -> TitleType | None:
    if val is None:
        return None
    try:
        return TitleType(val.upper())
    except ValueError:
        return None


def _safe_title_status(val: str | None) -> TitleStatus | None:
    if val is None:
        return None
    try:
        return TitleStatus(val.upper())
    except ValueError:
        return None
