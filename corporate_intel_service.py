"""
Corporate Intelligence Microservice
Insider trading monitoring, analyst recommendations, earnings calendar, dividend calendar.
Powered by yfinance.
"""
import os
import time
import threading
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
log = logging.getLogger('corporate_intel_service')

import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

app = FastAPI(debug=True, title="Corporate Intelligence Microservice")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Watchlist for corporate intel ---
WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
    "BRK-B", "JPM", "V", "JNJ", "WMT", "MA", "PG", "UNH",
    "HD", "DIS", "BAC", "NFLX", "ADBE", "CRM", "AMD", "INTC",
    "PYPL", "SQ", "COIN", "MSTR", "PLTR", "SNOW", "DDOG",
    "TLKM.JK", "BBCA.JK", "BBRI.JK", "BMRI.JK", "ASII.JK", "ICBP.JK", "GOTO.JK",
    "BBNI.JK", "SMGR.JK", "ADRO.JK", "ITMG.JK", "PTBA.JK",
]

# --- Cache ---
CORP_CACHE = {}
_CACHE_LOCK = threading.Lock()
CACHE_TTL = 1800  # 30 minutes (fundamental data changes slowly)

def clean(val):
    if val is None or (isinstance(val, (float, int, np.floating, np.integer)) and (np.isnan(val) or np.isinf(val))):
        return None
    try: return float(val)
    except: return None

def _get_cached(key):
    with _CACHE_LOCK:
        if key in CORP_CACHE and time.time() - CORP_CACHE[key]['ts'] < CACHE_TTL:
            return CORP_CACHE[key]['data']
    return None

def _set_cached(key, data):
    with _CACHE_LOCK:
        CORP_CACHE[key] = {'ts': time.time(), 'data': data}


# ===================== ENDPOINTS =====================

