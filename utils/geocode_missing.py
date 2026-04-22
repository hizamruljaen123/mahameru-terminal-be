import sys
import os
import time

# Add parent dir to path to import db_utils and geocoder
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_utils import execute_query
from utils.geocoder import geocode_place

def geocode_missing_countries():
    print("[GEO] Detecting countries with missing coordinates...")
    missing = execute_query("SELECT origin_id, origin_name FROM oil_trade_countries WHERE lat IS NULL OR lat = 0")
    
    if not missing:
        print("[GEO] No missing coordinates found. System is healthy.")
        return

    print(f"[GEO] Found {len(missing)} missing entries. Starting geocoding...")
    
    updated_count = 0
    for entry in missing:
        name = entry['origin_name']
        origin_id = entry['origin_id']
        
        # Skip 'World' as it has no specific coordinate
        if name.lower() == 'world':
            continue
            
        print(f"[GEO] Geocoding: {name}...")
        res = geocode_place(name)
        
        if res:
            execute_query(
                "UPDATE oil_trade_countries SET lat = %s, lon = %s WHERE origin_id = %s",
                (res['lat'], res['lon'], origin_id),
                commit=True
            )
            print(f"      -> SUCCESS: {res['lat']}, {res['lon']}")
            updated_count += 1
        else:
            print(f"      -> FAILED to find coordinates for {name}")
            
        # Respect rate limit
        time.sleep(1.2)
        
    print(f"[GEO] Task completed. {updated_count} records updated.")

if __name__ == "__main__":
    geocode_missing_countries()
