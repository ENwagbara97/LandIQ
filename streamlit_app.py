import streamlit as st
import folium
from streamlit_folium import st_folium
import sys
import os

# Add root to path so we can import agents
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from agents.coord_extract import run as coord_run
from core.schemas import Coordinate

def render_interactive_test_map(wgs84_coords):
    """
    Generates a live Leaflet map inside the Streamlit workbench
    featuring an interactive Google Maps-style basemap switcher.
    """
    # 1. Calculate a dynamic center point from the polygon vertices
    lats = [c[1] for c in wgs84_coords]
    lngs = [c[0] for c in wgs84_coords]
    centroid = [sum(lats) / len(lats), sum(lngs) / len(lngs)]
    
    # 2. Initialize the baseline map object
    m = folium.Map(location=centroid, zoom_start=16, control_scale=True)
    
    # 3. Inject the standard alternative tile providers
    # Standard Vector Map (OpenStreetMap)
    folium.TileLayer('openstreetmap', name='Street Map').add_to(m)
    
    # Premium High-Res Satellite Imagery (Esri World Imagery)
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri',
        name='Satellite Imagery',
        overlay=False
    ).add_to(m)
    
    # Google Satellite Hybrid Map Layer
    folium.TileLayer(
        tiles='https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
        attr='Google',
        name='Google Hybrid (Satellite + Labels)',
        overlay=False
    ).add_to(m)
    
    # 4. Plot the property boundary polygon over the layers
    # Swap lat/long formatting to match Folium specifications [[lat, lng], ...]
    folium_polygon = [[c[1], c[0]] for c in wgs84_coords]
    folium.Polygon(
        locations=folium_polygon,
        color='#FF0000', # High-visibility red boundary lines
        fill=True,
        fill_color='#FF0000',
        fill_opacity=0.15,
        weight=3
    ).add_to(m)
    
    # 5. The Golden Touch: Add the interactive layer selector widget
    folium.LayerControl(position='topright', collapsed=False).add_to(m)
    
    # 6. Push the map object to the active UI window frame
    st_folium(m, width=1200, height=500, returned_objects=[])

st.set_page_config(layout="wide", page_title="LandIQ Streamlit Workbench")

st.title("LandIQ — Interactive Coordinate Extraction Test")

with st.sidebar:
    st.header("Input Coordinates")
    raw_text = st.text_area("Raw Text (OCR/Tabular/DMS/DD):", height=300, 
        value="MINNA UTM ZONE 32\n\nSC/AK/K 49700 387804.297 550821.575\nSC/AK/K 49701 387852.254 550891.123\nSC/AK/K 49702 387910.500 550865.400\nSC/AK/K 49703 387875.100 550795.200\nSC/AK/K 49700 387804.297 550821.575")
    analyze_btn = st.button("Extract & Plot")

if analyze_btn:
    with st.spinner("Extracting coordinates..."):
        result = coord_run(raw_input=raw_text, run_id="st-test")
        
        if hasattr(result, "error_code"):
            st.error(f"Error: {result.error_code} - {result.instruction}")
        else:
            st.success(f"Successfully extracted {len(result.coordinates)} points. Detected CRS: {result.detected_crs.value}")
            
            if not result.is_inside_nigeria:
                st.warning("Warning: Coordinates resolved outside of Nigeria.")
                
            wgs84_coords = [(p[1], p[0]) for p in result.coordinates]
            render_interactive_test_map(wgs84_coords)
