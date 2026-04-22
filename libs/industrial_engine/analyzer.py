"""
modules/analyzer.py
====================
Business Activity Score engine.

IMPROVED FORMULA vs. original spec:
  Original: Score = (NO2_norm * 0.6) + (NTL_norm * 0.4)
  
  Problem:  NO2 readings are heavily confounded by meteorology.
            High wind or rain → low NO2 even if factories are running at 100%.
  
  Improved: 
    1. Apply meteorological correction to NO2 BEFORE normalization
    2. Normalize using HISTORICAL PERCENTILE of that specific ROI 
       (not arbitrary global min-max — avoids cross-zone bias)
    3. Score = (NO2_corr_norm * w_no2) + (NTL_norm * w_ntl)
    4. Trend = compare rolling-3m average vs. same period prior year

Normalization baseline:
  We use percentile-based normalization:
    norm = (x - P5) / (P95 - P5), clipped to [0, 1]
  This is more robust than min-max because a single outlier
  won't compress the entire series to near-zero.
"""

import numpy as np
import pandas as pd
from typing import Tuple, Optional
from datetime import datetime, timedelta


# ──────────────────────────────────────────────
#  Meteorological Correction for NO2
# ──────────────────────────────────────────────

def apply_meteo_correction(
    no2: pd.Series,
    wind_speed: pd.Series,
    precipitation: Optional[pd.Series] = None,
) -> pd.Series:
    """
    Correct NO2 readings for meteorological dispersion/washout effects.
    
    Physics basis:
    - NO2 lifetime in troposphere ≈ 1-2 days
    - Higher wind → faster dispersion → satellite sees less NO2 per km²
    - Higher precipitation → wet deposition removes NO2 → satellite reads less
    
    Correction factors derived from literature:
    - Laughner & Cohen (2019): Wind correction factor ~exp(0.1 * (WS - WS_ref))
    - WS_ref = 3 m/s (typical calm industrial zone baseline)
    
    Returns: NO2 series with upward correction for high-wind/high-rain months.
    
    IMPORTANT: This is an approximation. For rigorous analysis, a full CTM
    (Chemical Transport Model) correction like WRF-Chem is recommended.
    """
    no2_corr = no2.copy()

    # Align indices
    ws_aligned = wind_speed.reindex(no2.index, method="nearest")

    # Wind correction: factor increases NO2 estimate when wind was high
    # Factor = exp(k * (WS - WS_ref)) where k ≈ 0.10
    WS_REF = 3.0
    K_WIND = 0.10
    wind_factor = np.exp(K_WIND * (ws_aligned - WS_REF))
    no2_corr = no2_corr * wind_factor

    # Precipitation correction: rain washout
    if precipitation is not None and len(precipitation) > 0:
        precip_aligned = precipitation.reindex(no2.index, method="nearest")
        # For every 10mm/day above baseline (2 mm/day), add ~15% upward correction
        PRECIP_BASE = 2.0
        K_PRECIP    = 0.015
        precip_factor = 1.0 + K_PRECIP * (precip_aligned - PRECIP_BASE).clip(lower=0)
        no2_corr = no2_corr * precip_factor

    # Cap correction: don't over-correct (max 2x upward adjustment)
    no2_corr = no2_corr.clip(upper=no2.max() * 2.0)
    return no2_corr


# ──────────────────────────────────────────────
#  Percentile-based Normalization
# ──────────────────────────────────────────────

def normalize_series(s: pd.Series, p_low: float = 5, p_high: float = 95) -> pd.Series:
    """
    Normalize series to [0, 1] using percentile-based scaling.
    
    More robust than min-max because:
    - Outliers don't compress the bulk of the data
    - Physically meaningful: 0 = unusually low, 1 = unusually high
    
    Values below P5 → clipped to 0
    Values above P95 → clipped to 1
    """
    if s.dropna().empty:
        return pd.Series(0.5, index=s.index)

    lo = np.nanpercentile(s, p_low)
    hi = np.nanpercentile(s, p_high)

    if hi - lo < 1e-12:  # Constant series — no variance
        return pd.Series(0.5, index=s.index)

    norm = (s - lo) / (hi - lo)
    return norm.clip(0.0, 1.0)


# ──────────────────────────────────────────────
#  Business Activity Score
# ──────────────────────────────────────────────

