import requests
import time
import re
from typing import Optional, Dict

# Shared in-memory cache for geolocation results
_geocode_cache: Dict[str, dict] = {}

def geocode_place(place: str, user_agent: str = "AsetpediaGeo/1.0", language: str = "id,en") -> Optional[dict]:
    """
    Smarter geocoder using Nominatim with fallback logic and caching.
    
    Args:
        place (str): The name or address of the place to geocode.
        user_agent (str): User agent for Nominatim API (required by TOS).
        language (str): Preferred response languages.
        
    Returns:
        Optional[dict]: {lat: float, lon: float, display: str} or None.
    """
    if not place:
        return None
        
    if place in _geocode_cache:
        return _geocode_cache[place]

    def call_nominatim(q: str):
        try:
            r = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": q, "format": "json", "limit": 1},
                headers={"Accept-Language": language, "User-Agent": user_agent},
                timeout=5
            )
            data = r.json()
            if data:
                return data
            return None
        except Exception:
            return None

    # Fallback logic: split the place name into parts (e.g., "Village, District, Regency")
    parts = re.split(r'[/,]', place)
    parts = [p.strip() for p in parts if p.strip()]
    
    attempts = [place]
    if len(parts) > 1:
        # Build hierarchy-based fallbacks
        # If full path fails, try broad path (e.g. "Regency, Province, Indonesia")
        attempts.append(f"{parts[-2]}, {parts[-1]}, Indonesia")
    
    for q in attempts:
        data = call_nominatim(q)
        if data:
            result = {
                "lat": float(data[0]["lat"]),
                "lon": float(data[0]["lon"]),
                "display": data[0].get("display_name")
            }
            _geocode_cache[place] = result
            return result
        
        # Respect Nominatim's 1 req/sec rate limit on cache misses
        time.sleep(1.1)
    
    return None
