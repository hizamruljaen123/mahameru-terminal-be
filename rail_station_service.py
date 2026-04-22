from flask import Flask, jsonify, request
from flask_cors import CORS
from db import get_db_connection
import mysql.connector

app = Flask(__name__)
CORS(app)

@app.route('/api/rail/metadata', methods=['GET'])
def get_rail_metadata():
    return jsonify({
        "provider": "OpenRailwayMap",
        "layer_type": "Raster_Tiles",
        "global_coverage": True,
        "api_v": "1.0-ASETPEDIA",
        "attribution": "Data (c) OpenStreetMap contributors, ODbL; Cartography (c) OpenRailwayMap, CC-BY-SA"
    })

import requests # Required for proxy

@app.route('/orm_proxy/facility', methods=['GET'])
def proxy_rail_facility():
    """
    OSINT Proxy for OpenRailwayMap API - Direct Infrastructure Retrieval with Hardened Error Handling
    """
    query = request.args.get('name') or request.args.get('q', '')
    limit = request.args.get('limit', '10')
    if not query:
        return jsonify([])
        
    try:
        # Professional Headers required by OSM/ORM Policy
        headers = {
            'User-Agent': 'AsetpediaRailIntel/1.0 (Contact: admin@asetpedia.com) GeospatialAuditEngine',
            'Accept': 'application/json'
        }
        
        url = f"https://api.openrailwaymap.org/v2/facility?q={query}&limit={limit}"
        response = requests.get(url, headers=headers, timeout=15)
        
        # Check if response is empty or non-200
        if response.status_code != 200:
            print(f"ORM API ERROR [{response.status_code}]: {response.text}")
            return jsonify({"error": f"Upstream API Error {response.status_code}", "detail": response.text}), response.status_code
            
        return jsonify(response.json())
    except requests.exceptions.JSONDecodeError:
        print(f"ORM API PARSE ERROR: Body is not JSON -> {response.text}")
        return jsonify({"error": "Upstream sent invalid data", "body": response.text}), 502
    except Exception as e:
        print(f"PROXY EXCEPTION: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/rail/stats', methods=['GET'])
def get_rail_stats():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT COUNT(*) as total_stations FROM railway_stations")
        total = cursor.fetchone()
        
        cursor.execute("SELECT COUNT(DISTINCT country_code) as total_countries FROM railway_stations")
        countries = cursor.fetchone()
        
        cursor.execute("SELECT COUNT(*) as main_stations FROM railway_stations WHERE is_main_station = 1")
        main = cursor.fetchone()
        
        return jsonify({
            "total_stations": total['total_stations'],
            "total_countries": countries['total_countries'],
            "main_stations": main['main_stations']
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/rail/countries', methods=['GET'])
def get_rail_countries():
    search = request.args.get('q', '')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Full Global Sovereignty View with Search Capability
        query = """
        SELECT 
            c.code, 
            c.name, 
            c.continent,
            c.lat as latitude,
            c.lon as longitude,
            COUNT(rs.id) as station_count
        FROM countries c
        LEFT JOIN railway_stations rs ON c.code = rs.country_code
        WHERE 1=1
        """
        params = []
        if search:
            query += " AND (c.name LIKE %s OR c.code LIKE %s)"
            params.append(f"%{search}%")
            params.append(f"%{search}%")
            
        query += " GROUP BY c.code, c.name, c.continent, c.lat, c.lon ORDER BY c.name ASC"
        
        cursor.execute(query, params)
        return jsonify(cursor.fetchall())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/rail/stations', methods=['GET'])
def get_stations():
    country_code = request.args.get('country')
    search = request.args.get('q', '')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        query = "SELECT * FROM railway_stations WHERE 1=1"
        params = []
        
        if country_code:
            query += " AND country_code = %s"
            params.append(country_code)
            
        if search:
            query += " AND name LIKE %s"
            params.append(f"%{search}%")
            
        query += " LIMIT 1000" # Safety limit
        
        cursor.execute(query, params)
        return jsonify(cursor.fetchall())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/rail/multimodal', methods=['GET'])
def get_multimodal_assets():
    """
    Retrieves global logistics assets: Airports, Sea Ports, and Industrial Zones
    """
    country_code = request.args.get('country')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    results = {
        "airports": [],
        "ports": [],
        "industrial_zones": []
    }
    
    try:
        # 1. Fetch Airports
        air_query = "SELECT id, name, latitude_deg as latitude, longitude_deg as longitude, type, iata_code FROM airports"
        if country_code:
            air_query += " WHERE iso_country = %s"
            cursor.execute(air_query + " LIMIT 500", (country_code,))
        else:
            cursor.execute(air_query + " LIMIT 200")
        results["airports"] = cursor.fetchall()

        # 2. Fetch Sea Ports (WPI)
        port_query = "SELECT world_port_index_number as id, main_port_name as name, latitude, longitude, harbor_size_code, harbor_type_code FROM wpi_import"
        if country_code:
            port_query += " WHERE wpi_country_code = %s"
            cursor.execute(port_query + " LIMIT 500", (country_code,))
        else:
            cursor.execute(port_query + " LIMIT 200")
        results["ports"] = cursor.fetchall()

        # 3. Fetch Industrial Zones
        ind_query = "SELECT id, name, latitude, longitude, sector, ownership FROM industrial_zones"
        if country_code:
            ind_query += " WHERE country = (SELECT name FROM countries WHERE code = %s LIMIT 1)"
            cursor.execute(ind_query + " LIMIT 500", (country_code,))
        else:
            cursor.execute(ind_query + " LIMIT 200")
        results["industrial_zones"] = cursor.fetchall()

        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/rail/proximity', methods=['GET'])
def get_proximity_assets():
    """
    Multimodal Proximity Scan: High-speed Haversine calculation for regional logistics synthesis
    """
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
        radius = float(request.args.get('radius', 100))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid lat/lon/radius parameters"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    results = {
        "airports": [],
        "ports": [],
        "industrial_zones": []
    }
    
    # Haversine formula in SQL for radius detection
    dist_formula = """
        (6371 * acos(
            cos(radians(%s)) * cos(radians({lat_col})) * 
            cos(radians({lon_col}) - radians(%s)) + 
            sin(radians(%s)) * sin(radians({lat_col}))
        ))
    """

    try:
        # 1. Nearby Airports
        air_query = f"SELECT id, name, type, iata_code, latitude_deg as lat, longitude_deg as lon, {dist_formula.format(lat_col='latitude_deg', lon_col='longitude_deg')} AS distance FROM airports HAVING distance <= %s ORDER BY distance ASC"
        cursor.execute(air_query, (lat, lon, lat, radius))
        results["airports"] = cursor.fetchall()

        # 2. Nearby Sea Ports (WPI)
        port_query = f"SELECT world_port_index_number as id, main_port_name as name, harbor_size_code, latitude as lat, longitude as lon, {dist_formula.format(lat_col='latitude', lon_col='longitude')} AS distance FROM wpi_import HAVING distance <= %s ORDER BY distance ASC"
        cursor.execute(port_query, (lat, lon, lat, radius))
        results["ports"] = cursor.fetchall()

        # 3. Nearby Industrial Zones
        ind_query = f"SELECT id, name, sector, ownership, latitude as lat, longitude as lon, {dist_formula.format(lat_col='latitude', lon_col='longitude')} AS distance FROM industrial_zones HAVING distance <= %s ORDER BY distance ASC"
        cursor.execute(ind_query, (lat, lon, lat, radius))
        results["industrial_zones"] = cursor.fetchall()

        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(port=8111, debug=True)
