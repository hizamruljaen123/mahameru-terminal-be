from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import sys
import mysql.connector
import math

# Add be directory to path for db.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db import get_db_connection

app = Flask(__name__)
CORS(app)

def to_decimal(deg, min, hem):
    try:
        if deg is None: return 0.0
        d = float(deg) + float(min or 0) / 60.0
        if hem in ['S', 'W']:
            d = -d
        return d
    except:
        return 0.0

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

@app.route('/api/infra/ports/nearby', methods=['GET'])
def get_nearby_ports():
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
        limit = int(request.args.get('limit', 1))
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # We fetch ports that have latitude/longitude
        query = "SELECT world_port_index_number as id, main_port_name as name, latitude, longitude FROM wpi_import WHERE latitude IS NOT NULL"
        cursor.execute(query)
        ports = cursor.fetchall()
        cursor.close()
        conn.close()
        
        nearby = []
        for p in ports:
            dist = haversine(lat, lon, float(p['latitude']), float(p['longitude']))
            p['distance_km'] = round(dist, 2)
            nearby.append(p)
            
        nearby.sort(key=lambda x: x['distance_km'])
        return jsonify(nearby[:limit])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/infra/ports/continents', methods=['GET'])
def get_continents():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT DISTINCT continent FROM countries WHERE continent IS NOT NULL ORDER BY continent")
        result = cursor.fetchall()
        continents = [row['continent'] for row in result]
        cursor.close()
        conn.close()
        return jsonify(continents)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/infra/ports/countries', methods=['GET'])
def get_countries():
    continent = request.args.get('continent')
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
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

@app.route('/api/infra/ports/continent-nodes', methods=['GET'])
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
        # Count ports per continent by joining wpi_import with countries
        # Note: Collations might be tricky, same as airport service
        query = """
            SELECT c.continent, COUNT(w.world_port_index_number) as count
            FROM wpi_import w
            JOIN countries c ON w.wpi_country_code = c.code COLLATE utf8mb4_general_ci
            WHERE c.continent IS NOT NULL
            GROUP BY c.continent
        """
        cursor.execute(query)
        result = cursor.fetchall()
        cursor.close()
        conn.close()
        
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

@app.route('/api/infra/ports/country-nodes', methods=['GET'])
def get_country_nodes():
    continent = request.args.get('continent')
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Aggregating by country
        query = """
            SELECT c.code, c.name, c.lat, c.lon, COUNT(w.world_port_index_number) as count
            FROM countries c
            JOIN wpi_import w ON c.code = w.wpi_country_code COLLATE utf8mb4_general_ci
            WHERE 1=1
        """
        params = []
        if continent:
            query += " AND c.continent = %s"
            params.append(continent)
        query += " GROUP BY c.code, c.name, c.lat, c.lon ORDER BY c.name"
        cursor.execute(query, params)
        result = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/infra/ports/search', methods=['GET'])
def search_ports():
    continent = request.args.get('continent')
    country = request.args.get('country')
    limit = request.args.get('limit', 2000, type=int)
    
    q = request.args.get('q')
    
    # BBOX Reconnaissance Parameters
    min_lat = request.args.get('min_lat', type=float)
    max_lat = request.args.get('max_lat', type=float)
    min_lng = request.args.get('min_lng', type=float)
    max_lng = request.args.get('max_lng', type=float)

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Join wpi_import with countries and wpi_region (if possible)
        query = """
            SELECT w.*, c.name as country_name, r.area_name
            FROM wpi_import w
            LEFT JOIN countries c ON w.wpi_country_code = c.code COLLATE utf8mb4_general_ci
            LEFT JOIN wpi_region r ON w.world_port_index_number = r.world_port_index_number
            WHERE 1=1
        """
        params = []
        
        if q:
            query += " AND w.main_port_name LIKE %s"
            params.append(f"%{q}%")
        if continent:
            query += " AND c.continent = %s"
            params.append(continent)
        if country:
            query += " AND w.wpi_country_code = %s"
            params.append(country)
            
        # TACTICAL GEOSPATIAL FILTERING (BBOX)
        if all(v is not None for v in [min_lat, max_lat, min_lng, max_lng]):
            query += " AND w.latitude >= %s AND w.latitude <= %s AND w.longitude >= %s AND w.longitude <= %s"
            params.extend([min_lat, max_lat, min_lng, max_lng])
            
        query += " ORDER BY w.main_port_name ASC LIMIT %s"
        params.append(limit)
        
        cursor.execute(query, params)
        result = cursor.fetchall()
        cursor.close()
        conn.close()
        
        ports = []
        for row in result:
            # Prefer accurate decimal columns if available
            lat = row['latitude'] if row.get('latitude') is not None else to_decimal(row['latitude_degrees'], row['latitude_minutes'], row['latitude_hemisphere'])
            lon = row['longitude'] if row.get('longitude') is not None else to_decimal(row['longitude_degrees'], row['longitude_minutes'], row['longitude_hemisphere'])
            
            ports.append({
                "id": row['world_port_index_number'],
                "name": row['main_port_name'],
                "country_code": row['wpi_country_code'],
                "country_name": row['country_name'] or row['wpi_country_code'],
                "area_name": row['area_name'] or "N/A",
                "latitude": float(lat) if lat is not None else 0.0,
                "longitude": float(lon) if lon is not None else 0.0,
                "harbor_size": row['harbor_size_code'],
                "harbor_type": row['harbor_type_code'],
                "publication": row['publication'],
                "chart": row['chart']
            })
            
        return jsonify(ports)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8098, debug=True)
