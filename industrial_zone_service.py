from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import sys
import mysql.connector
import requests
import json

# Add be directory to path for db.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db import get_db_connection

app = Flask(__name__)
CORS(app)

@app.route('/api/industrial-zones', methods=['GET'])
def get_industrial_zones():
    try:
        limit = request.args.get('limit', 1000, type=int)
        search = request.args.get('q', '')
        country = request.args.get('country', '')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = "SELECT * FROM industrial_zones WHERE 1=1"
        params = []
        
        if search:
            query += " AND (name LIKE %s OR sector LIKE %s)"
            params.append(f"%{search}%")
            params.append(f"%{search}%")
        
        if country:
            query += " AND country = %s"
            params.append(country)
            
        query += " LIMIT %s"
        params.append(limit)
        
        cursor.execute(query, params)
        zones = cursor.fetchall()
        
        # Format decimal values for JSON serialization
        for zone in zones:
            if zone['latitude'] is not None:
                zone['latitude'] = float(zone['latitude'])
            if zone['longitude'] is not None:
                zone['longitude'] = float(zone['longitude'])
                
        cursor.close()
        conn.close()
        return jsonify(zones)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/industrial-zones/countries', methods=['GET'])
def get_industrial_countries():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # JOIN with countries table to get center lat/lon for each country that has industrial zones
        query = """
            SELECT c.name, c.lat, c.lon, COUNT(iz.id) as zone_count
            FROM countries c
            JOIN industrial_zones iz ON c.name = iz.country
            GROUP BY c.name, c.lat, c.lon
            ORDER BY zone_count DESC
        """
        cursor.execute(query)
        result = cursor.fetchall()
        
        # Format decimals
        for row in result:
            if row['lat'] is not None: row['lat'] = float(row['lat'])
            if row['lon'] is not None: row['lon'] = float(row['lon'])
            
        cursor.close()
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/industrial-zones/stats', methods=['GET'])
def get_stats():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Stats by country
        cursor.execute("SELECT country, COUNT(*) as count FROM industrial_zones GROUP BY country ORDER BY count DESC LIMIT 10")
        by_country = cursor.fetchall()
        
        # Stats by sector
        cursor.execute("SELECT sector, COUNT(*) as count FROM industrial_zones GROUP BY sector ORDER BY count DESC LIMIT 10")
        by_sector = cursor.fetchall()
        
        cursor.close()
        conn.close()
        return jsonify({
            "by_country": by_country,
            "by_sector": by_sector
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/industrial-zones/logistics', methods=['GET'])
def get_logistics():
    try:
        lat = request.args.get('lat', type=float)
        lon = request.args.get('lon', type=float)
        radius = request.args.get('radius', 150, type=int)

        if lat is None or lon is None:
            return jsonify({"error": "Missing coordinates"}), 400
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            airports = []
            try:
                airport_query = """
                    SELECT name, type, iata_code as code, elevation_ft, municipality, wikipedia_link, latitude_deg as lat, longitude_deg as lon,
                    (6371 * acos(cos(radians(%s)) * cos(radians(latitude_deg)) * cos(radians(longitude_deg) - radians(%s)) + sin(radians(%s)) * sin(radians(latitude_deg)))) AS distance
                    FROM airports
                    HAVING distance <= %s
                    ORDER BY distance ASC
                    LIMIT 10
                """
                cursor.execute(airport_query, (lat, lon, lat, radius))
                airports = cursor.fetchall()
                for a in airports: a['lat'], a['lon'] = float(a['lat']), float(a['lon'])
            except Exception as e:
                print(f"Airport query failed: {e}")

            ports = []
            try:
                port_query = """
                    SELECT main_port_name as name, harbor_type_code as type, chart as code, harbor_size_code, channel_depth, shelter_afforded_code, latitude as lat, longitude as lon,
                    (6371 * acos(cos(radians(%s)) * cos(radians(latitude)) * cos(radians(longitude) - radians(%s)) + sin(radians(%s)) * sin(radians(latitude)))) AS distance
                    FROM wpi_import
                    HAVING distance <= %s
                    ORDER BY distance ASC
                    LIMIT 10
                """
                cursor.execute(port_query, (lat, lon, lat, radius))
                ports = cursor.fetchall()
                for p in ports: p['lat'], p['lon'] = float(p['lat']), float(p['lon'])
            except Exception as e:
                print(f"Port query failed: {e}")

            power_plants = []
            try:
                power_query = """
                    SELECT name, primary_fuel as type, capacity_mw as capacity, commissioning_year, owner, latitude as lat, longitude as lon,
                    (6371 * acos(cos(radians(%s)) * cos(radians(latitude)) * cos(radians(longitude) - radians(%s)) + sin(radians(%s)) * sin(radians(latitude)))) AS distance
                    FROM power_plants
                    WHERE latitude IS NOT NULL AND longitude IS NOT NULL
                    HAVING distance <= 100
                    ORDER BY distance ASC
                    LIMIT 10
                """
                cursor.execute(power_query, (lat, lon, lat))
                power_plants = cursor.fetchall()
                for pp in power_plants: 
                    pp['lat'], pp['lon'] = float(pp['lat']), float(pp['lon'])
                    pp['capacity'] = float(pp['capacity'] or 0)
            except Exception as e:
                print(f"Power plant query failed: {e}")

            cursor.close()
            conn.close()

            return jsonify({
                "airports": airports,
                "ports": ports,
                "power_plants": power_plants
            })
        except Exception as e:
            print(f"Global logistics search failed: {e}")
            return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/industrial-zones/pois', methods=['GET'])
def get_zone_pois():
    try:
        zone_id = request.args.get('zone_id', type=int)
        lat = request.args.get('lat', type=float)
        lon = request.args.get('lon', type=float)
        
        if not zone_id:
            return jsonify({"error": "Missing zone_id"}), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Check cache
        cursor.execute("SELECT * FROM industrial_zone_poi WHERE hub_id = %s", (zone_id,))
        cached = cursor.fetchone()
        
        if cached:
            # If cached data is available, return it
            try:
                raw_pois = cached['facility_scan']
                if isinstance(raw_pois, str):
                    pois = json.loads(raw_pois)
                else:
                    pois = raw_pois
                
                # If we have actual facility data in the cache, return it
                if isinstance(pois, list) and len(pois) > 0:
                    cursor.close()
                    conn.close()
                    return jsonify({
                        "source": "cache",
                        "facilities": pois
                    })
            except Exception as e:
                print(f"Error parsing cached pois: {e}")

        # If we reach here, either there was no cache OR the cache was empty
        # Fetch from Overpass if not cached or cache empty
        if lat is None or lon is None:
             cursor.close()
             conn.close()
             return jsonify({"error": "Coordinates required for initial scan"}), 400

        amenities = 'bus_station|place_of_worship|hospital|bank|fuel'
        query = f'[out:json];(node["amenity"~"{amenities}"](around:5000,{lat},{lon});way["amenity"~"{amenities}"](around:5000,{lat},{lon}););out center;'
        
        overpass_mirrors = [
            "https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.openstreetmap.fr/api/interpreter",
            "https://overpass.nchc.org.tw/api/interpreter"
        ]
        
        data = None
        success = False
        last_err = ""

        for mirror_url in overpass_mirrors:
            try:
                response = requests.post(mirror_url, data={'data': query}, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    success = True
                    break
                last_err = f"HTTP {response.status_code} from {mirror_url}"
            except Exception as e:
                last_err = str(e)
                continue
        
        if not success:
            cursor.close()
            conn.close()
            return jsonify({"error": f"Geospatial intelligence cluster unreachable. Last trace: {last_err}"}), 503
        
        elements = data.get('elements', [])
        pois = []
        for el in elements:
            pois.append({
                "name": el.get('tags', {}).get('name', f"{el.get('tags', {}).get('amenity', 'facility').replace('_', ' ').upper()} (UNNAMED)"),
                "type": el.get('tags', {}).get('amenity'),
                "lat": el.get('lat') or el.get('center', {}).get('lat'),
                "lon": el.get('lon') or el.get('center', {}).get('lon'),
                "tags": el.get('tags', {})
            })

        # Save to DB
        insert_query = """
            INSERT INTO industrial_zone_poi 
            (hub_id, facility_scan)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE 
            facility_scan=VALUES(facility_scan)
        """
        cursor.execute(insert_query, (
            zone_id, json.dumps(pois)
        ))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "source": "overpass",
            "facilities": pois
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8094, debug=True)
