import os
import time
import asyncio
import threading
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
log = logging.getLogger('commodity_service')
import requests
import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import Dict, Any, List, Optional

app = FastAPI(debug=True, title="Commodity Intelligence Microservice")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

COMMODITY_ENTITIES = [
    {"symbol": "CL=F", "name": "Crude Oil", "category": "Energy"},
    {"symbol": "BZ=F", "name": "Brent Crude Oil", "category": "Energy"},
    {"symbol": "NG=F", "name": "Natural Gas", "category": "Energy"},
    {"symbol": "RB=F", "name": "RBOB Gasoline", "category": "Energy"},
    {"symbol": "HO=F", "name": "Heating Oil", "category": "Energy"},
    {"symbol": "GC=F", "name": "Gold", "category": "Metals"},
    {"symbol": "SI=F", "name": "Silver", "category": "Metals"},
    {"symbol": "HG=F", "name": "Copper", "category": "Metals"},
    {"symbol": "PL=F", "name": "Platinum", "category": "Metals"},
    {"symbol": "PA=F", "name": "Palladium", "category": "Metals"},
    {"symbol": "ALI=F", "name": "Aluminum", "category": "Metals"},
    {"symbol": "ZC=F", "name": "Corn", "category": "Agriculture"},
    {"symbol": "ZW=F", "name": "Wheat", "category": "Agriculture"},
    {"symbol": "ZS=F", "name": "Soybeans", "category": "Agriculture"},
    {"symbol": "ZL=F", "name": "Soybean Oil", "category": "Agriculture"},
    {"symbol": "ZR=F", "name": "Rough Rice", "category": "Agriculture"},
    {"symbol": "KC=F", "name": "Coffee", "category": "Agriculture"},
    {"symbol": "SB=F", "name": "Sugar", "category": "Agriculture"},
    {"symbol": "CC=F", "name": "Cocoa", "category": "Agriculture"},
    {"symbol": "CT=F", "name": "Cotton", "category": "Agriculture"},
    {"symbol": "OJ=F", "name": "Orange Juice", "category": "Agriculture"},
    {"symbol": "LE=F", "name": "Live Cattle", "category": "Livestock"},
    {"symbol": "GF=F", "name": "Feeder Cattle", "category": "Livestock"},
    {"symbol": "HE=F", "name": "Lean Hogs", "category": "Livestock"},
    {"symbol": "LBS=F", "name": "Lumber", "category": "Industrial"},
    {"symbol": "DC=F", "name": "Class III Milk", "category": "Agriculture"},
    {"symbol": "RT=F", "name": "Rubber", "category": "Industrial"},
    {"symbol": "ETH=F", "name": "Ethanol", "category": "Energy"},
    {"symbol": "FCPO=F", "name": "Crude Palm Oil", "category": "Agriculture"},
    {"symbol": "MTF=F", "name": "Coal (Newcastle)", "category": "Energy"}
]

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