def compute_activity_score(
    no2_norm: pd.Series,
    ntl_norm: pd.Series,
    w_no2: float = 0.6,
    w_ntl: float = 0.4,
) -> pd.Series:
    """
    Weighted composite Business Activity Score.
    
    Score = (NO2_corrected_normalized * w_no2) + (NTL_normalized * w_ntl)
    
    Interpretation:
      ≥ 0.70 → Peak Production (high emissions + bright lights = full operation)
      0.40–0.70 → Normal Operation
      < 0.40 → Economic Slowdown or planned shutdown
    
    Notes:
    - NTL is a lagging indicator (infrastructure investment)
    - NO2 is a leading indicator (operational activity)
    - This is why NO2 gets higher default weight (0.6)
    - In areas with high gas flaring (petrochemical), NTL may overestimate
      actual production — consider adjusting w_ntl down for such ROIs.
    """
    assert abs(w_no2 + w_ntl - 1.0) < 0.01, "Weights must sum to 1.0"

    score = (no2_norm * w_no2) + (ntl_norm * w_ntl)
    return score.clip(0.0, 1.0)


# ──────────────────────────────────────────────
#  Trend Classification
# ──────────────────────────────────────────────

def classify_trend(
    score: pd.Series,
    lookback_months: int = 3,
    yoy_months: int = 12,
) -> Tuple[str, float]:
    """
    Compare recent rolling average vs. same period one year ago.
    
    Returns:
        trend_label: "Growth" | "Stable" | "Contraction" | "Insufficient Data"
        trend_delta: percentage change (positive = growth)
    
    Threshold:
        > +5%  → Growth
        < -5%  → Contraction
        ±5%    → Stable
    """
    if len(score) < lookback_months + 1:
        return "Insufficient Data", 0.0

    recent_avg = score.iloc[-lookback_months:].mean()

    # Try year-over-year comparison
    if len(score) >= yoy_months + lookback_months:
        yoy_start = -(yoy_months + lookback_months)
        yoy_end   = -yoy_months
        prior_avg = score.iloc[yoy_start:yoy_end].mean()
    else:
        # Fallback: compare to overall mean
        prior_avg = score.iloc[:-lookback_months].mean()

    if prior_avg < 1e-6:
        return "Insufficient Data", 0.0

    delta_pct = ((recent_avg - prior_avg) / prior_avg) * 100

    if delta_pct > 5:
        label = "📈 Growth"
    elif delta_pct < -5:
        label = "📉 Contraction"
    else:
        label = "→ Stable"

    return label, round(delta_pct, 1)


# ──────────────────────────────────────────────
#  Demo Data Generator (when GEE unavailable)
# ──────────────────────────────────────────────

def generate_demo_data(start: datetime, end: datetime) -> pd.DataFrame:
    """
    Generate realistic synthetic data for UI preview when GEE is offline.
    Simulates seasonal patterns typical of manufacturing zones.
    """
    periods = pd.date_range(start=start, end=end, freq="MS")
    n = len(periods)

    rng = np.random.default_rng(42)

    # Seasonal NO2 pattern: higher in Q1/Q4 (winter, dry season in tropics)
    seasonal = np.sin(np.linspace(0, 4 * np.pi, n)) * 0.15
    trend    = np.linspace(0, 0.1, n)  # Slight upward trend
    noise    = rng.normal(0, 0.03, n)

    no2_base  = 1.5e-4  # mol/m² — typical industrial zone
    no2_vals  = no2_base * (1 + seasonal + trend + noise)

    ntl_base  = 45.0    # nW/cm²/sr — typical bright industrial zone
    ntl_vals  = ntl_base * (1 + 0.5 * seasonal + 0.5 * trend + rng.normal(0, 0.02, n))

    # Simulate a slowdown period (months 8-10)
    if n > 10:
        no2_vals[7:10] *= 0.65
        ntl_vals[7:10] *= 0.75

    df = pd.DataFrame({
        "date":          periods,
        "no2_mean":      no2_vals,
        "no2_std":       no2_vals * 0.1,
        "ntl_mean":      ntl_vals,
        "ntl_std":       ntl_vals * 0.08,
        "wind_speed":    rng.uniform(2.0, 8.0, n),
        "precipitation": rng.exponential(3.0, n),
        "temperature":   25.0 + rng.normal(0, 3, n),
    }).set_index("date")

    df["no2_corrected"] = apply_meteo_correction(
        df["no2_mean"], df["wind_speed"], df["precipitation"]
    )
    df["no2_norm"] = normalize_series(df["no2_corrected"])
    df["ntl_norm"] = normalize_series(df["ntl_mean"])
    df["activity_score"] = compute_activity_score(df["no2_norm"], df["ntl_norm"])

    return df
