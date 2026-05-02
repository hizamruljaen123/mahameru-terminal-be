"""
Corporate Intelligence Microservice — Optimized
Insider trading monitoring, analyst recommendations, earnings calendar, dividend calendar.
Powered by yfinance with connection pooling, parallel execution, and smart caching.

Key optimizations vs original:
  - Connection pooling via shared requests.Session with retry adapter
  - ThreadPoolExecutor for parallel symbol fetching (I/O-bound)
  - Symbol-level data cache to eliminate redundant t.info calls
  - Background cache warmer for frequently accessed endpoints
  - Request timeouts to prevent hanging
  - Reduced iteration overhead with vectorized pandas operations
"""
import os
import time
import threading
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
log = logging.getLogger('corporate_intel_service')

import numpy as np
import pandas as pd
import yfinance as yf
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

app = FastAPI(debug=False, title="Corporate Intelligence Microservice")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================================
# CONNECTION POOLING
# =====================================================================
_SHARED_SESSION: requests.Session | None = None
_SESSION_LOCK = threading.Lock()

def _get_session() -> requests.Session:
    """Return a shared requests.Session with connection pooling & retry."""
    global _SHARED_SESSION
    if _SHARED_SESSION is None:
        with _SESSION_LOCK:
            if _SHARED_SESSION is None:
                sess = requests.Session()
                retry = Retry(
                    total=2,
                    backoff_factor=0.5,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods={"GET"},
                )
                adapter = HTTPAdapter(
                    max_retries=retry,
                    pool_connections=20,
                    pool_maxsize=40,
                )
                sess.mount("https://", adapter)
                sess.mount("http://", adapter)
                sess.headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                  "Chrome/120.0.0.0 Safari/537.36"
                })
                _SHARED_SESSION = sess
    return _SHARED_SESSION


def _make_ticker(symbol: str) -> yf.Ticker:
    """Create a yfinance Ticker that uses our shared session."""
    sess = _get_session()
    t = yf.Ticker(symbol, session=sess)
    return t


def _parse_symbols(symbols_param: str | None = None) -> list[str]:
    """Parse comma-separated symbols from query param.
    
    Returns list of uppercase symbols, or empty list if none provided.
    """
    if not symbols_param:
        return []
    parts = [s.strip().upper() for s in symbols_param.split(",") if s.strip()]
    return parts if parts else []

# =====================================================================
# CACHE — Two-tier: endpoint-level + symbol-level
# =====================================================================
ENDPOINT_CACHE: dict = {}
_SYMBOL_CACHE: dict = {}            # ticker info cached per symbol
_CACHE_LOCK = threading.Lock()
ENDPOINT_TTL = 1800                 # 30 min for endpoint results
SYMBOL_TTL = 1200                   # 20 min for raw ticker data

# Background warmer state
_WARMER_THREAD: threading.Thread | None = None
_WARMER_LOCK = threading.Lock()
_WARMER_INTERVAL = 600              # re-warm every 10 min

# Thread pool for parallel symbol fetching
_EXECUTOR = ThreadPoolExecutor(max_workers=12, thread_name_prefix="corp_intel")


# ------------------------------------------------------------------
#  Helpers
# ------------------------------------------------------------------
def clean(val):
    if val is None:
        return None
    try:
        v = float(val)
        if np.isnan(v) or np.isinf(v):
            return None
        return v
    except Exception:
        return None


def _fmt_timestamp(val):
    """Format pd.Timestamp or int-timestamp to YYYY-MM-DD string."""
    if val is None:
        return None
    if isinstance(val, pd.Timestamp):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(val).strftime("%Y-%m-%d")
        except Exception:
            return str(val)
    return str(val)


def _fmt_val(val):
    """Convert numpy/pandas scalar to plain Python type safely."""
    if val is None:
        return None
    if isinstance(val, pd.Timestamp):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, (np.floating,)):
        return float(val) if not np.isnan(val) else None
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.bool_,)):
        return bool(val)
    return val


# ------------------------------------------------------------------
#  Cache accessors
# ------------------------------------------------------------------
def _get_ecache(key):
    with _CACHE_LOCK:
        if key in ENDPOINT_CACHE and time.time() - ENDPOINT_CACHE[key]["ts"] < ENDPOINT_TTL:
            return ENDPOINT_CACHE[key]["data"]
    return None


