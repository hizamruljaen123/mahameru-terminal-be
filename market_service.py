import os
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import asyncio
import time
import threading
import logging
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
from db import get_db_connection

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
log = logging.getLogger('market_service')

app = FastAPI(debug=True, title="Asetpedia Institutional Market Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WATCHLIST_CONFIG = {
    "indices": [
      {"symbol": "^GSPC", "name": "S&P 500", "country": "USA"},
      {"symbol": "^NDX", "name": "Nasdaq 100", "country": "USA"},
      {"symbol": "^N225", "name": "Nikkei 225", "country": "Japan"},
      {"symbol": "^FTSE", "name": "FTSE 100", "country": "UK"},
      {"symbol": "^GDAXI", "name": "DAX Performance Index", "country": "Germany"},
      {"symbol": "^HSI", "name": "Hang Seng Index", "country": "Hong Kong"},
      {"symbol": "000001.SS", "name": "SSE Composite", "country": "China"},
      {"symbol": "^JKSE", "name": "IHSG", "country": "Indonesia"}
    ],
    "cryptocurrency": [
      {"symbol": "BTC-USD", "name": "Bitcoin"},
      {"symbol": "ETH-USD", "name": "Ethereum"},
      {"symbol": "SOL-USD", "name": "Solana"},
      {"symbol": "BNB-USD", "name": "Binance Coin"},
      {"symbol": "XRP-USD", "name": "Ripple"}
    ],
    "commodities": [
      {"symbol": "GC=F", "name": "Gold"},
      {"symbol": "SI=F", "name": "Silver"},
      {"symbol": "CL=F", "name": "Crude Oil WTI"},
      {"symbol": "BZ=F", "name": "Brent Crude Oil"},
      {"symbol": "HG=F", "name": "Copper"},
      {"symbol": "NG=F", "name": "Natural Gas"}
    ],
    "forex": [
      {"symbol": "EURUSD=X", "name": "EUR/USD"},
      {"symbol": "JPY=X", "name": "USD/JPY"},
      {"symbol": "GBPUSD=X", "name": "GBP/USD"},
      {"symbol": "AUDUSD=X", "name": "AUD/USD"},
      {"symbol": "USDIDR=X", "name": "USD/IDR"}  # Fixed: was IDR=X
    ],
    "blue_chips_global": [
      {"symbol": "NVDA", "name": "NVIDIA Corporation"},
      {"symbol": "AAPL", "name": "Apple Inc."},
      {"symbol": "MSFT", "name": "Microsoft Corporation"},
      {"symbol": "GOOGL", "name": "Alphabet Inc."},
      {"symbol": "AMZN", "name": "Amazon.com Inc."}
    ],
    "blue_chips_indonesia": [
      {"symbol": "BBCA.JK", "name": "Bank Central Asia Tbk."},
      {"symbol": "BBRI.JK", "name": "Bank Rakyat Indonesia Tbk."},
      {"symbol": "TLKM.JK", "name": "Telkom Indonesia Tbk."},
      {"symbol": "BMRI.JK", "name": "Bank Mandiri Tbk."},
      {"symbol": "ASII.JK", "name": "Astra International Tbk."},
      {"symbol": "ICBP.JK", "name": "Indofood CBP Sukses Makmur Tbk."}
    ]
}

SECTOR_ETF = {
    'technology':           'XLK',
    'financial-services':   'XLF',
    'communication-services':'XLC',
    'consumer-cyclical':    'XLY',
    'industrials':          'XLI',
    'healthcare':           'XLV',
    'energy':               'XLE',
    'consumer-defensive':   'XLP',
    'basic-materials':      'XLB',
    'utilities':            'XLU',
    'real-estate':          'XLRE'
}

SECTOR_NAMES = {
    'technology': 'Technology',
    'financial-services': 'Financial Services',
    'communication-services': 'Communication Services',
    'consumer-cyclical': 'Consumer Cyclical',
    'industrials': 'Industrials',
    'healthcare': 'Healthcare',
    'energy': 'Energy',
    'consumer-defensive': 'Consumer Defensive',
    'basic-materials': 'Basic Materials',
    'utilities': 'Utilities',
    'real-estate': 'Real Estate'
}

SECTOR_CACHE = {
    "data": [],
    "last_updated": 0
}

def clean(val):
    """Return None for missing/invalid, float for valid values."""
    if val is None:
        return None
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None

_MARKET_EXEC = ThreadPoolExecutor(max_workers=8)

