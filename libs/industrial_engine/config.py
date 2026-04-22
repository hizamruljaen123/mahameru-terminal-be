"""
config.py — ROI Registry and Global Constants
"""

# ── Known Industrial Zones with bounding boxes [W, S, E, N]
ROI_REGISTRY ={
    "smk": {
        "name": "KEK Sei Mangkei, Sumatera Utara",
        "lat": 3.1322,
        "lon": 99.3406,
        "bbox": [99.2, 3.0, 99.5, 3.3],
        "sector": "Agroindustri (Sawit & Karet)",
        "country": "ID"
    },
    "aru": {
        "name": "KEK Arun Lhokseumawe, Aceh",
        "lat": 5.1875,
        "lon": 97.1382,
        "bbox": [97.0, 5.0, 97.3, 5.4],
        "sector": "Industri Kimia & Energi",
        "country": "ID"
    },
    "mdk": {
        "name": "KEK Mandalika, NTB",
        "lat": -8.8945,
        "lon": 116.2914,
        "bbox": [-8.95, 116.2, -8.80, 116.35],
        "sector": "Pariwisata",
        "country": "ID"
    },
    "btg": {
        "name": "KEK Bitung, Sulawesi Utara",
        "lat": 1.4406,
        "lon": 125.1282,
        "bbox": [125.0, 1.3, 125.3, 1.6],
        "sector": "Logistik & Industri",
        "country": "ID"
    },
    "grs": {
        "name": "KEK Gresik, Jawa Timur",
        "lat": -7.1566,
        "lon": 112.6555,
        "bbox": [-7.25, 112.5, -7.05, 112.8],
        "sector": "Industri Manufaktur",
        "country": "ID"
    },
    "plu": {
        "name": "KEK Palu, Sulawesi Tengah",
        "lat": -0.8950,
        "lon": 119.8594,
        "bbox": [-0.95, 119.7, -0.80, 120.0],
        "sector": "Industri & Logistik",
        "country": "ID"
    },
    "mrt": {
        "name": "KEK Morotai, Maluku Utara",
        "lat": 2.3000,
        "lon": 128.4000,
        "bbox": [128.2, 2.1, 128.6, 2.5],
        "sector": "Logistik & Pariwisata",
        "country": "ID"
    },
    "kdl": {
        "name": "KEK Kendal, Jawa Tengah",
        "lat": -7.0147,
        "lon": 110.5947,
        "bbox": [-7.1, 110.4, -6.9, 110.7],
        "sector": "Industri Manufaktur",
        "country": "ID"
    },
    "gbt": {
        "name": "KEK Galang Batang, Kepulauan Riau",
        "lat": 1.0500,
        "lon": 103.8500,
        "bbox": [103.7, 0.9, 104.0, 1.2],
        "sector": "Industri Aluminium & Logam",
        "country": "ID"
    },
    "mbtk": {
        "name": "KEK Maloy Batuta Trans Kalimantan, Kaltim",
        "lat": -0.8500,
        "lon": 117.2500,
        "bbox": [-1.0, 117.0, -0.6, 117.5],
        "sector": "Industri & Logistik",
        "country": "ID"
    },
    "ngs": {
        "name": "KEK Nongsa, Batam",
        "lat": 1.1500,
        "lon": 104.0500,
        "bbox": [104.0, 1.1, 104.1, 1.2],
        "sector": "Digital & Teknologi",
        "country": "ID"
    },
    "bat": {
        "name": "KEK Batam Aero Technic, Batam",
        "lat": 1.1300,
        "lon": 104.0300,
        "bbox": [104.0, 1.1, 104.1, 1.2],
        "sector": "Aerospace (MRO)",
        "country": "ID"
    },
    "tlj": {
        "name": "KEK Tanjung Lesung, Banten",
        "lat": -6.4800,
        "lon": 106.0500,
        "bbox": [-6.55, 105.9, -6.40, 106.2],
        "sector": "Pariwisata",
        "country": "ID"
    },
    "tky": {
        "name": "KEK Tanjung Kelayang, Belitung",
        "lat": -2.5500,
        "lon": 106.7500,
        "bbox": [-2.65, 106.6, -2.45, 106.9],
        "sector": "Pariwisata",
        "country": "ID"
    },
    "ldo": {
        "name": "KEK Lido, Jawa Barat",
        "lat": -6.4500,
        "lon": 106.8500,
        "bbox": [-6.55, 106.7, -6.35, 107.0],
        "sector": "Pariwisata & Properti",
        "country": "ID"
    },
    "sgh": {
        "name": "KEK Singhasari, Jawa Timur",
        "lat": -7.8500,
        "lon": 112.6500,
        "bbox": [-7.9, 112.5, -7.8, 112.8],
        "sector": "Digital & Teknologi",
        "country": "ID"
    },
    "lkp": {
        "name": "KEK Likupang, Sulawesi Utara",
        "lat": 1.5500,
        "lon": 124.8500,
        "bbox": [124.7, 1.4, 125.0, 1.7],
        "sector": "Pariwisata",
        "country": "ID"
    },
    "snr": {
        "name": "KEK Sanur, Bali",
        "lat": -8.6800,
        "lon": 115.2700,
        "bbox": [-8.72, 115.2, -8.65, 115.3],
        "sector": "Pariwisata & Kesehatan",
        "country": "ID"
    },
    "stg": {
        "name": "KEK Setangga, Kepulauan Riau",
        "lat": 0.9500,
        "lon": 103.9500,
        "bbox": [103.8, 0.8, 104.1, 1.1],
        "sector": "Industri",
        "country": "ID"
    },
    "tsu": {
        "name": "KEK Tanjung Sauh, Kepulauan Riau",
        "lat": 1.0500,
        "lon": 103.9000,
        "bbox": [103.8, 0.9, 104.0, 1.2],
        "sector": "Industri",
        "country": "ID"
    },
    "ibg": {
        "name": "KEK Industropolis Batang, Jawa Tengah",
        "lat": -6.9200,
        "lon": 109.7200,
        "bbox": [-7.0, 109.6, -6.8, 109.9],
        "sector": "Industri Manufaktur",
        "country": "ID"
    },
    "btk": {
        "name": "KEK Edukasi Teknologi Kesehatan Internasional Banten",
        "lat": -6.2000,
        "lon": 106.6500,
        "bbox": [-6.3, 106.5, -6.1, 106.8],
        "sector": "Pendidikan & Kesehatan",
        "country": "ID"
    },
    "bph": {
        "name": "KEK Pariwisata Kesehatan Internasional Batam",
        "lat": 1.1300,
        "lon": 104.0300,
        "bbox": [104.0, 1.1, 104.1, 1.2],
        "sector": "Kesehatan & Pariwisata",
        "country": "ID"
    },
    "krb": {
        "name": "KEK Kura Kura Bali",
        "lat": -8.5000,
        "lon": 115.2000,
        "bbox": [-8.55, 115.1, -8.45, 115.3],
        "sector": "Pariwisata",
        "country": "ID"
    },
    "srg": {
        "name": "KEK Sorong, Papua Barat Daya",
        "lat": -0.8800,
        "lon": 131.2500,
        "bbox": [-1.0, 131.1, -0.7, 131.4],
        "sector": "Industri & Logistik",
        "country": "ID"
    },
    "mwr": {
        "name": "Kawasan Industri Morowali, Sulawesi Tengah",
        "lat": -2.1500,
        "lon": 121.4500,
        "bbox": [-2.3, 121.2, -2.0, 121.7],
        "sector": "Nikely & Smelter",
        "country": "ID"
    },
    "knw": {
        "name": "Kawasan Industri Konawe, Sulawesi Tenggara",
        "lat": -3.9500,
        "lon": 122.4000,
        "bbox": [-4.1, 122.2, -3.8, 122.6],
        "sector": "Nikely & Industri Dasar",
        "country": "ID"
    },
    "ktj": {
        "name": "Kawasan Industri Kuala Tanjung, Sumatera Utara",
        "lat": 3.2500,
        "lon": 99.4500,
        "bbox": [99.3, 3.1, 99.6, 3.4],
        "sector": "Logistik & Industri",
        "country": "ID"
    },
    "ptb": {
        "name": "Kawasan Industri Terpadu Batang, Jawa Tengah",
        "lat": -6.9200,
        "lon": 109.7200,
        "bbox": [-7.0, 109.6, -6.8, 109.9],
        "sector": "Industri Manufaktur",
        "country": "ID"
    },
    "tbn": {
        "name": "Pelabuhan Patimban, Jawa Barat",
        "lat": -6.3200,
        "lon": 107.3500,
        "bbox": [-6.4, 107.2, -6.2, 107.5],
        "sector": "Logistik & Pelabuhan",
        "country": "ID"
    },
    "sha": {
        "name": "Bandara Soekarno-Hatta, Tangerang",
        "lat": -6.1256,
        "lon": 106.6558,
        "bbox": [-6.2, 106.5, -6.0, 106.8],
        "sector": "Aviation & Logistik",
        "country": "ID"
    },
    "ngb": {
        "name": "Bandara Ngurah Rai, Bali",
        "lat": -8.7470,
        "lon": 115.1670,
        "bbox": [-8.8, 115.1, -8.6, 115.3],
        "sector": "Aviation & Pariwisata",
        "country": "ID"
    },
    "Custom Location": {
        "name": "Custom Location",
        "lat": None,
        "lon": None,
        "bbox": None,
        "sector": "",
        "country": "ID"
    }
}
# ── Default analysis parameters
DEFAULT_MONTHS = 12

