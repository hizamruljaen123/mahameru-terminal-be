import os
import mysql.connector
from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime
from dotenv import load_dotenv


load_dotenv()

app = Flask(__name__)
CORS(app)

import re

def safe_int(value, default=0):
    if value is None: return default
    if isinstance(value, int): return value
    # Extract the first sequence of digits
    match = re.search(r'\d+', str(value).replace('.', '').replace(',', ''))
    if match:
        try:
            return int(match.group())
        except:
            return default
    return default

def calculate_source_credibility(row: dict) -> float:
    base = 0.5
    if row.get('jumlah_korban_meninggal'):
        fatalities = safe_int(row.get('jumlah_korban_meninggal'))
        if fatalities > 100:
            base += 0.3
        elif fatalities > 50:
            base += 0.2
        elif fatalities > 10:
            base += 0.1
    if row.get('sumber') and any(x in str(row.get('sumber', '')).lower() for x in ['official', 'reuters', 'ap', 'al jazeera']):
        base += 0.3
    if row.get('verifikasi') and 'terverifikasi' in str(row.get('verifikasi', '')).lower():
        base += 0.2
    return min(base, 1.0)


def calculate_impact_score(row: dict) -> float:
    severity = float(row.get('index_keparahan', 50))
    impact = severity / 100.0
    fatalities = safe_int(row.get('jumlah_korban_meninggal'))
    if fatalities > 100:
        impact += 0.2
    elif fatalities > 50:
        impact += 0.1
    return min(impact, 1.0)


def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "asetpedia")
    )

@app.route('/api/conflict/summary', methods=['GET'])
def get_conflict_summary():
    """Returns all conflict events from the database."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # We fetch all fields for the dashboard
        cursor.execute("SELECT * FROM global_conflicts ORDER BY index_keparahan DESC")
        rows = cursor.fetchall()
        
        # Format decimal to float for JSON stability
        for row in rows:
            if row['latitude']: row['latitude'] = float(row['latitude'])
            if row['longitude']: row['longitude'] = float(row['longitude'])
            # Add mapping for frontend compatibility
            row['country'] = row['negara']
            row['event_type'] = row['detail_konflik']
            row['fatalities'] = row['jumlah_korban_meninggal']
            row['id'] = row['id']
            
            # Crisis Watcher metadata
            row['impact_score'] = calculate_impact_score(row)
            row['source_credibility_index'] = calculate_source_credibility(row)
            
        cursor.close()
        conn.close()
        
        
        return jsonify(rows)
    except Exception as e:
        print(f"[CONFLICT_SERVICE] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/conflict/stats', methods=['GET'])
def get_conflict_stats():
    """Returns top level statistics."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT COUNT(*) as total_conflicts, SUM(index_keparahan)/COUNT(*) as avg_severity FROM global_conflicts")
        stats = cursor.fetchone()
        
        cursor.close()
        conn.close()
        return jsonify(stats)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/health')
def health():
    return jsonify({
        "status": "online", 
        "service": "global_conflict_intelligence_hub", 
        "db": "connected",
        "timestamp": datetime.now().isoformat()
    })

if __name__ == '__main__':
    print("Starting GLOBAL CONFLICT INTELLIGENCE SERVICE on port 8140...")
    app.run(host='0.0.0.0', port=8140, debug=True)