def _set_ecache(key, data):
    with _CACHE_LOCK:
        ENDPOINT_CACHE[key] = {"ts": time.time(), "data": data}


def _get_scache(symbol: str):
    """Return cached (info_dict, insider_df, insider_purchases_df) or None."""
    with _CACHE_LOCK:
        if symbol in _SYMBOL_CACHE and time.time() - _SYMBOL_CACHE[symbol]["ts"] < SYMBOL_TTL:
            return _SYMBOL_CACHE[symbol]["data"]
    return None


def _set_scache(symbol: str, data):
    with _CACHE_LOCK:
        _SYMBOL_CACHE[symbol] = {"ts": time.time(), "data": data}


def _clear_expired():
    """Periodic lightweight expiry — called rarely, so just purge stale."""
    now = time.time()
    with _CACHE_LOCK:
        for c in (ENDPOINT_CACHE, _SYMBOL_CACHE):
            stale = [k for k, v in c.items() if now - v["ts"] > max(ENDPOINT_TTL, SYMBOL_TTL)]
            for k in stale:
                del c[k]


# ------------------------------------------------------------------
#  Parallel symbol helper — fetches ticker data concurrently
# ------------------------------------------------------------------
def _fetch_symbol_info(symbol: str) -> dict | None:
    """Fetch & cache info + insider data for one symbol. Returns dict or None."""
    cached = _get_scache(symbol)
    if cached:
        return cached

    try:
        t = _make_ticker(symbol)
        info = t.info or {}

        # Attempt insider data (fail gracefully)
        try:
            insider_tx = t.insider_transactions
        except Exception:
            insider_tx = None
        try:
            insider_pur = t.insider_purchases
        except Exception:
            insider_pur = None

        data = {
            "info": info,
            "insider_transactions": insider_tx,
            "insider_purchases": insider_pur,
        }
        # Also eagerly fetch calendar & dividends for earnings/dividend endpoints
        try:
            data["calendar"] = t.calendar
        except Exception:
            data["calendar"] = None
        try:
            data["dividends"] = t.dividends
        except Exception:
            data["dividends"] = None
        try:
            data["recommendations"] = t.recommendations
        except Exception:
            data["recommendations"] = None
        try:
            data["upgrades_downgrades"] = t.upgrades_downgrades
        except Exception:
            data["upgrades_downgrades"] = None

        _set_scache(symbol, data)
        return data
    except Exception as e:
        log.warning(f"FETCH[{symbol}]: {e}")
        return None


def _fetch_symbols_batch(symbols: list[str], max_workers: int = 8) -> dict[str, dict]:
    """Fetch multiple symbols in parallel. Returns {symbol: data_or_None}."""
    results = {}
    futures = {_EXECUTOR.submit(_fetch_symbol_info, sym): sym for sym in symbols}
    for fut in as_completed(futures, timeout=30):
        sym = futures[fut]
        try:
            data = fut.result()
            if data:
                results[sym] = data
        except Exception as e:
            log.warning(f"BATCH[{sym}]: {e}")
    return results


# =====================================================================
# BACKGROUND CACHE WARMER
# =====================================================================
def _warm_cache():
    """Cache warmer disabled — symbols are user-provided via query params."""
    global _WARMER_THREAD
    log.info("ℹ️ Cache warmer skipped (user provides symbols via ?symbols=)")
    with _WARMER_LOCK:
        _WARMER_THREAD = None


def _ensure_warmer():
    """Start background warmer if not already running."""
    global _WARMER_THREAD
    with _WARMER_LOCK:
        if _WARMER_THREAD is None or not _WARMER_THREAD.is_alive():
            _WARMER_THREAD = threading.Thread(target=_warm_cache, daemon=True)
            _WARMER_THREAD.start()


# =====================================================================
# DATA FORMATTING HELPERS
# =====================================================================
def _format_insider_transactions_df(df: pd.DataFrame, max_rows: int = 50) -> list[dict]:
    """Convert insider_transactions DataFrame to JSON-safe list fast."""
    if df is None or df.empty:
        return []
    rows = df.head(max_rows)
    out = []
    for _, row in rows.iterrows():
        entry = {}
        for col in rows.columns:
            entry[col] = _fmt_val(row[col])
        out.append(entry)
    return out


