"""
Options Flow Intelligence Microservice
Put/Call ratios, max pain, IV rank, unusual options flow, earnings implied move.
Powered by yfinance option chains.
"""
import os
import time
import threading
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
log = logging.getLogger('options_service')

import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import Dict, Any, List, Optional

app = FastAPI(debug=True, title="Options Flow Intelligence Microservice")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Key tickers for options analysis ---
OPTIONS_TICKERS = {
    "SPY": "S&P 500 ETF",
    "QQQ": "NASDAQ 100 ETF",
    "IWM": "Russell 2000 ETF",
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corp",
    "NVDA": "NVIDIA Corp",
    "TSLA": "Tesla Inc.",
    "AMZN": "Amazon.com Inc.",
    "GOOGL": "Alphabet Inc.",
    "META": "Meta Platforms Inc.",
    "BTC-USD": "Bitcoin (ETF proxies)",
    "ETH-USD": "Ethereum (ETF proxies)",
}

# --- Cache ---
OPT_CACHE = {}
_CACHE_LOCK = threading.Lock()
CACHE_TTL = 600  # 10 minutes (option chains are heavy)

def clean(val):
    if val is None or (isinstance(val, (float, int, np.floating, np.integer)) and (np.isnan(val) or np.isinf(val))):
        return None
    try: return float(val)
    except: return None

def _get_cached(key):
    with _CACHE_LOCK:
        if key in OPT_CACHE and time.time() - OPT_CACHE[key]['ts'] < CACHE_TTL:
            return OPT_CACHE[key]['data']
    return None

def _set_cached(key, data):
    with _CACHE_LOCK:
        OPT_CACHE[key] = {'ts': time.time(), 'data': data}


# ===================== COMPUTATIONS =====================

def compute_max_pain(chain, current_price):
    """Compute max pain price level from option chain."""
    if chain is None or chain.empty:
        return None

    strikes = chain['strike'].unique()
    max_pain = None
    max_pain_value = -float('inf')

    for strike in strikes:
        # Total dollar value of options that would expire worthless at this strike
        total_pain = 0
        subset = chain[chain['strike'] == strike]
        for _, row in subset.iterrows():
            if row['option_type'] == 'call' and strike > current_price:
                # OTM calls expire worthless
                oi = row.get('openInterest', 0) or 0
                total_pain += oi * 100
            elif row['option_type'] == 'put' and strike < current_price:
                # OTM puts expire worthless
                oi = row.get('openInterest', 0) or 0
                total_pain += oi * 100

        if total_pain > max_pain_value:
            max_pain_value = total_pain
            max_pain = float(strike)

    return max_pain


def compute_pcr(puts, calls):
    """Compute Put/Call ratios."""
    total_put_oi = puts['openInterest'].sum() if 'openInterest' in puts else 0
    total_call_oi = calls['openInterest'].sum() if 'openInterest' in calls else 0
    total_put_vol = puts['volume'].sum() if 'volume' in puts else 0
    total_call_vol = calls['volume'].sum() if 'volume' in calls else 0

    pcr_oi = total_put_oi / total_call_oi if total_call_oi > 0 else None
    pcr_vol = total_put_vol / total_call_vol if total_call_vol > 0 else None

    return {
        "put_open_interest": int(total_put_oi),
        "call_open_interest": int(total_call_oi),
        "put_volume": int(total_put_vol),
        "call_volume": int(total_call_vol),
        "pcr_oi": round(pcr_oi, 3) if pcr_oi else None,
        "pcr_vol": round(pcr_vol, 3) if pcr_vol else None
    }


# ===================== ENDPOINTS =====================

