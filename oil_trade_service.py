import os
import requests
import sys
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import mysql.connector
from datetime import datetime
from typing import Optional, List

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

# Database configuration
from db_utils import get_db_connection

# EIA API Key - User provided
EIA_API_KEY = os.getenv("EIA_API_KEY", "") 

api = FastAPI(debug=True, title="Oil Trade Intelligence (Master EIA Sync)")

api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection is imported from db_utils

@api.get("/")
def read_root():
    return {
        "status": "online",
        "service": "Oil Trade Master Sync v2",
        "last_scan": datetime.now().isoformat()
    }

@api.get("/api/trade/countries")
def get_countries():
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
def get_periods(freq: str = "monthly"):
    """Fetches list of available periods from EIA."""
    try:
        # Fetch EIA Base URL via .env
        base_url = os.getenv("EIA_API_BASE", "https://api.eia.gov/v2")
        url = f"{base_url}/crude-oil-imports"
        if freq == "weekly":
            url = f"{base_url}/petroleum/move/wkly"
        
        r = requests.get(url, params={"api_key": EIA_API_KEY})
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

@api.get("/api/geocode")
def geocode(place: str = Query(...)):
    """
    Smarter geocoder using centralized utility.
    """
    if not place:
        return {"status": "error", "message": "EMPTY_PLACE"}
        
    result = geocode_place(place, user_agent="OilTradeIntelligence/1.0", language="en")
    
    if result:
        return {"status": "success", "source": "nominatim", **result}
        
    return {"status": "not_found", "place": place}

@api.get("/api/geocode/route")
def geocode_route(origin: str = Query(...), destination: str = Query(...)):
    """Geocode both endpoints of a trade route in one call, respects Nominatim rate limit."""
    import time
    o = geocode(origin)
    # Only wait if we actually hit Nominatim (not cache)
    if o.get("source") == "nominatim":
        time.sleep(1.1)
    d = geocode(destination)
    return {"status": "success", "origin": o, "destination": d}

@api.get("/api/trade/analytics")
def get_trade_analytics():
    """Aggregate analytics for the global report view."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Volume Trend (by Period)
        cursor.execute("""
            SELECT period, SUM(quantity) as total_volume 
            FROM oil_trades 
            GROUP BY period 
            ORDER BY period ASC
        """)
        trend = cursor.fetchall()
        
        # 2. Top Exporters (Origins)
        cursor.execute("""
            SELECT origin_name as name, SUM(quantity) as volume 
            FROM oil_trades 
            GROUP BY origin_name 
            ORDER BY volume DESC 
            LIMIT 10
        """)
        top_exporters = cursor.fetchall()

        # 3. Grade Distribution
        cursor.execute("""
            SELECT grade_name as name, SUM(quantity) as volume 
            FROM oil_trades 
            GROUP BY grade_name 
            ORDER BY volume DESC
        """)
        grades = cursor.fetchall()

        # 4. Total Stats Summary
        cursor.execute("SELECT SUM(quantity) as total, COUNT(DISTINCT origin_id) as countries FROM oil_trades")
        summary = cursor.fetchone()

        cursor.close(); conn.close()
        return {
            "status": "success",
            "data": {
                "trend": trend,
                "exporters": top_exporters,
                "grades": grades,
                "summary": summary
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api.get("/api/trade/data")
def get_trade_data(
    origin: Optional[str] = Query(None),
    period: Optional[str] = Query(None),
    frequency: str = Query("monthly"),
    limit: int = Query(50),
    offset: int = Query(0)
):
    """Smart Master Endpoint: Reads from DB, falls back to EIA API if empty."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 0. Get Total Count
        count_query = "SELECT COUNT(*) as total FROM oil_trades WHERE frequency = %s"
        count_params = [frequency]
        if origin:
            count_query += " AND origin_id = %s"; count_params.append(origin)
        if period:
            count_query += " AND period = %s"; count_params.append(period)
        
        cursor.execute(count_query, tuple(count_params))
        total_rec = cursor.fetchone()['total']

        # 1. Try DB first
        query = "SELECT * FROM oil_trades WHERE frequency = %s"
        params = [frequency]
        if origin:
            query += " AND origin_id = %s"; params.append(origin)
        if period:
            query += " AND period = %s"; params.append(period)
        query += " ORDER BY period DESC, quantity DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        cursor.execute(query, tuple(params))
        results = cursor.fetchall()
        
        # 2. Fallback to API if DB is empty for this specific request
        if not results and offset == 0:
            print(f"=:: DB_CACHE_MISS for period={period} origin={origin} ::=")
            sync_res = sync_trade_data(freq=frequency, period=period)
            
            # Re-query after sync
            cursor.execute(query, tuple(params))
            results = cursor.fetchall()
            
            # Update total after sync
            cursor.execute(count_query, tuple(count_params))
            total_rec = cursor.fetchone()['total']
            
            source = "eia_live_fallback"
        else:
            source = "db_cache"
            
        cursor.close(); conn.close()
        return {
            "status": "success", 
            "source": source, 
            "total": total_rec,
            "count": len(results),
            "data": results
        }
    except Exception as e:
        print(f"=:: SMART_TRADE_ERROR: {str(e)} ::=")
        raise HTTPException(status_code=500, detail=str(e))


