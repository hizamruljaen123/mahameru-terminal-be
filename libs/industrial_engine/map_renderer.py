"""
modules/map_renderer.py
========================
Leaflet map via Folium + streamlit-folium.

Why Folium over Leafmap for Streamlit:
  - leafmap uses ipyleaflet which has widget state conflicts in Streamlit
  - folium renders static HTML that streamlit_folium embeds cleanly
  - folium natively supports GEE tile URL layers (XYZ TileLayer)
  - Better performance for production dashboards

Map layers included:
  1. Base: CartoDB Dark Matter (satellite context)
  2. Base: ESRI World Imagery (switchable via LayerControl)
  3. Optional: NO2 intensity TileLayer (from GEE)
  4. Optional: NTL intensity TileLayer (from GEE)
  5. ROI bounding box rectangle
  6. Center marker with activity score popup
  7. Score heatmap overlay (synthetic grid if no GEE)
"""

import folium
from folium import plugins
import pandas as pd
import numpy as np
from typing import Optional

from config import MAP_TILES


def build_folium_map(
    center_lat: float,
    center_lon: float,
    zoom: int,
    no2_tile_url: Optional[str],
    ntl_tile_url: Optional[str],
    score_df: pd.DataFrame,
    bbox: list,
    activity_score: float,
    thresh_high: float,
    thresh_normal: float,
) -> folium.Map:
    """
    Build a Leaflet map via Folium with:
    - Dual base layers (dark + satellite)
    - GEE NO2/NTL tile layers
    - Activity score heatmap (synth grid)
    - Annotated ROI boundary
    - Score popup marker
    """

    # ── Base map — CartoDB Dark Matter
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom,
        tiles=None,  # We add tiles manually for LayerControl
        prefer_canvas=True,
    )

    # ── Base Layer 1: Dark
    folium.TileLayer(
        tiles=MAP_TILES["dark"],
        attr=MAP_TILES["dark_attr"],
        name="🌑 Dark (CartoDB)",
        show=True,
    ).add_to(m)

    # ── Base Layer 2: Satellite
    folium.TileLayer(
        tiles=MAP_TILES["satellite"],
        attr=MAP_TILES["sat_attr"],
        name="🛰️ Satellite (ESRI)",
        show=False,
    ).add_to(m)

    # ── GEE NO2 Layer
    if no2_tile_url:
        folium.TileLayer(
            tiles=no2_tile_url,
            attr="ESA/Copernicus Sentinel-5P · GEE",
            name="🟡 NO₂ Tropospheric Column",
            opacity=0.75,
            overlay=True,
            show=True,
        ).add_to(m)
    else:
        # Fallback: synthetic heatmap showing NO2 proxy from score_df
        _add_synthetic_no2_heatmap(m, center_lat, center_lon, score_df)

    # ── GEE NTL Layer
    if ntl_tile_url:
        folium.TileLayer(
            tiles=ntl_tile_url,
            attr="NASA/VIIRS Black Marble VNP46A2 · GEE",
            name="🔵 Nighttime Lights (NTL)",
            opacity=0.65,
            overlay=True,
            show=True,
        ).add_to(m)

    # ── ROI Bounding Box
    w, s, e, n = bbox
    folium.Rectangle(
        bounds=[[s, w], [n, e]],
        color="#58a6ff",
        weight=2,
        fill=True,
        fill_color="#58a6ff",
        fill_opacity=0.05,
        tooltip="Analysis ROI",
        popup=folium.Popup(
            f"""<div style="font-family:monospace; font-size:11px; color:#111;">
                <b>Region of Interest</b><br>
                W: {w:.3f} | E: {e:.3f}<br>
                S: {s:.3f} | N: {n:.3f}<br>
                <br>Activity Score: <b>{activity_score:.3f}</b>
            </div>""",
            max_width=200,
        ),
    ).add_to(m)

    # ── Center marker with activity badge
    score_color, icon_name = _score_to_style(activity_score, thresh_high, thresh_normal)

    popup_html = _build_popup_html(activity_score, thresh_high, thresh_normal, score_df)

    folium.Marker(
        location=[center_lat, center_lon],
        popup=folium.Popup(popup_html, max_width=260),
        tooltip=f"Activity Score: {activity_score:.3f}",
        icon=folium.Icon(color=score_color, icon=icon_name, prefix="fa"),
    ).add_to(m)

    # ── MiniMap
    plugins.MiniMap(
        toggle_display=True, 
        tile_layer=folium.TileLayer(
            tiles=MAP_TILES["dark"], 
            attr=MAP_TILES["dark_attr"], 
            name="MiniMap"
        )
    ).add_to(m)

    # ── Scale bar
    plugins.MeasureControl(position="bottomleft", primary_length_unit="kilometers").add_to(m)

    # ── Fullscreen button
    plugins.Fullscreen(position="topright").add_to(m)

    # ── Layer control
    folium.LayerControl(position="topright", collapsed=False).add_to(m)

    return m


