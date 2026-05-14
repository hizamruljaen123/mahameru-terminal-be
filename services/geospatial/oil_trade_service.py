import os
import sys
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import mysql.connector
from datetime import datetime
from typing import Optional, List
import httpx
import asyncio

# Add the local GNews library to path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GNEWS_DIR = os.path.join(BASE_DIR, "asset", "library", "GNews")
if GNEWS_DIR not in sys.path:
    sys.path.insert(0, GNEWS_DIR)

try:
    from gnews import GNews
    news_reader = GNews(language='en', country='US', max_results=8)
    print("=:: GNEWS_LOADED_FOR_TRADE_SERVICE ::=")
except ImportError as e:
    print(f"=:: GNEWS_LOAD_ERROR: {e} ::=")
    news_reader = None

# --- Path Injection for shared DB and Utils ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from services.system import db_utils
get_db_connection = db_utils.get_db_connection

# EIA API Key - User provided
EIA_API_KEY = os.getenv("EIA_API_KEY", "")
EIA_API_BASE = os.getenv("EIA_API_BASE", "https://api.eia.gov/v2")

# Async HTTP client timeout
HTTP_TIMEOUT = 30.0

api = FastAPI(debug=True, title="Oil Trade Intelligence (Master EIA Sync)")

api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@api.get("/")
async def read_root():
    return {
        "status": "online",
        "service": "Oil Trade Intelligence (Master EIA Sync)",
        "last_scan": datetime.now().isoformat()
    }

