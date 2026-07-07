import ee
import json
import logging

logging.basicConfig(level=logging.INFO)
ee.Initialize()

try:
    image = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM").mosaic()
    print("SUCCESS: Image loaded.")
    # test a small bbox
    bbox = ee.Geometry.Rectangle([8.67, 9.08, 8.68, 9.09])
    resampled = image.resample('bilinear')
    proj = ee.Projection('EPSG:4326').atScale(30.0)
    reprojected = resampled.reproject(crs=proj)
    pixel_data = reprojected.sampleRectangle(region=bbox, defaultValue=-9999).getInfo()
    elevations = pixel_data['properties']['DEM']
    print(f"SUCCESS: Fetched {len(elevations)} rows of elevation data.")
except Exception as e:
    print(f"ERROR: {e}")