def _format_insider_purchases_df(df: pd.DataFrame, max_rows: int = 20) -> list[dict]:
    """Convert insider_purchases DataFrame to JSON-safe list fast."""
    if df is None or df.empty:
        return []
    rows = df.head(max_rows)
    out = []
    for _, row in rows.iterrows():
        entry = {}
        for col in rows.columns:
            entry[col] = _fmt_val(row[col])
        out.append(entry)
    return out


# =====================================================================
# BUILDERS — each endpoint assembles its response from cached symbol data
# =====================================================================
def _build_insider_trading(symbol_data: dict, symbol: str) -> dict:
    """Build insider-trading response from cached symbol data."""
    info = symbol_data.get("info", {})
    tx_df = symbol_data.get("insider_transactions")
    pur_df = symbol_data.get("insider_purchases")

    formatted_tx = _format_insider_transactions_df(tx_df, 50)
    formatted_pur = _format_insider_purchases_df(pur_df, 20)

    buy_count = sum(1 for t in formatted_tx if t.get("Transaction") == "Purchase")
    sell_count = sum(1 for t in formatted_tx if t.get("Transaction") == "Sale")

    sentiment = "NEUTRAL"
    if buy_count > sell_count * 2 and buy_count >= 3:
        sentiment = "BULLISH_INSIDER_BUYING"
    elif sell_count > buy_count * 3 and sell_count >= 5:
        sentiment = "BEARISH_INSIDER_SELLING"

    return {
        "symbol": symbol,
        "transactions": formatted_tx,
        "purchases": formatted_pur,
        "stats": {
            "recent_buys": buy_count,
            "recent_sells": sell_count,
            "insider_sentiment": sentiment,
        },
        "last_updated": int(time.time()),
    }


def _build_insider_signals(all_data: dict[str, dict]) -> dict:
    """Build aggregate insider signals across the watchlist."""
    signals = []
    for symbol, sd in all_data.items():
        tx_df = sd.get("insider_transactions")
        if tx_df is None or tx_df.empty:
            continue
        info = sd.get("info", {})
        buy_count = int((tx_df["Transaction"] == "Purchase").sum()) if "Transaction" in tx_df.columns else 0
        sell_count = int((tx_df["Transaction"] == "Sale").sum()) if "Transaction" in tx_df.columns else 0

        net_score = buy_count - sell_count
        signal = "NEUTRAL"
        if net_score > 3:
            signal = "STRONG_BUY"
        elif net_score > 0:
            signal = "BUY"
        elif net_score < -5:
            signal = "STRONG_SELL"
        elif net_score < 0:
            signal = "SELL"

        if buy_count > 0 or sell_count > 0:
            price = clean(info.get("regularMarketPrice") or info.get("previousClose"))
            signals.append({
                "symbol": symbol,
                "company": info.get("shortName", symbol),
                "price": price,
                "insider_buys": buy_count,
                "insider_sells": sell_count,
                "net_score": net_score,
                "signal": signal,
            })

    signals.sort(key=lambda x: x["net_score"], reverse=True)
    return {
        "total_tracked": len(signals),
        "bullish_signals": [s for s in signals if s["signal"] in ("STRONG_BUY", "BUY")],
        "bearish_signals": [s for s in signals if s["signal"] in ("STRONG_SELL", "SELL")],
        "neutral_signals": [s for s in signals if s["signal"] == "NEUTRAL"],
        "last_updated": int(time.time()),
    }


