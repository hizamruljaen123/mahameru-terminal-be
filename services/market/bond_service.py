"""
Bond Market Intelligence Microservice
Yield curves, global bonds, inversion tracking, real yields, credit spreads.
Powered by yfinance.
"""
import os
import time
import threading
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
log = logging.getLogger('bond_service')

import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import Dict, Any, List, Optional

app = FastAPI(debug=True, title="Bond Market Intelligence Microservice")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- US Treasury Yield Curve ---
YIELD_CURVE_SYMBOLS = {
    "3m":  "^IRX",     # 13-Week Treasury Bill
    "6m":  "BIL",      # SPDR Bloomberg 1-3 Month T-Bill ETF (proxy for 6mo)
    "1y":  "SHV",      # iShares Short Treasury Bond ETF
    "2y":  "^2YY",     # ICE 2Y US Treasury Note Futures
    "3y":  "SHY",      # iShares 1-3 Year Treasury Bond ETF
    "5y":  "^FVX",     # 5-Year Treasury Note Yield
    "7y":  "IEI",      # iShares 3-7 Year Treasury Bond ETF
    "10y": "^TNX",     # 10-Year Treasury Note Yield
    "20y": "^TYX",     # 20-Year Treasury Bond Yield (actually 30y)
    "30y": "TLT",      # iShares 20+ Year Treasury Bond ETF (price proxy)
}

# --- Global Bond ETFs ---
GLOBAL_BOND_ETFS = {
    "US": {"ticker": "IEF", "name": "US 7-10 Year Treasury", "currency": "USD"},
    "JP": {"ticker": "BNDX", "name": "Total International Bond", "currency": "USD"},
    "DE": {"ticker": "BWX",  "name": "SPDR Bloomberg International Treasury Bond", "currency": "USD"},
    "UK": {"ticker": "IGOV", "name": "iShares International Treasury Bond", "currency": "USD"},
    "EM": {"ticker": "EMB",  "name": "iShares JP Morgan USD Emerging Markets Bond", "currency": "USD"},
    "IG": {"ticker": "LQD",  "name": "iShares iBoxx Investment Grade Corporate Bond", "currency": "USD"},
    "HY": {"ticker": "HYG",  "name": "iShares iBoxx High Yield Corporate Bond", "currency": "USD"},
    "TIP":{"ticker": "TIP",  "name": "iShares TIPS Bond (Real Yield Proxy)", "currency": "USD"},
}

# --- Cache ---
BOND_CACHE = {}
_CACHE_LOCK = threading.Lock()
CACHE_TTL = 300  # 5 minutes

def clean(val):
    if val is None or (isinstance(val, (float, int, np.floating, np.integer)) and (np.isnan(val) or np.isinf(val))):
        return None
    try: return float(val)
    except: return None

def _get_cached(key):
    with _CACHE_LOCK:
        if key in BOND_CACHE and time.time() - BOND_CACHE[key]['ts'] < CACHE_TTL:
            return BOND_CACHE[key]['data']
    return None

def _set_cached(key, data):
    with _CACHE_LOCK:
        BOND_CACHE[key] = {'ts': time.time(), 'data': data}


# ===================== ENDPOINTS =====================

