from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import sys
import mysql.connector
import json

# Add be directory to path for db.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db import get_db_connection

app = Flask(__name__)
CORS(app)

@app.route('/api/military-infra', methods=['GET'])
def get_military_facilities():
    try:
        limit = request.args.get('limit', 1000, type=int)
        search = request.args.get('q', '')
        country = request.args.get('country', '')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = "SELECT * FROM military_facilities WHERE 1=1"
        params = []
        
        if search:
            query += " AND (name LIKE %s OR city LIKE %s OR country LIKE %s)"
            params.append(f"%{search}%")
            params.append(f"%{search}%")
            params.append(f"%{search}%")
        
        if country:
            query += " AND country = %s"
            params.append(country)
            
        query += " LIMIT %s"
        params.append(limit)
        
        cursor.execute(query, params)
        facilities = cursor.fetchall()
        
        # Format decimal values for JSON serialization
        for fac in facilities:
            if fac['latitude'] is not None:
                fac['latitude'] = float(fac['latitude'])
            if fac['longitude'] is not None:
                fac['longitude'] = float(fac['longitude'])
                
        cursor.close()
        conn.close()
        return jsonify(facilities)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/military-infra/countries', methods=['GET'])
def get_military_countries():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # JOIN with countries table to get center lat/lon for each country that has military facilities
        query = """
            SELECT c.name, c.lat, c.lon, COUNT(m.id) as facility_count
            FROM countries c
            JOIN military_facilities m ON c.name = m.country
            GROUP BY c.name, c.lat, c.lon
            ORDER BY facility_count DESC
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

@app.route('/api/military-infra/strength', methods=['GET'])
def get_military_strength():
    try:
        country = request.args.get('country', '')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if country:
            query = "SELECT * FROM military_strength WHERE country = %s"
            cursor.execute(query, (country,))
            result = cursor.fetchone()
        else:
            query = "SELECT * FROM military_strength ORDER BY gfp_rank ASC"
            cursor.execute(query)
            result = cursor.fetchall()
            
        cursor.close()
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/military-infra/stats', methods=['GET'])
def get_stats():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Stats by country
        cursor.execute("SELECT country, COUNT(*) as count FROM military_facilities GROUP BY country ORDER BY count DESC LIMIT 15")
        by_country = cursor.fetchall()
        
        # Total global count
        cursor.execute("SELECT COUNT(*) as total FROM military_facilities")
        total = cursor.fetchone()
        
        cursor.close()
        conn.close()
        return jsonify({
            "by_country": by_country,
            "total": total['total']
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/police-infra', methods=['GET'])
def get_police_facilities():
    try:
        limit = request.args.get('limit', 1000, type=int)
        search = request.args.get('q', '')
        country = request.args.get('country', '')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = "SELECT * FROM police_facilities WHERE 1=1"
        params = []
        
        if search:
            query += " AND (hq_name LIKE %s OR organization_name LIKE %s OR city LIKE %s OR country LIKE %s)"
            params.append(f"%{search}%")
            params.append(f"%{search}%")
            params.append(f"%{search}%")
            params.append(f"%{search}%")
        
        if country:
            query += " AND country = %s"
            params.append(country)
            
        query += " LIMIT %s"
        params.append(limit)
        
        cursor.execute(query, params)
        facilities = cursor.fetchall()
        
        # Format decimal values for JSON serialization
        for fac in facilities:
            if fac['latitude'] is not None:
                fac['latitude'] = float(fac['latitude'])
            if fac['longitude'] is not None:
                fac['longitude'] = float(fac['longitude'])
                
        cursor.close()
        conn.close()
        return jsonify(facilities)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/police-infra/countries', methods=['GET'])
def get_police_countries():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = """
            SELECT c.name, c.lat, c.lon, COUNT(p.id) as facility_count
            FROM countries c
            JOIN police_facilities p ON c.name = p.country
            GROUP BY c.name, c.lat, c.lon
            ORDER BY facility_count DESC
        """
        cursor.execute(query)
        result = cursor.fetchall()
        
        for row in result:
            if row['lat'] is not None: row['lat'] = float(row['lat'])
            if row['lon'] is not None: row['lon'] = float(row['lon'])
            
        cursor.close()
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/infra-combined/stats', methods=['GET'])
def get_combined_stats():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Military stats
        cursor.execute("SELECT COUNT(*) as total FROM military_facilities")
        mil_total = cursor.fetchone()['total']
        
        # Police stats
        cursor.execute("SELECT COUNT(*) as total FROM police_facilities")
        pol_total = cursor.fetchone()['total']
        
        # Top military countries
        cursor.execute("SELECT country, COUNT(*) as count FROM military_facilities GROUP BY country ORDER BY count DESC LIMIT 10")
        mil_top = cursor.fetchall()
        
        # Top police countries
        cursor.execute("SELECT country, COUNT(*) as count FROM police_facilities GROUP BY country ORDER BY count DESC LIMIT 10")
        pol_top = cursor.fetchall()
        
        cursor.close()
        conn.close()
        return jsonify({
            "military_total": mil_total,
            "police_total": pol_total,
            "military_top": mil_top,
            "police_top": pol_top
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Use port 8160 for Military Service
    app.run(host='0.0.0.0', port=8160, debug=True)
