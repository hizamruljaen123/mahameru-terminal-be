"""
Global Capital Flow Monitor Microservice
Tracks ETF flows, emerging market flows, risk parity, safe haven flows, rotation signals.
Powered by yfinance.
"""
import os
import time
import threading
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
log = logging.getLogger('capital_flow_service')

import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import Dict, Any, List, Optional

app = FastAPI(debug=True, title="Global Capital Flow Monitor Microservice")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Major ETFs by category ---
ETF_CATEGORIES = {
    "US_Equities": {
        "SPY": "S&P 500",
        "QQQ": "NASDAQ 100",
        "IWM": "Russell 2000",
        "DIA": "Dow Jones",
        "VTI": "Total US Stock Market",
    },
    "International": {
        "EFA": "EAFE (Developed ex-US)",
        "VWO": "Emerging Markets",
        "EEM": "iShares Emerging Markets",
        "VXUS": "Total International Stock",
        "EWJ": "Japan",
        "EWZ": "Brazil",
        "FXI": "China Large-Cap",
        "INDA": "India",
        "EWT": "Taiwan",
        "EWY": "South Korea",
    },
    "Fixed_Income": {
        "TLT": "20+ Year Treasury",
        "IEF": "7-10 Year Treasury",
        "SHY": "1-3 Year Treasury",
        "LQD": "Investment Grade Corp",
        "HYG": "High Yield Corp",
        "EMB": "Emerging Market Bonds",
        "BND": "Total Bond Market",
    },
    "Commodities": {
        "GLD": "Gold",
        "SLV": "Silver",
        "USO": "Oil",
        "DBC": "Diversified Commodities",
        "GSG": "Broad Commodities",
    },
    "Sector": {
        "XLK": "Technology",
        "XLF": "Financials",
        "XLE": "Energy",
        "XLV": "Healthcare",
        "XLI": "Industrials",
        "XLP": "Consumer Staples",
        "XLY": "Consumer Discretionary",
        "XLU": "Utilities",
        "XLRE": "Real Estate",
        "XLC": "Communications",
        "XLB": "Materials",
    },
    "Factor": {
        "MTUM": "Momentum",
        "QUAL": "Quality",
        "SIZE": "Size",
        "VLUE": "Value",
        "USMV": "Low Volatility",
        "IVE": "S&P 500 Value",
        "IVW": "S&P 500 Growth",
    },
    "Safe_Haven": {
        "GLD": "Gold",
        "TLT": "Long Treasury",
        "SHV": "Short Treasury",
        "UUP": "US Dollar Bullish",
        "FXF": "Swiss Franc",
    },
}

# --- Cache ---
FLOW_CACHE = {}
_CACHE_LOCK = threading.Lock()
CACHE_TTL = 600  # 10 minutes

def clean(val):
    if val is None or (isinstance(val, (float, int, np.floating, np.integer)) and (np.isnan(val) or np.isinf(val))):
        return None
    try: return float(val)
    except: return None

def _get_cached(key):
    with _CACHE_LOCK:
        if key in FLOW_CACHE and time.time() - FLOW_CACHE[key]['ts'] < CACHE_TTL:
            return FLOW_CACHE[key]['data']
    return None

def _set_cached(key, data):
    with _CACHE_LOCK:
        FLOW_CACHE[key] = {'ts': time.time(), 'data': data}

def compute_flow_proxy(hist):
    """Compute flow proxy from price/volume data.
    Flow = Volume × Price Change (positive = buying pressure, negative = selling pressure)
    Normalized by average flow.
    """
    if hist.empty or len(hist) < 5:
        return 0, 0, 0
    flows = []
    for i in range(1, len(hist)):
        price_change = hist['Close'].iloc[i] - hist['Close'].iloc[i-1]
        vol = hist['Volume'].iloc[i]
        flow = price_change * vol
        flows.append(flow)

    if not flows:
        return 0, 0, 0

    recent_flow = sum(flows[-5:])
    prev_flow = sum(flows[-10:-5]) if len(flows) >= 10 else 0
    avg_abs_flow = np.mean(np.abs(flows)) if flows else 1

    return recent_flow, prev_flow, float(avg_abs_flow)


# ===================== ENDPOINTS =====================