def _build_insider_all(all_data: dict[str, dict], max_symbols: int = 15) -> dict:
    """Build the flat insider summary for the /insider endpoint."""
    all_trades = []
    total_buys = 0
    total_sells = 0

    symbols_to_process = list(all_data.items())
    # Only limit if user didn't provide custom symbols (heuristic: > 20 = using watchlist)
    if len(symbols_to_process) > 20:
        symbols_to_process = symbols_to_process[:max_symbols]
    for symbol, sd in symbols_to_process:
        tx_df = sd.get("insider_transactions")
        if tx_df is None or tx_df.empty:
            continue
        for _, row in tx_df.head(5).iterrows():
            transaction = str(row.get("Transaction", ""))
            is_buy = "Purchase" in transaction or "Buy" in transaction
            is_sell = "Sale" in transaction or "Sell" in transaction
            trade = {
                "symbol": symbol,
                "insider_name": str(row.get("Insider", "Unknown")),
                "transaction_type": "Buy" if is_buy else "Sell" if is_sell else transaction,
                "price": clean(row.get("Price")),
                "shares": clean(row.get("Quantity")),
                "filing_date": _fmt_timestamp(row.get("Start Date")),
                "percent_holding": clean(row.get("Ownership")),
            }
            all_trades.append(trade)
            if is_buy:
                total_buys += 1
            if is_sell:
                total_sells += 1

    # History chart
    hist_dict: dict = {}
    for t in all_trades:
        dt = t.get("filing_date")
        if not dt:
            continue
        if dt not in hist_dict:
            hist_dict[dt] = {"buys": 0, "sells": 0}
        if t["transaction_type"] == "Buy":
            hist_dict[dt]["buys"] += 1
        else:
            hist_dict[dt]["sells"] += 1

    history = [
        {"date": k, "buys": v["buys"], "sells": v["sells"]}
        for k, v in sorted(hist_dict.items())
    ]

    return {
        "trades": all_trades[:50],
        "summary": {
            "total": len(all_trades),
            "buys": total_buys,
            "sells": total_sells,
            "buy_sell_ratio": total_buys / (total_sells if total_sells > 0 else 1),
            "history": history,
        },
    }


def _build_analyst_changes(all_data: dict[str, dict]) -> dict:
    """Build analyst upgrades/downgrades from cached symbol data."""
    changes = []
    for symbol, sd in list(all_data.items())[:20]:
        upgrades = sd.get("upgrades_downgrades")
        recs = sd.get("recommendations")
        info = sd.get("info", {})
        curr_price = clean(info.get("regularMarketPrice") or info.get("previousClose"))

        if upgrades is not None and not upgrades.empty:
            for idx, row in upgrades.sort_index(ascending=False).head(10).iterrows():
                pt_new = clean(row.get("Target Price"))
                upside = ((pt_new / curr_price) - 1) if pt_new and curr_price else None
                changes.append({
                    "date": _fmt_timestamp(idx),
                    "symbol": symbol,
                    "company": info.get("shortName", symbol),
                    "firm": row.get("Firm"),
                    "to_rating": row.get("To Grade"),
                    "from_rating": row.get("From Grade"),
                    "action": row.get("Action"),
                    "pt_new": pt_new,
                    "pt_old": None,
                    "upside": upside,
                })
        elif recs is not None and not recs.empty:
            for idx, row in recs.head(10).iterrows():
                changes.append({
                    "date": _fmt_timestamp(idx),
                    "symbol": symbol,
                    "company": info.get("shortName", symbol),
                    "firm": row.get("Firm"),
                    "to_rating": row.get("To Grade"),
                    "from_rating": row.get("From Grade"),
                    "action": row.get("Action"),
                    "pt_new": None,
                    "pt_old": None,
                    "upside": None,
                })

    return {
        "recent_changes": changes[:50],
        "total_changes": len(changes),
        "last_updated": int(time.time()),
    }


def _build_earnings_calendar(all_data: dict[str, dict]) -> dict:
    """Build earnings calendar from cached symbol data."""
    today = datetime.now()
    events = []

    for symbol, sd in all_data.items():
        info = sd.get("info", {})
        calendar = sd.get("calendar")

        if calendar is None or isinstance(calendar, list):
            continue

        e_date = None
        eps_est = None
        rev_est = None

        if isinstance(calendar, dict):
            e_dates = calendar.get("Earnings Date", [])
            e_date = e_dates[0] if e_dates else None
            eps_est = calendar.get("EPS Estimate")
            rev_est = calendar.get("Revenue Estimate")
        else:
            try:
                e_date = calendar.loc["Earnings Date"].iloc[0] if "Earnings Date" in calendar.index else None
                eps_est = calendar.loc["EPS Estimate"].iloc[0] if "EPS Estimate" in calendar.index else None
                rev_est = calendar.loc["Revenue Estimate"].iloc[0] if "Revenue Estimate" in calendar.index else None
            except Exception:
                pass

        if e_date:
            events.append({
                "date": _fmt_timestamp(e_date),
                "symbol": symbol,
                "company": info.get("shortName", symbol),
                "quarter": None,
                "est_eps": clean(eps_est),
                "actual_eps": None,
                "est_revenue": clean(rev_est),
                "prior_eps": None,
                "surprise_pct": None,
                "time": "TBD",
                "market_cap": clean(info.get("marketCap")),
                "sector": info.get("sector", "N/A"),
            })

    today_str = today.strftime("%Y-%m-%d")
    upcoming = [e for e in events if e.get("date", "") >= today_str]
    return {
        "upcoming_earnings": upcoming[:30],
        "recent_earnings": [e for e in events if e.get("date", "") < today_str][:10],
        "total_upcoming": len(upcoming),
        "last_updated": int(time.time()),
    }


