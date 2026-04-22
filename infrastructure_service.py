from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import sys
import mysql.connector

# Add be directory to path for db.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db import get_db_connection

import math
import requests

app = Flask(__name__)
CORS(app)

def haversine(lat1, lon1, lat2, lon2):
    # Earth radius in kilometers
    R = 6371.0
    
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    
    a = math.sin(dphi / 2.0)**2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0)**2
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

@app.route('/api/infra/public/search', methods=['GET'])
def get_public_infra():
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
        radius = int(request.args.get('radius', 2000))
        
        # Mirror: https://overpass.kumi.systems/api/interpreter
        overpass_url = "https://overpass.kumi.systems/api/interpreter"
        query = f"""[out:json][timeout:60];
        (
          node["amenity"~"bus_station|taxi|bicycle_parking|car_wash|hospital|clinic|pharmacy|dentist|doctors|school|university|kindergarten|library|townhall|courthouse|police|post_office|atm|bank|fuel|marketplace|place_of_worship|community_centre|fire_station|restaurant|cafe|fast_food|food_court|ferry_terminal"](around:{radius},{lat},{lon});
          node["railway"~"station|subway_entrance"](around:{radius},{lat},{lon});
          node["shop"~"supermarket|convenience|mall|department_store"](around:{radius},{lat},{lon});
          node["leisure"~"park|playground|stadium|fitness_centre"](around:{radius},{lat},{lon});
          node["tourism"~"hotel|museum|attraction|viewpoint"](around:{radius},{lat},{lon});
          node["office"](around:{radius},{lat},{lon});
          node["industrial"="port"](around:{radius},{lat},{lon});
          node["harbour"="yes"](around:{radius},{lat},{lon});
          node["power"="plant"](around:{radius},{lat},{lon});
        );
        out body;
        """
        
        response = requests.get(overpass_url, params={'data': query}, timeout=45)
        data = response.json()
        
        elements = data.get('elements', [])
        formatted = []
        for item in elements:
            tags = item.get('tags', {})
            # Determine type
            kind = tags.get('amenity') or tags.get('railway') or tags.get('shop') or tags.get('leisure') or tags.get('tourism') or tags.get('office') or tags.get('power')
            if not kind and (tags.get('industrial') == 'port' or tags.get('harbour') == 'yes' or tags.get('amenity') == 'ferry_terminal'):
                kind = 'port'
            kind = kind or 'other'
            formatted.append({
                "id": item['id'],
                "lat": item['lat'],
                "lon": item['lon'],
                "type": kind,
                "name": tags.get('name', 'Unnamed Facility')
            })
            
        return jsonify(formatted)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/infra/public/search-between', methods=['GET'])