@app.get("/api/corporate/insider-trading/{symbol}")
def get_insider_trading(symbol: str):
    """Recent insider transactions for a symbol."""
    cache_key = f"insider_{symbol}"
    cached = _get_cached(cache_key)
    if cached: return {"status": "success", "data": cached}

    try:
        t = yf.Ticker(symbol)

        # Get insider transactions
        try:
            transactions = t.insider_transactions
        except:
            transactions = None

        # Get insider purchases (aggregated)
        try:
            purchases = t.insider_purchases
        except:
            purchases = None

        # Format transactions
        formatted_transactions = []
        if transactions is not None and not transactions.empty:
            for _, row in transactions.iterrows():
                entry = {}
                for col in transactions.columns:
                    val = row[col]
                    if isinstance(val, pd.Timestamp):
                        entry[col] = val.strftime('%Y-%m-%d')
                    elif isinstance(val, (np.floating,)):
                        entry[col] = float(val) if not np.isnan(val) else None
                    elif isinstance(val, (np.integer,)):
                        entry[col] = int(val)
                    else:
                        entry[col] = str(val) if val is not None else None
                formatted_transactions.append(entry)

        # Format purchases
        formatted_purchases = []
        if purchases is not None and not purchases.empty:
            for _, row in purchases.iterrows():
                entry = {}
                for col in purchases.columns:
                    val = row[col]
                    if isinstance(val, pd.Timestamp):
                        entry[col] = val.strftime('%Y-%m-%d')
                    elif isinstance(val, (np.floating,)):
                        entry[col] = float(val) if not np.isnan(val) else None
                    elif isinstance(val, (np.integer,)):
                        entry[col] = int(val)
                    else:
                        entry[col] = str(val) if val is not None else None
                formatted_purchases.append(entry)

        # Detect insider sentiment
        buy_count = sum(1 for t in formatted_transactions if t.get('Transaction') == 'Purchase')
        sell_count = sum(1 for t in formatted_transactions if t.get('Transaction') == 'Sale')

        sentiment = "NEUTRAL"
        if buy_count > sell_count * 2 and buy_count >= 3:
            sentiment = "BULLISH_INSIDER_BUYING"
        elif sell_count > buy_count * 3 and sell_count >= 5:
            sentiment = "BEARISH_INSIDER_SELLING"

        result = {
            "symbol": symbol,
            "transactions": formatted_transactions[:50],
            "purchases": formatted_purchases[:20],
            "stats": {
                "recent_buys": buy_count,
                "recent_sells": sell_count,
                "insider_sentiment": sentiment
            },
            "last_updated": int(time.time())
        }
        _set_cached(cache_key, result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/corporate/insider-signals")
def get_insider_signals():
    """Aggregate insider buying/selling signals across watchlist."""
    cached = _get_cached("insider_signals")
    if cached: return {"status": "success", "data": cached}

    try:
        signals = []
        for symbol in WATCHLIST[:30]:  # Limit to top 30 for performance
            try:
                t = yf.Ticker(symbol)
                try:
                    transactions = t.insider_transactions
                except:
                    continue

                if transactions is None or transactions.empty:
                    continue

                buy_count = sum(1 for _, r in transactions.iterrows() if r.get('Transaction') == 'Purchase')
                sell_count = sum(1 for _, r in transactions.iterrows() if r.get('Transaction') == 'Sale')

                # Net insider flow (simplified — count-based)
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
                    info = t.info
                    price = clean(info.get("regularMarketPrice") or info.get("previousClose"))
                    signals.append({
                        "symbol": symbol,
                        "company": info.get("shortName", symbol),
                        "price": price,
                        "insider_buys": buy_count,
                        "insider_sells": sell_count,
                        "net_score": net_score,
                        "signal": signal
                    })
            except Exception as e:
                log.warning(f"INSIDER_SIGNAL[{symbol}]: {e}")
                continue

        # Sort by net score
        signals.sort(key=lambda x: x['net_score'], reverse=True)

        result = {
            "total_tracked": len(signals),
            "bullish_signals": [s for s in signals if s['signal'] in ['STRONG_BUY', 'BUY']],
            "bearish_signals": [s for s in signals if s['signal'] in ['STRONG_SELL', 'SELL']],
            "neutral_signals": [s for s in signals if s['signal'] == 'NEUTRAL'],
            "last_updated": int(time.time())
        }
        _set_cached("insider_signals", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/corporate/analyst-changes")
def get_analyst_changes():
    """Recent analyst upgrades/downgrades for watchlist symbols."""
    cached = _get_cached("analyst_changes")
    if cached: return {"status": "success", "data": cached}

    try:
        changes = []
        for symbol in WATCHLIST[:20]:  # Limit for performance
            try:
                t = yf.Ticker(symbol)
                try:
                    recs = t.recommendations
                    upgrades = t.upgrades_downgrades
                except:
                    recs = None
                    upgrades = None

                info = t.info

                if recs is not None and not recs.empty:
                    # Get latest 5 recommendations
                    for _, row in recs.head(5).iterrows():
                        entry = {}
                        for col in recs.columns:
                            val = row[col]
                            if isinstance(val, pd.Timestamp):
                                entry[col] = val.strftime('%Y-%m-%d')
                            else:
                                entry[col] = str(val) if val is not None else None
                        entry['symbol'] = symbol
                        entry['company'] = info.get('shortName', symbol)
                        changes.append(entry)

            except Exception as e:
                log.warning(f"ANALYST[{symbol}]: {e}")
                continue

        result = {
            "recent_changes": changes[:50],
            "total_changes": len(changes),
            "last_updated": int(time.time())
        }
        _set_cached("analyst_changes", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/corporate/earnings-calendar")
def get_earnings_calendar():
    """Upcoming earnings dates for watchlist."""
    cached = _get_cached("earnings_calendar")
    if cached: return {"status": "success", "data": cached}

    try:
        today = datetime.now()
        events = []
        for symbol in WATCHLIST:
            try:
                t = yf.Ticker(symbol)
                info = t.info
                calendar = t.calendar

                if calendar is not None and not calendar.empty:
                    earnings_date = calendar.get('Earnings Date', None)
                    if earnings_date is not None:
                        if isinstance(earnings_date, list) and len(earnings_date) > 0:
                            earnings_date = earnings_date[0]
                        if isinstance(earnings_date, pd.Timestamp):
                            earnings_date = earnings_date.strftime('%Y-%m-%d')

                    eps_estimate = calendar.get('EPS Estimate', None)
                    eps_actual = calendar.get('EPS Actual', None)

                    if earnings_date:
                        events.append({
                            "symbol": symbol,
                            "company": info.get('shortName', symbol),
                            "earnings_date": str(earnings_date) if earnings_date else None,
                            "eps_estimate": clean(eps_estimate),
                            "eps_actual": clean(eps_actual),
                            "market_cap": clean(info.get('marketCap')),
                            "sector": info.get('sector', 'N/A')
                        })
            except Exception as e:
                log.warning(f"EARNINGS[{symbol}]: {e}")
                continue

        # Sort by date
        events.sort(key=lambda x: x.get('earnings_date') or '9999-12-31')

        # Upcoming only
        upcoming = [e for e in events if e.get('earnings_date', '') >= today.strftime('%Y-%m-%d')]

        result = {
            "upcoming_earnings": upcoming[:30],
            "recent_earnings": [e for e in events if e.get('earnings_date', '') < today.strftime('%Y-%m-%d')][:10],
            "total_upcoming": len(upcoming),
            "last_updated": int(time.time())
        }
        _set_cached("earnings_calendar", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/corporate/dividend-calendar")
def get_dividend_calendar():
    """Upcoming ex-dividend dates and dividend history."""
    cached = _get_cached("dividend_calendar")
    if cached: return {"status": "success", "data": cached}

    try:
        today = datetime.now()
        dividends = []
        for symbol in WATCHLIST:
            try:
                t = yf.Ticker(symbol)
                info = t.info

                # Get dividend info
                div_rate = clean(info.get('dividendRate'))
                div_yield = clean(info.get('dividendYield'))
                ex_date = info.get('exDividendDate')

                if ex_date:
                    if isinstance(ex_date, (int, float)):
                        ex_date = datetime.fromtimestamp(ex_date).strftime('%Y-%m-%d')
                    elif isinstance(ex_date, pd.Timestamp):
                        ex_date = ex_date.strftime('%Y-%m-%d')

                # Get dividend history
                div_hist = t.dividends
                last_div = None
                if div_hist is not None and not div_hist.empty:
                    last_div = {
                        "date": div_hist.index[-1].strftime('%Y-%m-%d') if hasattr(div_hist.index[-1], 'strftime') else str(div_hist.index[-1]),
                        "amount": float(div_hist.iloc[-1])
                    }

                if div_rate or div_yield:
                    dividends.append({
                        "symbol": symbol,
                        "company": info.get('shortName', symbol),
                        "dividend_rate": div_rate,
                        "dividend_yield": (div_yield * 100) if div_yield else None,
                        "ex_dividend_date": ex_date,
                        "last_dividend": last_div,
                        "payout_ratio": clean(info.get('payoutRatio')),
                        "sector": info.get('sector', 'N/A')
                    })
            except Exception as e:
                log.warning(f"DIVIDEND[{symbol}]: {e}")
                continue

        # Highest yields first
        dividends.sort(key=lambda x: x.get('dividend_yield') or 0, reverse=True)

        result = {
            "dividends": dividends,
            "highest_yield": dividends[:5] if dividends else [],
            "total_tracked": len(dividends),
            "last_updated": int(time.time())
        }
        _set_cached("dividend_calendar", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/corporate/summary/{symbol}")
def get_corporate_summary(symbol: str):
    """Full corporate intelligence summary for a symbol."""
    try:
        t = yf.Ticker(symbol)
        info = t.info

        # Get key metrics
        result = {
            "symbol": symbol,
            "company": info.get('longName', info.get('shortName', symbol)),
            "sector": info.get('sector', 'N/A'),
            "industry": info.get('industry', 'N/A'),
            "market_cap": clean(info.get('marketCap')),
            "enterprise_value": clean(info.get('enterpriseValue')),
            "pe_ratio": clean(info.get('trailingPE')),
            "forward_pe": clean(info.get('forwardPE')),
            "price_to_book": clean(info.get('priceToBook')),
            "debt_to_equity": clean(info.get('debtToEquity')),
            "return_on_equity": clean(info.get('returnOnEquity')),
            "profit_margin": clean(info.get('profitMargins')),
            "revenue_growth": clean(info.get('revenueGrowth')),
            "earnings_growth": clean(info.get('earningsQuarterlyGrowth')),
            "dividend_yield": clean(info.get('dividendYield')),
            "beta": clean(info.get('beta')),
            "short_ratio": clean(info.get('shortRatio')),
            "short_percent": clean(info.get('shortPercentOfFloat')),
            "recommendation": info.get('recommendationKey', 'N/A'),
            "target_price": clean(info.get('targetMeanPrice')),
            "number_of_analysts": info.get('numberOfAnalystOpinions'),
            "last_updated": int(time.time())
        }
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "corporate_intel_service_online", "timestamp": int(time.time())}


if __name__ == "__main__":
    log.info("Corporate Intelligence Service starting on port 8185")
    uvicorn.run(app, host="0.0.0.0", port=8185)
