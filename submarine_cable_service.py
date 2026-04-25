import uvicorn
import requests
import mysql.connector
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import os
import time
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(debug=True, title="Submarine Cable & ISP Data Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# MySQL Connection Helper
# ============================================================
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST', 'database.asetpedia.online'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'asetpedia')
    )

# ============================================================
# Simple in-memory cache with TTL
# ============================================================
_cache = {}

def cached_get(url: str, ttl_seconds: int = 3600, timeout: int = 30):
    """Fetch URL with simple TTL cache."""
    now = time.time()
    if url in _cache:
        data, ts = _cache[url]
        if now - ts < ttl_seconds:
            return data
    try:
        headers = {"Accept": "application/json"}
        resp = requests.get(url, timeout=timeout, headers=headers)
        resp.raise_for_status()
        
        if "application/json" not in resp.headers.get("Content-Type", "").lower():
             print(f"Non-JSON response from {url}")
             if url in _cache: return _cache[url][0]
             raise ValueError(f"Endpoint {url} did not return JSON")

        data = resp.json()
        _cache[url] = (data, now)
        return data
    except Exception as e:
        if url in _cache:
            return _cache[url][0]
        raise e

# ============================================================
# DATA ENDPOINTS
# ============================================================

BASE_API_URL = os.getenv("SUBMARINE_CABLE_API_BASE", "https://www.submarinecablemap.com/api/v3")

@app.get("/api/submarine-cables/geo")
async def get_submarine_cables_geo():
    """Fetch submarine cable GeoJSON."""
    try:
        data = cached_get(f"{BASE_API_URL}/cable/cable-geo.json", ttl_seconds=3600)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/submarine-cables/list")
async def list_cables(
    q: str = Query(None), 
    region: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1)
):
    """Search and paginate cables from the GeoJSON source."""
    try:
        geo_data = cached_get(f"{BASE_API_URL}/cable/cable-geo.json", ttl_seconds=3600)
        cables = []
        for feature in geo_data.get('features', []):
            props = feature.get('properties', {})
            # ID is usually the 'id' in properties or the feature itself
            # The cable JSON ID is what we need for the detail endpoint
            c_id = props.get('id')
            c_name = props.get('name', 'Unknown')
            
            # Simple filtering
            if q and q.lower() not in c_name.lower():
                continue
            
            # For regions, we use the first letter as a quick-and-dirty region mapping 
            # for this mock logic, or we could use landing point data if we joined it.
            # But let's just stick to name-based or letter-based for now.
            if region and region != "GLOBAL":
                if not c_name.startswith(region):
                    continue
                    
            cables.append(props)
            
        cables = sorted(cables, key=lambda x: x.get('name', ''))
        
        # Pagination
        total = len(cables)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_data = cables[start:end]
        
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "data": paginated_data,
            "total_pages": (total + page_size - 1) // page_size
        }
    except Exception as e:
        print(f"List error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/submarine-cables/grouped")
async def get_grouped_cables():
    """Grouped view for directory (fallback)."""
    # ... existing implementation ...
    try:
        geo_data = cached_get(f"{BASE_API_URL}/cable/cable-geo.json", ttl_seconds=3600)
        import collections
        groups = collections.defaultdict(list)
        for feature in geo_data.get('features', []):
            props = feature.get('properties', {})
            first_char = props.get('name', ' ')[0].upper()
            if not first_char.isalpha(): first_char = '#'
            groups[first_char].append(props)
        result = []
        for char in sorted(groups.keys()):
            result.append({"country": f"REGION_{char}", "cables": sorted(groups[char], key=lambda x: x.get('name', ''))})
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/submarine-cables/detail/{cable_id}")
async def get_cable_detail(cable_id: str):
    """Proxy for individual cable details to avoid CORS."""
    try:
        url = f"{BASE_API_URL}/cable/{cable_id}.json"
        data = cached_get(url, ttl_seconds=86400)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/submarine-cables/isps")
async def get_country_isps(country: str = Query(...)):
    """Fetch ISPs for a given country from MySQL."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        sql = "SELECT name as isp_name FROM isps WHERE LOWER(country) LIKE LOWER(%s) ORDER BY name"
        cursor.execute(sql, ('%' + country + '%',))
        isps = cursor.fetchall()
        cursor.close()
        conn.close()
        return isps
    except Exception as e:
        print(f"Database error: {e}")
        return []

@app.get("/api/health")
async def health():
    return {
        "status": "online",
        "service": "submarine_cable_service",
        "port": 8120,
        "cache_entries": len(_cache),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/")
async def root():
    """Root handler for avoiding 404 on service heartbeat probes."""
    return {"status": "online", "service": "submarine_cable_service"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", log_level="debug", port=8120)