@api.get("/api/trade/countries")
async def get_countries():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM oil_trade_countries ORDER BY origin_name ASC")
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        return {"status": "success", "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api.get("/api/trade/periods")
async def get_periods(freq: str = "monthly"):
    """Fetches list of available periods from EIA."""
    try:
        # Fetch EIA Base URL via .env
        base_url = EIA_API_BASE
        url = f"{base_url}/crude-oil-imports"
        if freq == "weekly":
            url = f"{base_url}/petroleum/move/wkly"

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.get(url, params={"api_key": EIA_API_KEY})
            r.raise_for_status()
            resp = r.json()

            if 'response' in resp:
                return {
                    "status": "success",
                    "start": resp['response'].get('startPeriod'),
                    "end": resp['response'].get('endPeriod')
                }
            return {"status": "error", "message": "NO_PERIOD_INFO"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from utils.geocoder import geocode_place

# Ensure we use the same user agent across the service
GEOCODE_USER_AGENT = "OilTradeIntelligence/1.0"
GEOCODE_LANGUAGE = "en"

def _geocode_sync(place: str):
    """Synchronous geocode_place call for executor."""
    return geocode_place(place, user_agent=GEOCODE_USER_AGENT, language=GEOCODE_LANGUAGE)

@api.get("/api/geocode")
async def geocode(place: str = Query(...)):
    """
    Smarter geocoder using centralized utility.
    Runs geocode_place in threadpool to avoid blocking event loop.
    """
    if not place:
        return {"status": "error", "message": "EMPTY_PLACE"}

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _geocode_sync, place)

    if result:
        return {"status": "success", "source": "nominatim", **result}
    return {"status": "not_found", "place": place}

@api.get("/api/geocode/route")
async def geocode_route(origin: str = Query(...), destination: str = Query(...)):
    """Geocode both endpoints of a trade route in one call, respects Nominatim rate limit."""
    loop = asyncio.get_event_loop()

    o = await loop.run_in_executor(None, _geocode_sync, origin)
    # Only wait if we actually hit Nominatim (not cache)
    if o and o.get("source") == "nominatim":
        await asyncio.sleep(1.1)
    d = await loop.run_in_executor(None, _geocode_sync, destination)

    if not o:
        o = {"status": "not_found", "place": origin}
    if not d:
        d = {"status": "not_found", "place": destination}

    return {"status": "success", "origin": o, "destination": d}

@api.post("/api/trade/sync")
async def sync_trade_data(freq: str = Query("monthly"), period: Optional[str] = Query(None)):
    """
    Overhauled sync using list of countries and date selection.
    Fetches data from EIA v2 for ALL countries.
    Uses bulk executemany for 25x faster inserts.
    """
    if freq == "monthly":
        endpoint = "https://api.eia.gov/v2/crude-oil-imports/data/"
        data_col = "quantity"
    else:
        endpoint = "https://api.eia.gov/v2/petroleum/move/wkly/data/"
        data_col = "value"

    params = {
        "api_key": EIA_API_KEY,
        "frequency": freq,
        "data[0]": data_col,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "offset": 0,
        "length": 5000  # Max length for comprehensive scan
    }

    if period:
        params["start"] = period
        params["end"] = period

    try:
        print(f"=:: EIA_SYNC_TASK: FREQ={freq.upper()} PERIOD={period or 'LATEST'} ::=")
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.get(endpoint, params=params)
            r.raise_for_status()
            resp = r.json()

            if 'response' in resp and 'data' in resp['response']:
                items = resp['response']['data']
                conn = get_db_connection()
                cursor = conn.cursor()

                # Get list of local country codes to match
                cursor.execute("SELECT origin_id, origin_name, iso3 FROM oil_trade_countries")
                local_countries = {row[2]: row for row in cursor.fetchall()}  # Map by ISO3

                # Build bulk arrays
                country_data = []
                trade_data = []
                for item in items:
                    # 1. Prepare country UPSERT data
                    origin_id = item.get('originId')
                    origin_name = item.get('originName')
                    if origin_id and origin_name:
                        from utils.iso_standardizer import EIA_TO_ISO3
                        iso3 = None
                        for key, val in EIA_TO_ISO3.items():
                            if key.lower() in origin_name.lower():
                                iso3 = val
                                break
                        country_data.append((origin_id, origin_name, iso3))

                    # 2. Prepare trade INSERT data
                    if freq == "monthly":
                        trade_data.append((
                            item.get('period'), item.get('originId'), item.get('originName'),
                            item.get('destinationId'), item.get('destinationName'),
                            item.get('gradeId', 'UNKNOWN'), item.get('gradeName', 'UNKNOWN'),
                            item.get('quantity', 0), 'monthly'
                        ))
                    else:
                        trade_data.append((
                            item.get('period'), item.get('areaId', 'GLOBAL'), item.get('areaName', 'Regional Agg'),
                            item.get('paddId', 'US_PADD_ALL'), item.get('paddName', 'National Hub'),
                            'W_OIL', 'Aggregate Weekly', item.get('value', 0), 'weekly'
                        ))

                # Bulk UPSERT countries
                if country_data:
                    cursor.executemany("""
                        INSERT INTO oil_trade_countries (origin_id, origin_name, iso3)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE origin_name = VALUES(origin_name), iso3 = COALESCE(iso3, VALUES(iso3))
                    """, country_data)

                # Bulk INSERT trades
                cursor.executemany("""
                    INSERT INTO oil_trades
                    (period, origin_id, origin_name, destination_id, destination_name, grade_id, grade_name, quantity, frequency)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE quantity = VALUES(quantity)
                """, trade_data)

                conn.commit()
                cursor.close()
                conn.close()

                # Detect latest period from data if not specified
                synced_period = items[0]['period'] if items else period
                print(f"=:: SYNC_SUCCESS: {len(trade_data)}_ITEMS_INTEGRATED (PERIOD={synced_period}) ::=")
                return {"status": "success", "integrated": len(trade_data), "period": synced_period}

            return {"status": "error", "message": "NO_DATA_FROM_EIA"}
    except Exception as e:
        print(f"=:: SYNC_FATAL: {str(e)} ::=")
        return {"status": "error", "message": str(e)}

@api.get("/api/trade/detail")
async def get_trade_detail(
    origin_id: str = Query(...),
    destination_id: Optional[str] = Query(None),
    grade_id: Optional[str] = Query(None),
    period: Optional[str] = Query(None),
):
    """
    Fetch detailed trade data for a specific route from EIA API v2.
    Also includes historical trend for the same route (last 12 months).
    """
    try:
        # 1. Get local DB row for base info
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        q = "SELECT * FROM oil_trades WHERE origin_id = %s"
        prm: list = [origin_id]
        if destination_id:
            q += " AND destination_id = %s"; prm.append(destination_id)
        if grade_id:
            q += " AND grade_id = %s"; prm.append(grade_id)
        if period:
            q += " AND period = %s"; prm.append(period)
        q += " ORDER BY period DESC LIMIT 1"
        cursor.execute(q, tuple(prm))
        base = cursor.fetchone()

        # 2. Fetch historical trend (last 24 months) from EIA for same route
        eia_params = {
            "api_key": EIA_API_KEY,
            "frequency": "monthly",
            "data[0]": "quantity",
            "facets[originId][]": origin_id,
            "sort[0][column]": "period",
            "sort[0][direction]": "desc",
            "length": 24
        }
        if destination_id:
            eia_params["facets[destinationId][]"] = destination_id
        if grade_id:
            eia_params["facets[gradeId][]"] = grade_id

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            eia_r = await client.get(
                f"{EIA_API_BASE}/crude-oil-imports/data/",
                params=eia_params
            )
            eia_data = []
            if eia_r.status_code == 200:
                rjson = eia_r.json()
                if 'response' in rjson and 'data' in rjson['response']:
                    eia_data = rjson['response']['data']

        # 3. Country info from DB
        cursor.execute("SELECT * FROM oil_trade_countries WHERE origin_id = %s", (origin_id,))
        country_info = cursor.fetchone()
        cursor.close()
        conn.close()

        return {
            "status":  "success",
            "source":  "eia_live",
            "base": base,
            "country": country_info,
            "history": eia_data  # list of {period, quantity, originName, destinationName, gradeName,...}
        }
    except Exception as e:
        print(f"=:: DETAIL_ERROR: {str(e)} ::=")
        raise HTTPException(status_code=500, detail=str(e))


@api.get("/api/trade/news")
def get_trade_news(origin: str = Query(...), destination: str = Query(...)):
    """Fetch news related to a specific trade lane (Origin & Destination)."""
    if not news_reader:
        return {"status": "error", "message": "GNEWS_NOT_LOADED"}
    
    query = f"crude oil trade {origin} {destination} energy shipment"
    print(f"=:: TRADE_LANE_NEWS_SEARCH: {query} ::=")
    
    try:
        results = news_reader.get_news(query)
        formatted = []
        for item in results:
            formatted.append({
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "pubDate": item.get("published date", ""),
                "url": item.get("url", ""),
                "publisher": item.get("publisher", {}).get("title", "Unknown") if isinstance(item.get("publisher"), dict) else item.get("publisher", "Unknown")
            })
        return {"status": "success", "data": formatted}
    except Exception as e:
        print(f"=:: TRADE_NEWS_ERROR: {str(e)} ::=")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    print("=:: EIA_TRADE_MASTER_ON_8090 ::=")
    uvicorn.run(api, host="0.0.0.0", log_level="debug", port=8090)
