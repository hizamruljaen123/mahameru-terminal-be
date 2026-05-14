"""
Volatility & Risk Intelligence Microservice
VIX, VIX term structure, volatility regime detection, cross-asset volatility.
Powered by yfinance.
"""
import os
import time
import threading
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
log = logging.getLogger('volatility_service')

import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import Dict, Any, List, Optional

app = FastAPI(debug=True, title="Volatility & Risk Intelligence Microservice")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Volatility Symbols ---
VOLATILITY_SYMBOLS = {
    "VIX": "^VIX",
    "VVIX": "^VVIX",  # VIX of VIX (implied vol of VIX options)
    "VXZ": "VXZ",     # VIX Mid-Term Futures ETN
    "VIXY": "VIXY",    # Short-Term VIX Futures ETF
    "UVXY": "UVXY",    # 1.5x Short-Term VIX Futures
    "SVXY": "SVXY",    # 1x Short VIX Futures
    "VXX": "VXX",      # Short-Term VIX Futures ETN
}

# --- Cross-asset volatility proxies ---
CROSS_ASSET_VOL = {
    "SPY": "SPY",
    "QQQ": "QQQ",
    "GLD": "GLD",
    "SLV": "SLV",
    "USO": "USO",
    "TLT": "TLT",
    "DXY": "DX-Y.NYB",
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
}

# --- Cache ---
VOL_CACHE = {}
_CACHE_LOCK = threading.Lock()
CACHE_TTL = 300  # 5 minutes

def clean(val):
    if val is None or (isinstance(val, (float, int, np.floating, np.integer)) and (np.isnan(val) or np.isinf(val))):
        return None
    try: return float(val)
    except: return None

def _get_cached(key):
    with _CACHE_LOCK:
        if key in VOL_CACHE and time.time() - VOL_CACHE[key]['ts'] < CACHE_TTL:
            return VOL_CACHE[key]['data']
    return None

def _set_cached(key, data):
    with _CACHE_LOCK:
        VOL_CACHE[key] = {'ts': time.time(), 'data': data}


# ===================== COMPUTATIONS =====================

def compute_realized_vol(prices, window=21):
    """Compute annualized realized volatility from price series."""
    if len(prices) < 2:
        return 0
    returns = np.diff(np.log(prices))
    if len(returns) < window:
        window = len(returns)
    if window < 2:
        return float(np.std(returns) * np.sqrt(252) * 100)
    rolling_vol = []
    for i in range(len(returns) - window + 1):
        vol = np.std(returns[i:i+window]) * np.sqrt(252) * 100
        rolling_vol.append(vol)
    return rolling_vol


def classify_vol_regime(vix_level, vix_percentile=None):
    """Classify volatility regime based on VIX level."""
    if vix_level is None:
        return "UNKNOWN"
    if vix_level < 12:
        return "LOW_VOL"
    elif vix_level < 18:
        return "NORMAL"
    elif vix_level < 25:
        return "ELEVATED"
    elif vix_level < 35:
        return "HIGH"
    else:
        return "CRISIS"


# ===================== ENDPOINTS =====================