@app.get("/api/commodities/list")
def get_commodities_list():
    try:
        data = []
        for item in COMMODITY_ENTITIES:
            data.append({
                "symbol": item["symbol"],
                "name": item["name"],
                "category": item["category"]
            })
        return {"status": "success", "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# COMMODITY CACHE — thread-safe
COMMODITY_CACHE = {
    "highlights": [],
    "last_updated": 0
}
_CACHE_LOCK = threading.Lock()

# DETAIL CACHE — reduce redundant yfinance calls for same symbol/period
COMMODITY_DETAIL_CACHE = {}
COMMODITY_D_CACHE_TTL = 900  # 15 mins

def get_commodity_detail_cache(symbol, period):
    key = f"{symbol}:{period}"
    if key in COMMODITY_DETAIL_CACHE:
        entry = COMMODITY_DETAIL_CACHE[key]
        if time.time() - entry['timestamp'] < COMMODITY_D_CACHE_TTL:
            return entry['data']
    return None

def set_commodity_detail_cache(symbol, period, data):
    key = f"{symbol}:{period}"
    COMMODITY_DETAIL_CACHE[key] = {'timestamp': time.time(), 'data': data}

# Fields the frontend actually uses from ticker.info — filter out 80KB of noise
COMMODITY_INSTITUTIONAL_FIELDS = [
    "shortName", "regularMarketPrice", "previousClose", "bid", "ask",
    "dayLow", "dayHigh", "fiftyTwoWeekLow", "fiftyTwoWeekHigh",
    "volume", "regularMarketVolume", "openInterest",
    "marketCap", "beta", "dividendYield", "payoutRatio",
    "fiftyDayAverage", "twoHundredDayAverage",
    "priceToSalesTrailing12Months", "trailingPE",
    "currency", "quoteType", "exchange", "market"
]

def filter_info(info):
    return {k: info.get(k) for k in COMMODITY_INSTITUTIONAL_FIELDS if k in info}

def _fetch_commodity_batch(targets):
    """Fetch price data for a batch of commodity symbols. Returns list."""
    data = []
    for item in targets:
        try:
            info = yf.Ticker(item["symbol"]).info
            price = info.get("regularMarketPrice") or info.get("previousClose")
            if price:
                raw_chg = info.get("regularMarketChangePercent")
                data.append({
                    "symbol": item["symbol"],
                    "name": item["name"],
                    "category": item["category"],
                    "price": float(price),
                    "regularMarketChangePercent": float(raw_chg) if raw_chg is not None else 0.0
                })
        except Exception as e:
            log.warning(f"COMMODITY_BG [{item['symbol']}]: {e}")
            continue
    return data

async def fetch_commodity_highlights_loop():
    """Background task: refresh ALL commodities every 60s into thread-safe cache."""
    log.info("COMMODITY_BG: Updater started")
    loop = asyncio.get_event_loop()
    while True:
        try:
            # Offload blocking YFinance calls to a thread pool
            data = await loop.run_in_executor(None, _fetch_commodity_batch, COMMODITY_ENTITIES)
            
            with _CACHE_LOCK:
                COMMODITY_CACHE["highlights"] = data
                COMMODITY_CACHE["last_updated"] = time.time()
            log.info(f"COMMODITY_BG: Cached {len(data)}/{len(COMMODITY_ENTITIES)} commodities")
        except Exception as e:
            log.error(f"COMMODITY_BG loop error: {e}")
        await asyncio.sleep(60)

@app.get("/api/commodity/prices")
def get_commodity_prices(sector: str = "all", commodity: str = ""):
    """Alias endpoint — gateway calls /api/commodity/prices?sector=...&commodity=...
    Delegates to the commodity highlights logic."""
    return get_commodities_highlights()


@app.get("/api/commodities/highlights")
def get_commodities_highlights():
    """Return cached commodity prices. Background loop keeps fresh every 60s."""
    with _CACHE_LOCK:
        data = list(COMMODITY_CACHE["highlights"])
        last_updated = COMMODITY_CACHE["last_updated"]
    if not data:
        return {"status": "loading", "data": [], "message": "Data is loading, retry in 10s"}
    return {"status": "success", "data": data, "cached": True, "age_seconds": round(time.time() - last_updated)}

@app.get("/api/commodities/detail/{symbol}")
def get_commodity_detail(symbol: str, period: str = "6mo"):
    try:
        # Check cache first
        cached = get_commodity_detail_cache(symbol, period)
        if cached:
            return {"status": "success", "data": cached}

        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        # History based on requested period
        hist = ticker.history(period=period)
        history_data = []
        if not hist.empty:
            hist = hist.reset_index()
            hist['Date'] = hist['Date'].dt.strftime('%Y-%m-%d')
            history_data = clean_data(hist.to_dict(orient='records'))

        # Construct commodity detail with filtered institutional field
        detail = {
            "symbol": symbol,
            "name": info.get("shortName", next((x["name"] for x in COMMODITY_ENTITIES if x["symbol"] == symbol), symbol)),
            "price": info.get("regularMarketPrice", info.get("previousClose")),
            "bid": info.get("bid"),
            "ask": info.get("ask"),
            "dayLow": info.get("dayLow"),
            "dayHigh": info.get("dayHigh"),
            "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
            "previousClose": info.get("previousClose"),
            "volume": info.get("volume") or info.get("regularMarketVolume"),
            "openInterest": info.get("openInterest"),
            "history": history_data,
            "institutional": filter_info(info)  # Filtered from ~80KB to ~5KB
        }
        
        set_commodity_detail_cache(symbol, period, detail)
        return {"status": "success", "data": detail}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/commodities/stats/seasonality/{symbol}")
def get_commodity_seasonality(symbol: str):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="10y")
        if df.empty: 
            raise HTTPException(status_code=404, detail="No data found")
            
        df['Month'] = df.index.month
        df['Year'] = df.index.year
        df['Returns'] = df['Close'].pct_change()
        
        perf = df.groupby(['Year', 'Month'])['Returns'].sum().unstack()
        
        years = [float(y) for y in perf.index]
        matrix = []
        for i, year in enumerate(perf.index):
            for m_idx in range(1, 13):
                val = perf.loc[year, m_idx] if m_idx in perf.columns else 0
                matrix.append([m_idx - 1, i, clean_data(val * 100)]) # percentage
        
        return {
            "status": "success",
            "data": {
                "months": ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"],
                "years": years,
                "matrix": matrix
            }
        }
    except Exception as e:
        print(f"Seasonality Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/commodities/market-summary")