@app.get("/api/bonds/yield-curve")
def get_yield_curve():
    """Full US Treasury yield curve with rates and inversion spreads."""
    cached = _get_cached("yield_curve")
    if cached: return {"status": "success", "data": cached}

    try:
        curve = []
        for maturity, symbol in YIELD_CURVE_SYMBOLS.items():
            try:
                t = yf.Ticker(symbol)
                info = t.info
                price = info.get("regularMarketPrice") or info.get("previousClose") or info.get("navPrice")
                # For yield symbols (^IRX, ^FVX, ^TNX, ^TYX), price IS the yield
                # For ETFs, derive yield from SEC yield or distribution rate
                if symbol.startswith("^"):
                    yield_val = price
                else:
                    yield_val = info.get("yield") or info.get("distributionYield") or info.get("secYield")
                    if not yield_val:
                        # Derive yield from price history
                        hist = t.history(period="1mo")
                        if not hist.empty:
                            div = t.dividends
                            if not div.empty:
                                annual_div = div.tail(12).sum() if len(div) >= 12 else div.tail(4).sum() * 3
                                yield_val = (annual_div / hist['Close'].iloc[-1]) * 100
                            else:
                                yield_val = None

                curve.append({
                    "maturity": maturity,
                    "symbol": symbol,
                    "yield": clean(yield_val),
                    "name": info.get("shortName", symbol)
                })
            except Exception as e:
                log.warning(f"YIELD_CURVE[{maturity}/{symbol}]: {e}")
                curve.append({"maturity": maturity, "symbol": symbol, "yield": None, "name": symbol})

        # Build inversion spreads
        spreads = {}
        yield_map = {c['maturity']: c['yield'] for c in curve if c['yield'] is not None}

        if '2y' in yield_map and '10y' in yield_map:
            spreads['2y10y'] = round(yield_map['2y'] - yield_map['10y'], 3) if yield_map['2y'] and yield_map['10y'] else None
        if '3m' in yield_map and '10y' in yield_map:
            spreads['3m10y'] = round(yield_map['3m'] - yield_map['10y'], 3) if yield_map['3m'] and yield_map['10y'] else None
        if '5y' in yield_map and '30y' in yield_map:
            spreads['5y30y'] = round(yield_map['5y'] - yield_map['30y'], 3) if yield_map['5y'] and yield_map['30y'] else None
        if '2y' in yield_map and '5y' in yield_map:
            spreads['2y5y'] = round(yield_map['2y'] - yield_map['5y'], 3) if yield_map['2y'] and yield_map['5y'] else None

        # Inversion status
        inversion_status = "NORMAL"
        for s in spreads.values():
            if s is not None and s < 0:
                inversion_status = "INVERTED"
                break
        if spreads.get('2y10y') is not None and spreads['2y10y'] < -0.5:
            inversion_status = "DEEP_INVERSION"
        elif spreads.get('2y10y') is not None and spreads['2y10y'] > 0:
            inversion_status = "NORMAL"

        result = {
            "curve": curve,
            "spreads": spreads,
            "inversion_status": inversion_status,
            "last_updated": int(time.time())
        }
        _set_cached("yield_curve", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bonds/global")
def get_global_bonds():
    """Global bond market overview via representative ETFs."""
    cached = _get_cached("global_bonds")
    if cached: return {"status": "success", "data": cached}

    try:
        bonds = []
        for code, meta in GLOBAL_BOND_ETFS.items():
            try:
                t = yf.Ticker(meta['ticker'])
                info = t.info
                hist = t.history(period="1mo")
                price = clean(info.get("regularMarketPrice") or info.get("previousClose") or info.get("navPrice"))
                prev_close = clean(info.get("previousClose"))
                change_pct = round(((price - prev_close) / prev_close) * 100, 2) if price and prev_close else None

                # Get distribution yield
                distrib_yield = info.get("yield") or info.get("distributionYield") or info.get("secYield")

                bonds.append({
                    "code": code,
                    "name": meta['name'],
                    "ticker": meta['ticker'],
                    "price": price,
                    "change_pct": change_pct,
                    "yield_pct": clean(distrib_yield),
                    "currency": meta['currency'],
                    "category": "Sovereign" if code in ["US","JP","DE","UK","EM"] else ("Corporate" if code in ["IG","HY"] else "Inflation"),
                    "region": code
                })
            except Exception as e:
                log.warning(f"GLOBAL_BOND[{code}/{meta['ticker']}]: {e}")

        # Calculate credit spread (HY - IG)
        hy_yield = None
        ig_yield = None
        for b in bonds:
            if b['code'] == 'HY' and b['yield_pct']: hy_yield = b['yield_pct']
            if b['code'] == 'IG' and b['yield_pct']: ig_yield = b['yield_pct']

        result = {
            "bonds": bonds,
            "credit_spread": round(hy_yield - ig_yield, 2) if hy_yield and ig_yield else None,
            "last_updated": int(time.time())
        }
        _set_cached("global_bonds", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bonds/inversion-tracker")
def get_inversion_tracker():
    """Historical yield curve inversion tracking."""
    cached = _get_cached("inversion_tracker")
    if cached: return {"status": "success", "data": cached}

    try:
        # Get historical data for 2Y and 10Y yields
        t2y = yf.Ticker("^2YY")
        t10y = yf.Ticker("^TNX")

        hist2y = t2y.history(period="1y")
        hist10y = t10y.history(period="1y")

        if hist2y.empty or hist10y.empty:
            # Fallback to ETF-based proxy
            t2y = yf.Ticker("SHY")
            t10y = yf.Ticker("IEF")
            hist2y = t2y.history(period="1y")
            hist10y = t10y.history(period="1y")

        # Combine into spread history
        spread_history = []
        common_dates = hist2y.index.intersection(hist10y.index)

        for date in common_dates[-365:]:  # Last year
            try:
                if 'Close' in hist2y.columns and 'Close' in hist10y.columns:
                    y2y = clean(hist2y.loc[date, 'Close'])
                    y10y = clean(hist10y.loc[date, 'Close'])
                    
                    if y2y is not None and y10y is not None:
                        spread = y2y - y10y
                        spread_history.append({
                            "date": date.strftime('%Y-%m-%d'),
                            "spread": round(spread, 3),
                            "y2y": round(y2y, 3),
                            "y10y": round(y10y, 3)
                        })
            except: continue

        # Identify inversion periods
        inversion_periods = []
        in_inversion = False
        inv_start = None
        inv_min = float('inf')
        inv_min_date = None

        for item in spread_history:
            if item['spread'] < 0:
                if not in_inversion:
                    in_inversion = True
                    inv_start = item['date']
                if item['spread'] < inv_min:
                    inv_min = item['spread']
                    inv_min_date = item['date']
            else:
                if in_inversion:
                    inversion_periods.append({
                        "start": inv_start,
                        "end": item['date'],
                        "min_spread": round(inv_min, 3),
                        "min_spread_date": inv_min_date
                    })
                    in_inversion = False
                    inv_min = float('inf')

        # Current status
        current_spread = spread_history[-1]['spread'] if spread_history else None

        result = {
            "spread_history": spread_history[-90:],  # Last 90 days for chart
            "inversion_periods": inversion_periods,
            "current_spread": clean(current_spread),
            "days_inverted": sum(1 for s in spread_history[-30:] if s['spread'] < 0) if spread_history else 0,
            "max_inversion_30d": clean(min((s['spread'] for s in spread_history[-30:] if s['spread'] < 0), default=0)),
            "last_updated": int(time.time())
        }
        _set_cached("inversion_tracker", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bonds/credit-spreads")
def get_credit_spreads():
    """Corporate bond spreads — HY vs IG, credit risk appetite."""
    cached = _get_cached("credit_spreads")
    if cached: return {"status": "success", "data": cached}

    try:
        # HYG = High Yield Corporate, LQD = Investment Grade Corporate
        # SPY = Risk-free proxy
        hyg = yf.Ticker("HYG")
        lqd = yf.Ticker("LQD")
        spy = yf.Ticker("SPY")

        hist_hyg = hyg.history(period="6mo")
        hist_lqd = lqd.history(period="6mo")
        hist_spy = spy.history(period="6mo")

        # Calculate spread series (HY yield - IG yield) using price inverse proxy
        # Lower price = higher yield = wider spread
        spread_series = []
        common = hist_hyg.index.intersection(hist_lqd.index).intersection(hist_spy.index)

        for date in common:
            try:
                hyg_p = clean(hist_hyg.loc[date, 'Close'])
                lqd_p = clean(hist_lqd.loc[date, 'Close'])
                spy_p = clean(hist_spy.loc[date, 'Close'])

                if hyg_p and lqd_p and spy_p:
                    # Normalized spread: HYG/LQD ratio (inverse of yield spread)
                    ratio = hyg_p / lqd_p
                    rel_strength = (hyg_p / spy_p) / (lqd_p / spy_p)

                    spread_series.append({
                        "date": date.strftime('%Y-%m-%d'),
                        "hyg_price": round(hyg_p, 2),
                        "lqd_price": round(lqd_p, 2),
                        "hy_lq_ratio": round(ratio, 4),
                        "relative_strength": round(rel_strength, 4)
                    })
            except: continue

        current = spread_series[-1] if spread_series else {}
        start = spread_series[0] if spread_series else {}

        # Trend analysis
        recent = spread_series[-20:] if len(spread_series) >= 20 else spread_series
        ratio_change = ((recent[-1]['hy_lq_ratio'] - recent[0]['hy_lq_ratio']) / recent[0]['hy_lq_ratio'] * 100) if recent else 0

        result = {
            "spread_history": spread_series,
            "current": current,
            "ratio_change_pct": round(ratio_change, 2),
            "credit_regime": "RISK_ON" if ratio_change > 0 else ("RISK_OFF" if ratio_change < -2 else "NEUTRAL"),
            "last_updated": int(time.time())
        }
        _set_cached("credit_spreads", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bonds/real-yields")
def get_real_yields():
    """TIPS-implied real yields and breakeven inflation."""
    cached = _get_cached("real_yields")
    if cached: return {"status": "success", "data": cached}

    try:
        # TIP = TIPS ETF (real yield proxy)
        # IEF = Nominal 7-10Y Treasury
        # Breakeven = Nominal Yield - Real Yield
        tip = yf.Ticker("TIP")
        ief = yf.Ticker("IEF")
        tnx = yf.Ticker("^TNX")  # 10Y nominal yield

        hist_tip = tip.history(period="1y")
        hist_ief = ief.history(period="1y")
        info_tnx = tnx.info

        nominal_10y = clean(info_tnx.get("regularMarketPrice") or info_tnx.get("previousClose"))

        # Estimate real yield from TIP price (inverse relationship)
        tip_info = tip.info
        tip_yield = tip_info.get("yield") or tip_info.get("secYield")

        # Derive real yield from TIP price history
        real_yield_history = []
        be_inflation_history = []
        common = hist_tip.index.intersection(hist_ief.index)

        for date in common:
            try:
                tip_p = clean(hist_tip.loc[date, 'Close'])
                ief_p = clean(hist_ief.loc[date, 'Close'])

                if tip_p and ief_p:
                    # TIP/IEF ratio as proxy for real yield trend
                    ratio = ief_p / tip_p if tip_p > 0 else 0
                    real_yield_history.append({
                        "date": date.strftime('%Y-%m-%d'),
                        "tip_price": round(tip_p, 2),
                        "ief_price": round(ief_p, 2),
                        "tip_ief_ratio": round(ratio, 4)
                    })
            except: continue

        result = {
            "current": {
                "nominal_10y": nominal_10y,
                "tips_yield": clean(tip_yield),
                # If both available, breakeven = nominal - real
                "breakeven_inflation": round(nominal_10y - (tip_yield or 0), 2) if nominal_10y and tip_yield else None
            },
            "real_yield_proxy_history": real_yield_history,
            "last_updated": int(time.time())
        }
        _set_cached("real_yields", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bonds/summary")
def get_bond_summary():
    """Aggregated bond market summary — one-call overview."""
    try:
        # Gather all in parallel
        yield_curve = (_get_cached("yield_curve") or {}).get("curve", [])
        global_bonds = (_get_cached("global_bonds") or {}).get("bonds", [])
        spreads = (_get_cached("yield_curve") or {}).get("spreads", {})

        # Key signals
        yield_map = {c['maturity']: c['yield'] for c in yield_curve if c['yield'] is not None}

        signals = []
        if spreads.get('2y10y') is not None:
            if spreads['2y10y'] < 0:
                signals.append({"signal": "YIELD_CURVE_INVERTED", "severity": "HIGH",
                    "detail": f"2Y-10Y spread at {spreads['2y10y']}bps — recession indicator"})
            elif spreads['2y10y'] < 0.5:
                signals.append({"signal": "YIELD_CURVE_FLATTENING", "severity": "MEDIUM",
                    "detail": f"2Y-10Y spread at {spreads['2y10y']}bps — flattening trend"})

        hy_yield = None
        ig_yield = None
        for b in global_bonds:
            if b['code'] == 'HY' and b.get('yield_pct'): hy_yield = b['yield_pct']
            if b['code'] == 'IG' and b.get('yield_pct'): ig_yield = b['yield_pct']

        if hy_yield and ig_yield:
            cs = hy_yield - ig_yield
            if cs > 5:
                signals.append({"signal": "CREDIT_STRESS", "severity": "HIGH",
                    "detail": f"HY-IG spread at {cs:.1f}% — credit market stress"})

        return {
            "status": "success",
            "data": {
                "yield_curve": yield_curve,
                "global_bonds": global_bonds,
                "spreads": spreads,
                "signals": signals,
                "last_updated": int(time.time())
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bonds/ticker-detail/{symbol}")
def get_ticker_detail(symbol: str):
    """Fetch full ticker detail and price history for any yfinance symbol.
    
    Returns current price, 52w high/low, and 6-month daily OHLCV history.
    Used by the Bond Detail Explorer in the frontend.
    """
    cache_key = f"ticker_detail_{symbol}"
    cached = _get_cached(cache_key)
    if cached:
        return {"status": "success", "data": cached}

    try:
        t = yf.Ticker(symbol)
        info = t.info

        # 6-month daily history
        hist = t.history(period="6mo")
        history = []
        if not hist.empty:
            for ts, row in hist.iterrows():
                history.append({
                    "date": ts.strftime('%Y-%m-%d'),
                    "open": clean(row.get('Open')),
                    "high": clean(row.get('High')),
                    "low": clean(row.get('Low')),
                    "close": clean(row.get('Close')),
                    "volume": int(row.get('Volume', 0)) if not np.isnan(row.get('Volume', 0)) else 0,
                    "adjclose": clean(row.get('Adj Close', row.get('Close'))),
                })

        detail = {
            "symbol": symbol,
            "name": info.get("shortName") or info.get("longName") or symbol,
            "currency": info.get("currency", "USD"),
            "currentPrice": clean(info.get("regularMarketPrice") or info.get("previousClose") or info.get("navPrice")),
            "previousClose": clean(info.get("previousClose")),
            "open": clean(info.get("regularMarketOpen")),
            "dayHigh": clean(info.get("dayHigh") or info.get("regularMarketDayHigh")),
            "dayLow": clean(info.get("dayLow") or info.get("regularMarketDayLow")),
            "high52w": clean(info.get("fiftyTwoWeekHigh")),
            "low52w": clean(info.get("fiftyTwoWeekLow")),
            "volume": clean(info.get("regularMarketVolume")),
            "avgVolume": clean(info.get("averageVolume")),
            "marketCap": clean(info.get("marketCap")),
            "dividendYield": clean(info.get("dividendYield") or info.get("yield")),
            "peRatio": clean(info.get("trailingPE")),
            "beta": clean(info.get("beta")),
            "category": info.get("category") or info.get("fundFamily"),
            "history": history[-120:],  # Last 120 trading days
            "last_updated": int(time.time()),
        }

        _set_cached(cache_key, detail)
        return {"status": "success", "data": detail}
    except Exception as e:
        log.warning(f"TICKER_DETAIL[{symbol}]: {e}")
        # Return minimal data with just the symbol
        return {"status": "error", "detail": str(e), "data": {"symbol": symbol}}


# ===================== HEALTH =====================

@app.get("/health")
def health():
    return {"status": "bond_service_online", "timestamp": int(time.time())}


# ===================== MAIN =====================

if __name__ == "__main__":
    log.info("Bond Intelligence Service starting on port 8145")
    uvicorn.run(app, host="0.0.0.0", port=8145)
