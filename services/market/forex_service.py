import os
import time
import asyncio
import threading
import concurrent.futures
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
log = logging.getLogger('forex_service')
import requests
import re
import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import Dict, Any, List, Optional

app = FastAPI(debug=True, title="Forex Intelligence Microservice")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAJOR_PAIRS = [
    # --- INDONESIA FOCUS ---
    "USDIDR=X", "EURIDR=X", "GBPIDR=X", "SGDIDR=X", 
    "JPYIDR=X", "CNYIDR=X", "AUDIDR=X", "MYRIDR=X", 
    "THBIDR=X", "HKDIDR=X", "KRWIDR=X",
    
    # --- GLOBAL MAJORS ---
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X", 
    "AUDUSD=X", "USDCAD=X", "NZDUSD=X",
    
    # --- IMPORTANT CROSSES ---
    "EURGBP=X", "EURJPY=X", "GBPJPY=X", "EURCHF=X", 
    "EURAUD=X", "GBPCHF=X", "AUDJPY=X", "CADJPY=X",
    
    # --- ASIAN & EMERGING NODES ---
    "USDCNY=X", "USDHKD=X", "USDSGD=X", "USDMYR=X", 
    "USDTHB=X", "USDPHP=X", "USDVND=X", "USDINR=X",
    "USDKRW=X", "USDMXN=X", "USDBRL=X", "USDZAR=X", 
    "USDTRY=X", "USDSAR=X", "USDAED=X", "USDILS=X"
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

# FOREX CACHE — thread-safe
FOREX_CACHE = {
    "list": [],
    "last_updated": 0
}
_CACHE_LOCK = threading.Lock()

# DETAIL CACHE — reduce redundant yfinance calls
FOREX_DETAIL_CACHE = {}
FOREX_D_CACHE_TTL = 900  # 15 mins

def get_forex_detail_cache(symbol, period):
    key = f"{symbol}:{period}"
    if key in FOREX_DETAIL_CACHE:
        entry = FOREX_DETAIL_CACHE[key]
        if time.time() - entry['timestamp'] < FOREX_D_CACHE_TTL:
            return entry['data']
    return None

def set_forex_detail_cache(symbol, period, data):
    key = f"{symbol}:{period}"
    FOREX_DETAIL_CACHE[key] = {'timestamp': time.time(), 'data': data}

# Fields the frontend actually uses — filter out 80KB+ of noise from ticker.info
FOREX_INSTITUTIONAL_FIELDS = [
    "shortName", "regularMarketPrice", "previousClose", "bid", "ask",
    "dayLow", "dayHigh", "fiftyTwoWeekLow", "fiftyTwoWeekHigh",
    "volume", "regularMarketVolume",
    "fiftyDayAverage", "twoHundredDayAverage",
    "currency", "quoteType", "exchange", "market",
    "fromCurrency", "toCurrency"
]

def filter_info(info):
    return {k: info.get(k) for k in FOREX_INSTITUTIONAL_FIELDS if k in info}

def _build_forex_entry(symbol, info):
    """Build a normalized forex dict from yfinance info."""
    price = info.get("regularMarketPrice") or info.get("previousClose")
    if not price:
        return None
    name = symbol.replace("=X", "")
    base, quote = (name[:3], name[3:]) if len(name) > 3 else ("USD", name)
    raw_chg = info.get("regularMarketChangePercent")
    return {
        "symbol": symbol,
        "name": f"{base} / {quote}",
        "price": float(price),
        "change_pct": float(raw_chg) if raw_chg is not None else 0.0
    }

def _fetch_single_pair(symbol):
    """Fetch a single forex pair — used by ThreadPoolExecutor for concurrent fetching."""
    try:
        info = yf.Ticker(symbol).info
        entry = _build_forex_entry(symbol, info)
        return entry
    except Exception as e:
        log.warning(f"FOREX_BG [{symbol}]: {e}")
        return None

async def fetch_forex_list_loop():
    """Background task: refresh ALL forex pairs every 60s into thread-safe cache (CONCURRENT)."""
    log.info("FOREX_BG: Updater started")
    loop = asyncio.get_event_loop()
    while True:
        try:
            # Concurrent fetching via ThreadPoolExecutor — was sequential 20-45s, now ~2-5s
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
                tasks = [loop.run_in_executor(pool, _fetch_single_pair, symbol) for symbol in MAJOR_PAIRS]
                results = await asyncio.gather(*tasks)
            
            data = [r for r in results if r is not None]
            
            with _CACHE_LOCK:
                FOREX_CACHE["list"] = data
                FOREX_CACHE["last_updated"] = time.time()
            log.info(f"FOREX_BG: Cached {len(data)}/{len(MAJOR_PAIRS)} pairs")
            
        except Exception as e:
            log.error(f"FOREX_BG loop error: {e}")
            
        await asyncio.sleep(60)

@app.get("/api/forex/list")
def get_forex_list():
    """Always return from cache. Background loop keeps it fresh every 60s."""
    with _CACHE_LOCK:
        cached_data = list(FOREX_CACHE["list"])
        last_updated = FOREX_CACHE["last_updated"]

    if not cached_data:
        # Cache not ready yet — return empty with status
        return {"status": "loading", "data": [], "message": "Data is loading, retry in 10s"}

    age_s = round(time.time() - last_updated)
    return {
        "status": "success",
        "data": cached_data,
        "cached": True,
        "age_seconds": age_s
    }

@app.get("/api/forex/detail/{symbol}")
def get_forex_detail(symbol: str, period: str = "6mo"):
    try:
        # Check cache first
        cached = get_forex_detail_cache(symbol, period)
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

        # Construct specific forex detail with filtered institutional field
        detail = {
            "symbol": symbol,
            "name": info.get("shortName", symbol),
            "price": info.get("regularMarketPrice", info.get("previousClose")),
            "bid": info.get("bid"),
            "ask": info.get("ask"),
            "dayLow": info.get("dayLow"),
            "dayHigh": info.get("dayHigh"),
            "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
            "previousClose": info.get("previousClose"),
            "history": history_data,
            "institutional": filter_info(info)  # Filtered from ~80KB to ~5KB
        }

        # News (Generic search for Forex news)
        news = []
        try:
            # yfinance news for forex tickers is often empty, let's try generic
            news_data = ticker.news
            for item in news_data[:5]:
                news.append({
                    "title": item.get("title"),
                    "source": item.get("publisher"),
                    "date": time.strftime('%Y-%m-%d', time.gmtime(item.get("provider_publish_time", 0))),
                    "url": item.get("link")
                })
        except: pass

        detail["news"] = news
        
        set_forex_detail_cache(symbol, period, detail)
        return {"status": "success", "data": detail}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/forex/stats/correlation")
def get_forex_correlation():
    try:
        # Use top 12 pairs for a clean heatmap
        symbols = MAJOR_PAIRS[:12]
        data = yf.download(symbols, period="1y", progress=False)['Close']
        
        # Fill missing values
        data = data.ffill().pct_change().dropna()
        corr = data.corr()
        
        nodes = [s.replace("=X", "") for s in corr.columns]
        matrix = []
        for i, row in enumerate(corr.index):
            for j, col in enumerate(corr.columns):
                val = corr.iloc[i, j]
                matrix.append([j, i, clean_data(val)])
                
        return {
            "status": "success", 
            "data": {
                "nodes": nodes,
                "matrix": matrix
            }
        }
    except Exception as e:
        print(f"Correlation Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/forex/stats/seasonality/{symbol}")
def get_forex_seasonality(symbol: str):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="10y") # Use 10 years for robust seasonality
        if df.empty: 
            raise HTTPException(status_code=404, detail="No data found")
            
        df['Month'] = df.index.month
        df['Year'] = df.index.year
        df['Returns'] = df['Close'].pct_change()
        
        # Monthly performance matrix (Year vs Month)
        # We group by Year and Month, and sum the daily returns for each month
        perf = df.groupby(['Year', 'Month'])['Returns'].sum().unstack()
        
        # Cleanup: Remove current year if it's incomplete for current month? 
        # No, just keep what we have.
        
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

@app.get("/")
async def root():
    return {"status": "online", "service": "forex_intelligence_service"}

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(fetch_forex_list_loop())

if __name__ == "__main__":
    print("=:: LAUNCHING FOREX INTELLIGENCE SERVICE (Port 8086) ::= ")
    uvicorn.run(app, host="0.0.0.0", port=8086)
