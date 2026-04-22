from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import sys

# Add be directory to path for db.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db import get_db_connection

import requests
import time

app = Flask(__name__)
CORS(app)

# Simple in-memory cache for Nominatim results
GEO_CACHE = {}

def geocode_nominatim(query):
    if query in GEO_CACHE:
        return GEO_CACHE[query]
    
    try:
        url = f"https://nominatim.openstreetmap.org/search?q={requests.utils.quote(query)}&format=json&limit=1"
        headers = {
            'User-Agent': 'ENQY-Terminal/1.0 (contact: info@asetpedia.ai)'
        }
        response = requests.get(url, headers=headers, timeout=5)
        data = response.json()
        if data:
            result = (float(data[0]['lat']), float(data[0]['lon']))
            GEO_CACHE[query] = result
            return result
    except Exception as e:
        print(f"Geocoding error for {query}: {e}")
    
    return None

@app.route('/api/gov-facilities/types', methods=['GET'])
def get_types():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT DISTINCT facility_type FROM government_facilities WHERE facility_type IS NOT NULL ORDER BY facility_type")
        result = cursor.fetchall()
        types = [row['facility_type'] for row in result]
        cursor.close()
        conn.close()
        return jsonify(types)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/gov-facilities/countries', methods=['GET'])
def get_countries():
    facility_type = request.args.get('type')
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = """
            SELECT DISTINCT g.country, c.lat, c.lon 
            FROM government_facilities g
            LEFT JOIN countries c ON g.country = c.name
            WHERE 1=1
        """
        params = []
        if facility_type:
            query += " AND g.facility_type = %s"
            params.append(facility_type)
        
        query += " HAVING lat IS NOT NULL"
        query += " ORDER BY g.country"
        cursor.execute(query, params)
        result = cursor.fetchall()
        
        # Format numeric fields
        for row in result:
            if row['lat']: row['lat'] = float(row['lat'])
            if row['lon']: row['lon'] = float(row['lon'])
            
        cursor.close()
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/gov-facilities/represented-countries', methods=['GET'])
def get_represented_countries():
    facility_type = request.args.get('type')
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = "SELECT DISTINCT operator FROM government_facilities WHERE 1=1"
        params = []
        if facility_type:
            query += " AND facility_type = %s"
            params.append(facility_type)
        
        query += " ORDER BY operator"
        cursor.execute(query, params)
        result = cursor.fetchall()
        countries = [row['operator'] for row in result]
        cursor.close()
        conn.close()
        return jsonify(countries)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/gov-facilities/list', methods=['GET'])
def get_facilities():
    facility_type = request.args.get('type')
    country = request.args.get('country') # Represented country (operator)
    location = request.args.get('location') # Physical location (country)
    limit = request.args.get('limit', 500, type=int)
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = """
            SELECT g.*, c.code as repr_code 
            FROM government_facilities g
            LEFT JOIN countries c ON g.operator = c.name
            WHERE 1=1
        """
        params = []
        
        if facility_type:
            query += " AND g.facility_type = %s"
            params.append(facility_type)
        if country:
            query += " AND g.operator = %s"
            params.append(country)
        if location:
            query += " AND g.country = %s"
            params.append(location)
            
        query += " LIMIT %s"
        params.append(limit)
        
        cursor.execute(query, params)
        result = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Format numeric fields and geocode if missing
        conn = get_db_connection()
        cursor = conn.cursor()
        
        for row in result:
            if row['latitude'] and row['longitude']:
                row['latitude'] = float(row['latitude'])
                row['longitude'] = float(row['longitude'])
            else:
                # Try geocoding fallback
                # Try specific first, then more general
                queries = [
                    f"{row['operator']}, {row['city']}, {row['country']}",
                    f"{row['operator']}, {row['country']}",
                    f"{row['city']}, {row['country']}"
                ]
                
                coords = None
                for q in queries:
                    coords = geocode_nominatim(q)
                    if coords: break
                    time.sleep(1) # Respect Nominatim rate limit (1req/s)
                
                if coords:
                    row['latitude'], row['longitude'] = coords
                    # Update database for future fast access
                    try:
                        cursor.execute(
                            "UPDATE government_facilities SET latitude = %s, longitude = %s WHERE id = %s",
                            (coords[0], coords[1], row['id'])
                        )
                        conn.commit()
                    except: pass
                else:
                    row['latitude'], row['longitude'] = None, None
                    row['geocoding_failed'] = True

        cursor.close()
        conn.close()
            
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/strategic-projects/list', methods=['GET'])
def get_strategic_projects():
    category = request.args.get('category')
    country = request.args.get('country')
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = "SELECT * FROM strategic_projects WHERE 1=1"
        params = []
        if category:
            query += " AND category = %s"
            params.append(category)
        if country:
            query += " AND country = %s"
            params.append(country)
            
        cursor.execute(query, params)
        result = cursor.fetchall()
        for row in result:
            if row['latitude']: row['latitude'] = float(row['latitude'])
            if row['longitude']: row['longitude'] = float(row['longitude'])
            if row['budget_usd']: row['budget_usd'] = float(row['budget_usd'])
        cursor.close()
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/strategic-projects/summary', methods=['GET'])
def get_project_summary():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Get countries with projects
        cursor.execute("SELECT DISTINCT country FROM strategic_projects ORDER BY country")
        countries = [row['country'] for row in cursor.fetchall()]
        
        # Get categories
        cursor.execute("SELECT DISTINCT category FROM strategic_projects ORDER BY category")
        categories = [row['category'] for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        return jsonify({"countries": countries, "categories": categories})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8150, debug=True)
