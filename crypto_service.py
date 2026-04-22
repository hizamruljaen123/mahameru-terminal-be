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

# API Key from environment — NEVER hardcode!
API_KEY = os.getenv('CMC_API_KEY', '')
if not API_KEY:
    import logging
    logging.warning("[CRYPTO_SERVICE] CMC_API_KEY not set in .env — API calls will fail!")

CMC_LISTINGS_URL = f"{os.getenv('CMC_API_BASE', 'https://pro-api.coinmarketcap.com')}/v1/cryptocurrency/listings/latest"
CMC_METADATA_URL = f"{os.getenv('CMC_API_BASE', 'https://pro-api.coinmarketcap.com')}/v2/cryptocurrency/info"
CMC_QUOTES_URL = f"{os.getenv('CMC_API_BASE', 'https://pro-api.coinmarketcap.com')}/v2/cryptocurrency/quotes/latest"
CMC_HISTORY_URL = f"{os.getenv('CMC_API_BASE', 'https://pro-api.coinmarketcap.com')}/v1/cryptocurrency/quotes/historical"
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

app = FastAPI(debug=True, title="Crypto Data Microservice (v9 + Live RSS)")

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

# CRYPTO DATA CACHE
CRYPTO_CACHE = {
    "top_coins": [],
    "last_updated": 0
}

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

async def fetch_top_coins_loop():
    """Background task to refresh top 200 coins every 60 seconds"""
    print("=:: STARTING CRYPTO_SERVICE BACKGROUND UPDATER ::= ")
    headers = {"X-CMC_PRO_API_KEY": API_KEY, "Accept": "application/json"}
    while True:
        try:
            # We fetch top 200 for a good balance of coverage and speed
            res = requests.get(CMC_LISTINGS_URL, headers=headers, params={"limit": 200, "convert": "USD"}, timeout=10)
            data = res.json().get("data", [])
            
            coins = []
            for coin in data:
                quote = coin.get("quote", {}).get("USD", {})
                coins.append({
                    "symbol": coin.get("symbol"),
                    "name": coin.get("name"),
                    "rank": coin.get("cmc_rank"),
                    "price": float(quote.get("price", 0.0)),
                    "price_idr": float(quote.get("price", 0.0)) * state["usd_idr_rate"],
                    "market_cap": float(quote.get("market_cap", 0.0)),
                    "change_1h": float(quote.get("percent_change_1h", 0.0)),
                    "change_24h": float(quote.get("percent_change_24h", 0.0)),
                    "change_7d": float(quote.get("percent_change_7d", 0.0)),
                    "volume_24h": float(quote.get("volume_24h", 0.0)),
                    "last_updated": quote.get("last_updated")
                })
            
            CRYPTO_CACHE["top_coins"] = coins
            CRYPTO_CACHE["last_updated"] = time.time()
            print(f"[CRYPTO_SYNC] Periodic update completed: {len(coins)} assets cached.")
            
        except Exception as e:
            print(f"[CRYPTO_SYNC_ERROR] {e}")
            
        await asyncio.sleep(60)

@app.get("/api/crypto/top")
def get_top_coins(top: int = 1000):
    # Use cache if available and top is within cached range
    if CRYPTO_CACHE["top_coins"] and top <= len(CRYPTO_CACHE["top_coins"]) and (time.time() - CRYPTO_CACHE["last_updated"] < 90):
        return {"status": "success", "data": CRYPTO_CACHE["top_coins"][:top], "cached": True}

    headers = {"X-CMC_PRO_API_KEY": API_KEY, "Accept": "application/json"}
    try:
        res = requests.get(CMC_LISTINGS_URL, headers=headers, params={"limit": top, "convert": "USD"}, timeout=10)
        data = res.json().get("data", [])
        
        coins = []
        for coin in data:
            quote = coin.get("quote", {}).get("USD", {})
            coins.append({
                "symbol": coin.get("symbol"),
                "name": coin.get("name"),
                "rank": coin.get("cmc_rank"),
                "price": float(quote.get("price", 0.0)),
                "price_idr": float(quote.get("price", 0.0)) * state["usd_idr_rate"],
                "market_cap": float(quote.get("market_cap", 0.0)),
                "change_1h": float(quote.get("percent_change_1h", 0.0)),
                "change_24h": float(quote.get("percent_change_24h", 0.0)),
                "change_7d": float(quote.get("percent_change_7d", 0.0)),
                "volume_24h": float(quote.get("volume_24h", 0.0)),
                "last_updated": quote.get("last_updated")
            })
            
        return {"status": "success", "data": coins}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crypto/detail/{symbol}")