# ── Score formula weights (NO2 + NTL must sum to 1.0)
SCORE_WEIGHTS = {
    "no2": 0.60,
    "ntl": 0.40,
}

# ── Band/column labels for display
BAND_LABELS = {
    "no2_mean":       "NO₂ Column Density (mol/m²)",
    "ntl_mean":       "NTL Radiance (nW/cm²/sr)",
    "no2_corrected":  "NO₂ Corrected (meteorology-adjusted)",
    "no2_norm":       "NO₂ Normalized [0–1]",
    "ntl_norm":       "NTL Normalized [0–1]",
    "activity_score": "Business Activity Score",
    "wind_speed":     "Wind Speed (m/s)",
    "precipitation":  "Precipitation (mm/day)",
}

# ── STAC Collection IDs (Planetary Computer)
STAC_COLLECTIONS = {
    "no2": "sentinel-5p-l2-netcdf",
    "ntl": "viirs-dnb-monthly", # Note: Some regions might use different aliases
}

# ── NASA POWER API base URL
NASA_POWER_BASE = "https://power.larc.nasa.gov/api/temporal/monthly/point"

# ── NASA POWER parameters to fetch
# WS10M: wind speed at 10m, PRECTOTCORR: corrected precipitation
POWER_PARAMS = "WS10M,PRECTOTCORR,T2M"

# ── Folium map tiles
MAP_TILES = {
    "dark":       "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    "dark_attr":  "© OpenStreetMap contributors © CARTO",
    "satellite":  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    "sat_attr":   "ESRI World Imagery",
}

# ── Colormap for NO2 (viridis-like for satellite data)
NO2_COLORMAP = {
    "palette": ["#440154", "#414487", "#2a788e", "#22a884", "#7ad151", "#fde725"],
    "min": 0.0,
    "max": 0.0003,  # mol/m² — typical tropospheric NO2 range over industrial zones
}

NTL_COLORMAP = {
    "palette": ["#000000", "#1a1a2e", "#16213e", "#0f3460", "#533483", "#e94560"],
    "min": 0,
    "max": 100,  # nW/cm²/sr
}
