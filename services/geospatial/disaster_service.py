import uvicorn
import requests
from fastapi import FastAPI, Query, APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
import json
import time
import os

app = FastAPI(debug=True, title="Optimized Disaster Intelligence Service", version="1.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory cache
_cache = {}

def cached_get(url: str, ttl_seconds: int = 300):
    now = time.time()
    if url in _cache:
        data, ts = _cache[url]
        if now - ts < ttl_seconds:
            return data
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        _cache[url] = (data, now)
        return data
    except Exception as e:
        if url in _cache:
            return _cache[url][0]
        raise e

@app.get("/api/disaster/gdacs")
async def get_gdacs(
    country: str = Query(None), 
    eventlist: str = Query("EQ;FL;TC;VO;DR;WF"),
    alertlevel: str = Query(None),
    limit: int = 20
):
    """
    Fetch GDACS GeoJSON feed using the Search API for optimization.
    Supports partial loading by country, event type, and alert level.
    """
    # Base Search API URL (Returns GeoJSON FeatureCollection)
    params = []
    if country: params.append(f"country={country}")
    if eventlist: params.append(f"eventlist={eventlist}")
    if alertlevel: params.append(f"alertlevel={alertlevel}")
    params.append(f"pageSize={limit}")
    
    query_string = "&".join(params)
    url = f"https://www.gdacs.org/gdacsapi/api/events/geteventlist/search?{query_string}"
    
    try:
        # Fetch filtered data
        data = cached_get(url, ttl_seconds=600) # Cache for 10 mins
        
        return {
            "status": "success", 
            "source": "GDACS_SEARCH_API",
            "filters": {"country": country, "eventlist": eventlist, "alertlevel": alertlevel, "limit": limit},
            "data": data
        }
    except Exception as e:
        # Fallback to local file or main feed if search fails
        return {"status": "error", "message": f"Search API failed: {str(e)}"}

@app.get("/api/disaster/usgs")
async def get_usgs(limit: int = Query(30)):
    """Fetch USGS Earthquake GeoJSON feed."""
    now = datetime.utcnow()
    yesterday = (now - timedelta(days=1)).isoformat()
    url = f"https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime={yesterday}&limit={limit}"
    try:
        data = cached_get(url, ttl_seconds=300)
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/disaster/bmkg")
async def get_bmkg():
    """Fetch BMKG Latest Earthquake data."""
    url = "https://data.bmkg.go.id/DataMKG/TEWS/autogempa.json"
    try:
        data = cached_get(url, ttl_seconds=300)
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/disaster/nasa_eonet")
async def get_nasa_eonet(days: int = 7):
    """Fetch NASA EONET disaster events."""
    url = f"https://eonet.gsfc.nasa.gov/api/v3/events?days={days}"
    try:
        data = cached_get(url, ttl_seconds=3600) # 1 hour cache
        return {"status": "success", "data": data}
    except Exception as e:
        return {"status": "error", "message": f"NASA EONET failed: {str(e)}"}

@app.get("/api/disaster/nasa_firms")
async def get_nasa_firms(source: str = "VIIRS_SNPP_NRT", area: str = "world", days: int = 1):
    """Fetch NASA FIRMS fire hotspots (Parses CSV to JSON)."""
    api_key = os.getenv("NASA_FIRMS_API_KEY", "")
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{api_key}/{source}/{area}/{days}"
    try:
        # FIRMS returns CSV, we need to parse it
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        lines = resp.text.strip().split('\n')
        if len(lines) < 2:
            return {"status": "success", "data": []}
        
        headers = lines[0].split(',')
        hotspots = []
        for line in lines[1:200]: # Limit to top 200 for performance
            values = line.split(',')
            if len(values) == len(headers):
                hotspots.append(dict(zip(headers, values)))
        
        return {"status": "success", "data": hotspots}
    except Exception as e:
        return {"status": "error", "message": f"NASA FIRMS failed: {str(e)}"}

@app.get("/api/disaster/proxy_tile")
def proxy_tile(url: str):
    """
    Proxies imagery from NASA to bypass CORS browser restrictions.
    """
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return Response(content=resp.content, media_type="image/jpeg")
        else:
            raise HTTPException(status_code=resp.status_code, detail="NASA server error")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/disaster/nasa_imagery")
async def get_nasa_imagery(
    lat: float, 
    lon: float, 
    range_deg: float = 0.5, 
    grid_size: int = 10, 
    img_res: int = 1200,
    date: str = None,
    layers: str = None
):
    """
    Generates tile URLs for a high-res NASA Satellite imagery grid based on a center point.
    Supports dynamic mapping of multiple layers (MODIS, VIIRS, GOES, etc.)
    """
    if not date:
        date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
        
    if not layers:
        # Default institutional recon layer set
        layers = "MODIS_Terra_CorrectedReflectance_TrueColor,VIIRS_SNPP_Thermal_Anomalies_375m_All,Coastlines_15m,Reference_Features_15m"
        
    lat_min = lat - range_deg / 2
    lat_max = lat + range_deg / 2
    lon_min = lon - range_deg / 2
    lon_max = lon + range_deg / 2
    
    step_lat = (lat_max - lat_min) / grid_size
    step_lon = (lon_max - lon_min) / grid_size
    
    base_url = "https://wvs.earthdata.nasa.gov/api/v1/snapshot"
    
    tiles = []
    
    for row in range(grid_size):
        for col in range(grid_size):
            b_lat_max = lat_max - (row * step_lat)
            b_lat_min = lat_max - ((row + 1) * step_lat)
            b_lon_min = lon_min + (col * step_lon)
            b_lon_max = lon_min + ((col + 1) * step_lon)
            
            bbox_str = f"{b_lat_min},{b_lon_min},{b_lat_max},{b_lon_max}"
            
            tile_url = f"{base_url}?REQUEST=GetSnapshot&LAYERS={layers}&CRS=EPSG:4326&BBOX={bbox_str}&FORMAT=image/jpeg&WIDTH={img_res}&HEIGHT={img_res}&TIME={date}"
            
            tiles.append({
                "row": row,
                "col": col,
                "url": tile_url
            })
            
    return {
        "status": "success",
        "data": {
            "center": [lat, lon],
            "date": date,
            "grid_size": grid_size,
            "img_res": img_res,
            "canvas_size": grid_size * img_res,
            "tiles": tiles
        }
    }

@app.get("/health")
async def health():
    return {"status": "online", "service": "disaster_service_v1.3"}

if __name__ == "__main__":
    print("=" * 60)
    print("ASETPEDIA DISASTER INTELLIGENCE SERVICE V1.2 // PORT 8095")
    print("Sources: GDACS, USGS, BMKG, NASA EONET, NASA FIRMS")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8095)
