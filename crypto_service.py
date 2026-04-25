import os
import time
import asyncio
import requests
import xml.etree.ElementTree as ET
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import uvicorn
from crypto_analysis import analyzer
import sys
import numpy as np
import pandas as pd
import threading
import random
import re
from typing import Dict, Any, List, Optional
from crypto_agents import crypto_multi_agent
import yfinance as yf
from crypto_onchain import onchain_analyzer
from crypto_derivatives import derivatives_analyzer
from crypto_quant import quant_analyzer
from crypto_macro import macro_analyzer
import json

# --- DELISTING MANAGEMENT ---
DELISTED_SYMBOLS_PATH = os.path.join(os.path.dirname(__file__), 'data', 'delisted_symbols.json')

def load_delisted_symbols():
    if os.path.exists(DELISTED_SYMBOLS_PATH):
        try:
            with open(DELISTED_SYMBOLS_PATH, 'r') as f:
                return set(json.load(f))
        except Exception as e:
            print(f"[DELISTED_LOAD_ERROR] {e}")
            return set()
    return set()

def save_delisted_symbol(symbol):
    delisted = load_delisted_symbols()
    if symbol not in delisted:
        delisted.add(symbol)
        os.makedirs(os.path.dirname(DELISTED_SYMBOLS_PATH), exist_ok=True)
        try:
            with open(DELISTED_SYMBOLS_PATH, 'w') as f:
                json.dump(list(delisted), f)
            print(f"[CRYPTO_SERVICE.PY] {symbol}: added to delisted list (JSON)")
        except Exception as e:
            print(f"[DELISTED_SAVE_ERROR] {e}")

# Global set for runtime filtering
DELISTED_CACHE = load_delisted_symbols()

class MonteCarloSimulator:
    def __init__(self, config=None):
        self.n_simulations = config.get('n_simulations', 1000) if config else 1000

    def simulate_price_paths(self, initial_price, expected_return, volatility, time_horizon):
        dt = 1 / 365
        n_steps = time_horizon
        mu = expected_return
        sigma = volatility
        
        # Drift and shock components
        drift = (mu - 0.5 * sigma**2) * dt
        shock = sigma * np.sqrt(dt)
        
        # Generate random shocks
        daily_shocks = np.random.normal(0, 1, (self.n_simulations, n_steps))
        daily_returns = drift + shock * daily_shocks
        
        # Cumulative returns to get the price paths
        cumulative_returns = np.cumsum(daily_returns, axis=1)
        price_paths = initial_price * np.exp(cumulative_returns)
        
        # Insert initial price at the beginning
        price_paths = np.hstack([np.full((self.n_simulations, 1), initial_price), price_paths])
        
        # Scenarios for visualization
        scenarios = pd.DataFrame(price_paths)
        
        final_prices = price_paths[:, -1]
        mean_final = np.mean(final_prices)
        
        # Returns for VaR/CVaR
        total_returns = (final_prices - initial_price) / initial_price
        sorted_returns = np.sort(total_returns)
        
        var_index = max(1, int(0.05 * self.n_simulations))
        var_95 = abs(sorted_returns[var_index])
        cvar_95 = abs(np.mean(sorted_returns[:var_index]))
        
        best_case = np.max(total_returns)
        worst_case = np.min(total_returns)
        
        class SimulationResult:
            def __init__(self, scenarios, statistics, var_results, cvar_results):
                self.scenarios = scenarios
                self.statistics = statistics
                self.var_results = var_results
                self.cvar_results = cvar_results
        
        return SimulationResult(
            scenarios=scenarios,
            statistics={
                'mean_final_value': mean_final,
                'max_return': best_case,
                'min_return': worst_case
            },
            var_results={0.95: var_95},
            cvar_results={0.95: cvar_95}
        )

HAS_SIMULATOR = True

# Load .env from current directory (be/)
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

BINANCE_KLINE_URL = f"{os.getenv('BINANCE_API_BASE', 'https://api.binance.com')}/api/v3/klines"