@app.get("/api/options/chain/{symbol}")
def get_options_chain(symbol: str, expiry: Optional[str] = None):
    """Get full option chain for a symbol."""
    cache_key = f"chain_{symbol}_{expiry or 'all'}"
    cached = _get_cached(cache_key)
    if cached: return {"status": "success", "data": cached}

    try:
        t = yf.Ticker(symbol)

        # Get all available expiries
        try:
            expirations = t.options
        except:
            expirations = []

        if not expirations:
            return {"status": "error", "detail": f"No options available for {symbol}"}

        target_expiry = expiry if expiry else expirations[0]  # Nearest expiry

        if target_expiry not in expirations:
            return {"status": "error", "detail": f"Expiry {target_expiry} not available. Available: {expirations[:5]}"}

        opt = t.option_chain(target_expiry)
        calls = opt.calls
        puts = opt.puts

        # Add option type marker
        calls['option_type'] = 'call'
        puts['option_type'] = 'put'

        # Combine
        chain = pd.concat([calls, puts], ignore_index=True)
        chain = chain.replace({np.nan: None})

        # Format
        formatted = []
        for _, row in chain.iterrows():
            entry = {}
            for col in chain.columns:
                val = row[col]
                if isinstance(val, (np.floating,)):
                    entry[col] = float(val) if not np.isnan(val) else None
                elif isinstance(val, (np.integer,)):
                    entry[col] = int(val)
                else:
                    entry[col] = val
            formatted.append(entry)

        # Current price
        info = t.info
        current_price = clean(info.get("regularMarketPrice") or info.get("previousClose") or info.get("currentPrice"))

        # PCR
        pcr = compute_pcr(puts, calls)

        # Max pain
        max_pain = compute_max_pain(chain, current_price or 0)

        # Unusual options detection (high volume relative to OI)
        unusual = []
        for _, row in chain.iterrows():
            vol = row.get('volume', 0) or 0
            oi = row.get('openInterest', 0) or 0
            iv = clean(row.get('impliedVolatility'))
            price = clean(row.get('lastPrice'))
            
            if vol > 0 and oi > 0 and vol / oi > 1.5:  # Lowered threshold to see more data
                unusual.append({
                    "strike": float(row['strike']),
                    "option_type": row['option_type'].upper(),
                    "volume": int(vol),
                    "size": int(vol),
                    "open_interest": int(oi),
                    "vol_oi_ratio": round(float(vol/oi), 2),
                    "expiry": target_expiry,
                    "iv": round(iv * 100, 1) if iv else 0,
                    "premium": round(vol * 100 * (price or 0), 0),
                    "sentiment": "BULLISH" if (row['option_type'] == 'call' and price and price > row.get('bid', 0)) else "BEARISH"
                })

        result = {
            "symbol": symbol,
            "current_price": current_price,
            "max_pain": max_pain,
            "pcr": pcr,
            "iv": round(iv_atm * 100, 1) if 'iv_atm' in locals() and iv_atm else None, # Compatibility field
            "total_options": len(formatted),
            "unusual_activity": sorted(unusual, key=lambda x: x['vol_oi_ratio'], reverse=True)[:10],
            "chain": formatted[:200],  # Limit to 200 for performance
            "last_updated": int(time.time())
        }
        _set_cached(cache_key, result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/options/put-call-ratio")
def get_put_call_ratio():
    """Aggregate Put/Call ratios for key market ETFs."""
    cached = _get_cached("pcr_aggregate")
    if cached: return {"status": "success", "data": cached}

    try:
        results = []
        total_put_oi = 0
        total_call_oi = 0

        for symbol, name in OPTIONS_TICKERS.items():
            if symbol in ["BTC-USD", "ETH-USD"]:
                continue  # Skip crypto for options (use ETF proxies)
            try:
                t = yf.Ticker(symbol)
                expirations = t.options
                if not expirations:
                    continue

                # Get nearest 2 expiries
                for exp in expirations[:2]:
                    opt = t.option_chain(exp)
                    pcr = compute_pcr(opt.puts, opt.calls)
                    results.append({
                        "symbol": symbol,
                        "name": name,
                        "expiry": exp,
                        **pcr
                    })
                    if pcr['put_open_interest']:
                        total_put_oi += pcr['put_open_interest']
                    if pcr['call_open_interest']:
                        total_call_oi += pcr['call_open_interest']
                    break  # Just nearest expiry
            except Exception as e:
                log.warning(f"PCR[{symbol}]: {e}")
                continue

        # Market-wide PCR
        market_pcr = total_put_oi / total_call_oi if total_call_oi > 0 else None

        # Sentiment interpretation
        sentiment = "NEUTRAL"
        if market_pcr:
            if market_pcr > 1.2:
                sentiment = "BEARISH"  # More puts = bearish
            elif market_pcr > 0.8:
                sentiment = "SLIGHTLY_BEARISH"
            elif market_pcr < 0.6:
                sentiment = "BULLISH"  # More calls = bullish
            elif market_pcr < 0.8:
                sentiment = "SLIGHTLY_BULLISH"

        result = {
            "market_pcr_oi": round(market_pcr, 3) if market_pcr else None,
            "sentiment": sentiment,
            "tickers": results,
            "aggregate": {
                "total_put_oi": total_put_oi,
                "total_call_oi": total_call_oi
            },
            "last_updated": int(time.time())
        }
        _set_cached("pcr_aggregate", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/options/max-pain")
def get_max_pain():
    """Max pain levels for key market ETFs."""
    cached = _get_cached("max_pain_all")
    if cached: return {"status": "success", "data": cached}

    try:
        results = []
        for symbol, name in OPTIONS_TICKERS.items():
            if symbol in ["BTC-USD", "ETH-USD"]:
                continue
            try:
                t = yf.Ticker(symbol)
                info = t.info
                current_price = clean(info.get("regularMarketPrice") or info.get("previousClose") or info.get("currentPrice"))

                expirations = t.options
                if not expirations:
                    continue

                # Check next 3 weekly expiries
                for exp in expirations[:3]:
                    opt = t.option_chain(exp)
                    calls = opt.calls
                    puts = opt.puts
                    calls['option_type'] = 'call'
                    puts['option_type'] = 'put'
                    chain = pd.concat([calls, puts], ignore_index=True)
                    mp = compute_max_pain(chain, current_price or 0)

                    results.append({
                        "symbol": symbol,
                        "name": name,
                        "current_price": current_price,
                        "expiry": exp,
                        "max_pain": mp,
                        "distance_pct": round(((mp - current_price) / current_price) * 100, 2) if mp and current_price else None
                    })
            except Exception as e:
                log.warning(f"MAX_PAIN[{symbol}]: {e}")
                continue

        result = {
            "tickers": results,
            "last_updated": int(time.time())
        }
        _set_cached("max_pain_all", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/options/iv-rank/{symbol}")
def get_iv_rank(symbol: str = "SPY"):
    """Implied volatility rank and percentile for a symbol."""
    cache_key = f"iv_rank_{symbol}"
    cached = _get_cached(cache_key)
    if cached: return {"status": "success", "data": cached}

    try:
        t = yf.Ticker(symbol)
        info = t.info

        # Get implied vol from options
        expirations = t.options
        if not expirations:
            return {"status": "error", "detail": "No options data"}

        # Get nearest expiry
        opt = t.option_chain(expirations[0])
        calls = opt.calls
        puts = opt.puts

        # ATM implied vol (strike closest to current price)
        curr_price = clean(info.get("regularMarketPrice") or info.get("previousClose") or info.get("currentPrice"))
        if not curr_price:
            return {"status": "error", "detail": "No price data"}

        # Find ATM call and put
        calls['price_dist'] = abs(calls['strike'] - curr_price)
        puts['price_dist'] = abs(puts['strike'] - curr_price)

        atm_call = calls.loc[calls['price_dist'].idxmin()] if not calls.empty else None
        atm_put = puts.loc[puts['price_dist'].idxmin()] if not puts.empty else None

        # Implied vol from IV column
        iv_call = clean(atm_call.get('impliedVolatility')) if atm_call is not None else None
        iv_put = clean(atm_put.get('impliedVolatility')) if atm_put is not None else None
        iv_atm = np.mean([iv for iv in [iv_call, iv_put] if iv]) if iv_call or iv_put else None

        # For IV rank, we need historical IV. Use HV as proxy.
        hist = t.history(period="1y")
        hv = None
        if not hist.empty and len(hist) > 21:
            returns = np.diff(np.log(hist['Close'].values))
            hv_21d = float(np.std(returns[-21:]) * np.sqrt(252) * 100)
            hv_1y = [float(np.std(returns[max(0,i-21):i]) * np.sqrt(252) * 100) for i in range(21, len(returns)+1)]
            hv_min = min(hv_1y) if hv_1y else 0
            hv_max = max(hv_1y) if hv_1y else 0
            hv_current = hv_1y[-1] if hv_1y else hv_21d

            hv_rank = ((hv_current - hv_min) / (hv_max - hv_min) * 100) if (hv_max - hv_min) > 0 else 50
            hv_percentile = sum(1 for h in hv_1y if h <= hv_current) / len(hv_1y) * 100 if hv_1y else 50
        else:
            hv_current = None
            hv_rank = None
            hv_percentile = None

        result = {
            "symbol": symbol,
            "current_price": curr_price,
            "iv": round(iv_atm * 100, 2) if iv_atm else None, # Compatibility field
            "atm_iv_call": round(iv_call * 100, 2) if iv_call else None,
            "atm_iv_put": round(iv_put * 100, 2) if iv_put else None,
            "atm_iv": round(iv_atm * 100, 2) if iv_atm else None,
            "realized_vol_21d": round(hv_current, 2) if hv_current else None,
            "iv_rank": round(hv_rank, 1) if hv_rank else None,
            "iv_percentile": round(hv_percentile, 1) if hv_percentile else None,
            "iv_rank_signal": "EXPENSIVE" if (hv_rank or 0) > 80 else ("CHEAP" if (hv_rank or 0) < 20 else "FAIR"),
            "last_updated": int(time.time())
        }
        _set_cached(cache_key, result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/options/iv-rank/all")
def get_all_iv_ranks():
    """Aggregate IV ranks for all watch symbols."""
    cached = _get_cached("iv_ranks_all")
    if cached: return {"status": "success", "data": cached}
    
    results = []
    for symbol in list(OPTIONS_TICKERS.keys()):
        if symbol in ["BTC-USD", "ETH-USD"]: continue
        try:
            # Re-use the existing logic by calling the function directly
            data = get_iv_rank(symbol)
            if data["status"] == "success":
                results.append(data["data"])
        except: continue
    
    _set_cached("iv_ranks_all", results)
    return {"status": "success", "data": results}


@app.get("/api/options/unusual/all")
def get_all_unusual_activity():
    """Aggregate unusual options activity across market."""
    cached = _get_cached("unusual_all")
    if cached: return {"status": "success", "data": cached}
    
    results = []
    for symbol in list(OPTIONS_TICKERS.keys()):
        if symbol in ["BTC-USD", "ETH-USD"]: continue
        try:
            data = get_options_chain(symbol)
            if data["status"] == "success":
                # chain endpoint returns unusual_activity for that symbol
                for item in data["data"].get("unusual_activity", []):
                    item["symbol"] = symbol
                    # Add timestamp for sorting
                    item["timestamp"] = int(time.time() * 1000)
                    results.append(item)
        except: continue
    
    # Sort by volume/oi ratio
    results.sort(key=lambda x: x.get('vol_oi_ratio', 0), reverse=True)
    
    _set_cached("unusual_all", results[:50])
    return {"status": "success", "data": results[:50]}


@app.get("/api/options/summary")
def get_options_summary():
    """Aggregated options market overview."""
    try:
        pcr_data = _get_cached("pcr_aggregate")
        if not pcr_data: pcr_data = get_put_call_ratio().get("data", {})
        
        max_pain_data = _get_cached("max_pain_all")
        if not max_pain_data: max_pain_data = get_max_pain().get("data", {})
        
        iv_rank_data = _get_cached("iv_ranks_all")
        if not iv_rank_data: iv_rank_data = get_all_iv_ranks().get("data", [])
        
        unusual_data = _get_cached("unusual_all")
        if not unusual_data: unusual_data = get_all_unusual_activity().get("data", [])

        # Key signals
        signals = []
        if pcr_data and pcr_data.get('market_pcr_oi'):
            pcr = pcr_data['market_pcr_oi']
            if pcr > 1.0:
                signals.append({"signal": "HIGH_PUT_ACTIVITY", "severity": "MEDIUM",
                    "detail": f"Put/Call ratio at {pcr} — elevated hedging/ bearish sentiment"})

        return {
            "status": "success",
            "data": {
                "put_call_ratio": pcr_data,
                "max_pain": max_pain_data,
                "iv_rank": iv_rank_data,
                "unusual_activity": unusual_data,
                "signals": signals,
                "last_updated": int(time.time())
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "options_service_online", "timestamp": int(time.time())}


if __name__ == "__main__":
    log.info("Options Flow Intelligence Service starting on port 8165")
    uvicorn.run(app, host="0.0.0.0", port=8165)