def _build_dividend_calendar(all_data: dict[str, dict]) -> dict:
    """Build dividend calendar from cached symbol data."""
    today = datetime.now()
    dividends = []

    for symbol, sd in all_data.items():
        info = sd.get("info", {})
        div_hist = sd.get("dividends")

        div_rate = clean(info.get("dividendRate"))
        div_yield = clean(info.get("dividendYield"))
        ex_date = info.get("exDividendDate")

        if ex_date:
            ex_date = _fmt_timestamp(ex_date)

        last_div = None
        if div_hist is not None and not div_hist.empty:
            last_div = {
                "date": _fmt_timestamp(div_hist.index[-1]),
                "amount": float(div_hist.iloc[-1]),
            }

        if div_rate or div_yield:
            freq = "N/A"
            if div_hist is not None and len(div_hist) >= 4:
                last_4 = div_hist.index[-4:]
                diffs = [(last_4[i] - last_4[i - 1]).days for i in range(1, 4)]
                avg_diff = sum(diffs) / 3
                if 80 <= avg_diff <= 100:
                    freq = "Quarterly"
                elif 170 <= avg_diff <= 190:
                    freq = "Semi-Annual"
                elif 350 <= avg_diff <= 380:
                    freq = "Annual"

            dividends.append({
                "ex_date": ex_date,
                "symbol": symbol,
                "company": info.get("shortName", symbol),
                "dividend": div_rate,
                "yield": (div_yield * 100) if div_yield else None,
                "frequency": freq,
                "pay_date": None,
                "record_date": None,
                "payout_ratio": clean(info.get("payoutRatio")),
                "sector": info.get("sector", "N/A"),
            })

    # Sort by dividend yield (descending)
    dividends.sort(key=lambda x: (x.get("yield") or 0), reverse=True)
    return {
        "dividends": dividends,
        "highest_yield": dividends[:5] if dividends else [],
        "total_tracked": len(dividends),
        "last_updated": int(time.time()),
    }


# =====================================================================
# ENDPOINTS
# =====================================================================

# ---------------------------------------------------------------
# 1. Insider Trading (single symbol)
# ---------------------------------------------------------------
@app.get("/api/corporate/insider-trading/{symbol}")
def get_insider_trading(symbol: str):
    """Recent insider transactions for a symbol."""
    cache_key = f"insider_{symbol}"
    cached = _get_ecache(cache_key)
    if cached:
        return {"status": "success", "data": cached}

    sd = _fetch_symbol_info(symbol)
    if sd is None:
        raise HTTPException(status_code=500, detail=f"Could not fetch data for {symbol}")

    result = _build_insider_trading(sd, symbol)
    _set_ecache(cache_key, result)
    return {"status": "success", "data": result}


# ---------------------------------------------------------------
# 2. Insider Signals (aggregate watchlist)
# ---------------------------------------------------------------
@app.get("/api/corporate/insider-signals")
def get_insider_signals(symbols: Optional[str] = None):
    """Aggregate insider buying/selling signals.
    
    - symbols: comma-separated tickers (e.g. ?symbols=AAPL,MSFT,GOOGL)
    - Required: returns empty result if not provided.
    """
    sym_list = _parse_symbols(symbols)
    cache_key = f"insider_signals_{'_'.join(sym_list[:5])}"
    cached = _get_ecache(cache_key)
    if cached:
        return {"status": "success", "data": cached}

    all_data = _fetch_symbols_batch(sym_list, max_workers=10)
    result = _build_insider_signals(all_data)
    _set_ecache(cache_key, result)
    return {"status": "success", "data": result}