def get_public_infra_between():
    try:
        lat1 = float(request.args.get('lat1'))
        lon1 = float(request.args.get('lon1'))
        lat2 = float(request.args.get('lat2'))
        lon2 = float(request.args.get('lon2'))
        radius = int(request.args.get('radius', 1000))
        
        overpass_url = "https://overpass.kumi.systems/api/interpreter"
        
        # Query searching around both points and their midpoint
        mid_lat = (lat1 + lat2) / 2
        mid_lon = (lon1 + lon2) / 2
        
        query = f"""
        [out:json][timeout:30];
        (
           // Point A
          node["amenity"~"bus_station|taxi|bicycle_parking|car_wash|hospital|clinic|pharmacy|dentist|doctors|school|university|kindergarten|library|townhall|courthouse|police|post_office|atm|bank|fuel|marketplace|place_of_worship|community_centre|fire_station|restaurant|cafe|fast_food|food_court|ferry_terminal"](around:{radius},{lat1},{lon1});
          node["railway"~"station|subway_entrance"](around:{radius},{lat1},{lon1});
          node["shop"~"supermarket|convenience|mall|department_store"](around:{radius},{lat1},{lon1});
          node["leisure"~"park|playground|stadium|fitness_centre"](around:{radius},{lat1},{lon1});
          node["tourism"~"hotel|museum|attraction|viewpoint"](around:{radius},{lat1},{lon1});
          node["office"](around:{radius},{lat1},{lon1});
          node["industrial"="port"](around:{radius},{lat1},{lon1});
          node["harbour"="yes"](around:{radius},{lat1},{lon1});
          node["power"="plant"](around:{radius},{lat1},{lon1});
          
          // Point B
          node["amenity"~"bus_station|taxi|bicycle_parking|car_wash|hospital|clinic|pharmacy|dentist|doctors|school|university|kindergarten|library|townhall|courthouse|police|post_office|atm|bank|fuel|marketplace|place_of_worship|community_centre|fire_station|restaurant|cafe|fast_food|food_court|ferry_terminal"](around:{radius},{lat2},{lon2});
          node["railway"~"station|subway_entrance"](around:{radius},{lat2},{lon2});
          node["shop"~"supermarket|convenience|mall|department_store"](around:{radius},{lat2},{lon2});
          node["leisure"~"park|playground|stadium|fitness_centre"](around:{radius},{lat2},{lon2});
          node["tourism"~"hotel|museum|attraction|viewpoint"](around:{radius},{lat2},{lon2});
          node["office"](around:{radius},{lat2},{lon2});
          node["industrial"="port"](around:{radius},{lat2},{lon2});
          node["harbour"="yes"](around:{radius},{lat2},{lon2});
          node["power"="plant"](around:{radius},{lat2},{lon2});

          // Midpoint
          node["amenity"~"bus_station|taxi|bicycle_parking|car_wash|hospital|clinic|pharmacy|dentist|doctors|school|university|kindergarten|library|townhall|courthouse|police|post_office|atm|bank|fuel|marketplace|place_of_worship|community_centre|fire_station|restaurant|cafe|fast_food|food_court|ferry_terminal"](around:{radius},{mid_lat},{mid_lon});
          node["railway"~"station|subway_entrance"](around:{radius},{mid_lat},{mid_lon});
          node["shop"~"supermarket|convenience|mall|department_store"](around:{radius},{mid_lat},{mid_lon});
          node["leisure"~"park|playground|stadium|fitness_centre"](around:{radius},{mid_lat},{mid_lon});
          node["tourism"~"hotel|museum|attraction|viewpoint"](around:{radius},{mid_lat},{mid_lon});
          node["office"](around:{radius},{mid_lat},{mid_lon});
          node["industrial"="port"](around:{radius},{mid_lat},{mid_lon});
          node["harbour"="yes"](around:{radius},{mid_lat},{mid_lon});
          node["power"="plant"](around:{radius},{mid_lat},{mid_lon});
        );
        out body;
        """
        
        response = requests.get(overpass_url, params={'data': query}, timeout=25)
        data = response.json()
        
        elements = data.get('elements', [])
        formatted = []
        seen_ids = set()
        
        for item in elements:
            if item['id'] in seen_ids:
                continue
            seen_ids.add(item['id'])
            
            tags = item.get('tags', {})
            kind = tags.get('amenity') or tags.get('railway') or tags.get('shop') or tags.get('leisure') or tags.get('tourism') or tags.get('office') or tags.get('power')
            if not kind and (tags.get('industrial') == 'port' or tags.get('harbour') == 'yes' or tags.get('amenity') == 'ferry_terminal'):
                kind = 'port'
            kind = kind or 'other'
            formatted.append({
                "id": item['id'],
                "lat": item['lat'],
                "lon": item['lon'],
                "type": kind,
                "name": tags.get('name', 'Unnamed Facility')
            })
            
        return jsonify(formatted)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/infra/power-plants/nearby', methods=['GET'])
def get_nearby_power_plants():
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
        radius_km = float(request.args.get('radius', 150))
        limit = int(request.args.get('limit', 5))
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Power plants are global, so we search all but limit to a reasonable radius
        # For efficiency, first filter by a rough bounding box
        lat_delta = radius_km / 111.0
        lon_delta = radius_km / (111.0 * math.cos(math.radians(lat)))
        
        query = """
            SELECT id, name, country_long, capacity_mw, primary_fuel, latitude, longitude, owner
            FROM power_plants 
            WHERE latitude BETWEEN %s AND %s 
              AND longitude BETWEEN %s AND %s
        """
        cursor.execute(query, (lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta))
        plants = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Calculate precise distance
        nearby = []
        for p in plants:
            dist = haversine(lat, lon, float(p['latitude']), float(p['longitude']))
            if dist <= radius_km:
                p['distance_km'] = round(dist, 2)
                # Map standard field names for consistency
                p['latitude'] = float(p['latitude'])
                p['longitude'] = float(p['longitude'])
                nearby.append(p)
        
        nearby.sort(key=lambda x: x['distance_km'])
        return jsonify(nearby[:limit])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/infra/airports/nearby', methods=['GET'])

@app.route('/api/infra/airports/continents', methods=['GET'])
def get_continents():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Fetch from countries table for speed
        cursor.execute("SELECT DISTINCT continent FROM countries WHERE continent IS NOT NULL ORDER BY continent")
        result = cursor.fetchall()
        continents = [row['continent'] for row in result]
        cursor.close()
        conn.close()
        return jsonify(continents)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/infra/airports/countries', methods=['GET'])