def get_coin_detail(symbol: str, period: str = "1mo"):
    cached = get_detail_cache(symbol)
    if cached: return cached

    headers = {"X-CMC_PRO_API_KEY": API_KEY, "Accept": "application/json"}
    
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

    # 2. Metadata
    metadata = state["metadata_cache"].get(symbol)
    if not metadata:
        try:
            res = requests.get(CMC_METADATA_URL, headers=headers, params={"symbol": symbol}, timeout=5)
            data_map = res.json().get("data", {})
            info_list = data_map.get(symbol, [{}])
            info = info_list[0] if isinstance(info_list, list) else info_list
            metadata = { "logo": info.get("logo"), "description": info.get("description"), "urls": info.get("urls", {}), "tags": info.get("tags", [])}
            state["metadata_cache"][symbol] = metadata
        except: metadata = {"logo": None, "description": "N/A", "urls": {}, "tags": []}

    # 3. TA & History
    ta_report = analyzer.analyze(symbol)
    history = []
    try:
        bin_symbol = f"{symbol}USDT"
        h_res = requests.get(BINANCE_KLINE_URL, params={"symbol": bin_symbol, "interval": "1d", "limit": limit}, timeout=10)
        if h_res.status_code == 200:
            for k in reversed(h_res.json()):
                history.append({"date": time.strftime('%Y-%m-%d', time.gmtime(int(k[0])/1000)), "open": float(k[1]), "high": float(k[2]), "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])})
    except: pass

    # 5. Latest Quote
    try:
        res = requests.get(CMC_QUOTES_URL, headers=headers, params={"symbol": symbol, "convert": "USD"}, timeout=10)
        quote_data_map = res.json().get("data", {})
        q_list = quote_data_map.get(symbol, [{}])
        quote_data = q_list[0] if isinstance(q_list, list) else q_list
        quote = quote_data.get("quote", {}).get("USD", {})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quote fetch failed: {str(e)}")

    # 6. Monte Carlo Simulation (Last 365 Days)
    monte_carlo = {}
    if HAS_SIMULATOR:
        try:
            # Fetch 365 days of data for better vol estimation
            sim_res = requests.get(BINANCE_KLINE_URL, params={"symbol": bin_symbol, "interval": "1d", "limit": 365}, timeout=10)
            if sim_res.status_code == 200:
                k_data = sim_res.json()
                closes = [float(k[4]) for k in k_data]
                returns = pd.Series(closes).pct_change().dropna()
                if len(returns) < 5:
                    vol = 0.5 # Fallback 50% vol
                    mu = 0.1 # Fallback 10% return
                else:
                    vol = returns.std() * np.sqrt(365) # Daily annualized
                    mu = returns.mean() * 365
                
                current_p = float(quote.get("price", closes[-1]))
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
            "name": quote_data.get("name"), "symbol": quote_data.get("symbol"),
            "price": float(quote.get("price", 0.0)), "market_cap": float(quote.get("market_cap", 0.0)),
            "volume_24h": float(quote.get("volume_24h", 0.0)), "percent_change_24h": float(quote.get("percent_change_24h", 0.0)),
            "rank": quote_data.get("cmc_rank"), "metadata": metadata,
            "ta_report": ta_report, "history": history,
            "news": state["rss_cache"], "rate": float(state["usd_idr_rate"]),
            "monte_carlo": monte_carlo
        }
    }
    set_detail_cache(symbol, result)
    return result

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

    # Search in-memory cache first (avoids CMC API call for 2000 coins)
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

    # Fallback: live CMC fetch if cache is empty
    headers = {"X-CMC_PRO_API_KEY": API_KEY, "Accept": "application/json"}
    try:
        res = requests.get(CMC_LISTINGS_URL, headers=headers, params={"limit": 500, "convert": "USD"}, timeout=10)
        data = res.json().get("data", [])
        results = []
        for coin in data:
            if query in coin['name'].lower() or query in coin['symbol'].lower():
                quote = coin.get("quote", {}).get("USD", {})
                results.append({
                    "symbol": coin.get("symbol"),
                    "name": coin.get("name"),
                    "rank": coin.get("cmc_rank"),
                    "price": float(quote.get("price", 0.0)),
                    "price_idr": float(quote.get("price", 0.0)) * state["usd_idr_rate"],
                    "market_cap": float(quote.get("market_cap", 0.0)),
                    "change_24h": float(quote.get("percent_change_24h", 0.0))
                })
        return {"status": "success", "data": results[:50]}
    except Exception as e:
        print(f"Error Search Crypto: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ai/analyze")
def api_ai_analyze(symbol: str):
    try:
        # Load small history and TA to mock real input
        ta_report = analyzer.analyze(symbol)
        history = []
        try:
            bin_symbol = f"{symbol}USDT"
            h_res = requests.get(BINANCE_KLINE_URL, params={"symbol": bin_symbol, "interval": "1d", "limit": 30}, timeout=5)
            if h_res.status_code == 200:
                for k in h_res.json():
                    history.append({"close": float(k[4]), "volume": float(k[5])})
        except: pass
        
        price = history[-1]['close'] if history else 0
        ai_verdict = crypto_multi_agent.run_all_agents(symbol, price, history, ta_report)
        return {"status": "success", "data": ai_verdict}
    except Exception as e:
        print(f"Error AI Analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/crypto/stats/seasonality/{symbol}")
def get_crypto_seasonality(symbol: str):
    try:
        import yfinance as yf
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

@app.get("/")
async def root():
    """Root handler for avoiding 404 on service heartbeat probes."""
    return {"status": "online", "service": "crypto_data_service"}

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(fetch_top_coins_loop())

if __name__ == "__main__":
    print("=:: MEMULAI SERVICE PYTHON CRYPTO DATA (v9 + Live RSS parsing) ::=")
    uvicorn.run("crypto_service:app", log_level="debug",  port=8085, reload=False)
