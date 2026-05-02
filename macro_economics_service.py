"""
Macro Economics Indicators Dashboard
FRED API integration for real economic data: GDP, CPI, PCE, Employment, Housing, PMI, etc.
Fallback: Uses yfinance ETFs as proxies when FRED API key not available.
"""
import os
import time
import threading
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
log = logging.getLogger('macro_economics_service')

import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import Dict, Any, List, Optional
from datetime import datetime

app = FastAPI(debug=True, title="Macro Economics Indicator Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Try to load FRED API key from .env
from dotenv import load_dotenv
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)
FRED_API_KEY = os.getenv('FRED_API_KEY', '')

# --- FRED Series IDs ---
FRED_SERIES = {
    # GDP
    "GDP": "GDP",              # Real Gross Domestic Product
    "GDPPC": "A939RX0Q048SBEA", # Real GDP per Capita
    "GDPNOW": "GDPNOW",        # GDP Nowcast
    # Inflation
    "CPI": "CPIAUCSL",         # Consumer Price Index All Items
    "CORECPI": "CPILFESL",     # Core CPI
    "PCE": "PCEPI",            # Personal Consumption Expenditures
    "COREPCE": "PCEPILFE",     # Core PCE
    "PPI": "PPIACO",           # Producer Price Index
    # Employment
    "PAYROLLS": "PAYEMS",      # Nonfarm Payrolls
    "UNEMPLOYMENT": "UNRATE",  # Unemployment Rate
    "LFPR": "CIVPART",         # Labor Force Participation Rate
    "JOLTS": "JTSJOL",         # Job Openings
    "AHE": "CES0500000003",    # Average Hourly Earnings
    # Housing
    "HSTARTS": "HOUST",        # Housing Starts
    "BPERMITS": "PERMIT",      # Building Permits
    "EXHOMES": "EXHOSLUSM495S",# Existing Home Sales
    "CSHPRICE": "CSUSHPISA",   # Case-Shiller Home Price Index
    "NAHB": "NAHB",            # NAHB Housing Market Index
    # Manufacturing
    "ISMMAN": "NAPM",          # ISM Manufacturing PMI
    "ISMNONMAN": "NAPMNONMAN", # ISM Services PMI
    "INDPRO": "INDPRO",        # Industrial Production
    "CAPUTIL": "TCU",          # Capacity Utilization
    "DURGOODS": "DGORDER",     # Durable Goods Orders
    # Consumer
    "RETAIL": "RSAFS",         # Retail Sales
    "CONF": "UMCSENT",         # University of Michigan Consumer Sentiment
    "CONF_CB": "CCSAABR",      # Conference Board Consumer Confidence
    "PERSONAL_INCOME": "PI",   # Personal Income
    "PERSONAL_SPENDING": "PCE",# Personal Spending
    # Trade
    "BALANCE": "BOPGSTB",      # Trade Balance
    "IMPORTS": "IMPGS",        # Imports
    "EXPORTS": "EXPGS",        # Exports
    # Central Bank
    "FEDFUNDS": "FEDFUNDS",    # Fed Funds Rate
    "DFEDTAR": "DFEDTARU",     # Fed Funds Target Rate
    "WALCL": "WALCL",          # Fed Balance Sheet
    "M2": "M2SL",              # M2 Money Supply
    # Global
    "T10Y2Y": "T10Y2Y",        # 10Y-2Y Treasury Spread
    "T5YIE": "T5YIE",          # 5-Year Breakeven Inflation
    "T10YIE": "T10YIE",        # 10-Year Breakeven Inflation
    "RECESSION": "USREC",      # NBER Recession Indicator
}

# --- yfinance proxies for when FRED is unavailable ---
YF_PROXIES = {
    "GDP": {"type": "etf", "symbol": "SPY", "desc": "S&P 500 (GDP Proxy)"},
    "CPI": {"type": "rate", "symbol": "^TNX", "desc": "10Y Yield (Inflation Proxy)"},
    "UNEMPLOYMENT": {"type": "etf", "symbol": "SHY", "desc": "1-3Y Treasury (Risk Proxy)"},
    "FEDFUNDS": {"type": "rate", "symbol": "^IRX", "desc": "13W T-Bill (Rate Proxy)"},
    "ISMMAN": {"type": "etf", "symbol": "XLI", "desc": "Industrials (PMI Proxy)"},
    "HSTARTS": {"type": "etf", "symbol": "XLRE", "desc": "Real Estate (Housing Proxy)"},
    "RETAIL": {"type": "etf", "symbol": "XLY", "desc": "Consumer Disc (Retail Proxy)"},
}

