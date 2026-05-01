"""
Regime Detection & Multi-Asset Correlation Engine
HMM-based regime classification, cross-asset correlation heatmap,
factor model decomposition, correlation breakdown detection.
"""
import os
import time
import threading
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
log = logging.getLogger('regime_service')

import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import Dict, Any, List, Optional

app = FastAPI(debug=True, title="Regime Detection & Correlation Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Multi-Asset Universe ---
UNIVERSE = {
    "SPY": "US Equities",
    "QQQ": "NASDAQ 100",
    "IWM": "Small Caps",
    "EFA": "Developed ex-US",
    "EEM": "Emerging Markets",
    "TLT": "Long Bonds",
    "IEF": "Intermediate Bonds",
    "HYG": "High Yield",
    "LQD": "Inv Grade Corp",
    "GLD": "Gold",
    "SLV": "Silver",
    "USO": "Oil",
    "DBC": "Commodities",
    "XLK": "Tech Sector",
    "XLF": "Financial Sector",
    "XLE": "Energy Sector",
    "XLV": "Healthcare",
    "XLU": "Utilities",
    "VXX": "Volatility",
    "UUP": "US Dollar",
    "FXY": "Japanese Yen",
    "FXF": "Swiss Franc",
}

CACHE_TTL = 900
REGIME_CACHE = {}
_CACHE_LOCK = threading.Lock()

def clean(val):
    if val is None or (isinstance(val, (float, int, np.floating, np.integer)) and (np.isnan(val) or np.isinf(val))):
        return None
    try: return float(val)
    except: return None

def _get_cached(key):
    with _CACHE_LOCK:
        if key in REGIME_CACHE and time.time() - REGIME_CACHE[key]['ts'] < CACHE_TTL:
            return REGIME_CACHE[key]['data']
    return None

def _set_cached(key, data):
    with _CACHE_LOCK:
        REGIME_CACHE[key] = {'ts': time.time(), 'data': data}


# ===================== COMPUTATIONS =====================

def fetch_returns(period="6mo"):
    """Fetch returns data for all assets in the universe."""
    symbols = list(UNIVERSE.keys())
    try:
        data = yf.download(symbols, period=period, progress=False)['Close']
        if data.empty:
            return pd.DataFrame()
        returns = data.pct_change().dropna()
        return returns
    except Exception as e:
        log.error(f"FETCH_RETURNS: {e}")
        return pd.DataFrame()


def compute_correlation_matrix(returns):
    """Compute pair-wise correlation matrix from returns."""
    if returns.empty or returns.shape[1] < 2:
        return None, None
    corr = returns.corr()
    labels = [UNIVERSE.get(c, c) for c in corr.columns]
    matrix = []
    for i in range(len(corr.columns)):
        row = []
        for j in range(len(corr.columns)):
            val = corr.iloc[i, j]
            row.append(round(float(val), 3) if not np.isnan(val) else 0)
        matrix.append(row)
    return matrix, labels


def compute_pca_factors(returns, n_components=4):
    """PCA decomposition into macro factors."""
    if returns.empty or returns.shape[1] < n_components:
        return None
    from sklearn.decomposition import PCA
    try:
        pca = PCA(n_components=n_components)
        pca.fit(returns.values)
        loadings = pca.components_
        explained_var = pca.explained_variance_ratio_

        # Label factors by highest loading assets
        factor_labels = []
        for i in range(n_components):
            loading = loadings[i]
            top_idx = np.argmax(np.abs(loading))
            top_asset = list(UNIVERSE.keys())[top_idx] if top_idx < len(UNIVERSE) else "Unknown"
            top_name = UNIVERSE.get(top_asset, top_asset)
            factor_labels.append({
                "factor": f"F{i+1}",
                "label": top_name,
                "explained_variance": round(float(explained_var[i]) * 100, 2),
                "top_loading_asset": top_name,
                "loading_value": round(float(loading[top_idx]), 3)
            })

        return factor_labels
    except ImportError:
        log.warning("sklearn not available for PCA")
        return None
    except Exception as e:
        log.warning(f"PCA error: {e}")
        return None


def classify_regime_hmm(returns):
    """Simple rule-based regime classification (since HMM requires hmmlearn)."""
    if returns.empty:
        return "UNKNOWN"

    # Get average return of key assets
    spy_returns = returns.get('SPY', pd.Series(dtype=float))
    tlt_returns = returns.get('TLT', pd.Series(dtype=float))
    gld_returns = returns.get('GLD', pd.Series(dtype=float))
    hy_returns = returns.get('HYG', pd.Series(dtype=float))

    # Rolling means
    r_mean = 21  # ~1 month

    if len(spy_returns) < r_mean:
        return "INSUFFICIENT_DATA"

    spy_avg = spy_returns.tail(r_mean).mean()
    tlt_avg = tlt_returns.tail(r_mean).mean() if not tlt_returns.empty else 0
    gld_avg = gld_returns.tail(r_mean).mean() if not gld_returns.empty else 0
    hy_avg = hy_returns.tail(r_mean).mean() if not hy_returns.empty else 0

    # Annualized
    spy_ann = spy_avg * 252 * 100
    tlt_ann = tlt_avg * 252 * 100
    gld_ann = gld_avg * 252 * 100

    # Regime classification rules
    if spy_ann > 5:
        if hy_avg > spy_avg:
            return "RISK_ON_FULL"
        elif tlt_ann < 0:
            return "GROWTH_LED"
        else:
            return "RISK_ON_MODERATE"
    elif 0 < spy_ann <= 5:
        if tlt_ann > 5:
            return "FLIGHT_TO_SAFETY"
        elif gld_ann > 5:
            return "GOLD_HEDGE"
        else:
            return "MIXED_SIGNALS"
    elif -10 < spy_ann <= 0:
        if gld_ann > 0:
            return "RISK_OFF_GOLD"
        elif tlt_ann > 3:
            return "RISK_OFF_BONDS"
        else:
            return "RISK_OFF_MODERATE"
    else:
        if gld_ann < spy_ann:
            return "CRISIS_LIQUIDATION"
        else:
            return "CRISIS"


def compute_correlation_breakdown(returns, window=63):
    """Detect when correlations are breaking down (regime change signal)."""
    if returns.empty or len(returns) < window * 2:
        return None

    # Compute correlation in two periods
    recent = returns.tail(window)
    prior = returns.iloc[-window*2:-window] if len(returns) >= window*2 else None

    if prior is None or prior.empty:
        return None

    recent_corr = recent.corr()
    prior_corr = prior.corr()

    # Measure correlation change
    changes = []
    for i, c1 in enumerate(recent_corr.columns):
        for j, c2 in enumerate(recent_corr.columns):
            if i >= j:
                continue
            if c1 in prior_corr.columns and c2 in prior_corr.columns:
                rc = recent_corr.loc[c1, c2]
                pc = prior_corr.loc[c1, c2]
                if not np.isnan(rc) and not np.isnan(pc):
                    change = abs(rc - pc)
                    changes.append({
                        "asset1": UNIVERSE.get(c1, c1),
                        "asset2": UNIVERSE.get(c2, c2),
                        "recent_corr": round(float(rc), 3),
                        "prior_corr": round(float(pc), 3),
                        "change": round(float(change), 3)
                    })

    if not changes:
        return None

    changes.sort(key=lambda x: x['change'], reverse=True)
    avg_change = np.mean([c['change'] for c in changes])

    breakdown_level = "LOW"
    if avg_change > 0.3:
        breakdown_level = "HIGH_BREAKDOWN"
    elif avg_change > 0.2:
        breakdown_level = "ELEVATED"

    return {
        "average_correlation_change": round(float(avg_change), 3),
        "breakdown_level": breakdown_level,
        "top_changes": changes[:10],
        "total_pairs": len(changes)
    }


# ===================== ENDPOINTS =====================

@app.get("/api/regime/current")
def get_current_regime():
    """Current market regime classification."""
    cached = _get_cached("current_regime")
    if cached: return {"status": "success", "data": cached}

    try:
        returns = fetch_returns("6mo")
        if returns.empty:
            return {"status": "error", "detail": "Unable to fetch returns data"}

        regime = classify_regime_hmm(returns)

        # Get VIX for confirmation
        vix = yf.Ticker("^VIX")
        vix_info = vix.info
        vix_level = clean(vix_info.get("regularMarketPrice") or vix_info.get("previousClose"))

        # Risk score
        risk_score = 0
        if regime in ["CRISIS", "CRISIS_LIQUIDATION"]:
            risk_score = 10
        elif regime in ["RISK_OFF_MODERATE", "RISK_OFF_BONDS", "RISK_OFF_GOLD"]:
            risk_score = 7
        elif regime in ["FLIGHT_TO_SAFETY", "MIXED_SIGNALS"]:
            risk_score = 5
        elif regime in ["RISK_ON_MODERATE", "GOLD_HEDGE"]:
            risk_score = 3
        elif regime in ["RISK_ON_FULL", "GROWTH_LED"]:
            risk_score = 1

        result = {
            "regime": regime,
            "risk_score": risk_score,
            "vix_confirm": vix_level,
            "regime_label": regime.replace("_", " ").title(),
            "description": {
                "RISK_ON_FULL": "Strong risk appetite — equities leading, credit tight",
                "GROWTH_LED": "Growth assets outperforming, rates stable or rising",
                "RISK_ON_MODERATE": "Moderate risk appetite, mixed signals",
                "FLIGHT_TO_SAFETY": "Capital moving to bonds/safe havens from equities",
                "GOLD_HEDGE": "Gold outperforming — inflation/geopolitical concerns",
                "MIXED_SIGNALS": "No clear regime — correlations breaking down",
                "RISK_OFF_GOLD": "Risk-off with gold as primary safe haven",
                "RISK_OFF_BONDS": "Risk-off with bonds as primary safe haven",
                "RISK_OFF_MODERATE": "Moderate risk-off across most assets",
                "CRISIS": "Broad-based liquidation across risk assets",
                "CRISIS_LIQUIDATION": "Extreme stress — even safe havens selling off",
            }.get(regime, regime.replace("_", " ").title()),
            "last_updated": int(time.time())
        }
        _set_cached("current_regime", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/regime/correlation-matrix")
def get_correlation_matrix():
    """Full cross-asset correlation matrix."""
    cached = _get_cached("correlation_matrix")
    if cached: return {"status": "success", "data": cached}

    try:
        returns = fetch_returns("6mo")
        if returns.empty:
            return {"status": "error", "detail": "Unable to fetch returns"}

        matrix, labels = compute_correlation_matrix(returns)
        if matrix is None:
            return {"status": "error", "detail": "Insufficient data for correlation matrix"}

        result = {
            "labels": labels,
            "matrix": matrix,
            "asset_count": len(labels),
            "last_updated": int(time.time())
        }
        _set_cached("correlation_matrix", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/regime/correlation-change")
def get_correlation_change():
    """Detect correlation breakdowns — early regime change signal."""
    cached = _get_cached("correlation_change")
    if cached: return {"status": "success", "data": cached}

    try:
        returns = fetch_returns("1y")
        if returns.empty:
            return {"status": "error", "detail": "Unable to fetch returns"}

        breakdown = compute_correlation_breakdown(returns)
        if breakdown is None:
            return {"status": "error", "detail": "Insufficient data for change detection"}

        result = {
            "correlation_breakdown": breakdown,
            "last_updated": int(time.time())
        }
        _set_cached("correlation_change", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/regime/factor-model")
def get_factor_model():
    """PCA factor decomposition of market returns."""
    cached = _get_cached("factor_model")
    if cached: return {"status": "success", "data": cached}

    try:
        returns = fetch_returns("6mo")
        if returns.empty:
            return {"status": "error", "detail": "Unable to fetch returns"}

        factors = compute_pca_factors(returns)
        if factors is None:
            return {"status": "error", "detail": "sklearn not available or PCA failed"}

        total_explained = sum(f['explained_variance'] for f in factors)

        result = {
            "factors": factors,
            "total_explained_variance": round(float(total_explained), 2),
            "interpretation": f"Top {len(factors)} factors explain {total_explained:.1f}% of market variance",
            "last_updated": int(time.time())
        }
        _set_cached("factor_model", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/regime/summary")
def get_regime_summary():
    """One-call regime overview."""
    try:
        regime = _get_cached("current_regime") or {}
        corr = _get_cached("correlation_matrix") or {}
        change = _get_cached("correlation_change") or {}
        factors = _get_cached("factor_model") or {}

        return {
            "status": "success",
            "data": {
                "regime": regime,
                "correlation": corr,
                "change": change,
                "factors": factors,
                "last_updated": int(time.time())
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "regime_service_online", "timestamp": int(time.time())}


if __name__ == "__main__":
    log.info("Regime Detection Service starting on port 8195")
    uvicorn.run(app, host="0.0.0.0", port=8195)