@api.get("/api/trade/live")
def get_trade_live(
    origin: Optional[str] = Query(None),
    period: Optional[str] = Query(None),
    frequency: str = Query("monthly"),
    limit: int = Query(5000)
):
    """
    Live endpoint — fetches directly from EIA API v2, no local DB involved.
    """
    if frequency == "monthly":
        endpoint = "https://api.eia.gov/v2/crude-oil-imports/data/"
        data_col  = "quantity"
    else:
        endpoint = "https://api.eia.gov/v2/petroleum/move/wkly/data/"
        data_col  = "value"

    params: dict = {
        "api_key": EIA_API_KEY,
        "frequency": frequency,
        "data[0]": data_col,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "offset": 0,
        "length": min(limit, 5000)
    }
    if origin:
        params["facets[originId][]"] = origin
    if period:
        params["start"] = period
        params["end"]   = period

    try:
        print(f"=:: EIA_LIVE_QUERY: freq={frequency} origin={origin} period={period} ::=")
        r = requests.get(endpoint, params=params, timeout=30)
        r.raise_for_status()
        resp = r.json()

        if 'response' in resp and 'data' in resp['response']:
            raw = resp['response']['data']
            # Normalize fields to a consistent schema
            items = []
            for item in raw:
                if frequency == "monthly":
                    items.append({
                        "period":           item.get("period"),
                        "origin_id":        item.get("originId"),
                        "origin_name":      item.get("originName"),
                        "destination_id":   item.get("destinationId"),
                        "destination_name": item.get("destinationName"),
                        "grade_id":         item.get("gradeId"),
                        "grade_name":       item.get("gradeName"),
                        "quantity":         item.get("quantity", 0),
                        "frequency":        "monthly",
                    })
                else:
                    items.append({
                        "period":           item.get("period"),
                        "origin_id":        item.get("areaId", "AGG"),
                        "origin_name":      item.get("areaName", "Aggregate"),
                        "destination_id":   item.get("paddId", "US"),
                        "destination_name": item.get("paddName", "United States"),
                        "grade_id":         "W_OIL",
                        "grade_name":       "Aggregate Weekly",
                        "quantity":         item.get("value", 0),
                        "frequency":        "weekly",
                    })
            print(f"=:: EIA_LIVE_RETURNED: {len(items)} RECORDS ::=")
            return {
                "status": "success",
                "source": "eia_live",
                "count": len(items),
                "data": items
            }

        return {"status": "error", "message": "EIA_EMPTY_RESPONSE", "raw": resp}
    except Exception as e:
        print(f"=:: EIA_LIVE_ERROR: {str(e)} ::=")
        raise HTTPException(status_code=500, detail=str(e))


@api.get("/api/trade/live-detail")
def get_trade_live_detail(
    origin_id:      str            = Query(...),
    destination_id: Optional[str]  = Query(None),
    grade_id:       Optional[str]  = Query(None),
    period:         Optional[str]  = Query(None),
):
    """
    Live detail endpoint — fetches history directly from EIA API v2.
    Also enriches with country reference from DB.
    """
    # Build history query (last 36 months, filtered by route)
    eia_params: dict = {
        "api_key": EIA_API_KEY,
        "frequency": "monthly",
        "data[0]": "quantity",
        "facets[originId][]": origin_id,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 36
    }
    if destination_id:
        eia_params["facets[destinationId][]"] = destination_id
    if grade_id:
        eia_params["facets[gradeId][]"] = grade_id
    if period:
        eia_params["start"] = period
        eia_params["end"]   = period

    try:
        print(f"=:: EIA_LIVE_DETAIL: {origin_id} -> {destination_id} grade={grade_id} period={period} ::=")
        base_url = os.getenv("EIA_API_BASE", "https://api.eia.gov/v2")
        r = requests.get(
            f"{base_url}/crude-oil-imports/data/",
            params=eia_params, timeout=20
        )
        r.raise_for_status()
        resp = r.json()

        history = []
        if 'response' in resp and 'data' in resp['response']:
            history = resp['response']['data']

        # Country ref from DB (read-only, light query)
        country_info = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT * FROM oil_trade_countries WHERE origin_id = %s OR iso3 = %s",
                (origin_id, origin_id)
            )
            country_info = cursor.fetchone()
            cursor.close(); conn.close()
        except Exception:
            pass  # Country info is optional enrichment

        return {
            "status":  "success",
            "source":  "eia_live",
            "history": history,
            "country": country_info
        }
    except Exception as e:
        print(f"=:: EIA_LIVE_DETAIL_ERROR: {str(e)} ::=")
        raise HTTPException(status_code=500, detail=str(e))