# --- Cache ---
MACRO_CACHE = {}
_CACHE_LOCK = threading.Lock()
CACHE_TTL = 3600  # 1 hour (macro data changes slowly)

def clean(val):
    """Return a JSON-safe float, or None for NaN/Inf/None."""
    if val is None:
        return None
    try:
        v = float(val)
        if np.isnan(v) or np.isinf(v):
            return None
        return v
    except Exception:
        return None

def safe_row(d: dict) -> dict:
    """Sanitize every numeric value in a dict so it is JSON-safe."""
    return {k: (clean(v) if isinstance(v, (float, int, np.floating, np.integer)) else v)
            for k, v in d.items()}

def _get_cached(key):
    with _CACHE_LOCK:
        if key in MACRO_CACHE and time.time() - MACRO_CACHE[key]['ts'] < CACHE_TTL:
            return MACRO_CACHE[key]['data']
    return None

def _set_cached(key, data):
    with _CACHE_LOCK:
        MACRO_CACHE[key] = {'ts': time.time(), 'data': data}


# ===================== FRED API =====================

def fetch_fred_series(series_id):
    """Fetch a single FRED series. Returns list of {date, value}."""
    if not FRED_API_KEY:
        return None

    import requests
    try:
        url = f"https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": series_id,
            "api_key": FRED_API_KEY,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 100
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            log.warning(f"FRED[{series_id}]: HTTP {resp.status_code}")
            return None

        data = resp.json()
        observations = data.get('observations', [])
        result = []
        for obs in observations:
            if obs.get('value') and obs['value'] != '.':
                result.append({
                    "date": obs['date'],
                    "value": float(obs['value'])
                })
        return result[:60]  # Last 60 observations
    except Exception as e:
        log.warning(f"FRED[{series_id}]: {e}")
        return None


def fetch_yf_proxy(proxy_config):
    """Fetch yfinance proxy data for macro indicator."""
    try:
        if proxy_config['type'] == 'rate':
            t = yf.Ticker(proxy_config['symbol'])
            info = t.info
            price = info.get("regularMarketPrice") or info.get("previousClose")
            hist = t.history(period="1y")
            if hist.empty:
                return None, None
            history = []
            for ts, r in hist.iterrows():
                v = clean(r['Close'])
                if v is None:
                    continue
                history.append(safe_row({
                    "date": ts.strftime('%Y-%m-%d'),
                    "value": round(v, 4)
                }))
            return clean(price), history[-60:]
        else:
            t = yf.Ticker(proxy_config['symbol'])
            info = t.info
            price = info.get("regularMarketPrice") or info.get("previousClose")
            hist = t.history(period="1y")
            if hist.empty:
                return None, None
            first_close = clean(hist['Close'].iloc[0])
            history = []
            for ts, r in hist.iterrows():
                v = clean(r['Close'])
                if v is None:
                    continue
                chg = round((v / first_close - 1) * 100, 2) if first_close else None
                history.append(safe_row({
                    "date": ts.strftime('%Y-%m-%d'),
                    "value": round(v, 2),
                    "change": chg
                }))
            return clean(price), history[-60:]
    except Exception as e:
        log.warning(f"YF_PROXY[{proxy_config['symbol']}]: {e}")
        return None, None


# ===================== ENDPOINTS =====================

