"""
modules/nasa_power.py
======================
NASA POWER (Prediction Of Worldwide Energy Resources) API client.

Free REST API — no authentication required.
Endpoint: https://power.larc.nasa.gov/api/temporal/monthly/point

Parameters fetched:
  WS10M         — Wind speed at 10m height (m/s)
                  CRITICAL for NO2 correction: high winds disperse NO2 plumes,
                  causing GEE satellite readings to underestimate actual emissions.
  PRECTOTCORR   — Precipitation (mm/day)
                  Rain washout removes NO2 from troposphere → another source of bias.
  T2M           — Temperature at 2m (°C)
                  Proxy for seasonal industrial demand (heating/cooling)

Why this matters for the Business Activity Score:
  If wind_speed > 5 m/s → NO2 is dispersed, not low production.
  If precipitation > 10 mm/day → NO2 is washed out, not low production.
  Without correction, a rainy windy month will appear as "economic slowdown"
  when factories are actually running at full capacity.
"""

import requests
import pandas as pd
import numpy as np
import logging
from datetime import datetime
from typing import Optional

from .config import NASA_POWER_BASE, POWER_PARAMS


def fetch_power_meteorology(
    lat: float,
    lon: float,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """
    Fetch monthly meteorological data from NASA POWER API.
    
    Returns DataFrame with index=date and columns:
        wind_speed      (m/s)
        precipitation   (mm/day)
        temperature     (°C)
    
    API Docs: https://power.larc.nasa.gov/docs/services/api/
    """
    start_str = start.strftime("%Y%m")
    end_str   = end.strftime("%Y%m")

    params = {
        "parameters":  POWER_PARAMS,
        "community":   "RE",          # Renewable Energy community dataset
        "longitude":   lon,
        "latitude":    lat,
        "start":       start_str,
        "end":         end_str,
        "format":      "JSON",
        "header":      "false",
    }

    try:
        resp = requests.get(NASA_POWER_BASE, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        props = data["properties"]["parameter"]
        ws10m  = props.get("WS10M", {})
        precip = props.get("PRECTOTCORR", {})
        t2m    = props.get("T2M", {})

        # YYYYMM keys → parse to datetime
        rows = []
        for yyyymm, ws in ws10m.items():
            try:
                dt = datetime.strptime(yyyymm, "%Y%m")
                rows.append({
                    "date":          dt,
                    "wind_speed":    float(ws)   if ws   != -999 else np.nan,
                    "precipitation": float(precip.get(yyyymm, np.nan))
                                     if precip.get(yyyymm, -999) != -999 else np.nan,
                    "temperature":   float(t2m.get(yyyymm, np.nan))
                                     if t2m.get(yyyymm, -999) != -999 else np.nan,
                })
            except (ValueError, TypeError):
                continue

        if not rows:
            return _empty_meteo_df()

        df = pd.DataFrame(rows).set_index("date").sort_index()
        # Fill missing with column medians
        df = df.fillna(df.median(numeric_only=True))
        return df

    except requests.RequestException as e:
        logging.warning(f"NASA POWER API unavailable: {e}. Meteorological correction disabled.")
        return _empty_meteo_df()
    except (KeyError, ValueError) as e:
        logging.warning(f"NASA POWER data parsing error: {e}")
        return _empty_meteo_df()


def _empty_meteo_df() -> pd.DataFrame:
    """Return empty DataFrame with correct schema when API fails"""
    return pd.DataFrame(columns=["wind_speed", "precipitation", "temperature"])


def compute_meteo_quality_flag(df: pd.DataFrame) -> pd.Series:
    """
    Generate a monthly 'meteo quality' flag (0=clean, 1=light correction, 2=heavy correction).
    Used in the UI to visually flag months where NO2 correction was significant.
    
    Rules:
        wind_speed > 7 m/s   → flag += 1 (strong dispersion)
        precipitation > 8 mm/day → flag += 1 (significant washout)
    """
    flag = pd.Series(0, index=df.index, name="meteo_flag")
    if "wind_speed" in df.columns:
        flag += (df["wind_speed"] > 7.0).astype(int)
    if "precipitation" in df.columns:
        flag += (df["precipitation"] > 8.0).astype(int)
    return flag
