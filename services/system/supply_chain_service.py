"""
3.3 — SUPPLY CHAIN PRESSURE INDEX SERVICE
Integrated OSINT intelligence for global supply chain monitoring.
Combines:
  - AIS vessel traffic (ports/congestion)
  - yfinance commodity prices (copper, lumber, oil, grains, container rates)
  - Macro indicators (PMI, freight rates proxy)
  - Composite pressure index

Port: 8210
"""

import os
import time
import asyncio
import threading
import logging
import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import Dict, Any, List, Optional

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
log = logging.getLogger('supply_chain_service')

app = FastAPI(debug=True, title="Supply Chain Pressure Index Microservice")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# SUPPLY CHAIN COMPONENTS
# ============================================================================

# Key commodities that drive supply chain costs
SUPPLY_CHAIN_TICKERS = {
    "CL=F": {"name": "Crude Oil WTI", "weight": 0.20, "category": "energy"},
    "BZ=F": {"name": "Brent Crude", "weight": 0.10, "category": "energy"},
    "NG=F": {"name": "Natural Gas", "weight": 0.08, "category": "energy"},
    "HG=F": {"name": "Copper", "weight": 0.15, "category": "industrial"},
    "LBS=F": {"name": "Lumber", "weight": 0.10, "category": "industrial"},
    "ZC=F": {"name": "Corn", "weight": 0.05, "category": "agriculture"},
    "ZW=F": {"name": "Wheat", "weight": 0.05, "category": "agriculture"},
    "ALI=F": {"name": "Aluminum", "weight": 0.08, "category": "industrial"},
    "RT=F": {"name": "Rubber", "weight": 0.04, "category": "industrial"},
    "ZS=F": {"name": "Soybeans", "weight": 0.05, "category": "agriculture"},
}

# Freight rate proxies via container/shipping ETFs
FREIGHT_PROXIES = {
    "SEA.L": {"name": "Clarksons Sea Index", "weight": 0.05, "category": "freight"},
    "MATX": {"name": "Matson Inc (Shipping)", "weight": 0.02, "category": "freight"},
    "ZIM": {"name": "ZIM Shipping", "weight": 0.02, "category": "freight"},
}

# PMI proxies via sector ETFs
PMI_PROXIES = {
    "XLI": {"name": "Manufacturing PMI Proxy", "weight": 0.06, "category": "pmi"},
}

# ============================================================================
# CACHE
# ============================================================================
SC_CACHE = {}
SC_CACHE_TTL = 900  # 15 minutes
_CACHE_LOCK = threading.Lock()

def _get_cache(key):
    entry = SC_CACHE.get(key)
    if entry and time.time() - entry['ts'] < SC_CACHE_TTL:
        return entry['data']
    return None

def _set_cache(key, data):
    SC_CACHE[key] = {'ts': time.time(), 'data': data}