# Top RSS Feeds from the requested config
RSS_FEEDS = [
    {"name": "Cointelegraph", "url": "https://cointelegraph.com/rss"},
    {"name": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml"},
    {"name": "The Block", "url": "https://www.theblock.co/rss.xml"},
    {"name": "CryptoPotato", "url": "https://cryptopotato.com/feed/"},
    {"name": "CryptoSlate", "url": "https://cryptoslate.com/feed/"},
    {"name": "Decrypt", "url": "https://decrypt.co/feed"},
    {"name": "Investing.com", "url": "https://id.investing.com/rss/news_301.rss"}
]

ECONOMY_FEEDS = [
    {"name": "Bloomberg Markets", "url": "https://feeds.bloomberg.com/markets/news.rss"},
    {"name": "NYT Economy", "url": "https://rss.nytimes.com/services/xml/rss/nyt/Economy.xml"},
    {"name": "The Economist", "url": "https://www.economist.com/latest/rss.xml"},
    {"name": "Forbes Business", "url": "https://www.forbes.com/business/feed/"},
    {"name": "CNBC Indonesia", "url": "https://www.cnbcindonesia.com/news/rss"},
    {"name": "Detik Finance", "url": "https://finance.detik.com/rss"}
]

app = FastAPI(debug=True, title="Crypto Data Microservice (v9 + yFinance)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

state: Dict[str, Any] = {
    "usd_idr_rate": 15500.0,
    "rate_last_updated": 0.0,
    "metadata_cache": {},
    "rss_cache": [],
    "rss_last_updated": 0.0
}
_RSS_LOCK = threading.Lock()  # Thread-safe RSS cache access

# --- CMC CONFIG ---
CMC_API_KEY = os.getenv('CMC_API_KEY')
CMC_API_BASE = os.getenv('CMC_API_BASE', 'https://pro-api.coinmarketcap.com')

def fetch_cmc_top_coins(limit=100):
    """Fetch top coins directly from CoinMarketCap Professional API"""
    if not CMC_API_KEY:
        return []
    
    url = f"{CMC_API_BASE}/v1/cryptocurrency/listings/latest"
    parameters = {
        'start': '1',
        'limit': str(limit),
        'convert': 'USD'
    }
    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': CMC_API_KEY,
    }

    try:
        response = requests.get(url, params=parameters, headers=headers)
        data = response.json()
        if data.get('status', {}).get('error_code') == 0:
            return data.get('data', [])
        else:
            print(f"[CMC_ERROR] {data.get('status', {}).get('error_message')}")
            return []
    except Exception as e:
        print(f"[CMC_EXCEPTION] {e}")
        return []

MAJOR_CRYPTO_SYMBOLS = [
    "BTC-USD", "ETH-USD", "USDT-USD", "XRP-USD", "BNB-USD", "SOL-USD", "USDC-USD", "DOGE-USD", "ADA-USD", "TRX-USD",
    "AVAX-USD", "LINK-USD", "SHIB-USD", "TON-USD", "WBTC-USD", "SUI20947-USD", "DOT-USD", "BCH-USD", "LTC-USD", "NEAR-USD",
    "UNI7083-USD", "ICP-USD", "APT21794-USD", "POL-USD", "STX4847-USD", "OP-USD", "AAVE-USD", "IMX10603-USD", "ARB11841-USD", "FIL-USD"
]

def clean_html(raw_html):
    if not raw_html: return ""
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext[:150] + "..." if len(cleantext) > 150 else cleantext

def fetch_rss_feeds(feeds_list):
    all_items = []
    for feed in feeds_list:
        try:
            resp = requests.get(feed["url"], timeout=5, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item")[:10]:
                    title = item.find("title").text if item.find("title") is not None else "No Title"
                    link = item.find("link").text if item.find("link") is not None else "#"
                    desc = item.find("description").text if item.find("description") is not None else ""
                    pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                    all_items.append({
                        "title": title, "url": link, "body": clean_html(desc),
                        "source": feed["name"], "date": pub_date
                    })
        except Exception as e:
            print(f"Error fetching RSS {feed['name']}: {e}")
    
    random.shuffle(all_items)
    return all_items

def clean_nans(obj):
    """Recursively replace NaN and Inf with None or 0.0 for JSON compatibility."""
    if isinstance(obj, dict):
        return {k: clean_nans(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nans(v) for v in obj]
    elif isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return 0.0
        return obj
    return obj

def safe_float(val, default=0.0):
    try:
        if val is None or np.isnan(val) or np.isinf(val):
            return default
        return float(val)
    except:
        return default

# CRYPTO DATA CACHE
CRYPTO_CACHE = {
    "top_coins": [],
    "cmc_full": [],
    "last_updated": 0
}

# Persistent metadata store for names and market caps (updated less frequently)
METADATA_STORE = {}

DETAIL_CACHE = {}
D_CACHE_TTL = 900 # 15 mins for heavy simulations

def get_detail_cache(symbol):
    if symbol in DETAIL_CACHE:
        entry = DETAIL_CACHE[symbol]
        if time.time() - entry['timestamp'] < D_CACHE_TTL:
            return entry['data']
    return None

def set_detail_cache(symbol, data):
    DETAIL_CACHE[symbol] = {'timestamp': time.time(), 'data': data}

async def fetch_metadata_loop():
    """Background task to fetch coin names and market caps every 60 minutes"""
    print("=:: STARTING CRYPTO_METADATA UPDATER (CMC/yF) ::= ")
    while True:
        try:
            # Try CMC first
            cmc_data = fetch_cmc_top_coins(100)
            if cmc_data:
                CRYPTO_CACHE["cmc_full"] = cmc_data
                for coin in cmc_data:
                    ticker = f"{coin['symbol']}-USD"
                    METADATA_STORE[ticker] = {
                        "name": coin['name'],
                        "market_cap": float(coin['quote']['USD']['market_cap']),
                        "cmc_rank": coin['cmc_rank']
                    }
                print(f"[METADATA_SYNC] CMC update success. Metadata for {len(cmc_data)} assets.")
            else:
                # Fallback to yfinance
                for ticker in MAJOR_CRYPTO_SYMBOLS:
                    try:
                        t = yf.Ticker(ticker)
                        info = t.info
                        METADATA_STORE[ticker] = {
                            "name": info.get("name") or info.get("shortName") or ticker.replace("-USD", ""),
                            "market_cap": float(info.get("marketCap") or 0.0)
                        }
                        await asyncio.sleep(0.5)
                    except:
                        continue
                print(f"[METADATA_SYNC] Fallback yFinance update completed.")
        except Exception as e:
            print(f"[METADATA_SYNC_ERROR] {e}")
        await asyncio.sleep(3600) # Update metadata every hour

async def fetch_top_coins_loop():
    """Background task to refresh crypto data using yfinance every 90 seconds"""
    print("=:: STARTING CRYPTO_SERVICE BACKGROUND UPDATER (yFinance) ::= ")
    while True:
        try:
            # Get top symbols dynamically
            current_symbols = []
            if METADATA_STORE:
                sorted_meta = sorted(METADATA_STORE.items(), key=lambda x: x[1].get('market_cap', 0), reverse=True)
                current_symbols = [k for k, v in sorted_meta[:100] if k not in DELISTED_CACHE][:35] # Top 35 active
            
            if not current_symbols:
                current_symbols = MAJOR_CRYPTO_SYMBOLS

            data = yf.download(current_symbols, period="8d", interval="1h", group_by='ticker', progress=False)
            
            coins = []
            for i, ticker in enumerate(current_symbols):
                try:
                    symbol_raw = ticker.replace("-USD", "")
                    
                    if len(current_symbols) > 1:
                        if ticker not in data.columns.get_level_values(0):
                            continue
                        df = data[ticker]
                    else:
                        df = data

                    if df is None or df.empty or len(df) < 2:
                        print(f"[CRYPTO_SERVICE.PY] {ticker}: possibly delisted; no price data found")
                        if ticker not in MAJOR_CRYPTO_SYMBOLS:
                            save_delisted_symbol(ticker)
                            DELISTED_CACHE.add(ticker)
                        continue
                    
                    last_row = df.iloc[-1]
                    price = float(last_row['Close'])
                    
                    price_1h = float(df.iloc[-2]['Close']) if len(df) >= 2 else price
                    change_1h = ((price - price_1h) / price_1h * 100) if price_1h != 0 else 0
                    
                    idx_24h = -25 if len(df) >= 25 else 0
                    price_24h = float(df.iloc[idx_24h]['Close'])
                    change_24h = ((price - price_24h) / price_24h * 100) if price_24h != 0 else 0
                    
                    price_7d = float(df.iloc[0]['Close'])
                    change_7d = ((price - price_7d) / price_7d * 100) if price_7d != 0 else 0
                    
                    vol_24h = float(df.iloc[-24:]['Volume'].sum()) if len(df) >= 24 else float(df['Volume'].sum())
                    
                    meta = METADATA_STORE.get(ticker, {})
                    
                    coins.append({
                        "symbol": symbol_raw,
                        "name": meta.get("name", symbol_raw),
                        "rank": meta.get("cmc_rank", i + 1),
                        "price": safe_float(price),
                        "price_idr": safe_float(price * state["usd_idr_rate"]),
                        "market_cap": safe_float(meta.get("market_cap", 0.0)),
                        "change_1h": safe_float(change_1h),
                        "change_24h": safe_float(change_24h),
                        "change_7d": safe_float(change_7d),
                        "volume_24h": safe_float(vol_24h),
                        "last_updated": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                    })
                except Exception as ex:
                    print(f"Error processing ticker {ticker}: {ex}")
            
            if coins:
                CRYPTO_CACHE["top_coins"] = coins
                CRYPTO_CACHE["last_updated"] = time.time()
                print(f"[CRYPTO_SYNC] yFinance update completed: {len(coins)} assets cached.")
            
        except Exception as e:
            print(f"[CRYPTO_SYNC_ERROR] {e}")
            
        await asyncio.sleep(90)

@app.get("/api/crypto/top")
def get_top_coins(top: int = 100):
    # Use cache if available
    if CRYPTO_CACHE["top_coins"] and (time.time() - CRYPTO_CACHE["last_updated"] < 90):
        return clean_nans({"status": "success", "data": CRYPTO_CACHE["top_coins"][:top], "cached": True})

    # If cache empty, return empty list (loop will fill it)
    return clean_nans({"status": "success", "data": CRYPTO_CACHE["top_coins"][:top], "cached": False})

@app.get("/api/crypto/cmc/list")
def get_cmc_list():
    """Returns the full top 100 list from CMC cache"""
    if CRYPTO_CACHE["cmc_full"]:
        return {"status": "success", "data": CRYPTO_CACHE["cmc_full"]}
    
    # Trigger one-time fetch if cache empty
    data = fetch_cmc_top_coins(100)
    if data:
        CRYPTO_CACHE["cmc_full"] = data
        return {"status": "success", "data": data}
    
    return {"status": "error", "message": "CMC data unavailable"}

@app.get("/api/crypto/detail/{symbol}")
def get_coin_detail(symbol: str, period: str = "1mo"):
    ticker_symbol = f"{symbol}-USD"
    if ticker_symbol in DELISTED_CACHE:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} is delisted or unavailable.")
        
    cached = get_detail_cache(symbol)
    if cached: return cached
    
    ticker = yf.Ticker(ticker_symbol)
    
    range_limit_map = {
        "1d": 1, "5d": 5, "1mo": 30, "3mo": 90, 
        "6mo": 180, "1y": 365, "2y": 730, "5y": 1000, "max": 1000
    }
    limit = range_limit_map.get(period, 100)
    
    # 1. RSS Live Feed
    current_time = time.time()
    if not state["rss_cache"] or (current_time - state["rss_last_updated"] > 300):
        state["rss_cache"] = fetch_rss_feeds(RSS_FEEDS)
        state["rss_last_updated"] = current_time

    # 2. Metadata & Quote
    try:
        info = ticker.info
        metadata = {
            "logo": info.get("logo_url"),
            "description": info.get("description", "N/A"),
            "urls": {"website": [info.get("website")] if info.get("website") else []},
            "tags": []
        }
        price = float(info.get("regularMarketPrice") or info.get("previousClose") or 0.0)
        market_cap = float(info.get("marketCap") or 0.0)
        volume_24h = float(info.get("volume24Hr") or info.get("regularMarketVolume") or 0.0)
        change_24h = float(info.get("regularMarketChangePercent") or 0.0)
        name = info.get("name") or info.get("shortName") or symbol
    except Exception as e:
        print(f"yFinance Info fetch failed for {symbol}: {e}")
        metadata = {"logo": None, "description": "N/A", "urls": {}, "tags": []}
        price = 0.0
        market_cap = 0.0
        volume_24h = 0.0
        change_24h = 0.0
        name = symbol

    # 3. TA & History
    ta_report = analyzer.analyze(symbol)
    history = []
    try:
        hist_df = ticker.history(period=period)
        if not hist_df.empty:
            for ts, row in hist_df.iterrows():
                history.append({
                    "date": ts.strftime('%Y-%m-%d'),
                    "open": float(row['Open']),
                    "high": float(row['High']),
                    "low": float(row['Low']),
                    "close": float(row['Close']),
                    "volume": float(row['Volume'])
                })
    except: pass

    # 4. Monte Carlo Simulation (Last 365 Days)
    monte_carlo = {}
    if HAS_SIMULATOR:
        try:
            sim_hist = ticker.history(period="1y")
            if not sim_hist.empty:
                closes = sim_hist['Close'].tolist()
                returns = pd.Series(closes).pct_change().dropna()
                if len(returns) < 5:
                    vol = 0.5 # Fallback 50% vol
                    mu = 0.1 # Fallback 10% return
                else:
                    vol = returns.std() * np.sqrt(365) # Daily annualized
                    mu = returns.mean() * 365
                
                current_p = price if price > 0 else closes[-1]
                print(f"[MONTE_CARLO] Running for {symbol} at ${current_p} (Vol: {vol:.2f})")
                
                simulator = MonteCarloSimulator({'n_simulations': 5000})
                
                # Sim for 7d, 30d, 90d
                horizons = [7, 30, 90]
                for h in horizons:
                    sim_out = simulator.simulate_price_paths(
                        initial_price=current_p,
                        expected_return=mu,
                        volatility=vol,
                        time_horizon=h
                    )
                    
                    # Extract scenarios
                    paths = []
                    if sim_out.scenarios is not None:
                        for i in range(5):
                            path_row = sim_out.scenarios.iloc[i].tolist()
                            paths.append(path_row)
                    
                    monte_carlo[f"{h}d"] = {
                        "horizon": h,
                        "expected_final": round(sim_out.statistics['mean_final_value'], 2),
                        "var_95": round(sim_out.var_results.get(0.95, 0) * 100, 2),
                        "cvar_95": round(sim_out.cvar_results.get(0.95, 0) * 100, 2),
                        "best_case": round(sim_out.statistics['max_return'] * 100, 2),
                        "worst_case": round(sim_out.statistics['min_return'] * 100, 2),
                        "paths": paths
                    }
        except Exception as e:
            print(f"Monte Carlo Breach: {e}")

    result = {
        "status": "success",
        "data": {
            "name": name, "symbol": symbol,
            "price": price, "market_cap": market_cap,
            "volume_24h": volume_24h, "percent_change_24h": change_24h,
            "rank": 0, "metadata": metadata,
            "ta_report": ta_report, "history": history,
            "news": state["rss_cache"], "rate": float(state["usd_idr_rate"]),
            "monte_carlo": monte_carlo
        }
    }
    set_detail_cache(symbol, result)
    return clean_nans(result)

@app.get("/api/news/economy")
def get_economy_news():
    try:
        news = fetch_rss_feeds(ECONOMY_FEEDS)
        return {"status": "success", "data": news}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crypto/search")
def search_crypto(q: str = ""):
    if not q:
        return {"status": "success", "data": []}

    query = q.lower()

    # Search in-memory cache
    cached_coins = CRYPTO_CACHE.get("top_coins", [])
    if cached_coins:
        results = [
            {
                "symbol": c["symbol"],
                "name": c["name"],
                "rank": c["rank"],
                "price": c["price"],
                "price_idr": c["price_idr"],
                "market_cap": c["market_cap"],
                "change_24h": c["change_24h"]
            }
            for c in cached_coins
            if query in c["name"].lower() or query in c["symbol"].lower()
        ]
        return {"status": "success", "data": results[:50], "source": "cache"}

    return {"status": "success", "data": []}

@app.get("/api/ai/analyze")
def api_ai_analyze(symbol: str):
    try:
        # Load small history and TA to mock real input
        ta_report = analyzer.analyze(symbol)
        history = []
        try:
            ticker = yf.Ticker(f"{symbol}-USD")
            hist_df = ticker.history(period="1mo")
            if not hist_df.empty:
                for ts, row in hist_df.iterrows():
                    history.append({"close": float(row['Close']), "volume": float(row['Volume'])})
        except: pass
        
        price = history[-1]['close'] if history else 0
        ai_verdict = crypto_multi_agent.run_all_agents(symbol, price, history, ta_report)
        return clean_nans({"status": "success", "data": ai_verdict})
    except Exception as e:
        print(f"Error AI Analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crypto/stats/seasonality/{symbol}")
def get_crypto_seasonality(symbol: str):
    try:
        ticker_symbol = f"{symbol}-USD"
        ticker = yf.Ticker(ticker_symbol)
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
                if np.isnan(val) or np.isinf(val): val = 0
                matrix.append([m_idx - 1, i, float(round(val * 100, 2))])
        
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

# ============================================================
# INSTITUTIONAL ANALYTICS ENDPOINTS
# ============================================================

@app.get("/api/crypto/onchain/{symbol}")
def get_onchain_data(symbol: str):
    try:
        data = onchain_analyzer.get_full_report(symbol)
        return clean_nans({"status": "success", "data": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crypto/onchain/flow/{symbol}")
def get_exchange_flow(symbol: str, period: str = "3mo"):
    try:
        data = onchain_analyzer.compute_exchange_flow(symbol, period)
        return clean_nans({"status": "success", "data": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crypto/onchain/whales/{symbol}")
def get_whale_activity(symbol: str):
    try:
        data = onchain_analyzer.detect_whale_activity(symbol)
        return clean_nans({"status": "success", "data": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crypto/onchain/nvt/{symbol}")
def get_nvt_ratio(symbol: str):
    try:
        data = onchain_analyzer.compute_nvt_ratio(symbol)
        return clean_nans({"status": "success", "data": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crypto/derivatives/{symbol}")
def get_derivatives_data(symbol: str):
    try:
        data = derivatives_analyzer.get_full_derivatives(symbol)
        return clean_nans({"status": "success", "data": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crypto/derivatives/funding/{symbol}")
def get_funding_rate(symbol: str):
    try:
        sym = symbol.replace("-USD","") + "USDT"
        data = derivatives_analyzer.get_funding_rates(sym)
        return clean_nans({"status": "success", "data": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crypto/derivatives/oi/{symbol}")
def get_open_interest_ep(symbol: str):
    try:
        sym = symbol.replace("-USD","") + "USDT"
        data = derivatives_analyzer.get_open_interest(sym)
        return clean_nans({"status": "success", "data": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crypto/derivatives/liquidations/{symbol}")
def get_liquidation_zones(symbol: str):
    try:
        sym = symbol.replace("-USD","") + "USDT"
        data = derivatives_analyzer.estimate_liquidation_zones(sym)
        return clean_nans({"status": "success", "data": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crypto/quant/{symbol}")
def get_quant_data(symbol: str):
    try:
        data = quant_analyzer.get_full_quant(symbol)
        return clean_nans({"status": "success", "data": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crypto/quant/correlation/{symbol}")
def get_correlation_matrix(symbol: str):
    try:
        data = quant_analyzer.compute_correlation_matrix(symbol)
        return clean_nans({"status": "success", "data": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crypto/quant/drawdown/{symbol}")
def get_drawdown(symbol: str):
    try:
        data = quant_analyzer.compute_drawdown_analysis(symbol)
        return clean_nans({"status": "success", "data": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crypto/quant/volatility/{symbol}")
def get_volatility(symbol: str):
    try:
        data = quant_analyzer.compute_volatility_metrics(symbol)
        return clean_nans({"status": "success", "data": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crypto/quant/beta/{symbol}")
def get_beta(symbol: str):
    try:
        data = quant_analyzer.compute_beta(symbol)
        return clean_nans({"status": "success", "data": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crypto/macro")
def get_macro_data():
    try:
        data = macro_analyzer.get_full_macro()
        return clean_nans({"status": "success", "data": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crypto/macro/etf")
def get_etf_flows():
    try:
        data = macro_analyzer.get_etf_flows()
        return clean_nans({"status": "success", "data": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crypto/macro/stablecoin")
def get_stablecoin_metrics():
    try:
        data = macro_analyzer.get_stablecoin_metrics()
        return clean_nans({"status": "success", "data": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crypto/macro/feargreed")
def get_fear_greed():
    try:
        data = macro_analyzer.get_fear_greed_index()
        return clean_nans({"status": "success", "data": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crypto/macro/dominance")
def get_dominance():
    try:
        data = macro_analyzer.get_market_dominance()
        return clean_nans({"status": "success", "data": data})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    """Root handler for avoiding 404 on service heartbeat probes."""
    return {"status": "online", "service": "crypto_data_service_v10_institutional"}

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(fetch_metadata_loop())
    asyncio.create_task(fetch_top_coins_loop())

if __name__ == "__main__":
    print("=:: MEMULAI SERVICE PYTHON CRYPTO DATA (v10 + INSTITUTIONAL) ::=")
    uvicorn.run("crypto_service:app", host="0.0.0.0", port=8085, reload=False)
