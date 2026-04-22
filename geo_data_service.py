import uvicorn
import requests
import xml.etree.ElementTree as ET
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import json
import time
import sqlite3
import os
import pytz

app = FastAPI(debug=True, title="Geo Data Proxy Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# Simple in-memory cache with TTL
# ============================================================
from utils.geocoder import geocode_place

# ============================================================
# Database Configuration
# ============================================================
from db_utils import get_db_connection

# Simple in-memory cache for BMKG API responses (non-geo)
_cache = {}

def cached_get(url: str, ttl_seconds: int = 300, timeout: int = 30):
    """Fetch URL with simple TTL cache."""
    now = time.time()
    if url in _cache:
        data, ts = _cache[url]
        if now - ts < ttl_seconds:
            return data
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        _cache[url] = (data, now)
        return data
    except Exception as e:
        # Return cached data even if expired, if available
        if url in _cache:
            return _cache[url][0]
        raise e


# ============================================================
# WEATHER ENDPOINTS (Open-Meteo)
# ============================================================


# ============================================================
# WEATHER ENDPOINTS (Open-Meteo)
# ============================================================

@app.get("/api/weather/forecast")
async def weather_forecast(
    lat: float = Query(...),
    lng: float = Query(...),
    tz: str = Query("UTC"),
    past_days: int = Query(0)
):
    """Fetch weather forecast from Open-Meteo API."""
    params = (
        f"latitude={lat}&longitude={lng}"
        f"&current_weather=true"
        f"&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m,cloud_cover,"
        f"surface_pressure,visibility,precipitation_probability,dewpoint_2m,apparent_temperature,weathercode"
        f"&daily=weathercode,temperature_2m_max,temperature_2m_min,sunrise,sunset,uv_index_max"
        f"&timezone={tz}"
    )
    if past_days > 0:
        params += f"&past_days={past_days}"
    
    # Fetch from Open-Meteo Base URL via .env
    base_url = os.getenv("OPEN_METEO_BASE", "https://api.open-meteo.com/v1")
    url = f"{base_url}/forecast?{params}"
    # Weather: cache for 10 minutes
    try:
        data = cached_get(url, ttl_seconds=600)
        return data
    except Exception as e:
        print(f"[WEATHER_TIMEOUT] {lat},{lng}: {e}")
        return {
            "latitude": lat,
            "longitude": lng,
            "current_weather": {
                "temperature": 0, 
                "windspeed": 0, 
                "winddirection": 0, 
                "weathercode": 0, 
                "time": datetime.now().isoformat()
            },
            "hourly": {"time": [], "temperature_2m": []},
            "daily": {"time": [], "weathercode": []},
            "status": "error",
            "message": "Weather API timeout - fallback data used"
        }


@app.get("/api/weather/search")
async def weather_search_city(
    name: str = Query(..., min_length=2),
    count: int = Query(8)
):
    """Search for cities via Open-Meteo Geocoding API."""
    base_url = os.getenv("OPEN_METEO_GEO_BASE", "https://geocoding-api.open-meteo.com/v1")
    url = f"{base_url}/search?name={requests.utils.quote(name)}&count={count}&language=en&format=json"
    data = cached_get(url, ttl_seconds=3600)  # Cache city searches for 1 hour
    return data


# ============================================================
# COUNTRY DETAILS (RestCountries)
# ============================================================

@app.get("/api/country/{code}")
async def country_details(code: str):
    """Fetch country details from RestCountries API."""
    url = f"https://restcountries.com/v3.1/alpha/{code}"
    data = cached_get(url, ttl_seconds=86400)  # 24 hours
    if isinstance(data, list) and len(data) > 0:
        return data[0]
    return data

@app.get("/api/geo/countries/lite")
async def get_countries_lite():
    """Retrieve full country registry for orbital proximity lookups."""
    from db_utils import execute_query
    try:
        # Fetch minimal geographical data for all countries
        query = "SELECT id, code, name, lat, lon FROM countries ORDER BY name"
        rows = execute_query(query)
        return {"status": "success", "data": rows}
    except Exception as e:
        print(f"[GEO_COUNTRIES_LITE_ERROR] {e}")
        return {"status": "error", "message": str(e), "data": []}

@app.get("/api/geo/countries/in-range")
async def get_countries_in_range(
    lat: float = Query(...),
    lon: float = Query(...),
    radius: float = Query(2.0) # Degrees offset (~220km)
):
    """Detect territorial sovereignty within high-precision spatial bounding box."""
    from db_utils import execute_query
    try:
        # Optimized B-Tree range scan for fast spatial intersections
        query = """
            SELECT id, code, name, lat, lon 
            FROM countries 
            WHERE (lat BETWEEN %s - %s AND %s + %s)
              AND (lon BETWEEN %s - %s AND %s + %s)
            LIMIT 5
        """
        params = (lat, radius, lat, radius, lon, radius, lon, radius)
        rows = execute_query(query, params)
        return {"status": "success", "data": rows}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============================================================
# EXCHANGE RATES (Frankfurter)
# ============================================================

@app.get("/api/exchange-rates")
async def exchange_rates(base: str = Query("USD")):
    """Fetch latest exchange rates from Frankfurter API."""
    url = f"https://api.frankfurter.app/latest?from={base}"
    data = cached_get(url, ttl_seconds=3600)  # 1 hour
    return data


# ============================================================
# WORLD BANK MACRO INDICATORS
# ============================================================

WORLD_BANK_INDICATORS = {
    "gdpGrowth": "NY.GDP.MKTP.KD.ZG",
    "inflation": "FP.CPI.TOTL.ZG",
    "unemployment": "SL.UEM.TOTL.ZS",
    "stability": "PV.EST",
    "internet": "IT.NET.USER.ZS",
    "mobile": "IT.CEL.SETS.P2"
}

@app.get("/api/worldbank/{country_code}")
async def worldbank_indicators(country_code: str):
    """Fetch macro-economic indicators from World Bank API."""
    results = {}
    
    for key, indicator_id in WORLD_BANK_INDICATORS.items():
        url = f"https://api.worldbank.org/v2/country/{country_code}/indicator/{indicator_id}?format=json&date=2021:2024&per_page=1"
        try:
            data = cached_get(url, ttl_seconds=86400)  # 24 hours
            if data and isinstance(data, list) and len(data) > 1 and data[1]:
                # Find the most recent non-null value
                latest = next((d for d in data[1] if d.get("value") is not None), None)
                results[key] = latest["value"] if latest else None
            else:
                results[key] = None
        except Exception:
            results[key] = None
    
    return results


# ============================================================
# PUBLIC HOLIDAYS (Nager.At)
# ============================================================

@app.get("/api/holidays/{country_code}")
async def public_holidays(
    country_code: str,
    upcoming_only: bool = Query(True),
    limit: int = Query(3)
):
    """Fetch public holidays from Nager.At API."""
    year = datetime.now().year
    url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/{country_code}"
    try:
        data = cached_get(url, ttl_seconds=86400)  # 24 hours
        
        if upcoming_only:
            today = datetime.now().date()
            data = [h for h in data if datetime.strptime(h["date"], "%Y-%m-%d").date() >= today]
        
        return data[:limit]
    except Exception:
        return []


# ============================================================
# BMKG EARTHQUAKE DATA (Indonesia)
# ============================================================

@app.get("/api/earthquakes")
async def get_earthquakes():
    """Fetch latest earthquake data from BMKG (Indonesia)."""
    # Using gempaterkini.xml for a list of recent quakes (top 15)
    url = "https://data.bmkg.go.id/DataMKG/TEWS/gempaterkini.xml"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        
        # Parse XML
        root = ET.fromstring(resp.content)
        quakes = []
        
        for gempa in root.findall(".//gempa"):
            coords_elem = gempa.find("point/coordinates")
            if coords_elem is not None and coords_elem.text:
                coords = coords_elem.text.split(",")
                
                def get_text(tag):
                    elem = gempa.find(tag)
                    return elem.text if elem is not None else ""

                quakes.append({
                    "tanggal": get_text("Tanggal"),
                    "jam": get_text("Jam"),
                    "datetime": get_text("DateTime"),
                    "lat": float(coords[0]),
                    "lng": float(coords[1]),
                    "magnitude": get_text("Magnitude"),
                    "kedalaman": get_text("Kedalaman"),
                    "wilayah": get_text("Wilayah"),
                    "potensi": get_text("Potensi"),
                    "dirasakan": get_text("Dirasakan")
                })
        return quakes
    except Exception as e:
        print(f"BMKG Error: {e}")
        return []

@app.get("/api/earthquakes/latest")
async def get_latest_earthquake():
    """Fetch the single most recent major earthquake from BMKG autogempa.xml."""
    url = "https://data.bmkg.go.id/DataMKG/TEWS/autogempa.xml"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        
        root = ET.fromstring(resp.content)
        gempa = root.find(".//gempa")
        if gempa is not None:
            def get_text(tag):
                elem = gempa.find(tag)
                return elem.text if elem is not None else ""

            coords_elem = gempa.find("point/coordinates")
            if coords_elem is not None and coords_elem.text:
                coords = coords_elem.text.split(",")
                return {
                    "tanggal": get_text("Tanggal"),
                    "jam": get_text("Jam"),
                    "datetime": get_text("DateTime"),
                    "lat": float(coords[0]),
                    "lng": float(coords[1]),
                    "magnitude": get_text("Magnitude"),
                    "kedalaman": get_text("Kedalaman"),
                    "wilayah": get_text("Wilayah"),
                    "potensi": get_text("Potensi"),
                    "dirasakan": get_text("Dirasakan"),
                    "shakemap": get_text("Shakemap")
                }
        return None
    except Exception as e:
        print(f"BMKG Latest Error: {e}")
        return None

# ============================================================
# COMBINED COUNTRY INTEL (all-in-one endpoint)
# ============================================================

@app.get("/api/country-intel/{code}")
async def country_intel(code: str):
    """
    Combined endpoint: country details + exchange rates + macro indicators + holidays.
    Reduces frontend round-trips from 4+ calls to 1.
    """
    import asyncio
    
    results = {}
    
    # Country details
    try:
        country_url = f"https://restcountries.com/v3.1/alpha/{code}"
        country_data = cached_get(country_url, ttl_seconds=86400)
        results["country"] = country_data[0] if isinstance(country_data, list) and len(country_data) > 0 else None
    except Exception:
        results["country"] = None
    
    # Extract currency code for FX
    currency_code = None
    if results["country"] and "currencies" in results["country"]:
        currency_code = list(results["country"]["currencies"].keys())[0] if results["country"]["currencies"] else None
    
    # Exchange rates
    try:
        fx_url = "https://api.frankfurter.app/latest?from=USD"
        results["exchangeRates"] = cached_get(fx_url, ttl_seconds=3600)
    except Exception:
        results["exchangeRates"] = None
    
    # World Bank indicators
    try:
        wb_results = {}
        for key, indicator_id in WORLD_BANK_INDICATORS.items():
            wb_url = f"https://api.worldbank.org/v2/country/{code}/indicator/{indicator_id}?format=json&date=2021:2024&per_page=1"
            try:
                wb_data = cached_get(wb_url, ttl_seconds=86400)
                if wb_data and isinstance(wb_data, list) and len(wb_data) > 1 and wb_data[1]:
                    latest = next((d for d in wb_data[1] if d.get("value") is not None), None)
                    wb_results[key] = latest["value"] if latest else None
                else:
                    wb_results[key] = None
            except Exception:
                wb_results[key] = None
        results["worldBank"] = wb_results
    except Exception:
        results["worldBank"] = {}
    
    # Holidays
    try:
        year = datetime.now().year
        holidays_url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/{code}"
        holidays_data = cached_get(holidays_url, ttl_seconds=86400)
        today = datetime.now().date()
        results["holidays"] = [
            h for h in holidays_data 
            if datetime.strptime(h["date"], "%Y-%m-%d").date() >= today
        ][:3]
    except Exception:
        results["holidays"] = []
    
    return results


# ============================================================
# ANALYTICS: GEOGRAPHIC TRENDING
# ============================================================

@app.get("/api/geo/trending")
async def geo_trending(category: str = Query(None), limit: int = 1000, today: bool = Query(True)):
    """
    ULTRA-FAST PROTOCOL (GEO):
    Calculates geographic trending directly from the JSON rolling buffer.
    Sorted by pubDate (Latest first).
    """
    try:
        buffer_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_news_buffer.json")
        if not os.path.exists(buffer_path):
            return {"status": "success", "data": {"mentions": [], "totalArticles": 0}}
            
        try:
            with open(buffer_path, 'r', encoding='utf-8') as f:
                all_buffer = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[GEO_BUFFER_CORRUPTION] Error loading JSON: {e}")
            return {"status": "success", "data": {"mentions": [], "totalArticles": 0}}
            
        articles = all_buffer
        
        # 1. Category Filter
        if category:
            articles = [a for a in articles if str(a.get('category', '')).lower() == category.lower()]
        
        # 2. Date Precision (Ensure Latest First)
        articles.sort(key=lambda x: str(x.get('pubDate', '')), reverse=True)
        
        # 3. Dynamic "Recency" Logic
        # If 'today' results in 0 articles, fall back to the last 24-48h or simply the newest buffer items
        if today:
            today_str = datetime.now().strftime('%Y-%m-%d')
            today_articles = [a for a in articles if str(a.get('pubDate', '')).startswith(today_str)]
            
            if not today_articles:
                # FALLBACK: If no articles today, take the most recent 200 from the buffer
                print(f"[GEO_TRENDING] No articles for {today_str}. Using most recent buffer content.")
                articles = articles[:limit]
                today_active = False
            else:
                articles = today_articles[:limit]
                today_active = True
        else:
            articles = articles[:limit]
            today_active = False
        
        # 4. Extract Geographic Mentions
        # Delayed import to avoid circular dependencies
        from utils.country_detector import count_country_mentions
        mentions = count_country_mentions(articles)
        
        return {
            "status": "success",
            "data": {
                "mentions": mentions,
                "topCountries": mentions[:20],
                "totalArticles": len(articles),
                "todayOnly": today,
                "todayActive": today_active,
                "timestamp": datetime.now().isoformat()
            }
        }
    except Exception as e:
        print(f"[GEO_TRENDING_JSON_ERROR] {e}")
        return {"status": "error", "message": str(e)}


# ============================================================
# HEALTH CHECK
# ============================================================

@app.get("/api/geo/db-recap")
async def geo_db_recap(days: int = Query(7)):
    """
    Recaps news_cache.db to find trending countries and their top categories.
    """
    import sqlite3
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "news_cache.db")
    if not os.path.exists(db_path):
        return {"status": "error", "message": "Database not found"}

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Calculate timestamp threshold
        threshold = time.time() - (days * 86400)
        
        cursor.execute("SELECT category, data FROM hot_news WHERE timestamp > ?", (threshold,))
        rows = cursor.fetchall()
        
        from utils.country_detector import detect_countries
        
        country_stats = {} # {code: {count: 0, categories: {cat: count}}}
        
        for category, data_json in rows:
            try:
                data = json.loads(data_json)
                text = f"{data.get('title', '')} {data.get('description', '') or ''}"
                found_countries = detect_countries(text)
                
                cat = category or data.get('category', 'General')
                
                for country in found_countries:
                    code = country["code"]
                    if code not in country_stats:
                        country_stats[code] = {
                            "name": country["name"],
                            "code": code,
                            "lat": country["lat"],
                            "lng": country["lng"],
                            "count": 0,
                            "categories": {}
                        }
                    
                    country_stats[code]["count"] += 1
                    country_stats[code]["categories"][cat] = country_stats[code]["categories"].get(cat, 0) + 1
            except Exception:
                continue
                
        conn.close()
        
        # Finalize stats: find top category
        recap = []
        for code, stats in country_stats.items():
            top_cat = "N/A"
            if stats["categories"]:
                top_cat = max(stats["categories"], key=stats["categories"].get)
            
            recap.append({
                "name": stats["name"],
                "code": stats["code"],
                "lat": stats["lat"],
                "lng": stats["lng"],
                "count": stats["count"],
                "topCategory": top_cat
            })
            
        # Sort by count
        recap.sort(key=lambda x: x["count"], reverse=True)
        
        return {
            "status": "success",
            "data": recap,
            "total_articles": len(rows)
        }
    except Exception as e:
        print(f"[GEO_RECAP_ERROR] {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/geo/archive-trends")