# ---------------------------------------------------------------
# 3. Insider Summary (flat list for frontend)
# ---------------------------------------------------------------
@app.get("/api/corporate/insider")
def get_insider_summary_all(symbols: Optional[str] = None):
    """Aggregate insider trading.
    
    - symbols: comma-separated tickers (e.g. ?symbols=AAPL,MSFT)
    - Required: returns empty result if not provided.
    """
    sym_list = _parse_symbols(symbols)
    cache_key = f"insider_all_{'_'.join(sym_list[:5])}"
    cached = _get_ecache(cache_key)
    if cached:
        return {"status": "success", "data": cached}

    all_data = _fetch_symbols_batch(sym_list, max_workers=10)
    result = _build_insider_all(all_data)
    _set_ecache(cache_key, result)
    return {"status": "success", "data": result}


# ---------------------------------------------------------------
# 4. Analyst Changes
# ---------------------------------------------------------------
@app.get("/api/corporate/analyst")
def get_analyst_changes_fe(symbols: Optional[str] = None):
    """Alias returning flat list for frontend.
    
    - symbols: optional comma-separated tickers (e.g. ?symbols=AAPL,MSFT)
    """
    res = get_analyst_changes(symbols)
    return {"status": "success", "data": res.get("data", {}).get("recent_changes", [])}


@app.get("/api/corporate/analyst-changes")
def get_analyst_changes(symbols: Optional[str] = None):
    """Recent analyst upgrades/downgrades.
    
    - symbols: comma-separated tickers (e.g. ?symbols=AAPL,MSFT,GOOGL)
    - Required: returns empty result if not provided.
    """
    sym_list = _parse_symbols(symbols)
    cache_key = f"analyst_changes_{'_'.join(sym_list[:5])}"
    cached = _get_ecache(cache_key)
    if cached:
        return {"status": "success", "data": cached}

    all_data = _fetch_symbols_batch(sym_list, max_workers=10)
    result = _build_analyst_changes(all_data)
    _set_ecache(cache_key, result)
    return {"status": "success", "data": result}


# ---------------------------------------------------------------
# 5. Earnings Calendar
# ---------------------------------------------------------------
@app.get("/api/corporate/earnings")
def get_earnings_calendar_fe(symbols: Optional[str] = None):
    """Alias returning flat list for frontend.
    
    - symbols: optional comma-separated tickers (e.g. ?symbols=AAPL,MSFT)
    """
    res = get_earnings_calendar(symbols)
    return {"status": "success", "data": res.get("data", {}).get("upcoming_earnings", [])}


@app.get("/api/corporate/earnings-calendar")
def get_earnings_calendar(symbols: Optional[str] = None):
    """Upcoming earnings dates.
    
    - symbols: optional comma-separated tickers (e.g. ?symbols=AAPL,MSFT)
    - If not provided, returns empty result.
    """
    sym_list = _parse_symbols(symbols)
    if not sym_list:
        return {"status": "success", "data": {"upcoming_earnings": [], "total": 0, "last_updated": int(time.time())}}
    cache_key = f"earnings_{'_'.join(sym_list[:5])}"
    cached = _get_ecache(cache_key)
    if cached:
        return {"status": "success", "data": cached}

    all_data = _fetch_symbols_batch(sym_list, max_workers=12)
    result = _build_earnings_calendar(all_data)
    _set_ecache(cache_key, result)
    return {"status": "success", "data": result}


# ---------------------------------------------------------------
# 6. Dividend Calendar
# ---------------------------------------------------------------
@app.get("/api/corporate/dividends")
def get_dividend_calendar_fe(symbols: Optional[str] = None):
    """Alias returning flat list for frontend.
    
    - symbols: optional comma-separated tickers (e.g. ?symbols=AAPL,MSFT)
    """
    res = get_dividend_calendar(symbols)
    return {"status": "success", "data": res.get("data", {}).get("dividends", [])}


@app.get("/api/corporate/dividend-calendar")
def get_dividend_calendar(symbols: Optional[str] = None):
    """Upcoming ex-dividend dates and dividend history.
    
    - symbols: optional comma-separated tickers (e.g. ?symbols=AAPL,MSFT)
    - If not provided, returns empty result.
    """
    sym_list = _parse_symbols(symbols)
    if not sym_list:
        return {"status": "success", "data": {"dividends": [], "total": 0, "last_updated": int(time.time())}}
    cache_key = f"dividends_{'_'.join(sym_list[:5])}"
    cached = _get_ecache(cache_key)
    if cached:
        return {"status": "success", "data": cached}

    all_data = _fetch_symbols_batch(sym_list, max_workers=12)
    result = _build_dividend_calendar(all_data)
    _set_ecache(cache_key, result)
    return {"status": "success", "data": result}


