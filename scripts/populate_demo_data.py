"""
LandIQ — scripts/populate_demo_data.py
=======================================
ONE-RUN DATA POPULATION SCRIPT for IDICE Demo Stabilisation.

Populates REAL GIS data for 4 key demo metros:
  1. Lagos       — OSM roads + HydroRIVERS (SRTM already present)
  2. Rivers/PH   — OSM roads + HydroRIVERS (SRTM already present)
  3. FCT Abuja   — OSM roads + HydroRIVERS + SRTM tile N08E007
  4. Akwa Ibom   — OSM roads + HydroRIVERS

PREREQUISITES:
  pip install osmnx requests tqdm

USAGE:
  python scripts/populate_demo_data.py
  python scripts/populate_demo_data.py --roads-only
  python scripts/populate_demo_data.py --srtm-only
  python scripts/populate_demo_data.py --summary-only
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT_DIR     = Path(__file__).resolve().parent.parent
DATA_DIR     = ROOT_DIR / "data"
OSM_PATH     = DATA_DIR / "osm"   / "roads_nigeria.gpkg"
HYDRO_PATH   = DATA_DIR / "hydro" / "hydrorivers_nigeria.gpkg"
RASTER_DIR   = DATA_DIR / "rasters"
SENTINEL_DIR = DATA_DIR / "sentinel"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("populate_demo_data")


# ── STEP 1: OSM ROAD NETWORKS ──────────────────────────────────────────────────

DEMO_REGIONS = {
    "Lagos":    "Lagos, Nigeria",
    "Rivers":   "Rivers State, Nigeria",
    "FCT":      "Federal Capital Territory, Nigeria",
    "AkwaIbom": "Akwa Ibom State, Nigeria",
}

def populate_roads() -> None:
    try:
        import osmnx as ox
        import geopandas as gpd
    except ImportError:
        logger.error("Missing dependency: pip install osmnx geopandas")
        return

    logger.info("─── STEP 1: OSM Road Networks ───────────────────────────────")
    all_roads: list = []

    for region_name, region_query in DEMO_REGIONS.items():
        logger.info(f"  Downloading roads: {region_name}...")
        try:
            G = ox.graph_from_place(region_query, network_type="drive", simplify=True)
            edges = ox.graph_to_gdfs(G, nodes=False)
            edges = edges[["geometry", "length", "highway"]].copy()
            edges["region"] = region_name
            all_roads.append(edges)
            logger.info(f"  OK {region_name}: {len(edges):,} road segments")
        except Exception as e:
            logger.warning(f"  FAILED {region_name}: {e}")

    if not all_roads:
        logger.error("No road data downloaded. Check internet connection.")
        return

    import pandas as pd
    combined = gpd.GeoDataFrame(pd.concat(all_roads, ignore_index=True), crs="EPSG:4326")
    OSM_PATH.parent.mkdir(parents=True, exist_ok=True)
    combined.to_file(OSM_PATH, driver="GPKG", layer="roads")
    logger.info(f"  OK Roads saved: {len(combined):,} total features -> {OSM_PATH}")


# ── STEP 2: HYDRORIVERS ───────────────────────────────────────────────────────

NIGERIA_BBOX = (2.676932, 4.240594, 14.680073, 13.885645)

def populate_hydrorivers(source_path: str | None = None) -> None:
    try:
        import geopandas as gpd
    except ImportError:
        logger.error("Missing dependency: pip install geopandas")
        return

    logger.info("─── STEP 2: HydroRIVERS ─────────────────────────────────────")

    if source_path:
        shp = Path(source_path)
        if not shp.exists():
            logger.error(f"Source shapefile not found: {shp}")
            return
        rivers = gpd.read_file(str(shp), bbox=NIGERIA_BBOX)
    else:
        import urllib.request, zipfile, io
        WA_URL = "https://data.hydrosheds.org/file/hydrorivers/HydroRIVERS_v10_af_shp.zip"
        try:
            logger.info(f"  Downloading {WA_URL} ...")
            with urllib.request.urlopen(WA_URL, timeout=120) as r:
                raw = r.read()
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                zf.extractall(DATA_DIR / "hydro" / "_hydrorivers_src")
            shp_files = list((DATA_DIR / "hydro" / "_hydrorivers_src").rglob("*.shp"))
            if not shp_files:
                logger.error("  No .shp found in downloaded archive.")
                return
            rivers = gpd.read_file(str(shp_files[0]), bbox=NIGERIA_BBOX)
        except Exception as e:
            logger.error(
                f"  Auto-download failed: {e}\n"
                "  ACTION REQUIRED: Download HydroRIVERS_v10_af.zip from\n"
                "  https://www.hydrosheds.org/products/hydrorivers then run:\n"
                "  python scripts/populate_demo_data.py --hydro-source <path/to/HydroRIVERS_v10_af.shp>"
            )
            return

    if rivers.empty:
        logger.warning("  No river features within Nigeria bounding box.")
        return

    HYDRO_PATH.parent.mkdir(parents=True, exist_ok=True)
    rivers.to_file(HYDRO_PATH, driver="GPKG", layer="rivers")
    logger.info(f"  OK HydroRIVERS saved: {len(rivers):,} features -> {HYDRO_PATH}")


# ── STEP 3: SRTM TILE (N08E007 for Abuja/FCT) ─────────────────────────────────

def download_srtm_tile(tile: str = "N08E007") -> None:
    import urllib.request, zipfile, io

    logger.info(f"─── STEP 3: SRTM Tile {tile} ──────────────────────────────────")
    out_tif = RASTER_DIR / f"{tile}.tif"
    if out_tif.exists() and out_tif.stat().st_size > 500_000:
        logger.info(f"  OK Already exists: {out_tif}")
        return

    # CGIAR SRTM grid calculation
    lat_char = tile[0]
    lat_deg  = int(tile[1:3])
    lon_char = tile[3]
    lon_deg  = int(tile[4:])
    cgiar_col = (lon_deg // 5) + 37 if lon_char == "E" else (36 - (lon_deg // 5))
    cgiar_row = (60 - lat_deg) // 5 + 1 if lat_char == "N" else ((lat_deg + 60) // 5 + 13)
    tile_zip  = f"srtm_{cgiar_col:02d}_{cgiar_row:02d}.zip"
    url       = f"https://srtm.csi.cgiar.org/wp-content/uploads/files/srtm_5x5/TIFF/{tile_zip}"

    logger.info(f"  Downloading {url}...")
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            raw = r.read()
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            tif_files = [n for n in zf.namelist() if n.endswith(".tif")]
            if not tif_files:
                logger.error(f"  No .tif in {tile_zip}")
                return
            RASTER_DIR.mkdir(parents=True, exist_ok=True)
            data = zf.read(tif_files[0])
            out_tif.write_bytes(data)
        logger.info(f"  OK SRTM tile saved: {out_tif}")
    except Exception as e:
        logger.error(
            f"  SRTM download failed: {e}\n"
            f"  ACTION REQUIRED: Download {tile}.tif manually from:\n"
            f"    https://dwtkns.com/srtm/  (visual tile selector)\n"
            f"  Save to: {out_tif}"
        )


# ── STEP 4: SENTINEL RASTERS (GEE) ───────────────────────────────────────────

SENTINEL_GEE_ZONES = [
    {
        "name": "abuja",
        "bbox": [7.20, 8.80, 7.80, 9.20],
        "ndwi_out": SENTINEL_DIR / "abuja_ndwi_2023.tif",
        "ndvi_out": SENTINEL_DIR / "abuja_ndvi_2023.tif",
    },
    {
        "name": "akwaibom",
        "bbox": [7.50, 4.50, 8.30, 5.40],
        "ndwi_out": SENTINEL_DIR / "akwaibom_ndwi_2023.tif",
        "ndvi_out": SENTINEL_DIR / "akwaibom_ndvi_2023.tif",
    },
]

def populate_sentinel_via_gee() -> None:
    logger.info("─── STEP 4: Sentinel-2 Rasters (GEE) ───────────────────────")
    try:
        import ee
    except ImportError:
        logger.error("  Missing dependency: pip install earthengine-api")
        return
    try:
        ee.Initialize()
        logger.info("  GEE initialized.")
    except Exception as e:
        logger.error(
            f"  GEE not authenticated: {e}\n"
            "  Run: python -c \"import ee; ee.Authenticate()\" first."
        )
        return

    SENTINEL_DIR.mkdir(parents=True, exist_ok=True)
    for zone in SENTINEL_GEE_ZONES:
        bbox   = zone["bbox"]
        region = ee.Geometry.Rectangle(bbox)
        logger.info(f"  Zone: {zone['name']} bbox={bbox}")
        try:
            col = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(region)
                .filterDate("2023-01-01", "2023-12-31")
                .filterMetadata("CLOUDY_PIXEL_PERCENTAGE", "less_than", 10)
                .sort("CLOUDY_PIXEL_PERCENTAGE")
            )
            img  = col.first()
            ndwi = img.normalizedDifference(["B3", "B8"]).rename("NDWI")
            ndvi = img.normalizedDifference(["B8", "B4"]).rename("NDVI")
            for idx_img, out_path in [(ndwi, zone["ndwi_out"]), (ndvi, zone["ndvi_out"])]:
                if out_path.exists() and out_path.stat().st_size > 100_000:
                    logger.info(f"    OK Already exists: {out_path}")
                    continue
                import urllib.request
                url = idx_img.getDownloadURL({"scale": 30, "crs": "EPSG:4326",
                                              "region": region, "format": "GEO_TIFF"})
                logger.info(f"    Downloading: {out_path.name}...")
                urllib.request.urlretrieve(url, str(out_path))
                logger.info(f"    OK Saved: {out_path}")
        except Exception as e:
            logger.error(f"  Zone {zone['name']} failed: {e}")


# ── COVERAGE SUMMARY ──────────────────────────────────────────────────────────

def print_coverage_summary() -> None:
    logger.info("─── DATA COVERAGE SUMMARY ──────────────────────────────────")

    def fsize(p: Path) -> str:
        if not p.exists():
            return "MISSING"
        s = p.stat().st_size
        if s < 200_000:
            return f"STUB ({s:,} bytes)"
        return f"OK {s/1_048_576:.1f} MB"

    logger.info(f"  OSM Roads:       {fsize(OSM_PATH)}")
    logger.info(f"  HydroRIVERS:     {fsize(HYDRO_PATH)}")
    for tile in ["N04E007", "N05E006", "N06E003", "N08E007"]:
        for ext in [".tif", ".hgt"]:
            p = RASTER_DIR / f"{tile}{ext}"
            if p.exists():
                logger.info(f"  SRTM {tile}:   {fsize(p)}")
                break
        else:
            logger.info(f"  SRTM {tile}:   MISSING")
    for zone in ["lagos", "rivers", "abuja", "akwaibom"]:
        for idx in ["ndwi", "ndvi"]:
            p = SENTINEL_DIR / f"{zone}_{idx}_2023.tif"
            logger.info(f"  Sentinel {zone}_{idx}: {fsize(p)}")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Populate LandIQ IDICE demo GIS data.")
    parser.add_argument("--roads-only",    action="store_true")
    parser.add_argument("--hydro-only",    action="store_true")
    parser.add_argument("--srtm-only",     action="store_true")
    parser.add_argument("--sentinel-only", action="store_true")
    parser.add_argument("--summary-only",  action="store_true")
    parser.add_argument("--hydro-source",  default=None,
                        help="Path to HydroRIVERS_v10_af.shp")
    parser.add_argument("--srtm-tile",     default="N08E007",
                        help="SRTM tile name e.g. N08E007")
    args = parser.parse_args()

    run_all = not any([
        args.roads_only, args.hydro_only, args.srtm_only,
        args.sentinel_only, args.summary_only
    ])

    logger.info("=" * 64)
    logger.info("  LandIQ — IDICE Demo Data Population Script")
    logger.info("=" * 64)

    if args.summary_only:
        print_coverage_summary()
        return

    if run_all or args.roads_only:
        populate_roads()
    if run_all or args.hydro_only:
        populate_hydrorivers(args.hydro_source)
    if run_all or args.srtm_only:
        download_srtm_tile(args.srtm_tile)
    if run_all or args.sentinel_only:
        populate_sentinel_via_gee()

    print_coverage_summary()
    logger.info("Done. Restart the LandIQ server for changes to take effect.")


if __name__ == "__main__":
    main()