async def geo_archive_trends(date: str = Query(...)):
    """
    Calculates geographic trends for a specific date from MySQL 'article' table.
    """
    from db_utils import execute_query
    from utils.country_detector import detect_countries
    
    try:
        # Fetch articles for the specific date
        query = "SELECT category, title, description FROM article WHERE DATE(pubDate) = %s"
        rows = execute_query(query, (date,))
        
        country_stats = {} 
        
        for row in rows:
            text = f"{row.get('title', '')} {row.get('description', '') or ''}"
            found_countries = detect_countries(text)
            cat = row.get('category', 'General')
            
            for country in found_countries:
                code = country["code"]
                if code not in country_stats:
                    country_stats[code] = {
                        "name": country["name"],
                        "code": code,
                        "lat": country["lat"],
                        "lng": country["lng"],
                        "count": 0,
                        "categories": {}
                    }
                
                country_stats[code]["count"] += 1
                country_stats[code]["categories"][cat] = country_stats[code]["categories"].get(cat, 0) + 1
                
        # Finalize stats
        recap = []
        for code, stats in country_stats.items():
            top_cat = "N/A"
            if stats["categories"]:
                top_cat = max(stats["categories"], key=stats["categories"].get)
            
            recap.append({
                "name": stats["name"],
                "code": stats["code"],
                "lat": stats["lat"],
                "lng": stats["lng"],
                "count": stats["count"],
                "topCategory": top_cat
            })
            
        recap.sort(key=lambda x: x["count"], reverse=True)
        
        return {
            "status": "success",
            "date": date,
            "data": recap,
            "total_articles": len(rows)
        }
    except Exception as e:
        print(f"[GEO_ARCHIVE_ERROR] {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/health")
