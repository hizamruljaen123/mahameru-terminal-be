import asyncio
import json
import os
import aiohttp
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Global Satellite Tracking Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CELESTRAK_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=json"
CACHE_FILE = os.path.join(os.path.dirname(__file__), "data", "active.json")

# In-memory cache
cached_data = None

@app.get("/api/satellites/active")
async def get_active_satellites():
    global cached_data
    if cached_data is not None:
        return {"status": "success", "source": "memory", "data": cached_data}
    
    # Prioritize local cache
    try:
        if os.path.exists(CACHE_FILE):
             with open(CACHE_FILE, "r") as f:
                 data = json.load(f)
                 cached_data = data
                 return {"status": "success", "source": "cache", "data": data}
    except Exception as e:
        print("Cache file read failed:", e)

    # Fallback to Celestrak if cache is unavailable
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(CELESTRAK_URL, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    cached_data = data
                    try:
                        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
                        with open(CACHE_FILE, "w") as f:
                            json.dump(data, f)
                    except Exception as e:
                        print("Failed to write to cache file:", e)
                    return {"status": "success", "source": "api", "data": data}
    except Exception as e:
        print("Celestrak fetch failed:", e)
        
    return {"status": "error", "message": "Failed to fetch data and no valid cache available", "data": []}

@app.get("/api/osm/search")
async def osm_search(q: str):
    url = f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=5"
    headers = {"User-Agent": "AsetpediaEngine/1.0 (Contact: admin@asetpedia.local)"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {"status": "success", "data": data}
                else:
                    return {"status": "error", "message": f"OSM API error: {resp.status}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    uvicorn.run("satellite_visual_service:app", host="0.0.0.0", port=8130, reload=True)