def _sync_fetch_ticker(symbol, metadata):
    """Synchronous ticker fetch — runs inside thread pool."""
    try:
        info = yf.Ticker(symbol).info
        price = clean(info.get("regularMarketPrice") or info.get("previousClose") or info.get("currentPrice"))
        return {
            "symbol": symbol,
            "name": metadata.get("name", info.get("shortName", symbol)),
            "price": price,
            "change_pct": clean(info.get("regularMarketChangePercent")) or 0.0,
            "country": metadata.get("country"),
            "category": metadata.get("category")
        }
    except Exception as e:
        log.warning(f"MARKET_FETCH [{symbol}]: {e}")
        return None

# GLOBAL MARKET CACHE
MARKET_CACHE = {
    "data": {},
    "last_updated": 0
}

async def market_update_loop():
    """Background task: fetch all watchlist via thread pool every 60s."""
    log.info("MARKET_BG: Updater started")
    while True:
        try:
            futures = []
            meta_list = []
            for cat, items in WATCHLIST_CONFIG.items():
                for item in items:
                    meta = {**item, "category": cat}
                    meta_list.append(meta)
                    futures.append(_MARKET_EXEC.submit(_sync_fetch_ticker, item["symbol"], meta))

            new_data = {}
            for future, meta in zip(futures, meta_list):
                try:
                    res = future.result(timeout=15)
                    if res:
                        cat = res["category"]
                        new_data.setdefault(cat, []).append(res)
                except Exception as e:
                    log.warning(f"MARKET_BG future error: {e}")

            MARKET_CACHE["data"] = new_data
            MARKET_CACHE["last_updated"] = time.time()
            total = sum(len(v) for v in new_data.values())
            log.info(f"MARKET_BG: {total} assets cached")
        except Exception as e:
            log.error(f"MARKET_BG loop error: {e}")
        await asyncio.sleep(60)

@app.get("/api/market/watchlist")
async def get_watchlist():
    if MARKET_CACHE["data"] and (time.time() - MARKET_CACHE["last_updated"] < 90):
        return {"status": "success", "data": MARKET_CACHE["data"], "cached": True}
    # Cache miss — offload to thread pool and await
    loop = asyncio.get_event_loop()
    futures = []
    meta_list = []
    for cat, items in WATCHLIST_CONFIG.items():
        for item in items:
            meta = {**item, "category": cat}
            meta_list.append(meta)
            futures.append(loop.run_in_executor(_MARKET_EXEC, _sync_fetch_ticker, item["symbol"], meta))
    results = await asyncio.gather(*futures, return_exceptions=True)
    final_data = {}
    for res in results:
        if res and isinstance(res, dict):
            cat = res["category"]
            final_data.setdefault(cat, []).append(res)
    return {"status": "success", "data": final_data}

@app.get("/api/market/health")
def market_health():
    age = round(time.time() - MARKET_CACHE["last_updated"]) if MARKET_CACHE["last_updated"] else None
    total = sum(len(v) for v in MARKET_CACHE["data"].values())
    return {"status": "ok", "cached_assets": total, "cache_age_seconds": age}