@app.get("/api/macro/indicators")
def get_macro_indicators():
    """All major economic indicators in one call."""
    cached = _get_cached("all_indicators")
    if cached: return {"status": "success", "data": cached}

    try:
        indicators = {}

        for name, series_id in FRED_SERIES.items():
            try:
                if FRED_API_KEY:
                    fred_data = fetch_fred_series(series_id)
                    if fred_data:
                        current = clean(fred_data[0]['value']) if fred_data else None
                        prev = clean(fred_data[1]['value']) if len(fred_data) > 1 else None
                        change = clean(current - prev) if current is not None and prev is not None else None
                        change_pct = clean((current - prev) / prev * 100) if current is not None and prev is not None and prev != 0 else None

                        indicators[name] = {
                            "fred_series": series_id,
                            "current": current,
                            "previous": prev,
                            "change": change,
                            "change_pct": change_pct,
                            "history": [safe_row(row) for row in fred_data[:30]],
                            "data_source": "FRED"
                        }
                        continue

                # Fallback to yfinance proxy
                if name in YF_PROXIES:
                    current, history = fetch_yf_proxy(YF_PROXIES[name])
                    if current is not None:
                        indicators[name] = {
                            "proxy_symbol": YF_PROXIES[name]['symbol'],
                            "current": current,
                            "desc": YF_PROXIES[name]['desc'],
                            "history": history,
                            "data_source": "yfinance_proxy"
                        }
            except Exception as e:
                log.warning(f"MACRO_INDICATOR[{name}]: {e}")
                continue

        result = {
            "indicators": indicators,
            "fred_available": bool(FRED_API_KEY),
            "last_updated": int(time.time())
        }
        _set_cached("all_indicators", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/macro/central-bank-rates")
def get_central_bank_rates():
    """Global central bank interest rate tracker."""
    cached = _get_cached("central_bank_rates")
    if cached: return {"status": "success", "data": cached}

    try:
        rates = []

        # Use yfinance ETFs/rates as proxy for central bank expectations
        central_banks = {
            "Federal Reserve (US)": {
                "rate_symbol": "^IRX",  # 13W T-Bill
                "etf_symbol": "TLT",    # Long bonds
            },
            "ECB (EU)": {
                "rate_symbol": "FXE",   # Euro currency
                "etf_symbol": "BWX",    # International bonds
            },
            "BOJ (Japan)": {
                "rate_symbol": "FXY",   # Yen currency
                "etf_symbol": "EWJ",    # Japan equities
            },
            "BOE (UK)": {
                "rate_symbol": "FXB",   # GBP currency
                "etf_symbol": "EWU",    # UK equities
            },
            "BI (Indonesia)": {
                "rate_symbol": "EIDO",  # Indonesia equities
                "etf_symbol": "IDR=X",  # USDIDR exchange rate
            },
            "PBOC (China)": {
                "rate_symbol": "FXI",   # China equities
                "etf_symbol": "CYB",    # China yuan
            },
            "RBI (India)": {
                "rate_symbol": "INDA",  # India equities
                "etf_symbol": "USDINR=X",  # USD/INR
            },
        }

        for bank, symbols in central_banks.items():
            try:
                # Get rate proxy
                rate_t = yf.Ticker(symbols['rate_symbol'])
                rate_info = rate_t.info
                rate = clean(rate_info.get("regularMarketPrice") or rate_info.get("previousClose"))

                # Get 6-month trend
                hist = rate_t.history(period="6mo")
                trend = "NEUTRAL"
                if not hist.empty and len(hist) > 60:
                    recent = hist['Close'].iloc[-20:].mean()
                    prior = hist['Close'].iloc[-60:-20].mean()
                    if recent > prior * 1.02:
                        trend = "TIGHTENING"
                    elif recent < prior * 0.98:
                        trend = "EASING"

                # Policy stance
                policy_stance = "NEUTRAL"
                if trend == "TIGHTENING":
                    policy_stance = "HAWKISH"
                elif trend == "EASING":
                    policy_stance = "DOVISH"

                rates.append({
                    "central_bank": bank,
                    "proxy_symbol": symbols['rate_symbol'],
                    "proxy_rate": rate,
                    "trend_6m": trend,
                    "policy_stance": policy_stance,
                    "description": f"{rate:.2f} (proxy)" if rate is not None else "N/A"
                })
            except Exception as e:
                log.warning(f"CB_RATE[{bank}]: {e}")
                continue

        result = {
            "central_banks": rates,
            "total_tracked": len(rates),
            "hawkish_count": sum(1 for r in rates if r['policy_stance'] == 'HAWKISH'),
            "dovish_count": sum(1 for r in rates if r['policy_stance'] == 'DOVISH'),
            "global_policy_tilt": "HAWKISH" if sum(1 for r in rates if r['policy_stance'] == 'HAWKISH') > sum(1 for r in rates if r['policy_stance'] == 'DOVISH') else "DOVISH",
            "last_updated": int(time.time())
        }
        _set_cached("central_bank_rates", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/macro/inflation-dashboard")
def get_inflation_dashboard():
    """Inflation metrics dashboard."""
    cached = _get_cached("inflation_dashboard")
    if cached: return {"status": "success", "data": cached}

    try:
        inflation_data = {}

        if FRED_API_KEY:
            # CPI data
            cpi = fetch_fred_series("CPIAUCSL")
            core_cpi = fetch_fred_series("CPILFESL")
            pce = fetch_fred_series("PCEPI")
            core_pce = fetch_fred_series("PCEPILFE")
            ppi = fetch_fred_series("PPIACO")
            breakeven_5y = fetch_fred_series("T5YIE")
            breakeven_10y = fetch_fred_series("T10YIE")

            inflation_data = {
                "cpi": cpi,
                "core_cpi": core_cpi,
                "pce": pce,
                "core_pce": core_pce,
                "ppi": ppi,
                "breakeven_5y": breakeven_5y,
                "breakeven_10y": breakeven_10y,
            }
        else:
            # Use yfinance proxies
            # TIP = TIPS (real yield), IEF = nominal => breakeven proxy
            tip = yf.Ticker("TIP")
            ief = yf.Ticker("IEF")
            tip_info = tip.info
            ief_info = ief.info
            tip_yield = tip_info.get("yield") or tip_info.get("secYield")
            ief_yield = ief_info.get("yield") or ief_info.get("secYield")

            tip_hist = tip.history(period="1y")
            ief_hist = ief.history(period="1y")

            tip_hist_data = []
            ief_hist_data = []
            if not tip_hist.empty:
                for ts, r in tip_hist.iterrows():
                    tip_hist_data.append({"date": ts.strftime('%Y-%m-%d'), "value": round(float(r['Close']), 2)})
            if not ief_hist.empty:
                for ts, r in ief_hist.iterrows():
                    ief_hist_data.append({"date": ts.strftime('%Y-%m-%d'), "value": round(float(r['Close']), 2)})

            inflation_data = {
                "tips_yield": clean(tip_yield),
                "nominal_yield": clean(ief_yield),
                "breakeven_proxy": round((ief_yield or 0) - (tip_yield or 0), 2) if tip_yield and ief_yield else None,
                "tip_history": tip_hist_data,
                "ief_history": ief_hist_data,
                "note": "FRED API key not configured. Using TIPS/IEF yields as inflation proxy."
            }

        # Extract current values for summary
        current_values = {}
        for key, data in inflation_data.items():
            if isinstance(data, list) and data:
                current_values[key] = data[0]['value']
            elif isinstance(data, (int, float)):
                current_values[key] = data

        result = {
            "data": inflation_data,
            "summary": current_values,
            "fred_available": bool(FRED_API_KEY),
            "last_updated": int(time.time())
        }
        _set_cached("inflation_dashboard", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/macro/labor-market")
def get_labor_market():
    """Labor market indicators."""
    cached = _get_cached("labor_market")
    if cached: return {"status": "success", "data": cached}

    try:
        labor_data = {}

        if FRED_API_KEY:
            for name, sid in [("nonfarm_payrolls", "PAYEMS"), ("unemployment", "UNRATE"),
                              ("lfpr", "CIVPART"), ("ahe", "CES0500000003")]:
                data = fetch_fred_series(sid)
                if data:
                    labor_data[name] = data
        else:
            # Use market proxies
            spy = yf.Ticker("SPY")
            spy_hist = spy.history(period="1y")
            spy_data = []
            if not spy_hist.empty:
                for ts, r in spy_hist.iterrows():
                    spy_data.append({"date": ts.strftime('%Y-%m-%d'), "value": round(float(r['Close']), 2)})
            labor_data = {
                "spy_proxy": spy_data,
                "note": "FRED API key not configured. Using SPY as employment proxy."
            }

        result = {
            "data": labor_data,
            "fred_available": bool(FRED_API_KEY),
            "last_updated": int(time.time())
        }
        _set_cached("labor_market", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/macro/summary")
def get_macro_summary():
    """One-call macro overview."""
    try:
        indicators = _get_cached("all_indicators") or {}
        cb_rates = _get_cached("central_bank_rates") or {}
        inflation = _get_cached("inflation_dashboard") or {}

        return {
            "status": "success",
            "data": {
                "indicators": indicators,
                "central_bank_rates": cb_rates,
                "inflation": inflation,
                "last_updated": int(time.time())
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "macro_economics_service_online", "timestamp": int(time.time())}


if __name__ == "__main__":
    log.info("Macro Economics Service starting on port 8205")
    uvicorn.run(app, host="0.0.0.0", port=8205)