def _score_to_style(score: float, thresh_high: float, thresh_normal: float):
    """Map activity score to folium marker color and icon"""
    if score >= thresh_high:
        return "green", "industry"
    elif score >= thresh_normal:
        return "blue", "bar-chart"
    else:
        return "red", "arrow-down"


def _build_popup_html(
    score: float,
    thresh_high: float,
    thresh_normal: float,
    df: pd.DataFrame,
) -> str:
    """Build HTML popup content for the center marker"""
    if score >= thresh_high:
        status = "⬆ PEAK PRODUCTION"
        color  = "#3fb950"
    elif score >= thresh_normal:
        status = "→ NORMAL OPERATION"
        color  = "#58a6ff"
    else:
        status = "⬇ ECONOMIC SLOWDOWN"
        color  = "#f85149"

    last_no2 = df["no2_mean"].iloc[-1] if "no2_mean" in df.columns else 0
    last_ntl = df["ntl_mean"].iloc[-1] if "ntl_mean" in df.columns else 0

    return f"""
    <div style="font-family:'Courier New',monospace; font-size:11px; 
                background:#0d1117; color:#c9d1d9; padding:10px; 
                border-radius:6px; border:1px solid #30363d; min-width:200px;">
        <div style="color:{color}; font-weight:bold; font-size:13px; margin-bottom:8px;">
            {status}
        </div>
        <div style="color:#8b949e; margin-bottom:4px;">Activity Score</div>
        <div style="color:#f0f6fc; font-size:18px; font-weight:bold; margin-bottom:8px;">
            {score:.3f}
        </div>
        <hr style="border-color:#30363d; margin:6px 0;">
        <div>NO₂: <b>{last_no2:.2e}</b> mol/m²</div>
        <div>NTL:  <b>{last_ntl:.1f}</b> nW/cm²/sr</div>
        <hr style="border-color:#30363d; margin:6px 0;">
        <div style="color:#8b949e; font-size:10px;">
            Sources: Sentinel-5P + Black Marble
        </div>
    </div>
    """


def _add_synthetic_no2_heatmap(
    m: folium.Map,
    center_lat: float,
    center_lon: float,
    df: pd.DataFrame,
):
    """
    Add synthetic heatmap when GEE tiles are unavailable.
    Generates a Gaussian distribution of points around center,
    weighted by the latest activity score.
    """
    if df.empty:
        return

    latest_score = float(df["activity_score"].iloc[-1]) if "activity_score" in df.columns else 0.5
    n_points = 200
    rng = np.random.default_rng(42)

    lats = rng.normal(center_lat, 0.05, n_points)
    lons = rng.normal(center_lon, 0.06, n_points)
    weights = rng.exponential(latest_score, n_points)
    weights = (weights / weights.max()).tolist()

    heat_data = [[lat, lon, w] for lat, lon, w in zip(lats, lons, weights)]

    plugins.HeatMap(
        heat_data,
        name="🔥 Activity Heatmap (Demo)",
        min_opacity=0.2,
        radius=20,
        blur=15,
        gradient={0.2: "#440154", 0.4: "#31688e", 0.6: "#35b779", 0.8: "#fde725"},
    ).add_to(m)