# ─────────────────────────────────────────────────────────────────────────────
# QUICK PRICE LOOKUP — single symbol, any yfinance-supported ticker
# Used by Watchlist View to fetch current prices for user positions
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/market/price")
async def get_quick_price(symbol: str):
    """Fast price lookup for any yfinance symbol (stock/forex/commodity/crypto)."""
    try:
        loop = asyncio.get_event_loop()
        def _fetch():
            ticker = yf.Ticker(symbol)
            info = ticker.info
            price = clean(info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose"))
            prev  = clean(info.get("regularMarketPreviousClose") or info.get("previousClose"))
            chg_pct = clean(info.get("regularMarketChangePercent"))
            if chg_pct is None and price and prev and prev > 0:
                chg_pct = (price - prev) / prev * 100
            return {
                "status": "success",
                "symbol": symbol,
                "name": info.get("shortName") or info.get("longName") or symbol,
                "price": price,
                "change_pct": chg_pct or 0.0,
                "currency": info.get("currency", "USD")
            }
        result = await loop.run_in_executor(_MARKET_EXEC, _fetch)
        return result
    except Exception as e:
        log.warning(f"QUICK_PRICE [{symbol}]: {e}")
        return {"status": "error", "symbol": symbol, "price": None, "change_pct": None, "currency": None}


# ─────────────────────────────────────────────────────────────────────────────
# HISTORICAL OHLCV — for Watchlist chart panel
# ─────────────────────────────────────────────────────────────────────────────
RANGE_MAP = {
    '1W':  ('5d',    '15m'),
    '1M':  ('1mo',   '1d'),
    '3M':  ('3mo',   '1d'),
    '6M':  ('6mo',   '1d'),
    '1Y':  ('1y',    '1wk'),
    '5Y':  ('5y',    '1wk'),
    'ALL': ('max',   '1mo'),
}

@app.get("/api/market/history")
async def get_history(symbol: str, range: str = "1M"):
    """Return OHLCV history for any yfinance symbol."""
    period, interval = RANGE_MAP.get(range, ('1mo', '1d'))
    try:
        loop = asyncio.get_event_loop()
        def _fetch():
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            if df.empty:
                return {"status": "error", "history": []}
            records = []
            for ts, row in df.iterrows():
                records.append({
                    "date": str(ts)[:10] if interval in ('1d', '1wk', '1mo') else str(ts)[:16],
                    "open":   clean(row["Open"]),
                    "high":   clean(row["High"]),
                    "low":    clean(row["Low"]),
                    "close":  clean(row["Close"]),
                    "volume": int(row["Volume"]) if not pd.isna(row["Volume"]) else 0,
                })
            info = ticker.info
            return {
                "status": "success",
                "symbol": symbol,
                "name": info.get("shortName") or info.get("longName") or symbol,
                "currency": info.get("currency", "USD"),
                "range": range,
                "interval": interval,
                "history": records,
            }
        result = await loop.run_in_executor(_MARKET_EXEC, _fetch)
        return result
    except Exception as e:
        log.warning(f"HISTORY [{symbol}]: {e}")
        return {"status": "error", "symbol": symbol, "history": []}


# ─────────────────────────────────────────────────────────────────────────────
# CROSS-ASSET CORRELATION ENGINE
# ─────────────────────────────────────────────────────────────────────────────
class CorrelationRequest(BaseModel):
    symbols: list
    names: dict = {}
    window: str = "30d"

def _fetch_returns(symbol: str, window: str) -> pd.Series:
    """Fetch daily % returns for a symbol."""
    hist = yf.Ticker(symbol).history(period=window)["Close"]
    return hist.pct_change().dropna().rename(symbol)

@app.post("/api/market/correlation")
async def get_correlation(req: CorrelationRequest):
    """Calculate Pearson correlation matrix for the given symbols."""
    symbols = req.symbols
    if not symbols or len(symbols) < 2:
        raise HTTPException(status_code=400, detail="Minimum 2 symbols required")
    if len(symbols) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 symbols allowed")

    try:
        loop = asyncio.get_event_loop()
        futures = [loop.run_in_executor(_MARKET_EXEC, _fetch_returns, s, req.window) for s in symbols]
        series_list = await asyncio.gather(*futures, return_exceptions=True)

        price_dict = {}
        valid_symbols = []
        for s, series in zip(symbols, series_list):
            if isinstance(series, pd.Series) and len(series) >= 3:
                price_dict[s] = series
                valid_symbols.append(s)

        if len(valid_symbols) < 2:
            return {"status": "error", "detail": "Insufficient data for symbols"}

        df = pd.DataFrame(price_dict).dropna(how="all")
        corr = df.corr(method="pearson")

        return {
            "status": "success",
            "symbols": valid_symbols,
            "names": {s: req.names.get(s, s) for s in valid_symbols},
            "matrix": [[round(float(v), 4) if pd.notna(v) else 0.0 for v in row]
                        for row in corr.values],
            "data_points": len(df),
            "window": req.window
        }
    except Exception as e:
        log.error(f"CORRELATION error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/market/var")
async def calculate_var(req: CorrelationRequest):
    """Calculate Value at Risk (VaR) and Expected Shortfall for a portfolio."""
    symbols = req.symbols
    if not symbols:
        raise HTTPException(status_code=400, detail="Minimum 1 symbol required")
        
    try:
        loop = asyncio.get_event_loop()
        futures = [loop.run_in_executor(_MARKET_EXEC, _fetch_returns, s, req.window) for s in symbols]
        series_list = await asyncio.gather(*futures, return_exceptions=True)

        price_dict = {}
        for s, series in zip(symbols, series_list):
            if isinstance(series, pd.Series) and len(series) >= 20: 
                price_dict[s] = series

        if not price_dict:
            return {"status": "error", "detail": "Insufficient historical data for VaR calculation"}

        df = pd.DataFrame(price_dict).dropna(how="all").fillna(0)
        
        # Assume equal weight portfolio
        weights = np.array([1/len(price_dict)] * len(price_dict))
        
        # Portfolio historical returns
        port_returns = df.dot(weights)
        
        # Historical VaR (95% confidence)
        var_95 = np.percentile(port_returns, 5) * 100
        var_99 = np.percentile(port_returns, 1) * 100
        
        # Expected Shortfall (CVaR)
        cvar_95 = port_returns[port_returns <= (var_95/100)].mean() * 100
        if pd.isna(cvar_95): cvar_95 = 0.0
        
        # Volatility (Annualized)
        volatility = port_returns.std() * np.sqrt(252) * 100
        
        # Max Drawdown
        cum_returns = (1 + port_returns).cumprod()
        rolling_max = cum_returns.cummax()
        drawdown = (cum_returns - rolling_max) / rolling_max
        max_drawdown = drawdown.min() * 100

        return {
            "status": "success",
            "symbols": list(price_dict.keys()),
            "metrics": {
                "var_95_pct": round(float(var_95), 2),
                "var_99_pct": round(float(var_99), 2),
                "expected_shortfall_95_pct": round(float(cvar_95), 2),
                "volatility_annualized_pct": round(float(volatility), 2),
                "max_drawdown_pct": round(float(max_drawdown), 2)
            },
            "window": req.window,
            "data_points": len(df)
        }
    except Exception as e:
        log.error(f"VAR error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────────────────────────────────────
# CORPORATE EVENT ENGINE (Earnings & Dividends)
# ─────────────────────────────────────────────────────────────────────────────
CALENDAR_TARGETS = [
    # Indonesia
    "BBCA.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASII.JK", "GOTO.JK", 
    # Global
    "AAPL", "MSFT", "NVDA", "TSLA", "GOOGL", "META", "AMZN"
]

def _fetch_calendar(symbol: str) -> dict:
    try:
        cal = yf.Ticker(symbol).calendar
        if not cal: return None
        events = []
        name = symbol.replace(".JK", "")
        # Extract earnings
        if "Earnings Date" in cal and isinstance(cal["Earnings Date"], list) and len(cal["Earnings Date"]) > 0:
            events.append({
                "type": "EARNINGS",
                "symbol": symbol,
                "name": f"{name} Earnings",
                "date": str(cal["Earnings Date"][0]),
                "consensus_eps": _safe(cal.get("Earnings Average")),
                "consensus_rev": _safe(cal.get("Revenue Average"))
            })
        # Extract dividend
        if "Ex-Dividend Date" in cal:
            events.append({
                "type": "DIVIDEND",
                "symbol": symbol,
                "name": f"{name} Ex-Div",
                "date": str(cal["Ex-Dividend Date"])
            })
        return events
    except Exception as e:
        log.warning(f"CALENDAR failed for {symbol}: {e}")
        return None

@app.get("/api/market/calendar")
async def get_market_calendar():
    """Aggregates upcoming corporate events (Earnings/Dividends) from key tickers + User Watchlist."""
    loop = asyncio.get_event_loop()
    
    # 1. Fetch user-custom symbols from DB
    custom_symbols = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT symbol FROM user_calendar_watchlist")
        rows = cursor.fetchall()
        custom_symbols = [r[0] for r in rows]
        cursor.close()
        conn.close()
    except Exception as e:
        log.warning(f"Failed to fetch user calendar watchlist: {e}")

    # 2. Combine with default targets (unique)
    all_targets = list(set(CALENDAR_TARGETS + custom_symbols))
    
    futures = [loop.run_in_executor(_MARKET_EXEC, _fetch_calendar, sym) for sym in all_targets]
    results = await asyncio.gather(*futures, return_exceptions=True)
    
    events = []
    for r in results:
        if isinstance(r, list):
            events.extend(r)
            
    # Sort events by date
    events_sorted = sorted([e for e in events if "date" in e and e["date"] != "None"], key=lambda x: x["date"])
    
    return {"status": "success", "events": events_sorted}

@app.get("/api/market/company-events")
async def get_company_events(symbol: str):
    """Fetch upcoming corporate events for a single ticker."""
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(_MARKET_EXEC, _fetch_calendar, symbol.upper())
    return {"status": "success", "symbol": symbol, "events": res or []}

@app.get("/api/market/search")
async def search_ticker(query: str):
    """Simple ticker search placeholder — for now return exact matches or lookup via yf."""
    if not query: return {"results": []}
    try:
        # yfinance doesn't have a direct 'search' but we can check if it exists
        # or just return common suggestions. For professional UI, usually we'd use a search API.
        t = yf.Ticker(query)
        info = t.info
        if info.get('symbol'):
            return {"results": [{"symbol": info['symbol'], "name": info.get('shortName', info['symbol'])}]}
    except: pass
    return {"results": []}


# ─────────────────────────────────────────────────────────────────────────────
# FUNDAMENTAL DATA ENGINE — Multi-year P&L, Balance Sheet, Valuation
# ─────────────────────────────────────────────────────────────────────────────
def _safe(val):
    if val is None: return None
    try:
        f = float(val)
        return None if (np.isnan(f) or np.isinf(f)) else round(f, 4)
    except: return None

def _pct(val):
    v = _safe(val)
    return round(v * 100, 2) if v is not None else None

def _fmt_fin_df(df):
    if df is None or df.empty:
        return {}
    result = {}
    for col in df.columns:
        year = str(col)[:4]
        result[year] = {}
        for idx in df.index:
            try:
                v = df.loc[idx, col]
                if pd.notna(v):
                    result[year][str(idx)] = round(float(v), 0)
            except: pass
    return result

@app.get("/api/market/fundamental")
async def get_fundamental(symbol: str):
    """Fetch comprehensive fundamental data for a symbol using yfinance."""
    try:
        loop = asyncio.get_event_loop()
        def _fetch():
            t = yf.Ticker(symbol)
            info = t.info
            snapshot = {
                "symbol": symbol,
                "name": info.get("shortName") or info.get("longName", symbol),
                "sector": info.get("sector", "N/A"),
                "industry": info.get("industry", "N/A"),
                "currency": info.get("currency", "USD"),
                "country": info.get("country", "N/A"),
                "marketCap": _safe(info.get("marketCap")),
                "enterpriseValue": _safe(info.get("enterpriseValue")),
                "trailingPE": _safe(info.get("trailingPE")),
                "forwardPE": _safe(info.get("forwardPE")),
                "priceToBook": _safe(info.get("priceToBook")),
                "priceToSales": _safe(info.get("priceToSalesTrailing12Months")),
                "evToEbitda": _safe(info.get("enterpriseToEbitda")),
                "evToRevenue": _safe(info.get("enterpriseToRevenue")),
                "grossMargins": _pct(info.get("grossMargins")),
                "operatingMargins": _pct(info.get("operatingMargins")),
                "profitMargins": _pct(info.get("profitMargins")),
                "returnOnEquity": _pct(info.get("returnOnEquity")),
                "returnOnAssets": _pct(info.get("returnOnAssets")),
                "trailingEps": _safe(info.get("trailingEps")),
                "forwardEps": _safe(info.get("forwardEps")),
                "bookValue": _safe(info.get("bookValue")),
                "revenuePerShare": _safe(info.get("revenuePerShare")),
                "dividendYield": _pct(info.get("dividendYield")),
                "dividendRate": _safe(info.get("dividendRate")),
                "payoutRatio": _pct(info.get("payoutRatio")),
                "debtToEquity": _safe(info.get("debtToEquity")),
                "currentRatio": _safe(info.get("currentRatio")),
                "quickRatio": _safe(info.get("quickRatio")),
                "totalCash": _safe(info.get("totalCash")),
                "totalDebt": _safe(info.get("totalDebt")),
                "freeCashflow": _safe(info.get("freeCashflow")),
                "operatingCashflow": _safe(info.get("operatingCashflow")),
                "totalRevenue": _safe(info.get("totalRevenue")),
                "revenueGrowth": _pct(info.get("revenueGrowth")),
                "earningsGrowth": _pct(info.get("earningsGrowth")),
                "week52High": _safe(info.get("fiftyTwoWeekHigh")),
                "week52Low": _safe(info.get("fiftyTwoWeekLow")),
                "beta": _safe(info.get("beta")),
                "sharesOutstanding": _safe(info.get("sharesOutstanding")),
            }
            try: income = _fmt_fin_df(t.financials)
            except: income = {}
            try: balance = _fmt_fin_df(t.balance_sheet)
            except: balance = {}
            try: cashflow = _fmt_fin_df(t.cashflow)
            except: cashflow = {}
            all_years = sorted(set(list(income.keys()) + list(balance.keys()) + list(cashflow.keys())), reverse=True)
            years_data = {}
            for yr in all_years:
                years_data[yr] = {**income.get(yr, {}), **balance.get(yr, {}), **cashflow.get(yr, {})}
            return {"status": "success", "snapshot": snapshot, "years": all_years, "financials": years_data}
        result = await loop.run_in_executor(_MARKET_EXEC, _fetch)
        return result
    except Exception as e:
        log.warning(f"FUNDAMENTAL [{symbol}]: {e}")
        return {"status": "error", "symbol": symbol, "snapshot": {}, "years": [], "financials": {}}

@app.get("/api/market/calendar/watchlist")
async def get_calendar_watchlist():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM user_calendar_watchlist ORDER BY added_at DESC")
        items = cursor.fetchall()
        cursor.close()
        conn.close()
        return {"status": "success", "watchlist": items}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/market/calendar/watchlist")
async def add_to_calendar_watchlist(item: dict):
    sym = item.get('symbol', '').upper()
    name = item.get('name', sym)
    if not sym: raise HTTPException(status_code=400, detail="Symbol required")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO user_calendar_watchlist (symbol, name) VALUES (%s, %s)", (sym, name))
        conn.commit()
        cursor.close()
        conn.close()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": "Already in watchlist or DB error"}

@app.delete("/api/market/calendar/watchlist/{symbol}")
async def remove_from_calendar_watchlist(symbol: str):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_calendar_watchlist WHERE symbol = %s", (symbol.upper(),))
        conn.commit()
        cursor.close()
        conn.close()
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# SECTOR & INDUSTRY PERFORMANCE ENGINE
# ─────────────────────────────────────────────────────────────────────────────
def _get_industry_ytd_from_ind(ind_obj, companies=None):
    """
    Unified industry YTD calculation.
    1. Try ind_obj.performance['YTD']
    2. Fallback to mean of provided companies or fetch them if missing
    """
    try:
        perf = getattr(ind_obj, 'performance', {})
        if isinstance(perf, dict) and 'YTD' in perf:
            val = clean(perf['YTD'])
            if val is not None:
                # yfinance usually returns fractions (0.15 = 15%)
                if abs(val) < 2.0:
                    return round(val * 100, 2)
                return round(val, 2)
    except Exception as e:
        log.debug(f"Unified YTD fetch error: {e}")
        
    # If companies provided (e.g. from sector-detail)
    if companies:
        valid_ytds = [c['ytd_return'] for c in companies if c.get('ytd_return') is not None]
        if valid_ytds:
            return round(sum(valid_ytds) / len(valid_ytds), 2)
            
    # Deep Fallback: Fetch companies directly from the industry object (for global sector view)
    try:
        df_perf = getattr(ind_obj, 'top_performing_companies', None)
        if df_perf is not None and not df_perf.empty:
            ytds = []
            for _, row in df_perf.iterrows():
                y = clean(row.get('ytd return'))
                if y is not None:
                    if abs(y) < 2.0: y *= 100
                    ytds.append(y)
            if ytds:
                return round(sum(ytds) / len(ytds), 2)
    except: pass
            
    return 0.0


def _fetch_single_sector(s_key, etf_ticker):
    try:
        ticker = yf.Ticker(etf_ticker)
        hist = ticker.history(period="ytd")
        
        s_return = 0.0
        if len(hist) >= 2:
            try:
                s_return = (hist['Close'].iloc[-1] / hist['Close'].iloc[0] - 1) * 100
            except: pass
        
        s_name = SECTOR_NAMES.get(s_key, s_key.title())
        
        # Try to get industries for this sector
        sector_movers_pool = []
        try:
            sec = yf.Sector(s_key)
            df_ind = sec.industries
        except Exception as e:
            log.debug(f"SECTOR_FETCH: No industry list for {s_key}: {e}")
            df_ind = pd.DataFrame()
        
        industries_batch = []
        if df_ind.empty:
            industries_batch.append({
                "sector": s_name,
                "sector_return_ytd": round(float(s_return), 2),
                "industry": "N/A",
                "industry_return_ytd": 0.0
            })
        else:
            for idx, row in df_ind.iterrows():
                i_key = str(idx)
                i_name = row.get('name') or row.get('industryName') or i_key.replace('-', ' ').title()
                
                i_return = 0.0
                if i_key:
                    try:
                        ind = yf.Industry(i_key)
                        df_p = getattr(ind, 'top_performing_companies', pd.DataFrame())
                        i_comps = []
                        if not df_p.empty:
                            for sym, crow in df_p.iterrows():
                                y = clean(crow.get('ytd return'))
                                if y is not None:
                                    if abs(y) < 2.0: y *= 100
                                    c_obj = {"symbol": str(sym), "ytd_return": round(y, 2)}
                                    i_comps.append(c_obj)
                                    sector_movers_pool.append(c_obj)
                        
                        i_return = _get_industry_ytd_from_ind(ind, i_comps)
                    except: pass
                
                industries_batch.append({
                    "sector": s_name,
                    "sector_return_ytd": round(float(s_return), 2),
                    "industry": i_name,
                    "industry_return_ytd": round(float(i_return), 2)
                })

        # Calculate top 3 movers/losers for this sector
        spool = sorted([m for m in sector_movers_pool if m.get('ytd_return')], key=lambda x: x['ytd_return'], reverse=True)
        top_m = spool[:3]
        top_l = spool[-3:][::-1]

        for item in industries_batch:
            item["top_movers"] = top_m
            item["top_losers"] = top_l
            
        return industries_batch
    except Exception as e:
        log.warning(f"SECTOR_FETCH Error on {s_key} ({etf_ticker}): {e}")
        return []

def _fetch_sector_report():
    """Fetch sector performance via ETFs and industry details via yfinance Sector/Industry objects."""
    report_data = []
    log.info("SECTOR_FETCH: Starting sector performance report collection")
    
    futures = []
    for s_key, etf_ticker in SECTOR_ETF.items():
        futures.append(_MARKET_EXEC.submit(_fetch_single_sector, s_key, etf_ticker))
        
    for future in futures:
        try:
            res = future.result(timeout=60)
            if res:
                report_data.extend(res)
        except Exception as e:
            log.warning(f"SECTOR_FETCH future error: {e}")
                
    log.info(f"SECTOR_FETCH: Completed. {len(report_data)} industry records collected.")
    return report_data


async def sector_update_loop():
    """Background task: fetch sector performance in the background periodically."""
    log.info("SECTOR_BG: Updater started")
    await asyncio.sleep(5)
    while True:
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(_MARKET_EXEC, _fetch_sector_report)
            if data:
                SECTOR_CACHE["data"] = data
                SECTOR_CACHE["last_updated"] = time.time()
                log.info(f"SECTOR_BG: {len(data)} sector records cached")
        except Exception as e:
            log.error(f"SECTOR_BG loop error: {e}")
        await asyncio.sleep(900)

@app.get("/api/market/sectors")
async def get_sector_performance(refresh: bool = False):
    """Return sector & industry performance. Always serves cache instantly if available."""
    if not refresh and SECTOR_CACHE["data"]:
        return {
            "status": "success", 
            "data": SECTOR_CACHE["data"], 
            "cached": True, 
            "last_updated": SECTOR_CACHE["last_updated"]
        }
    
    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(_MARKET_EXEC, _fetch_sector_report)
        if data:
            SECTOR_CACHE["data"] = data
            SECTOR_CACHE["last_updated"] = time.time()
        return {"status": "success", "data": data, "cached": False}
    except Exception as e:
        log.error(f"SECTOR_API Error: {e}")
        return {"status": "error", "message": str(e)}




# ─────────────────────────────────────────────────────────────────────────────
# SECTOR DETAIL — Per-sector deep dive with industry holdings & movers
# ─────────────────────────────────────────────────────────────────────────────

SECTOR_DETAIL_CACHE = {}

def _fetch_sector_detail(sector_key: str):
    """Fetch detailed holdings, industry breakdown, and movers for a single sector."""
    etf_ticker = SECTOR_ETF.get(sector_key)
    if not etf_ticker:
        return None

    s_name = SECTOR_NAMES.get(sector_key, sector_key.title())
    log.info(f"SECTOR_DETAIL: Fetching {s_name} ({etf_ticker})")

    result = {
        "sector_key": sector_key,
        "sector_name": s_name,
        "etf_ticker": etf_ticker,
        "sector_return_ytd": 0.0,
        "sector_return_1m": 0.0,
        "sector_return_3m": 0.0,
        "sparkline": [],
        "industries": [],
        "top_movers": [],
        "top_losers": [],
        "all_companies": []
    }

    try:
        # 1. ETF overview & sparkline
        ticker = yf.Ticker(etf_ticker)
        info = ticker.info

        hist_ytd = ticker.history(period="ytd")
        hist_1m  = ticker.history(period="1mo")
        hist_3m  = ticker.history(period="3mo")
        hist_6m  = ticker.history(period="6mo")

        def pct(h):
            if h is not None and len(h) >= 2:
                try: 
                    val = (h['Close'].iloc[-1] / h['Close'].iloc[0] - 1) * 100
                    return clean(val) or 0.0
                except: pass
            return 0.0

        result["sector_return_ytd"] = pct(hist_ytd)
        result["sector_return_1m"]  = pct(hist_1m)
        result["sector_return_3m"]  = pct(hist_3m)
        result["sector_return_6m"]  = pct(hist_6m)

        # Sparkline: last 60 trading days
        if not hist_6m.empty:
            spark = hist_6m["Close"].tolist()[-60:]
            result["sparkline"] = [clean(v) for v in spark if v is not None]

        result["pe_ratio"]      = clean(info.get("trailingPE"))
        result["market_cap"]    = clean(info.get("totalAssets") or info.get("marketCap"))
        result["volume"]        = clean(info.get("regularMarketVolume"))
        result["name_full"]     = info.get("longName") or s_name

    except Exception as e:
        log.warning(f"SECTOR_DETAIL ETF error {etf_ticker}: {e}")

    try:
        # 2. Industries & companies via yfinance Sector
        sec = yf.Sector(sector_key)
        df_ind = sec.industries  # index = industry_key, columns = ['name', 'symbol', 'market weight']

        industries_out = []

        if not df_ind.empty:
            for i_key, row in df_ind.iterrows():   # i_key from index!
                i_name = row.get('name') or str(i_key).replace('-', ' ').title()

                i_return = 0.0
                companies_out = []

                try:
                    ind = yf.Industry(i_key)

                    # top_performing_companies: symbol(index), name, ytd return, last price, target price
                    df_perf = getattr(ind, 'top_performing_companies', pd.DataFrame())
                    # top_companies:           symbol(index), name, rating, market weight
                    df_base = getattr(ind, 'top_companies',  pd.DataFrame())

                    # merge on index (symbol)
                    if df_perf is not None and not df_perf.empty:
                        df_merged = df_perf.copy()
                        if df_base is not None and not df_base.empty:
                            df_merged = df_merged.join(df_base[['rating', 'market weight']], how='left')
                    elif df_base is not None and not df_base.empty:
                        df_merged = df_base.copy()
                        df_merged['ytd return'] = None
                        df_merged['last price'] = None
                    else:
                        df_merged = pd.DataFrame()

                    for sym, crow in df_merged.iterrows():
                        raw_ytd = crow.get('ytd return')
                        ytd_val = clean(raw_ytd)
                        if ytd_val is not None:
                            # yfinance often returns fractions (0.15 = 15%), normalize
                            if abs(ytd_val) < 2.0: # Most YTD returns are not > 200% as a fraction
                                ytd_val = round(ytd_val * 100, 2)
                            else:
                                ytd_val = round(ytd_val, 2)

                        companies_out.append({
                            "symbol":      str(sym),
                            "name":        str(crow.get('name', sym)),
                            "last_price":  clean(crow.get('last price')),
                            "target_price":clean(crow.get('target price')),
                            "market_weight": clean(crow.get('market weight')),
                            "rating":      str(crow.get('rating', '')),
                            "ytd_return":  ytd_val,
                            "industry":    i_name,
                            "sector":      s_name
                        })

                except Exception as e:
                    log.debug(f"SECTOR_DETAIL industry {i_key}: {e}")

                # Industry YTD: unified calculation (try performance then mean)
                i_return = _get_industry_ytd_from_ind(ind, companies_out)

                industries_out.append({
                    "industry_key":         str(i_key),
                    "industry_name":        i_name,
                    "industry_return_ytd":  i_return,
                    "companies":            companies_out
                })

                result["all_companies"].extend(companies_out)

        result["industries"] = industries_out

        # 3. Compute top movers & losers
        all_c = [c for c in result["all_companies"] if c.get("ytd_return") is not None]
        all_sorted = sorted(all_c, key=lambda x: x["ytd_return"], reverse=True)
        result["top_movers"] = all_sorted[:10]
        result["top_losers"] = all_sorted[-10:][::-1]

    except Exception as e:
        log.warning(f"SECTOR_DETAIL yfinance Sector error for {sector_key}: {e}")

    return result


@app.get("/api/market/sector-detail/{sector_key}")
async def get_sector_detail(sector_key: str, refresh: bool = False):
    """Return full sector intelligence report: industries, top companies, movers, losers, sparkline."""
    now = time.time()
    cached = SECTOR_DETAIL_CACHE.get(sector_key)
    if not refresh and cached and (now - cached.get("_ts", 0) < 3600):
        return {"status": "success", "data": cached["data"], "cached": True}

    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(_MARKET_EXEC, _fetch_sector_detail, sector_key)
        if data:
            SECTOR_DETAIL_CACHE[sector_key] = {"data": data, "_ts": now}
            return {"status": "success", "data": data, "cached": False}
        return {"status": "error", "message": f"Unknown sector: {sector_key}"}
    except Exception as e:
        log.error(f"SECTOR_DETAIL_API Error: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/")
def root():
    return {"status": "online", "service": "market_service"}

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(market_update_loop())
    asyncio.create_task(sector_update_loop())


if __name__ == "__main__":
    print("=:: LAUNCHING ASETPEDIA INSTITUTIONAL MARKET SERVICE (Port 8088) ::= ")
    uvicorn.run(app, host="0.0.0.0", port=8088)