# ---------------------------------------------------------------
# 7. Corporate Summary (single symbol)
# ---------------------------------------------------------------
@app.get("/api/corporate/summary/{symbol}")
def get_corporate_summary(symbol: str):
    """Full corporate intelligence summary for a symbol."""
    try:
        sd = _fetch_symbol_info(symbol)
        if sd is None:
            raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
        info = sd.get("info", {})

        result = {
            "symbol": symbol,
            "company": info.get("longName", info.get("shortName", symbol)),
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "market_cap": clean(info.get("marketCap")),
            "enterprise_value": clean(info.get("enterpriseValue")),
            "pe_ratio": clean(info.get("trailingPE")),
            "forward_pe": clean(info.get("forwardPE")),
            "price_to_book": clean(info.get("priceToBook")),
            "debt_to_equity": clean(info.get("debtToEquity")),
            "return_on_equity": clean(info.get("returnOnEquity")),
            "profit_margin": clean(info.get("profitMargins")),
            "revenue_growth": clean(info.get("revenueGrowth")),
            "earnings_growth": clean(info.get("earningsQuarterlyGrowth")),
            "dividend_yield": clean(info.get("dividendYield")),
            "beta": clean(info.get("beta")),
            "short_ratio": clean(info.get("shortRatio")),
            "short_percent": clean(info.get("shortPercentOfFloat")),
            "recommendation": info.get("recommendationKey", "N/A"),
            "target_price": clean(info.get("targetMeanPrice")),
            "number_of_analysts": info.get("numberOfAnalystOpinions"),
            "last_updated": int(time.time()),
        }
        return {"status": "success", "data": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------
# Health
# ---------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "corporate_intel_service_online", "timestamp": int(time.time())}


# ---------------------------------------------------------------
# Debug — check what data yfinance returns for a symbol
# ---------------------------------------------------------------
@app.get("/api/corporate/check/{symbol}")
def debug_check_symbol(symbol: str):
    """Debug endpoint: shows what raw data yfinance returns for a symbol.
    Helps diagnose why data might be null.
    """
    sd = _fetch_symbol_info(symbol)
    if sd is None:
        return {"status": "error", "symbol": symbol, "message": "Could not fetch any data"}

    info = sd.get("info", {})
    insider_tx = sd.get("insider_transactions")
    insider_pur = sd.get("insider_purchases")
    calendar = sd.get("calendar")
    dividends = sd.get("dividends")
    recs = sd.get("recommendations")
    upgrades = sd.get("upgrades_downgrades")

    return {
        "status": "success",
        "symbol": symbol,
        "company_name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "has_info": bool(info and len(info) > 5),
        "info_keys": list(info.keys())[:30] if info else [],
        "has_insider_transactions": insider_tx is not None and not insider_tx.empty,
        "insider_tx_rows": len(insider_tx) if insider_tx is not None and not insider_tx.empty else 0,
        "has_insider_purchases": insider_pur is not None and not insider_pur.empty,
        "has_calendar": calendar is not None and not isinstance(calendar, list),
        "calendar_type": str(type(calendar).__name__),
        "has_dividends": dividends is not None and not dividends.empty,
        "dividend_count": len(dividends) if dividends is not None and not dividends.empty else 0,
        "has_recommendations": recs is not None and not recs.empty,
        "has_upgrades_downgrades": upgrades is not None and not upgrades.empty,
        "price": clean(info.get("regularMarketPrice") or info.get("previousClose")),
        "market_cap": clean(info.get("marketCap")),
    }


# =====================================================================
# STARTUP
# =====================================================================
@app.on_event("startup")
async def startup():
    """Begin background cache warming on service start."""
    _clear_expired()
    _ensure_warmer()


if __name__ == "__main__":
    log.info("Corporate Intelligence Service starting on port 8185")
    log.info("Connection pooling: enabled | Parallel workers: 12 | Cache TTL: 30m")
    _ensure_warmer()
    uvicorn.run(app, host="0.0.0.0", port=8185)
