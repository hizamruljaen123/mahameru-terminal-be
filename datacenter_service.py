from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import sys
import mysql.connector

# Add be directory to path for db.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db import get_db_connection

app = Flask(__name__)
CORS(app)

@app.route('/api/infra/datacenters', methods=['GET'])
def get_datacenters():
    country = request.args.get('country')
    operator = request.args.get('operator')
    q = request.args.get('q')
    limit = request.args.get('limit', 1000, type=int)

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = "SELECT * FROM high_priority_datacenters WHERE 1=1"
        params = []
        
        if country:
            query += " AND country_code = %s"
            params.append(country)
        if operator:
            query += " AND operator_name = %s"
            params.append(operator)
        if q:
            query += " AND (facility_name LIKE %s OR operator_name LIKE %s OR city LIKE %s)"
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
            
        query += " ORDER BY facility_name ASC LIMIT %s"
        params.append(limit)
        
        cursor.execute(query, params)
        result = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/infra/datacenters/country-nodes', methods=['GET'])
def get_country_nodes():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Aggregate by country to get center points and counts
        # Since we don't have a lookup table for country coords, we'll average the lat/lon of DCs in those countries
        query = """
            SELECT 
                country_code as name,
                AVG(CAST(NULLIF(latitude, 'N/A') AS DECIMAL(10,6))) as lat,
                AVG(CAST(NULLIF(longitude, 'N/A') AS DECIMAL(10,6))) as lon,
                COUNT(*) as datacenter_count
            FROM high_priority_datacenters
            WHERE latitude != 'N/A' AND longitude != 'N/A'
            GROUP BY country_code
            ORDER BY country_code ASC
        """
        cursor.execute(query)
        result = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/infra/datacenters/stats', methods=['GET'])
def get_stats():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Stats by Operator
        cursor.execute("SELECT operator_name, COUNT(*) as count FROM high_priority_datacenters GROUP BY operator_name ORDER BY count DESC LIMIT 10")
        by_operator = cursor.fetchall()
        
        # Stats by Country
        cursor.execute("SELECT country_code, COUNT(*) as count FROM high_priority_datacenters GROUP BY country_code ORDER BY count DESC LIMIT 10")
        by_country = cursor.fetchall()
        
        # Stats by Status
        cursor.execute("SELECT operational_status, COUNT(*) as count FROM high_priority_datacenters GROUP BY operational_status")
        by_status = cursor.fetchall()
        
        # Total MW (if available)
        cursor.execute("SELECT SUM(CAST(NULLIF(it_load_mw, 'N/A') AS DECIMAL(10,2))) as total_mw FROM high_priority_datacenters")
        total_mw = cursor.fetchone()['total_mw'] or 0
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "by_operator": by_operator,
            "by_country": by_country,
            "by_status": by_status,
            "total_mw": float(total_mw),
            "total_count": sum(c['count'] for c in by_country)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/infra/datacenters/hub', methods=['GET'])
def get_hub_datacenters():
    mode = request.args.get('mode', 'all') # all, geospatial, non-geospatial
    country = request.args.get('country')
    q = request.args.get('q')
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 100, type=int)

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = "SELECT * FROM datacenter_hub WHERE 1=1"
        count_query = "SELECT COUNT(*) as total FROM datacenter_hub WHERE 1=1"
        params = []
        
        # Mode logic
        mode_cond = ""
        if mode == 'geospatial':
            mode_cond = " AND latitude != 0.0 AND longitude != 0.0"
        elif mode == 'non-geospatial':
            mode_cond = " AND (latitude = 0.0 OR longitude = 0.0)"
        
        query += mode_cond
        count_query += mode_cond

        if country:
            query += " AND country_name = %s"
            count_query += " AND country_name = %s"
            params.append(country)
            
        if q:
            q_cond = " AND (facility_name LIKE %s OR company_name LIKE %s OR city_name LIKE %s OR full_address LIKE %s)"
            query += q_cond
            count_query += q_cond
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"])
            
        # Get total for pagination
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()['total']

        # Pagination logic
        query += " ORDER BY facility_name ASC LIMIT %s OFFSET %s"
        offset = (page - 1) * page_size
        p_params = params + [page_size, offset]
        
        cursor.execute(query, p_params)
        result = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify({
            "data": result,
            "pagination": {
                "total": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": (total_count + page_size - 1) // page_size
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/infra/datacenters/hub/country-nodes', methods=['GET'])
def get_hub_country_nodes():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Aggregate by country
        # For those with lat/lon 0.0, we put them at (0, 0) - Equator/Prime Meridian (Null Island)
        query = """
            SELECT 
                IF(country_name = '' OR country_name IS NULL, 'UNKNOWN_DOMAIN', country_name) as name,
                AVG(IF(latitude = 0, 0, latitude)) as lat,
                AVG(IF(longitude = 0, 0, longitude)) as lon,
                COUNT(*) as datacenter_count
            FROM datacenter_hub
            GROUP BY country_name
            ORDER BY name ASC
        """
        cursor.execute(query)
        result = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/infra/datacenters/hub/stats', methods=['GET'])
def get_hub_stats():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT COUNT(*) as total FROM datacenter_hub")
        total = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(*) as geo_ready FROM datacenter_hub WHERE latitude != 0.0 AND longitude != 0.0")
        geo_ready = cursor.fetchone()['geo_ready']
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "total_records": total,
            "geospatial_ready_count": geo_ready,
            "missing_location_count": total - geo_ready
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8110, debug=True)