@api.post("/api/trade/sync")
def sync_trade_data(freq: str = Query("monthly"), period: Optional[str] = Query(None)):
    """
    Overhauled sync using list of countries and date selection.
    Fetches data from EIA v2 for ALL countries.
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
        "length": 5000 # Max length for comprehensive scan
    }
    
    if period:
        params["start"] = period
        params["end"] = period

    try:
        print(f"=:: EIA_SYNC_TASK: FREQ={freq.upper()} PERIOD={period or 'LATEST'} ::=")
        r = requests.get(endpoint, params=params, timeout=60)
        r.raise_for_status()
        resp = r.json()
        
        if 'response' in resp and 'data' in resp['response']:
            items = resp['response']['data']
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Get list of local country codes to match
            cursor.execute("SELECT origin_id, origin_name, iso3 FROM oil_trade_countries")
            local_countries = {row[2]: row for row in cursor.fetchall()} # Map by ISO3
            
            count = 0
            for item in items:
                # 1. UPSERT into oil_trade_countries first
                origin_id = item.get('originId')
                origin_name = item.get('originName')
                if origin_id and origin_name:
                    # Auto-assign ISO3 if possible
                    from utils.iso_standardizer import EIA_TO_ISO3
                    iso3 = None
                    for key, val in EIA_TO_ISO3.items():
                        if key.lower() in origin_name.lower():
                            iso3 = val
                            break
                            
                    cursor.execute("""
                        INSERT INTO oil_trade_countries (origin_id, origin_name, iso3)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE origin_name = VALUES(origin_name), iso3 = COALESCE(iso3, VALUES(iso3))
                    """, (origin_id, origin_name, iso3))

                # 2. INSERT into oil_trades
                sql = """
                    INSERT INTO oil_trades 
                    (period, origin_id, origin_name, destination_id, destination_name, grade_id, grade_name, quantity, frequency)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE quantity = VALUES(quantity)
                """
                if freq == "monthly":
                    # For monthly crude-oil-imports, originId is usually CTY_XX
                    # We store it as is, but we try to match originName for cleaner UI
                    val = (
                        item.get('period'), item.get('originId'), item.get('originName'),
                        item.get('destinationId'), item.get('destinationName'),
                        item.get('gradeId', 'UNKNOWN'), item.get('gradeName', 'UNKNOWN'),
                        item.get('quantity', 0), 'monthly'
                    )
                else:
                    # Weekly aggregated data
                    val = (
                        item.get('period'), item.get('areaId', 'GLOBAL'), item.get('areaName', 'Regional Agg'),
                        item.get('paddId', 'US_PADD_ALL'), item.get('paddName', 'National Hub'),
                        'W_OIL', 'Aggregate Weekly', item.get('value', 0), 'weekly'
                    )
                cursor.execute(sql, val)
                count += 1
            
            conn.commit()
            cursor.close()
            conn.close()
            # Detect latest period from data if not specified
            synced_period = items[0]['period'] if items else period
            print(f"=:: SYNC_SUCCESS: {count}_ITEMS_INTEGRATED (PERIOD={synced_period}) ::=")
            return {"status": "success", "integrated": count, "period": synced_period}
            
        return {"status": "error", "message": "NO_DATA_FROM_EIA"}
    except Exception as e:
         print(f"=:: SYNC_FATAL: {str(e)} ::=")
         return {"status": "error", "message": str(e)}

@api.get("/api/trade/detail")
def get_trade_detail(
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

        eia_r = requests.get(
            "https://api.eia.gov/v2/crude-oil-imports/data/",
            params=eia_params, timeout=20
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
            "status": "success",
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
    uvicorn.run(api, log_level="debug",  port=8090)
