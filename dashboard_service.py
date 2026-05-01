import os
import time
import requests
import asyncio
import httpx
import yfinance as yf
import xml.etree.ElementTree as ET
import numpy as np
import sqlite3
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import Dict, Any, List

app = FastAPI(debug=True, title="Asetpedia Unified Dashboard Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SERVICE REGISTRY (Only for Complex Logic)
SERVICES = {
    "news": os.getenv('NEWS_SERVICE_URL', 'https://api.asetpedia.online/news'),
    "sentiment": os.getenv('SENTIMENT_SERVICE_URL', 'https://api.asetpedia.online/sentiment'),
    "geo": os.getenv('GEO_DATA_API_URL', 'https://api.asetpedia.online/geo')
}

# GLOBAL MARKET CACHE (Real-time in-memory persistence)
MARKET_DATA_CACHE = {
    "data": {},
    "last_updated": 0,
    "status": "INITIALIZING"
}

from db import get_db_connection

WATCHLIST_CONFIG = {
    "indices": [
      {"symbol": "^JKSE", "name": "IHSG", "country": "Indonesia"},
      {"symbol": "^GSPC", "name": "S&P 500", "country": "USA"}
    ],
    "cryptocurrency": [
      {"symbol": "BTC-USD", "name": "Bitcoin"},
      {"symbol": "ETH-USD", "name": "Ethereum"}
    ],
    "commodities": [
      {"symbol": "GC=F", "name": "Gold"},
      {"symbol": "CL=F", "name": "Crude Oil WTI"}
    ],
    "forex": [
      {"symbol": "EURUSD=X", "name": "EUR/USD"},
      {"symbol": "IDR=X", "name": "USD/IDR"}
    ],
    "blue_chips_global": [
      {"symbol": "NVDA", "name": "NVIDIA Corporation"},
      {"symbol": "AAPL", "name": "Apple Inc."}
    ],
    "blue_chips_indonesia": [
      {"symbol": "BBCA.JK", "name": "Bank Central Asia Tbk."},
      {"symbol": "BBRI.JK", "name": "Bank Rakyat Indonesia Tbk."}
    ]
}

async def fetch_google_trends(client, geo, country_name="Unknown"):
    url = f"https://trends.google.com/trending/rss?geo={geo}&hours=24&cat=b"
    try:
        resp = await client.get(url, timeout=10.0)
        if resp.status_code != 200: return []
        
        root = ET.fromstring(resp.content)
        items = []
        ns = {'ht': 'https://trends.google.com/trending/rss'}
        
        for item in root.findall(".//item"):
            title = item.find("title").text if item.find("title") is not None else "N/A"
            approx_traffic = item.find("ht:approx_traffic", ns).text if item.find("ht:approx_traffic", ns) is not None else "0+"
            items.append({
                "country_code": geo,
                "country_name": country_name,
                "topic": title,
                "traffic": approx_traffic,
                "cat": "BUSINESS"
            })
        return items[:3] # Top 3 per country
    except Exception as e:
        return []

def parse_traffic(traffic_str):
    try:
        # e.g. "200,000+" -> 200000
        clean = traffic_str.replace('+', '').replace(',', '')
        return int(clean)
    except:
        return 0

def clean(val):
    if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
        return 0.0
    return float(val)

async def fetch_service(client, url, default=None):
    """Single-attempt fetch with 10s timeout — allows for complex geo-recap analysis."""
    try:
        resp = await client.get(url, timeout=10.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"[FETCH_SERVICE_ERROR] {url}: {e}")
    return default

async def fetch_ticker_direct(symbol, metadata):
    try:
        # Check cache if data is fresh ( < 90 seconds old )
        current_time = time.time()
        cached = MARKET_DATA_CACHE["data"].get(symbol)
        if cached and (current_time - MARKET_DATA_CACHE["last_updated"] < 90):
            return cached

        # Fallback to direct fetch if cache missing or stale
        loop = asyncio.get_event_loop()
        ticker = yf.Ticker(symbol)
        info = await loop.run_in_executor(None, lambda: ticker.info)
        data = {
            "symbol": symbol,
            "name": metadata.get("name", info.get("shortName", symbol)),
            "price": clean(info.get("regularMarketPrice") or info.get("previousClose") or info.get("currentPrice")),
            "change_pct": clean(info.get("regularMarketChangePercent", 0.0)),
            "country": metadata.get("country"),
            "category": metadata.get("category"),
            "timestamp": current_time
        }
        return data
    except:
        return None

async def market_update_loop():
    """Background task to fetch market data every 60 seconds"""
    print("=:: STARTING BACKGROUND MARKET INTELLIGENCE LOOP ::= ")
    while True:
        try:
            start_sync = time.time()
            all_symbols = []
            for cat, items in WATCHLIST_CONFIG.items():
                for item in items:
                    meta = item.copy()
                    meta["category"] = cat
                    all_symbols.append((item["symbol"], meta))
            
            # Fetch symbols one by one to keep the feed "alive" and updating incrementally
            updated = 0
            for symbol, meta in all_symbols:
                try:
                    res = await fetch_ticker_direct(symbol, meta)
                    if res:
                        MARKET_DATA_CACHE["data"][res["symbol"]] = res
                        updated += 1
                        # Update timestamp so FE knows cache is being refreshed
                        MARKET_DATA_CACHE["last_updated"] = time.time()
                    
                    # Small sleep between each to mimic "streaming" update and avoid rate limits
                    await asyncio.sleep(0.2)
                except Exception as inner_e:
                    print(f"[MARKET_SYNC_ITEM_ERROR] {symbol}: {inner_e}")

            MARKET_DATA_CACHE["status"] = "ACTIVE"
            duration = round(time.time() - start_sync, 2)
            print(f"[MARKET_SYNC] Sequential update of {updated}/{len(all_symbols)} assets finished in {duration}s")
            
        except Exception as e:
            print(f"[MARKET_SYNC_ERROR] {e}")
            MARKET_DATA_CACHE["status"] = f"ERROR: {str(e)}"
            
        await asyncio.sleep(60) # Wait 1 minute as requested

@app.get("/api/dashboard/summary")
async def get_dashboard_summary():
    # Keep compatibility with old endpoint but suggest using split ones
    async with httpx.AsyncClient() as client:
        ms_tasks = {
            "news": fetch_service(client, f"{SERVICES['news']}/api/news/data"),
            "sentiment": fetch_service(client, f"{SERVICES['sentiment']}/api/sentiment/summary-all"),
            "geo": fetch_service(client, f"{SERVICES['geo']}/api/db-recap?days=7")
        }
        
        market_tasks = []
        for cat, items in WATCHLIST_CONFIG.items():
            for item in items:
                meta = item.copy()
                meta["category"] = cat
                market_tasks.append(fetch_ticker_direct(item["symbol"], meta))
        
        results = await asyncio.gather(
            asyncio.gather(*ms_tasks.values()),
            asyncio.gather(*market_tasks)
        )
        
        ms_results = results[0]
        market_results = results[1]
        
        mapped_ms = dict(zip(ms_tasks.keys(), ms_results))
        watchlist = {}
        highlights = {"crypto": [], "forex": [], "commodity": []}
        
        for res in market_results:
            if res:
                cat = res["category"]
                if cat not in watchlist: watchlist[cat] = []
                watchlist[cat].append(res)
                if cat == "cryptocurrency" and len(highlights["crypto"]) < 3: highlights["crypto"].append(res)
                if cat == "forex" and len(highlights["forex"]) < 3: highlights["forex"].append(res)
                if cat == "commodities" and len(highlights["commodity"]) < 3: highlights["commodity"].append(res)

        return {
            "status": "success", 
            "data": {
                "market_sentiment": process_sentiment(mapped_ms.get("sentiment")),
                "top_news": process_news(mapped_ms.get("news")),
                "crypto_highlights": highlights["crypto"],
                "forex_highlights": highlights["forex"],
                "commodity_highlights": highlights["commodity"],
                "geo_trends": process_geo(mapped_ms.get("geo")),
                "watchlist": watchlist,
                "timestamp": time.time()
            }
        }

@app.get("/api/dashboard/intelligence")
async def get_dashboard_intelligence():
    """Fast intelligence endpoint: news, sentiment, geo, Google Trends.
    DB query is offloaded to executor; Google Trends capped at 10 countries
    with 5s timeout each to prevent long-tail blocking.
    """
    loop = asyncio.get_event_loop()

    # Supported countries — capped at 10 for speed
    supported = ['US', 'ID', 'GB', 'JP', 'DE', 'IN', 'BR', 'SG', 'AU', 'FR']

    # Offload blocking DB query to thread pool so it doesn't block the event loop
    def _query_countries():
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            placeholders = ",".join(["%s"] * len(supported))
            cursor.execute(f"SELECT code, name FROM countries WHERE code IN ({placeholders})", tuple(supported))
            rows = cursor.fetchall()
            cursor.close()
            return rows
        except:
            return [{"code": "US", "name": "United States"}, {"code": "ID", "name": "Indonesia"}]
        finally:
            conn.close()

    async with httpx.AsyncClient() as client:
        # Run DB query and all API fetches concurrently
        db_task = loop.run_in_executor(None, _query_countries)

        ms_tasks = {
            "news": fetch_service(client, f"{SERVICES['news']}/api/news/data"),
            "sentiment": fetch_service(client, f"{SERVICES['sentiment']}/api/sentiment/summary-all"),
            "geo": fetch_service(client, f"{SERVICES['geo']}/api/db-recap?days=7")
        }

        # Gather DB + microservices simultaneously
        db_countries, ms_results_list = await asyncio.gather(
            db_task,
            asyncio.gather(*ms_tasks.values())
        )

        # Fetch Google Trends for discovered countries (5s timeout, all at once)
        trend_tasks = [fetch_google_trends(client, c['code'], c['name']) for c in db_countries]
        trend_results = await asyncio.gather(*trend_tasks)

        mapped_ms = dict(zip(ms_tasks.keys(), ms_results_list))
        flat_trends = [item for sublist in trend_results for item in sublist]
        flat_trends.sort(key=lambda x: parse_traffic(x.get("traffic", "0")), reverse=True)

        sentiment_data = process_sentiment(mapped_ms.get("sentiment"))
        geo_data = process_geo(mapped_ms.get("geo"))

        return {
            "status": "success",
            "data": {
                "market_sentiment": sentiment_data,
                "top_news": process_news(mapped_ms.get("news")),
                "geo_trends": geo_data,
                "google_trends": flat_trends,
                "available_countries": db_countries,
                "trending_topics": [
                    {"name": s["category"], "count": int(s["total"]), "score": s["score"], "type": "SENTIMENT"}
                    for s in sentiment_data if s.get("total", 0) > 0
                ]
            }
        }

@app.get("/api/dashboard/google-trends")
async def get_specific_google_trends(geo: str = "US", name: str = "United States"):
    """Fetch trends for a specific geographic node."""
    async with httpx.AsyncClient() as client:
        trends = await fetch_google_trends(client, geo, name)
        return {"status": "success", "data": trends}

@app.get("/api/dashboard/countries")
async def get_dashboard_countries():
    """List all countries in the database for selection."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT code, name FROM countries ORDER BY name ASC")
        db_countries = cursor.fetchall()
        cursor.close()
        return {"status": "success", "data": db_countries}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

@app.get("/api/dashboard/sentiment-heatmap")
async def get_sentiment_heatmap():
    """⚡ Direct-DB sentiment heatmap for today's articles.

    Replaces the old sentiment microservice call that loaded a 6MB payload.
    Queries the `article` table for today's records that already have
    sentiment analysis stored, groups by category, and computes
    positive / neutral / negative percentages entirely in MySQL — <10ms.
    """
    loop = asyncio.get_event_loop()

    def _query():
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            # Fetch and calculate all metrics directly in SQL for max performance
            cursor.execute("""
                SELECT
                    category,
                    COUNT(*) AS total,
                    -- Calculate percentages
                    ROUND(SUM(CASE WHEN LOWER(sentiment) IN ('positive','pos','bullish') THEN 1 ELSE 0 END) / COUNT(*) * 100, 1) AS positive_pct,
                    ROUND(SUM(CASE WHEN LOWER(sentiment) IN ('neutral','neu')            THEN 1 ELSE 0 END) / COUNT(*) * 100, 1) AS neutral_pct,
                    ROUND(SUM(CASE WHEN LOWER(sentiment) IN ('negative','neg','bearish') THEN 1 ELSE 0 END) / COUNT(*) * 100, 1) AS negative_pct,
                    -- Handle score with fallback: use AVG(sentimentScore) or inferred (Pos-Neg)/Total
                    ROUND(
                        COALESCE(
                            AVG(sentimentScore), 
                            SUM(CASE 
                                WHEN LOWER(sentiment) IN ('positive','pos','bullish') THEN 1 
                                WHEN LOWER(sentiment) IN ('negative','neg','bearish') THEN -1 
                                ELSE 0 
                            END) / COUNT(*)
                        ) * 100, 
                    1) AS score
                FROM article
                WHERE
                    sentiment IS NOT NULL
                    AND category IS NOT NULL
                    AND DATE(COALESCE(pubDate, createdAt)) = CURDATE()
                    AND category != 'Indonesia'
                GROUP BY category
                ORDER BY total DESC
            """)
            rows = cursor.fetchall()
            cursor.close()
            return rows
        except Exception as e:
            print(f"[SENTIMENT_HEATMAP_ERROR] {e}")
            return []
        finally:
            conn.close()

    rows = await loop.run_in_executor(None, _query)

    # Final mapping to match FE expected structure
    result = []
    for row in rows:
        result.append({
            "category":     (row["category"] or "Uncategorized").replace("_", " ").title(),
            "total":        row["total"],
            "positive_pct": float(row["positive_pct"] or 0),
            "neutral_pct":  float(row["neutral_pct"] or 0),
            "negative_pct": float(row["negative_pct"] or 0),
            "score":        float(row["score"] or 0),
            "value":        row["total"],
        })

    return {"status": "success", "data": result}

@app.get("/api/dashboard/news-preload")
async def get_news_preload(category: str = None):
    """⚡ FAST news preload from local SQLite cache (hot_news).
    
    Reads directly from be/data/news_cache.db to provide the last 10
    articles instantly for the dashboard stream.
    """
    db_path = os.path.join(os.getcwd(), "data", "news_cache.db")
    if not os.path.exists(db_path):
        # Try one level up if run from subfolder
        db_path = os.path.join(os.getcwd(), "be", "data", "news_cache.db")

    if not os.path.exists(db_path):
        return {"status": "error", "message": f"Cache not found at {db_path}", "data": []}

    loop = asyncio.get_event_loop()
    def _query():
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Get last 10 articles, filtered by category if requested
            if category:
                cursor.execute(
                    "SELECT data FROM hot_news WHERE category = ? ORDER BY timestamp DESC LIMIT 10", 
                    (category.upper(),)
                )
            else:
                cursor.execute("SELECT data FROM hot_news ORDER BY timestamp DESC LIMIT 10")
                
            rows = cursor.fetchall()
            conn.close()
            
            items = []
            for row in rows:
                try:
                    item = json.loads(row[0])
                    # Ensure minimal consistency
                    if isinstance(item, dict):
                        items.append(item)
                except:
                    continue
            return items
        except Exception as e:
            print(f"[NEWS_PRELOAD_ERROR] {e}")
            return []

    articles = await loop.run_in_executor(None, _query)
    return {"status": "success", "data": articles}

@app.get("/api/dashboard/google-news")
async def get_google_news(q: str):
    """Drill down into specific news for a trending topic."""
    import urllib.parse
    encoded_q = urllib.parse.quote(q)
    url = f"https://news.google.com/rss/search?q={encoded_q}&hl=en-US&gl=US&ceid=US:en"
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, timeout=10.0)
            if resp.status_code != 200: return {"status": "error", "data": []}
            
            root = ET.fromstring(resp.content)
            items = []
            for item in root.findall(".//item"):
                items.append({
                    "title": item.find("title").text if item.find("title") is not None else "",
                    "link": item.find("link").text if item.find("link") is not None else "",
                    "pubDate": item.find("pubDate").text if item.find("pubDate") is not None else "",
                    "source": item.find("source").text if item.find("source") is not None else "Google News"
                })
            return {"status": "success", "data": items[:15]}
        except Exception as e:
            return {"status": "error", "message": str(e), "data": []}

@app.get("/api/dashboard/markets")
async def get_dashboard_markets():
    """⚡ INSTANT market data endpoint — reads directly from the background cache.

    The `market_update_loop()` keeps MARKET_DATA_CACHE warm every 60s.
    This endpoint NEVER triggers live yfinance calls; it just reshapes
    cached data into the expected response structure in <5ms.

    If the cache is cold (server just started), it returns whatever data
    is already available plus a 'cache_status' hint so the FE can retry.
    """
    cached = MARKET_DATA_CACHE["data"]
    cache_age = time.time() - MARKET_DATA_CACHE["last_updated"] if MARKET_DATA_CACHE["last_updated"] else None

    watchlist = {}
    highlights = {"crypto": [], "forex": [], "commodity": []}

    # Reshape from flat cache dict → categorised structure
    for cat, items in WATCHLIST_CONFIG.items():
        for item in items:
            symbol = item["symbol"]
            res = cached.get(symbol)
            if res:
                res = {**res, "category": cat}  # ensure category is set
                if cat not in watchlist:
                    watchlist[cat] = []
                watchlist[cat].append(res)
                if cat == "cryptocurrency" and len(highlights["crypto"]) < 4:
                    highlights["crypto"].append(res)
                if cat == "forex" and len(highlights["forex"]) < 4:
                    highlights["forex"].append(res)
                if cat == "commodities" and len(highlights["commodity"]) < 4:
                    highlights["commodity"].append(res)

    return {
        "status": "success",
        "data": {
            "watchlist": watchlist,
            "highlights": highlights,
            "timestamp": time.time(),
            "cache_status": MARKET_DATA_CACHE["status"],
            "cache_age_seconds": round(cache_age, 1) if cache_age else None
        }
    }






@app.get("/api/economy/sectors")
async def get_sector_performance():
    sectors = {
        "Technology": "XLK",
        "Financials": "XLF",
        "Energy": "XLE",
        "Healthcare": "XLV",
        "Consumer_Disc": "XLY",
        "Industrials": "XLI",
        "Utilities": "XLU",
        "Materials": "XLB",
        "Real_Estate": "XLRE",
        "Communication": "XLC"
    }
    
    tasks = []
    for name, symbol in sectors.items():
        tasks.append(fetch_ticker_direct(symbol, {"name": name}))
    
    results = await asyncio.gather(*tasks)
    return {"status": "success", "data": [r for r in results if r]}

@app.get("/api/economy/country-proxies/{code}")
async def get_country_proxies(code: str):
    # Mapping for common countries
    mapping = {
        "USA": {"index": "^GSPC", "currency": "DX-Y.NYB", "yield": "^TNX"},
        "CHN": {"index": "000001.SS", "currency": "CNY=X", "yield": "3119.HK"}, 
        "RUS": {"index": "IMOEX.ME", "currency": "RUB=X", "yield": None},
        "IDN": {"index": "^JKSE", "currency": "IDR=X", "yield": "EBND"},
        "JPN": {"index": "^N225", "currency": "JPY=X", "yield": "1566.T"},
        "DEU": {"index": "^GDAXI", "currency": "EURUSD=X", "yield": "EXX1.DE"},
        "GBR": {"index": "^FTSE", "currency": "GBPUSD=X", "yield": "IGLT.L"}
    }
    
    config = mapping.get(code.upper())
    if not config:
        return {"status": "error", "message": "Country code not supported"}
    
    tasks = []
    if config["index"]: tasks.append(fetch_ticker_direct(config["index"], {"name": "MARKET_INDEX", "type": "index"}))
    if config["currency"]: tasks.append(fetch_ticker_direct(config["currency"], {"name": "CURRENCY_STRENGTH", "type": "fx"}))
    if config.get("yield"): tasks.append(fetch_ticker_direct(config["yield"], {"name": "BOND_PROXY", "type": "yield"}))
    
    results = await asyncio.gather(*tasks)
    return {"status": "success", "data": [r for r in results if r]}

@app.get("/api/economy/country-news/{code}/{name}")
async def get_country_news_enhanced(code: str, name: str):
    async with httpx.AsyncClient() as client:
        # We perform 4 separate searches for comprehensive intel
        topics = ["economy", "politics", "military", "investment"]
        tasks = []
        for t in topics:
            query = f"{name} {t}"
            tasks.append(client.get(f"{os.getenv('NEWS_SERVICE_URL', 'https://api.asetpedia.online/news')}/api/news/search?q={query}", timeout=10.0))
        
        responses = await asyncio.gather(*tasks)
        
        all_results = []
        seen_urls = set()
        
        for resp in responses:
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                for r in results:
                    if r["url"] not in seen_urls:
                        all_results.append(r)
                        seen_urls.add(r["url"])
        
        # Sort by timestamp descending
        all_results.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        return {"status": "success", "data": all_results[:60]}

@app.get("/api/economy/country-profile/{code}/{name}")
async def get_country_profile(code: str, name: str):
    async with httpx.AsyncClient() as client:
        # World Bank Indicators (GDP, Inflation, Population)
        indicators = {
            "gdp": "NY.GDP.MKTP.CD",
            "inflation": "FP.CPI.TOTL.ZG",
            "population": "SP.POP.TOTL",
            "gdp_per_capita": "NY.GDP.PCAP.CD"
        }
        wb_tasks = {}
        for key, ind in indicators.items():
            wb_tasks[key] = client.get(f"http://api.worldbank.org/v2/country/{code}/indicator/{ind}?format=json&per_page=1", timeout=10.0)
        
        # Gather all
        responses = await asyncio.gather(*wb_tasks.values())
        
        profile = {
            "stats": {}
        }
            
        for i, (key, _) in enumerate(wb_tasks.items()):
            resp = responses[i]
            if resp.status_code == 200:
                data = resp.json()
                if len(data) > 1 and data[1]:
                    val = data[1][0].get("value")
                    profile["stats"][key] = val
                    
        return {"status": "success", "data": profile}

def process_sentiment(data):
    if not data or data.get("status") != "success": return []
    items = data.get("data", [])
    items.sort(key=lambda x: abs(x.get("score", 0)), reverse=True)
    return items[:6]

def process_news(data):
    if not data or not data.get("news"): return []
    all_news = []
    for cat, articles in data.get("news", {}).items():
        for art in articles:
            art["category"] = cat
            all_news.append(art)
    all_news.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return all_news[:10]

def process_geo(data):
    if not data or data.get("status") != "success": return []
    # Return directly if format is already what we expect (from db-recap)
    items = data.get("data", [])
    if not items: return []
    
    # Sort and take top 8
    items.sort(key=lambda x: x.get("count", 0), reverse=True)
    return items[:8]

@app.get("/")
def root():
    return {"status": "online", "service": "unified_dashboard_aggregator"}

@app.on_event("startup")
async def startup_event():
    # Start the background market update loop
    asyncio.create_task(market_update_loop())

if __name__ == "__main__":
    print("=:: LAUNCHING ASETPEDIA UNIFIED DASHBOARD AGGREGATOR (Port 8000) ::= ")
    uvicorn.run(app, host="0.0.0.0", port=8000)