@app.get("/api/volatility/vix")
def get_vix():
    """Current VIX with historical context and percentile rank."""
    cached = _get_cached("vix")
    if cached: return {"status": "success", "data": cached}

    try:
        t = yf.Ticker("^VIX")
        info = t.info
        hist = t.history(period="1y")

        vix_current = clean(info.get("regularMarketPrice") or info.get("previousClose"))
        vix_prev_close = clean(info.get("previousClose"))

        if hist.empty:
            return {"status": "error", "detail": "No VIX data available"}

        # Historical statistics
        closes = hist['Close'].values
        vix_1w = closes[-5:].mean() if len(closes) >= 5 else vix_current
        vix_1m = closes[-21:].mean() if len(closes) >= 21 else vix_current
        vix_1y_avg = closes.mean()
        vix_min = float(closes.min())
        vix_max = float(closes.max())

        # Percentile rank
        if vix_current is not None:
            rank = sum(1 for c in closes if c <= vix_current) / len(closes) * 100
        else:
            rank = 50

        # History for charting
        history = []
        for ts, r in hist.iterrows():
            history.append({
                "date": ts.strftime('%Y-%m-%d'),
                "vix": round(float(r['Close']), 2),
                "open": round(float(r['Open']), 2),
                "high": round(float(r['High']), 2),
                "low": round(float(r['Low']), 2)
            })

        change = round(vix_current - vix_prev_close, 2) if vix_current and vix_prev_close else 0
        change_pct = round((change / vix_prev_close) * 100, 2) if vix_prev_close and vix_prev_close != 0 else 0

        regime = classify_vol_regime(vix_current, rank)

        result = {
            "current": {
                "vix": vix_current,
                "change": change,
                "change_pct": change_pct,
                "prev_close": vix_prev_close
            },
            "statistics": {
                "1w_avg": round(float(vix_1w), 2),
                "1m_avg": round(float(vix_1m), 2),
                "1y_avg": round(float(vix_1y_avg), 2),
                "1y_min": round(vix_min, 2),
                "1y_max": round(vix_max, 2),
                "percentile_rank": round(float(rank), 1)
            },
            "regime": regime,
            "history": history[-252:],
            "last_updated": int(time.time())
        }
        _set_cached("vix", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/volatility/vix-term-structure")
def get_vix_term_structure():
    """VIX futures curve — contango/backwardation detection."""
    cached = _get_cached("vix_term")
    if cached: return {"status": "success", "data": cached}

    try:
        # Use VIX ETFs as proxy for futures curve
        # VIXY = 1-month, VXZ = 5-month, VXX = 1-month rolling
        proxies = {
            "spot":  ("^VIX", "VIX Spot"),
            "m1":    ("VIXY", "1-Month VIX Futures"),
            "m2":    ("VXX",  "Short-Term VIX Futures"),
            "m5":    ("VXZ",  "Mid-Term VIX Futures"),
            "inverse": ("SVXY", "Short VIX (1x Inverse)")
        }

        curve = []
        for label, (sym, name) in proxies.items():
            try:
                t = yf.Ticker(sym)
                info = t.info
                price = clean(info.get("regularMarketPrice") or info.get("previousClose") or info.get("navPrice"))
                change = clean(info.get("regularMarketChangePercent"))
                curve.append({
                    "label": label,
                    "name": name,
                    "symbol": sym,
                    "price": price,
                    "change_pct": change
                })
            except Exception as e:
                log.warning(f"VIX_TERM[{label}/{sym}]: {e}")

        # Determine contango vs backwardation
        spot_val = None
        m1_val = None
        for c in curve:
            if c['label'] == 'spot': spot_val = c['price']
            if c['label'] == 'm1': m1_val = c['price']

        structure = "FLAT"
        if spot_val and m1_val:
            diff = m1_val - spot_val
            if diff > 0.5:
                structure = "CONTANGO"
            elif diff < -0.5:
                structure = "BACKWARDATION"

        result = {
            "curve": curve,
            "structure": structure,
            "spot_future_diff": round(m1_val - spot_val, 2) if spot_val and m1_val else None,
            "last_updated": int(time.time())
        }
        _set_cached("vix_term", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/volatility/regime")
def get_vol_regime():
    """Volatility regime detection combining VIX, realized vol, and cross-asset signals."""
    cached = _get_cached("vol_regime")
    if cached: return {"status": "success", "data": cached}

    try:
        # Get VIX
        vix = yf.Ticker("^VIX")
        vix_info = vix.info
        vix_current = clean(vix_info.get("regularMarketPrice") or vix_info.get("previousClose"))
        vix_hist = vix.history(period="6mo")

        # Get SPY realized vol
        spy = yf.Ticker("SPY")
        spy_hist = spy.history(period="6mo")

        # Get QQQ realized vol
        qqq = yf.Ticker("QQQ")
        qqq_hist = qqq.history(period="6mo")

        # Compute realized vols
        spy_vols = {}
        qqq_vols = {}
        if not spy_hist.empty:
            spy_close = spy_hist['Close'].values
            spy_vols['10d'] = round(float(np.std(np.diff(np.log(spy_close[-10:]))) * np.sqrt(252) * 100), 2) if len(spy_close) >= 11 else 0
            spy_vols['21d'] = round(float(np.std(np.diff(np.log(spy_close[-21:]))) * np.sqrt(252) * 100), 2) if len(spy_close) >= 22 else 0
            spy_vols['63d'] = round(float(np.std(np.diff(np.log(spy_close[-63:]))) * np.sqrt(252) * 100), 2) if len(spy_close) >= 64 else 0

        if not qqq_hist.empty:
            qqq_close = qqq_hist['Close'].values
            qqq_vols['10d'] = round(float(np.std(np.diff(np.log(qqq_close[-10:]))) * np.sqrt(252) * 100), 2) if len(qqq_close) >= 11 else 0
            qqq_vols['21d'] = round(float(np.std(np.diff(np.log(qqq_close[-21:]))) * np.sqrt(252) * 100), 2) if len(qqq_close) >= 22 else 0
            qqq_vols['63d'] = round(float(np.std(np.diff(np.log(qqq_close[-63:]))) * np.sqrt(252) * 100), 2) if len(qqq_close) >= 64 else 0

        # Historical volatility percentiles
        vix_percentile = 50
        if not vix_hist.empty and vix_current:
            closes = vix_hist['Close'].values
            vix_percentile = sum(1 for c in closes if c <= vix_current) / len(closes) * 100

        regime = classify_vol_regime(vix_current, vix_percentile)

        # Composite signal
        risk_level = "LOW"
        if vix_current:
            if vix_current > 25: risk_level = "HIGH"
            elif vix_current > 18: risk_level = "MEDIUM"

        result = {
            "current_regime": regime,
            "risk_level": risk_level,
            "vix": {
                "current": vix_current,
                "percentile_6m": round(float(vix_percentile), 1)
            },
            "realized_vol": {
                "SPY": spy_vols,
                "QQQ": qqq_vols
            },
            "composite_signals": {
                "fear_gauge": "HIGH_FEAR" if vix_current and vix_current > 25 else ("MODERATE_FEAR" if vix_current and vix_current > 18 else "LOW_FEAR"),
                "vol_regime_label": regime
            },
            "last_updated": int(time.time())
        }
        _set_cached("vol_regime", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/volatility/cross-asset")
def get_cross_asset_volatility():
    """Cross-asset volatility comparison — which assets are most volatile."""
    cached = _get_cached("cross_asset_vol")
    if cached: return {"status": "success", "data": cached}

    try:
        results = []
        for name, symbol in CROSS_ASSET_VOL.items():
            try:
                t = yf.Ticker(symbol)
                hist = t.history(period="3mo")
                if hist.empty:
                    continue
                closes = hist['Close'].values
                if len(closes) < 5:
                    continue

                # 21-day realized vol
                returns = np.diff(np.log(closes))
                vol_21d = float(np.std(returns[-21:]) * np.sqrt(252) * 100) if len(returns) >= 21 else 0
                vol_63d = float(np.std(returns[-63:]) * np.sqrt(252) * 100) if len(returns) >= 63 else 0

                results.append({
                    "asset": name,
                    "symbol": symbol,
                    "realized_vol_21d": round(vol_21d, 2),
                    "realized_vol_63d": round(vol_63d, 2),
                    "vol_change_ratio": round(vol_21d / vol_63d, 2) if vol_63d > 0 else 0
                })
            except Exception as e:
                log.warning(f"CROSS_VOL[{name}/{symbol}]: {e}")

        # Sort by vol (highest first)
        results.sort(key=lambda x: x['realized_vol_21d'], reverse=True)

        # Average vol across all assets
        avg_vol = np.mean([r['realized_vol_21d'] for r in results]) if results else 0

        result = {
            "assets": results,
            "average_vol_21d": round(float(avg_vol), 2),
            "most_volatile": results[0]['asset'] if results else None,
            "least_volatile": results[-1]['asset'] if results else None,
            "last_updated": int(time.time())
        }
        _set_cached("cross_asset_vol", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/volatility/summary")
def get_vol_summary():
    """Aggregated volatility summary — one-call overview."""
    try:
        vix_data = _get_cached("vix") or {}
        regime_data = _get_cached("vol_regime") or {}
        cross_data = _get_cached("cross_asset_vol") or {}

        return {
            "status": "success",
            "data": {
                "vix": vix_data,
                "regime": regime_data,
                "cross_asset": cross_data,
                "last_updated": int(time.time())
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "volatility_service_online", "timestamp": int(time.time())}


if __name__ == "__main__":
    log.info("Volatility & Risk Service starting on port 8155")
    uvicorn.run(app, host="0.0.0.0", port=8155)
