import mysql.connector
import os
import sys
import json
import requests
import time
import math
from datetime import datetime, timedelta

# Add be directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
be_path = os.path.join(current_dir, '..', 'be')
libs_path = os.path.join(be_path, 'libs')
sys.path.append(be_path)
sys.path.append(libs_path)

from db import get_db_connection
try:
    import investment_scorer
    import industrial_engine as engine
except ImportError:
    print("Warning: Could not import internal libs directly. Please ensure this script is in news_stream/scratch/")

def setup_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS industrial_investment_cache (
        hub_id INT PRIMARY KEY,
        investment_index FLOAT,
        classification VARCHAR(50),
        profitability_rating VARCHAR(100),
        total_facilities INT,
        strategic_analysis TEXT,
        facility_breakdown JSON,
        full_stats_json LONGTEXT,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dln = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dln/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def seed_cache():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, latitude as lat, longitude as lon, country FROM industrial_zones")
    hubs = cursor.fetchall()
    conn.close()
    
    print(f"--- STANDALONE SEEDING MODE ---")
    print(f"Bypassing localhost:8092 requirement. Processing {len(hubs)} hubs directly.")
    
    for hub in hubs:
        h_id, h_name, h_lat, h_lon = hub['id'], hub['name'], float(hub['lat']), float(hub['lon'])
        print(f"PROCESING: {h_name}...")
        
        try:
            # 1. FETCH LOGISTICS (Using other microservices if they are up, or fallback)
            logistics = {"airports": [], "power_plants": [], "vessels": [], "aircraft": []}
            
            # Airport Fetch
            try:
                res = requests.get(f"{os.getenv('INFRASTRUCTURE_API_URL', 'http://localhost:8097')}/api/infra/airports/nearby?lat={h_lat}&lon={h_lon}&radius=100", timeout=5).json()
                for a in res: a['latitude'], a['longitude'] = a['latitude_deg'], a['longitude_deg']
                logistics["airports"] = res
            except: pass
            
            # Power Plant Fetch
            try:
                res = requests.get(f"{os.getenv('INFRASTRUCTURE_API_URL', 'http://localhost:8097')}/api/infra/power-plants/nearby?lat={h_lat}&lon={h_lon}&radius=150", timeout=5).json()
                logistics["power_plants"] = res
            except: pass

            # 2. FETCH PUBLIC INFRA (OSM - Overpass is heavy, so we call infra_service)
            public_infra = []
            try:
                osm_res = requests.get(f"{os.getenv('INFRASTRUCTURE_API_URL', 'http://localhost:8097')}/api/infra/public/search?lat={h_lat}&lon={h_lon}&radius=100000", timeout=60).json()
                raw = osm_res if isinstance(osm_res, list) else osm_res.get('elements', [])
                for item in raw:
                    i_lat, i_lon = item.get('lat'), item.get('lon')
                    if i_lat and i_lon:
                        dist = haversine(h_lat, h_lon, float(i_lat), float(i_lon))
                        if dist <= 100.0:
                            item['distance_km'] = round(dist, 1)
                            public_infra.append(item)
                public_infra = sorted(public_infra, key=lambda x: x.get('distance_km', 999))[:150]
            except: pass

            # 3. DIRECT SCORING (IMPORT FROM LIBS)
            inv = investment_scorer.calculate_investment_score(logistics, public_infra)
            
            # 4. BUNDLE AS JSON
            data_bundle = {
                "investment_analysis": inv,
                "logistics": logistics,
                "public_infra": public_infra,
                "current_score": 0.5, # Default placeholder if engine is not fully involved
                "last_sync": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

            # 5. DB SAVE
            conn = get_db_connection()
            cursor = conn.cursor()
            sql = """
            INSERT INTO industrial_investment_cache 
            (hub_id, investment_index, classification, profitability_rating, total_facilities, strategic_analysis, facility_breakdown, full_stats_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
            investment_index=VALUES(investment_index), classification=VALUES(classification),
            profitability_rating=VALUES(profitability_rating), total_facilities=VALUES(total_facilities),
            strategic_analysis=VALUES(strategic_analysis), facility_breakdown=VALUES(facility_breakdown),
            full_stats_json=VALUES(full_stats_json)
            """
            cursor.execute(sql, (
                h_id, inv['investment_index'], inv['classification'], inv['profitability_rating'],
                inv['total_facilities'], inv['strategic_analysis'], json.dumps(inv['facility_breakdown']),
                json.dumps(data_bundle)
            ))
            conn.commit()
            conn.close()
            print(f"SUCCESS: {h_name} -> Index: {inv['investment_index']}")

        except Exception as e:
            print(f"CRITICAL ERROR for {h_name}: {e}")
        
        time.sleep(1) # Be nice to OSM

if __name__ == "__main__":
    setup_table()
    seed_cache()
