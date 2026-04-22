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
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        # History based on requested period
        hist = ticker.history(period=period)
        history_data = []
        if not hist.empty:
            hist = hist.reset_index()
            hist['Date'] = hist['Date'].dt.strftime('%Y-%m-%d')
            history_data = clean_data(hist.to_dict(orient='records'))

        # Construct commodity detail
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
            "institutional": info
        }
        
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

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(fetch_commodity_highlights_loop())

if __name__ == "__main__":
    print("=:: LAUNCHING COMMODITY INTELLIGENCE SERVICE (Port 8087) ::= ")
    uvicorn.run(app, host="0.0.0.0", port=8087)