def clean_data(obj):
    if isinstance(obj, (float, int, np.floating, np.integer)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    elif isinstance(obj, dict):
        return {k: clean_data(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_data(x) for x in obj]
    return obj


# ============================================================================
# COMPOSITE INDEX COMPUTATION
# ============================================================================

def _compute_composite_index():
    """Compute the Supply Chain Pressure Index from all sub-components.
    Returns dict with overall index value, category breakdown, and component details.
    The index is scaled 0-100 where:
      0  = minimal pressure (healthy supply chain)
      50 = normal/historical average
      100 = maximum pressure (crisis conditions)
    """
    results = {}
    component_prices = {}
    category_scores = {}
    total_weight = 0

    # 1. Fetch commodity prices and compute z-scores
    for ticker, meta in SUPPLY_CHAIN_TICKERS.items():
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period="1y")
            if hist.empty or len(hist) < 20:
                continue

            current_price = hist['Close'].iloc[-1]
            mean_price = hist['Close'].mean()
            std_price = hist['Close'].std()

            if std_price == 0:
                continue

            # Z-score: how many std devs above/below 1-year average
            z_score = (current_price - mean_price) / std_price

            # Convert z-score to 0-100 pressure scale
            # z=0 -> 50, z=+2 -> 85, z=-2 -> 15
            pressure = min(100, max(0, 50 + z_score * 17.5))

            component_prices[ticker] = current_price
            results[ticker] = {
                "name": meta["name"],
                "category": meta["category"],
                "current_price": float(current_price),
                "z_score": round(float(z_score), 2),
                "pressure_score": round(pressure, 1),
                "weight": meta["weight"],
                "1y_mean": float(mean_price),
                "1y_std": float(std_price),
                "1y_high": float(hist['Close'].max()),
                "1y_low": float(hist['Close'].min())
            }

            # Accumulate category scores
            cat = meta["category"]
            if cat not in category_scores:
                category_scores[cat] = {"score": 0, "weight": 0}
            category_scores[cat]["score"] += pressure * meta["weight"]
            category_scores[cat]["weight"] += meta["weight"]
            total_weight += meta["weight"]

        except Exception as e:
            log.warning(f"SC_INDEX [{ticker}]: {e}")
            continue
        time.sleep(0.1)

    # 2. Fetch freight proxies (stock-based)
    for ticker, meta in FREIGHT_PROXIES.items():
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period="6mo")
            if hist.empty or len(hist) < 10:
                continue

            current_price = hist['Close'].iloc[-1]
            # 3-month change as pressure signal
            p3m = hist['Close'].iloc[-63] if len(hist) >= 63 else hist['Close'].iloc[0]
            perf_3m = ((current_price / p3m) - 1) * 100

            # Positive change = higher pressure (shipping costs up)
            pressure = min(100, max(0, 50 + perf_3m * 2))

            results[ticker] = {
                "name": meta["name"],
                "category": meta["category"],
                "current_price": float(current_price),
                "perf_3m_pct": round(perf_3m, 2),
                "pressure_score": round(pressure, 1),
                "weight": meta["weight"]
            }

            cat = meta["category"]
            if cat not in category_scores:
                category_scores[cat] = {"score": 0, "weight": 0}
            category_scores[cat]["score"] += pressure * meta["weight"]
            category_scores[cat]["weight"] += meta["weight"]
            total_weight += meta["weight"]

        except Exception as e:
            log.warning(f"SC_FREIGHT [{ticker}]: {e}")
            continue
        time.sleep(0.1)

    # 3. PMI Proxy (XLI — Industrials ETF as PMI indicator)
    for ticker, meta in PMI_PROXIES.items():
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period="6mo")
            if hist.empty or len(hist) < 10:
                continue

            current_price = hist['Close'].iloc[-1]
            perf_3m = ((current_price / hist['Close'].iloc[-63]) - 1) * 100 if len(hist) >= 63 else 0

            # PMI: when industrial stocks fall = economic pressure up
            pressure = min(100, max(0, 50 - perf_3m * 1.5))

            results[ticker] = {
                "name": meta["name"],
                "category": meta["category"],
                "current_price": float(current_price),
                "perf_3m_pct": round(perf_3m, 2),
                "pressure_score": round(pressure, 1),
                "weight": meta["weight"]
            }

            cat = meta["category"]
            if cat not in category_scores:
                category_scores[cat] = {"score": 0, "weight": 0}
            category_scores[cat]["score"] += pressure * meta["weight"]
            category_scores[cat]["weight"] += meta["weight"]
            total_weight += meta["weight"]

        except Exception as e:
            log.warning(f"SC_PMI [{ticker}]: {e}")
            continue
        time.sleep(0.1)

    # 4. Compute overall composite index
    weighted_sum = sum(
        v["pressure_score"] * v["weight"]
        for v in results.values()
        if "pressure_score" in v
    )

    composite_index = round(weighted_sum / total_weight, 1) if total_weight > 0 else 50.0

    # Normalize category scores
    normalized_categories = {}
    for cat, data in category_scores.items():
        if data["weight"] > 0:
            normalized_categories[cat] = round(data["score"] / data["weight"], 1)
        else:
            normalized_categories[cat] = 50.0

    # Determine pressure regime
    if composite_index >= 75:
        regime = "CRISIS"
    elif composite_index >= 60:
        regime = "ELEVATED"
    elif composite_index >= 40:
        regime = "NORMAL"
    elif composite_index >= 25:
        regime = "LOW"
    else:
        regime = "MINIMAL"

    return {
        "composite_index": composite_index,
        "regime": regime,
        "category_scores": normalized_categories,
        "components": clean_data(results),
        "total_components": len(results),
        "timestamp": time.time()
    }