def get_countries():
    continent = request.args.get('continent')
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Directly from countries table
        query = "SELECT code, name FROM countries WHERE 1=1"
        params = []
        if continent:
            query += " AND continent = %s"
            params.append(continent)
        query += " ORDER BY name"
        cursor.execute(query, params)
        result = cursor.fetchall()
        countries = [{"code": row['code'], "name": row['name'] or row['code']} for row in result]
        cursor.close()
        conn.close()
        return jsonify(countries)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/infra/airports/types', methods=['GET'])
def get_types():
    continent = request.args.get('continent')
    country = request.args.get('country')
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = "SELECT DISTINCT type FROM airports WHERE 1=1"
        params = []
        if continent:
            query += " AND continent = %s"
            params.append(continent)
        if country:
            query += " AND iso_country = %s"
            params.append(country)
        query += " ORDER BY type"
        cursor.execute(query, params)
        result = cursor.fetchall()
        types = [row['type'] for row in result]
        cursor.close()
        conn.close()
        return jsonify(types)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/infra/airports/continent-nodes', methods=['GET'])
def get_continent_nodes():
    continent_coords = {
        'AF': {'lat': 1.65, 'lon': 17.32},
        'AN': {'lat': -75.25, 'lon': -0.07},
        'AS': {'lat': 34.04, 'lon': 100.61},
        'EU': {'lat': 47.75, 'lon': 13.33},
        'NA': {'lat': 45.42, 'lon': -93.63},
        'OC': {'lat': -21.45, 'lon': 133.51},
        'SA': {'lat': -21.23, 'lon': -59.55}
    }
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Get counts from optimized countries table
        query = """
            SELECT continent, SUM(airport_count) as count
            FROM countries 
            WHERE continent IS NOT NULL
            GROUP BY continent
        """
        cursor.execute(query)
        result = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Merge with hardcoded coords
        nodes = []
        for row in result:
            cont = row['continent']
            if cont in continent_coords:
                nodes.append({
                    "continent": cont,
                    "lat": continent_coords[cont]['lat'],
                    "lon": continent_coords[cont]['lon'],
                    "count": int(row['count'] or 0)
                })
        return jsonify(nodes)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/infra/airports/country-nodes', methods=['GET'])
def get_country_nodes():
    continent = request.args.get('continent')
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Directly from countries table (assuming lat/lon cols exist from previous optimize run)
        # If optimization script failed or interrupted, we can fallback or join back to airports
        # Let's try to use the countries table but handle if lat is NULL
        query = """
            SELECT code, name, lat, lon, airport_count as count
            FROM countries
            WHERE 1=1
        """
        params = []
        if continent:
            query += " AND continent = %s"
            params.append(continent)
        query += " AND lat IS NOT NULL ORDER BY name"
        cursor.execute(query, params)
        result = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # If no optimized results, fallback to slow query (temporary safety)
        if not result:
            return jsonify({"status": "FALLBACK_TRIGGERED", "nodes": []})

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/infra/airports/search', methods=['GET'])
def search_airports():
    continent = request.args.get('continent')
    country = request.args.get('country')
    airport_type = request.args.get('type')
    search_query = request.args.get('q')
    limit = request.args.get('limit', 1000, type=int)

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Explicitly set collation for join to avoid Illegal mix of collations error
        query = """
            SELECT a.*, c.name as country_name 
            FROM airports a 
            LEFT JOIN countries c ON a.iso_country = c.code COLLATE utf8mb4_general_ci
            WHERE 1=1
        """
        params = []
        
        if continent:
            query += " AND a.continent = %s"
            params.append(continent)
        if country:
            query += " AND a.iso_country = %s"
            params.append(country)
        if airport_type:
            query += " AND a.type = %s"
            params.append(airport_type)
        if search_query:
            query += " AND a.name LIKE %s"
            params.append(f"%{search_query}%")
            
        query += " LIMIT %s"
        params.append(limit)
        
        cursor.execute(query, params)
        result = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Format for GeoJSON or simple list
        airports = []
        for row in result:
            airports.append({
                "id": row['id'],
                "ident": row['ident'],
                "type": row['type'],
                "name": row['name'],
                "latitude": row['latitude_deg'],
                "longitude": row['longitude_deg'],
                "elevation": row['elevation_ft'],
                "country_code": row['iso_country'],
                "country_name": row['country_name'] or row['iso_country'],
                "region": row['iso_region'],
                "municipality": row['municipality'],
                "iata": row['iata_code'],
                "wikipedia": row['wikipedia_link']
            })
            
        return jsonify(airports)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8097, debug=True)