async def health():
    return {
        "status": "online",
        "service": "geo_data_service",
        "port": 8091,
        "cache_entries": len(_cache),
        "timestamp": datetime.now().isoformat(),
        "endpoints": [
            "/api/weather/forecast",
            "/api/weather/search",
            "/api/country/{code}",
            "/api/exchange-rates",
            "/api/worldbank/{code}",
            "/api/holidays/{code}",
            "/api/gdelt/{code}",
            "/api/country-intel/{code}",
            "/api/geo/trending",
            "/api/geo/db-recap",
            "/api/geo/timezone-map"
        ]
    }


@app.get("/")
async def root():
    """Root handler for avoiding 404 on service heartbeat probes."""
    return {"status": "online", "service": "geo_data_service"}


@app.get("/api/geo/timezone-map")
async def get_timezone_map():
    """
    Retrieve all countries with their current accurate times.
    Uses pytz for precise timezone calculations.
    """
    from db_utils import execute_query
    try:
        # Fetch countries from DB
        query = "SELECT code, name, lat, lon FROM countries"
        rows = execute_query(query)
        
        results = []
        now_utc = datetime.now(pytz.utc)
        
        for row in rows:
            code = row['code']
            if not code: continue
            
            try:
                # Get list of timezones for this country code
                tz_names = pytz.country_timezones.get(code.upper())
                if tz_names:
                    tz_list = []
                    for tz_name in tz_names:
                        tz = pytz.timezone(tz_name)
                        local_time = now_utc.astimezone(tz)
                        tz_list.append({
                            "zone": tz_name,
                            "time": local_time.strftime("%H:%M:%S"),
                            "date": local_time.strftime("%Y-%m-%d"),
                            "offset": local_time.strftime("%z"),
                            "abbr": local_time.strftime("%Z")
                        })
                    
                    results.append({
                        "code": code,
                        "name": row['name'],
                        "lat": float(row['lat']) if row['lat'] else 0,
                        "lon": float(row['lon']) if row['lon'] else 0,
                        "timezones": tz_list
                    })
            except Exception:
                continue
        
        return {"status": "success", "data": results, "timestamp": now_utc.isoformat()}
    except Exception as e:
        print(f"[TIMEZONE_MAP_ERROR] {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    print("=" * 50)
    print("GEO_DATA_SERVICE // PORT 8091")
    print("Proxying: Open-Meteo, RestCountries, Frankfurter,")
    print("          World Bank, Nager.At, GDELT")
    print("=" * 50)
    uvicorn.run(app, log_level="debug",  port=8091)