@app.get("/api/supply-chain/index")
async def get_supply_chain_index(refresh: bool = False):
    """Get the Supply Chain Pressure Index (0-100 scale)."""
    if not refresh:
        cached = _get_cache("composite_index")
        if cached:
            return {"status": "success", "data": cached, "cached": True}

    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, _compute_composite_index)
    _set_cache("composite_index", data)
    return {"status": "success", "data": data}


@app.get("/api/supply-chain/components")
async def get_supply_chain_components():
    """Get detailed breakdown of all supply chain components with their individual pressure scores."""
    cached = _get_cache("composite_index")
    if cached:
        components = cached.get("components", {})
        return {"status": "success", "data": components}

    return {"status": "loading", "message": "Data is being computed, try again in a moment"}


@app.get("/api/supply-chain/categories")
async def get_supply_chain_categories():
    """Get pressure scores broken down by category (energy, industrial, agriculture, freight, pmi)."""
    cached = _get_cache("composite_index")
    if cached:
        return {
            "status": "success",
            "data": {
                "category_scores": cached.get("category_scores", {}),
                "composite_index": cached.get("composite_index"),
                "regime": cached.get("regime")
            }
        }
    return {"status": "loading", "message": "Data is being computed, try again in a moment"}


@app.get("/api/supply-chain/timeline")
async def get_supply_chain_timeline(days: int = 90):
    """Get historical supply chain pressure (estimated from key components)."""
    try:
        loop = asyncio.get_event_loop()

        def _compute_timeline():
            # Use Crude Oil + Copper + Lumber as primary historical indicators
            primary = ["CL=F", "HG=F", "LBS=F"]
            points = []

            # Get 3 months of daily data
            end_date = pd.Timestamp.now()
            start_date = end_date - pd.Timedelta(days=days)

            for ticker in primary:
                try:
                    tk = yf.Ticker(ticker)
                    hist = tk.history(start=start_date.strftime('%Y-%m-%d'), end=end_date.strftime('%Y-%m-%d'))
                    if hist.empty:
                        continue

                    # Compute z-score for each day
                    mean_p = hist['Close'].mean()
                    std_p = hist['Close'].std()
                    if std_p == 0:
                        continue

                    for idx, row in hist.iterrows():
                        z = (row['Close'] - mean_p) / std_p
                        pressure = min(100, max(0, 50 + z * 17.5))
                        date_str = str(idx.date())
                        points.append({
                            "date": date_str,
                            "ticker": ticker,
                            "pressure": round(pressure, 1),
                            "price": float(row['Close'])
                        })
                except:
                    continue

            return points

        data = await loop.run_in_executor(None, _compute_timeline)
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/supply-chain/summary")
async def get_supply_chain_summary():
    """Quick summary of supply chain health."""
    cached = _get_cache("composite_index")
    if cached:
        return {
            "status": "success",
            "data": {
                "index": cached["composite_index"],
                "regime": cached["regime"],
                "categories": cached.get("category_scores", {}),
                "timestamp": cached["timestamp"]
            }
        }

    # Compute on-demand if cache is cold
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, _compute_composite_index)
    _set_cache("composite_index", data)
    return {
        "status": "success",
        "data": {
            "index": data["composite_index"],
            "regime": data["regime"],
            "categories": data.get("category_scores", {}),
            "timestamp": data["timestamp"]
        }
    }


@app.get("/")
async def root():
    return {"status": "online", "service": "supply_chain_pressure_index", "port": 8210}

@app.on_event("startup")
async def startup_event():
    # Pre-warm cache on startup
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(None, _compute_composite_index)
        _set_cache("composite_index", data)
        log.info(f"SC_INDEX: Cache pre-warmed. Index = {data['composite_index']}, Regime = {data['regime']}")
    except Exception as e:
        log.warning(f"SC_INDEX: Pre-warm failed: {e}")

if __name__ == "__main__":
    print("=:: LAUNCHING SUPPLY CHAIN PRESSURE INDEX SERVICE (Port 8210) ::= ")
    uvicorn.run(app, host="0.0.0.0", port=8210)