@app.get("/api/capital-flows/etf-flows")
def get_etf_flows():
    """Aggregate ETF flow analysis across all categories."""
    cached = _get_cached("etf_flows")
    if cached: return {"status": "success", "data": cached}

    try:
        categories = {}
        all_flow_signals = []

        for cat_name, etfs in ETF_CATEGORIES.items():
            etf_data = []
            cat_flow = 0
            for symbol, name in etfs.items():
                try:
                    t = yf.Ticker(symbol)
                    info = t.info
                    hist = t.history(period="3mo")
                    if hist.empty:
                        continue

                    price = clean(info.get("regularMarketPrice") or info.get("previousClose"))
                    change = clean(info.get("regularMarketChangePercent"))

                    recent_flow, prev_flow, avg_flow = compute_flow_proxy(hist)

                    # Flow signal
                    if avg_flow > 0:
                        flow_ratio = recent_flow / avg_flow if avg_flow != 0 else 0
                    else:
                        flow_ratio = 0

                    direction = "NEUTRAL"
                    if flow_ratio > 1.5:
                        direction = "STRONG_INFLOW"
                    elif flow_ratio > 0.5:
                        direction = "INFLOW"
                    elif flow_ratio < -1.5:
                        direction = "STRONG_OUTFLOW"
                    elif flow_ratio < -0.5:
                        direction = "OUTFLOW"

                    cat_flow += recent_flow

                    etf_data.append({
                        "symbol": symbol,
                        "name": name,
                        "price": price,
                        "change_pct": change,
                        "flow_proxy": round(float(recent_flow), 0),
                        "flow_signal": direction,
                        "avg_daily_flow": round(float(avg_flow), 0)
                    })
                except Exception as e:
                    log.warning(f"FLOW[{cat_name}/{symbol}]: {e}")

            categories[cat_name] = {
                "etfs": etf_data,
                "category_flow": round(float(cat_flow), 0),
                "direction": "INFLOW" if cat_flow > 0 else "OUTFLOW"
            }
            if etf_data:
                all_flow_signals.append({
                    "category": cat_name,
                    "flow": round(float(cat_flow), 0),
                    "direction": "INFLOW" if cat_flow > 0 else "OUTFLOW"
                })

        # Sort categories by flow magnitude
        all_flow_signals.sort(key=lambda x: abs(x['flow']), reverse=True)

        result = {
            "categories": categories,
            "summary": {
                "categories_with_inflow": sum(1 for x in all_flow_signals if x['flow'] > 0),
                "categories_with_outflow": sum(1 for x in all_flow_signals if x['flow'] < 0),
                "top_inflow_category": all_flow_signals[0]['category'] if all_flow_signals and all_flow_signals[0]['flow'] > 0 else None,
                "top_outflow_category": all_flow_signals[0]['category'] if all_flow_signals and all_flow_signals[0]['flow'] < 0 else None,
            },
            "last_updated": int(time.time())
        }
        _set_cached("etf_flows", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/capital-flows/rotation-signal")
def get_rotation_signal():
    """Capital rotation signal — which asset classes are gaining/losing flows."""
    cached = _get_cached("rotation_signal")
    if cached: return {"status": "success", "data": cached}

    try:
        # Compare performance of major asset classes
        # Equities (SPY) vs Bonds (TLT) vs Gold (GLD) vs Cash (SHV)
        proxies = {
            "Equities": "SPY",
            "Bonds": "TLT",
            "Gold": "GLD",
            "Cash": "SHV",
            "Commodities": "DBC",
            "EM_Equities": "EEM",
            "REITs": "VNQ",
        }

        perf_data = []
        for name, symbol in proxies.items():
            try:
                t = yf.Ticker(symbol)
                hist = t.history(period="3mo")
                if hist.empty:
                    continue

                closes = hist['Close'].values
                ret_1w = ((closes[-1] - closes[-6]) / closes[-6] * 100) if len(closes) >= 6 else 0
                ret_1m = ((closes[-1] - closes[-22]) / closes[-22] * 100) if len(closes) >= 22 else 0
                ret_3m = ((closes[-1] - closes[0]) / closes[0] * 100) if len(closes) >= 2 else 0

                perf_data.append({
                    "asset": name,
                    "symbol": symbol,
                    "return_1w": round(float(ret_1w), 2),
                    "return_1m": round(float(ret_1m), 2),
                    "return_3m": round(float(ret_3m), 2)
                })
            except Exception as e:
                log.warning(f"ROTATION[{name}/{symbol}]: {e}")

        # Rank by 1-month return
        perf_data.sort(key=lambda x: x['return_1m'], reverse=True)

        # Determine rotation phase
        spy_ret = next((x['return_1m'] for x in perf_data if x['asset'] == 'Equities'), 0)
        tlt_ret = next((x['return_1m'] for x in perf_data if x['asset'] == 'Bonds'), 0)
        gld_ret = next((x['return_1m'] for x in perf_data if x['asset'] == 'Gold'), 0)

        if spy_ret > 0 and tlt_ret > 0:
            rotation_phase = "RISK_ON"
        elif spy_ret < 0 and tlt_ret > 0 and gld_ret > 0:
            rotation_phase = "FLIGHT_TO_SAFETY"
        elif spy_ret < 0 and tlt_ret < 0 and gld_ret > 0:
            rotation_phase = "EVERYTHING_TO_GOLD"
        elif spy_ret < 0 and tlt_ret < 0 and gld_ret < 0:
            rotation_phase = "RISK_OFF_CASH"
        elif spy_ret > 0 and tlt_ret < 0:
            rotation_phase = "GROWTH_OVER_BONDS"
        else:
            rotation_phase = "MIXED"

        result = {
            "rotation_phase": rotation_phase,
            "rankings": perf_data,
            "signals": {
                "equities_vs_bonds": "EQUITIES_LEADING" if spy_ret > tlt_ret else "BONDS_LEADING",
                "gold_vs_equities": "GOLD_LEADING" if gld_ret > spy_ret else "EQUITIES_LEADING"
            },
            "last_updated": int(time.time())
        }
        _set_cached("rotation_signal", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/capital-flows/safe-haven")
def get_safe_haven_flows():
    """Safe haven asset analysis — gold, USD, JPY, CHF, Treasuries."""
    cached = _get_cached("safe_haven")
    if cached: return {"status": "success", "data": cached}

    try:
        havens = {
            "Gold": "GLD",
            "Silver": "SLV",
            "US Dollar": "UUP",
            "Swiss Franc": "FXF",
            "Long Treasury": "TLT",
            "Short Treasury": "SHV",
            "VIX Proxy": "VXX",
            "Japanese Yen": "FXY",
        }

        haven_data = []
        for name, symbol in havens.items():
            try:
                t = yf.Ticker(symbol)
                info = t.info
                hist = t.history(period="1m")
                price = clean(info.get("regularMarketPrice") or info.get("previousClose"))
                change = clean(info.get("regularMarketChangePercent"))

                # 5-day trend
                if not hist.empty and len(hist) >= 5:
                    closes = hist['Close'].values
                    trend_5d = ((closes[-1] - closes[-5]) / closes[-5] * 100) if len(closes) >= 5 else 0
                else:
                    trend_5d = 0

                haven_data.append({
                    "asset": name,
                    "symbol": symbol,
                    "price": price,
                    "change_pct": change,
                    "trend_5d": round(float(trend_5d), 2)
                })
            except Exception as e:
                log.warning(f"HAVEN[{name}/{symbol}]: {e}")

        # Compute safe haven demand index (average performance of all)
        avg_trend = np.mean([h['trend_5d'] for h in haven_data]) if haven_data else 0

        demand_level = "NEUTRAL"
        if avg_trend > 2:
            demand_level = "HIGH_SAFE_HAVEN_DEMAND"
        elif avg_trend > 1:
            demand_level = "ELEVATED_SAFE_HAVEN_DEMAND"
        elif avg_trend < -1:
            demand_level = "RISK_ON_MODE"

        result = {
            "safe_havens": haven_data,
            "safe_haven_demand_index": round(float(avg_trend), 2),
            "demand_level": demand_level,
            "last_updated": int(time.time())
        }
        _set_cached("safe_haven", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/capital-flows/emerging-markets")
def get_emerging_market_flows():
    """Focus on EM capital flows — equities, bonds, currencies."""
    cached = _get_cached("em_flows")
    if cached: return {"status": "success", "data": cached}

    try:
        em_assets = {
            "EM Equities": "EEM",
            "EM Bonds": "EMB",
            "EM Local Currency": "EMLC",
            "China": "FXI",
            "India": "INDA",
            "Brazil": "EWZ",
            "Indonesia": "EIDO",
            "Mexico": "EWW",
            "South Africa": "EZA",
            "Turkey": "TUR",
            "EM Small Cap": "EEMS",
        }

        em_data = []
        for name, symbol in em_assets.items():
            try:
                t = yf.Ticker(symbol)
                info = t.info
                hist = t.history(period="1m")
                price = clean(info.get("regularMarketPrice") or info.get("previousClose"))
                change = clean(info.get("regularMarketChangePercent"))

                if not hist.empty and len(hist) >= 5:
                    closes = hist['Close'].values
                    trend_5d = ((closes[-1] - closes[-5]) / closes[-5] * 100)
                    trend_1m = ((closes[-1] - closes[0]) / closes[0] * 100)
                else:
                    trend_5d = 0
                    trend_1m = 0

                em_data.append({
                    "name": name,
                    "symbol": symbol,
                    "price": price,
                    "change_pct": change,
                    "trend_5d": round(float(trend_5d), 2),
                    "trend_1m": round(float(trend_1m), 2)
                })
            except Exception as e:
                log.warning(f"EM[{name}/{symbol}]: {e}")

        avg_em_1m = np.mean([d['trend_1m'] for d in em_data]) if em_data else 0
        em_sentiment = "BULLISH" if avg_em_1m > 2 else ("BEARISH" if avg_em_1m < -2 else "NEUTRAL")

        result = {
            "assets": em_data,
            "average_em_return_1m": round(float(avg_em_1m), 2),
            "em_sentiment": em_sentiment,
            "last_updated": int(time.time())
        }
        _set_cached("em_flows", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/capital-flows/summary")
def get_flow_summary():
    """Aggregated capital flow summary."""
    try:
        etf_data = _get_cached("etf_flows") or {}
        rotation_data = _get_cached("rotation_signal") or {}
        haven_data = _get_cached("safe_haven") or {}

        return {
            "status": "success",
            "data": {
                "etf_flows": etf_data,
                "rotation": rotation_data,
                "safe_haven": haven_data,
                "last_updated": int(time.time())
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "capital_flow_service_online", "timestamp": int(time.time())}


if __name__ == "__main__":
    log.info("Global Capital Flow Monitor starting on port 8175")
    uvicorn.run(app, host="0.0.0.0", port=8175)