def get_market_summary(currency: Optional[str] = None):
    """
    Get a summary of major oil benchmarks and exchange rate for localization.
    """
    try:
        benchmarks = ["BZ=F", "CL=F", "RB=F"]
        results = {}
        
        # 1. Fetch Oil Benchmarks
        for sym in benchmarks:
            ticker = yf.Ticker(sym)
            info = ticker.info
            results[sym] = {
                "name": info.get("shortName", sym),
                "price": info.get("regularMarketPrice") or info.get("previousClose"),
                "change_pct": info.get("regularMarketChangePercent", 0)
            }
            
        # 2. Fetch Exchange Rate if currency provided
        rate = 1.0
        if currency and currency != "USD":
            fx_sym = f"USD{currency}=X"
            fx = yf.Ticker(fx_sym).info
            rate = fx.get("regularMarketPrice") or fx.get("previousClose") or 1.0
            
        return {
            "status": "success",
            "data": {
                "benchmarks": results,
                "currency": currency or "USD",
                "rate": float(rate)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {"status": "online", "service": "commodity_intelligence_service"}

# ============================================================================
# 2.3 COMMODITY FUTURES CURVE — Term Structure, Crack Spread, Crush Spread
# ============================================================================

# Futures contract months mapping for key commodities
FUTURES_MONTHS = {
    "CL=F": {"codes": ["CL=F", "CLG26.NYM", "CLJ26.NYM", "CLK26.NYM", "CLM26.NYM", "CLN26.NYM", "CLQ26.NYM", "CLU26.NYM", "CLV26.NYM", "CLX26.NYM", "CLZ26.NYM", "CLF27.NYM"], "name": "Crude Oil WTI"},
    "BZ=F": {"codes": ["BZ=F", "BZG26.NYM", "BZJ26.NYM", "BZK26.NYM", "BZM26.NYM", "BZN26.NYM", "BZQ26.NYM", "BZU26.NYM", "BZV26.NYM", "BZX26.NYM", "BZZ26.NYM", "BZF27.NYM"], "name": "Brent Crude"},
    "NG=F": {"codes": ["NG=F", "NGG26.NYM", "NGJ26.NYM", "NGK26.NYM", "NGM26.NYM", "NGN26.NYM", "NGQ26.NYM", "NGU26.NYM", "NGV26.NYM", "NGX26.NYM", "NGZ26.NYM", "NGF27.NYM"], "name": "Natural Gas"},
    "GC=F": {"codes": ["GC=F", "GCG26.CMX", "GCJ26.CMX", "GCM26.CMX", "GCQ26.CMX", "GCV26.CMX", "GCZ26.CMX", "GCG27.CMX"], "name": "Gold"},
    "SI=F": {"codes": ["SI=F", "SIH26.CMX", "SIK26.CMX", "SIN26.CMX", "SIU26.CMX", "SIV26.CMX", "SIZ26.CMX", "SIH27.CMX"], "name": "Silver"},
    "HG=F": {"codes": ["HG=F", "HGH26.CMX", "HGK26.CMX", "HGN26.CMX", "HGU26.CMX", "HGV26.CMX", "HGZ26.CMX", "HGH27.CMX"], "name": "Copper"},
}

FUTURES_CACHE = {}
FUTURES_CACHE_TTL = 3600  # 1 hour — term structure changes slowly

def _get_futures_cache(key):
    entry = FUTURES_CACHE.get(key)
    if entry and time.time() - entry['ts'] < FUTURES_CACHE_TTL:
        return entry['data']
    return None

def _set_futures_cache(key, data):
    FUTURES_CACHE[key] = {'ts': time.time(), 'data': data}

@app.get("/api/commodities/futures-curve")
async def get_futures_curve(symbol: str = "CL=F"):
    """Get futures term structure for a commodity. Returns front-month to 12th month prices."""
    try:
        # Check cache
        cached = _get_futures_cache(f"curve_{symbol}")
        if cached:
            return {"status": "success", "data": cached, "cached": True}

        config = FUTURES_MONTHS.get(symbol.upper())
        if not config:
            # Try to build dynamically
            base = symbol.upper()
            config = {"codes": [base], "name": base.replace("=F", "")}

        loop = asyncio.get_event_loop()

        def _fetch_curve():
            curve = []
            for code in config["codes"]:
                try:
                    tk = yf.Ticker(code)
                    info = tk.info
                    price = info.get("regularMarketPrice") or info.get("previousClose")
                    if price:
                        curve.append({
                            "contract": code,
                            "price": float(price),
                            "change_pct": float(info.get("regularMarketChangePercent", 0) or 0),
                            "volume": info.get("volume") or info.get("regularMarketVolume"),
                            "open_interest": info.get("openInterest")
                        })
                except:
                    continue
                time.sleep(0.1)  # Rate limit protection
            return curve

        curve = await loop.run_in_executor(None, _fetch_curve)
        result = {
            "symbol": symbol,
            "name": config["name"],
            "contango": True,  # Will be determined if front < back
            "curve": curve,
            "spread": None
        }

        # Determine contango/backwardation
        if len(curve) >= 2:
            front = curve[0]["price"]
            back = curve[-1]["price"]
            result["contango"] = back > front
            result["spread"] = round(((back / front) - 1) * 100, 2)  # Annualized roughly

        _set_futures_cache(f"curve_{symbol}", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/commodities/crack-spread")
async def get_crack_spread():
    """3:2:1 Crack Spread — profit margin of refining 3 barrels of crude into 2 gas + 1 heating oil."""
    try:
        cached = _get_futures_cache("crack_spread")
        if cached:
            return {"status": "success", "data": cached, "cached": True}

        loop = asyncio.get_event_loop()

        def _fetch_crack():
            # Fetch crude (CL=F), gasoline (RB=F), heating oil (HO=F)
            cl = yf.Ticker("CL=F")
            rb = yf.Ticker("RB=F")
            ho = yf.Ticker("HO=F")

            cl_info = cl.info
            rb_info = rb.info
            ho_info = ho.info

            crude_price = cl_info.get("regularMarketPrice") or cl_info.get("previousClose")
            gas_price = rb_info.get("regularMarketPrice") or rb_info.get("previousClose")
            heat_price = ho_info.get("regularMarketPrice") or ho_info.get("previousClose")

            if not all([crude_price, gas_price, heat_price]):
                return None

            crude_price = float(crude_price)
            gas_price = float(gas_price)
            heat_price = float(heat_price)

            # 3:2:1 Crack Spread = (2 * RBOB + 1 * HO) - (3 * Crude)
            # All converted to $/bbl: RBOB (42 gal = 1 bbl), HO (42 gal = 1 bbl), Crude is already $/bbl
            crack_value = (2 * gas_price + 1 * heat_price) - (3 * crude_price)
            crack_percent = (crack_value / (3 * crude_price)) * 100 if crude_price > 0 else 0

            return {
                "crude_price": crude_price,
                "gasoline_price": gas_price,
                "heating_oil_price": heat_price,
                "crack_spread_3_2_1": round(crack_value, 2),
                "crack_spread_pct": round(crack_percent, 2),
                "interpretation": "PROFITABLE" if crack_value > 0 else "UNPROFITABLE",
                "timestamp": time.time()
            }

        result = await loop.run_in_executor(None, _fetch_crack)
        if not result:
            raise HTTPException(status_code=502, detail="Failed to fetch crack spread data")
        _set_futures_cache("crack_spread", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/commodities/crush-spread")
async def get_crush_spread():
    """Soybean Crush Spread — profit margin of crushing soybeans into meal + oil.
    Board Crush = Soybean Meal (1 contract = 100 short tons) + Soybean Oil (1 contract = 60,000 lbs) - Soybeans (1 contract = 5,000 bu)
    Simplified: ZL (soybean oil) + ZM (soybean meal) - ZS (soybeans)
    """
    try:
        cached = _get_futures_cache("crush_spread")
        if cached:
            return {"status": "success", "data": cached, "cached": True}

        loop = asyncio.get_event_loop()

        def _fetch_crush():
            zs = yf.Ticker("ZS=F")
            zl = yf.Ticker("ZL=F")
            zm = yf.Ticker("ZM=F")

            zs_info = zs.info
            zl_info = zl.info
            zm_info = zm.info

            soy_price = zs_info.get("regularMarketPrice") or zs_info.get("previousClose")
            oil_price = zl_info.get("regularMarketPrice") or zl_info.get("previousClose")
            meal_price = zm_info.get("regularMarketPrice") or zm_info.get("previousClose")

            if not all([soy_price, oil_price, meal_price]):
                return None

            soy_price = float(soy_price)
            oil_price = float(oil_price)
            meal_price = float(meal_price)

            # Simplified crush: value of meal + oil vs cost of beans (per bushel)
            # 1 bushel soybeans ≈ 44 lbs meal + 11 lbs oil
            # Simplified: crush_margin = meal_price * 0.022 + oil_price * 0.0055 - soy_price
            # more practically: margin = (meal_price/100 * 44) + (oil_price/100 * 11) - soy_price
            crush_margin = (meal_price / 100 * 44) + (oil_price / 100 * 11) - soy_price
            crush_pct = (crush_margin / soy_price) * 100 if soy_price > 0 else 0

            return {
                "soybean_price": soy_price,
                "soybean_oil_price": oil_price,
                "soybean_meal_price": meal_price,
                "crush_spread": round(crush_margin, 2),
                "crush_spread_pct": round(crush_pct, 2),
                "interpretation": "PROFITABLE" if crush_margin > 0 else "UNPROFITABLE",
                "timestamp": time.time()
            }

        result = await loop.run_in_executor(None, _fetch_crush)
        if not result:
            raise HTTPException(status_code=502, detail="Failed to fetch crush spread data")
        _set_futures_cache("crush_spread", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    return {"status": "online", "service": "commodity_intelligence_service"}

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(fetch_commodity_highlights_loop())

if __name__ == "__main__":
    print("=:: LAUNCHING COMMODITY INTELLIGENCE SERVICE (Port 8087) ::= ")
    uvicorn.run(app, host="0.0.0.0", port=8087)
