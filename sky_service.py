import os
from flask import Flask, jsonify
from flask_cors import CORS
import requests
import time

app = Flask(__name__)
CORS(app) # Enable CORS for Solid JS FE

# ST Tactical Bounding Boxes (lamin, lomin, lamax, lomax)
COUNTRY_BOUNDS = {
    "AFG": [29.3, 60.4, 38.5, 74.9], "DZA": [18.9, -8.7, 37.1, 12.0], "AUS": [-43.7, 112.9, -9.1, 159.1], 
    "BRA": [-33.7, -74.0, 5.3, -28.8], "CAN": [41.7, -141.0, 83.1, -52.6], "CHN": [18.1, 73.5, 53.6, 134.8], 
    "FRA": [42.3, -5.2, 51.1, 9.6], "DEU": [47.3, 5.8, 55.1, 15.1], "IND": [6.7, 68.2, 35.5, 97.4], 
    "IDN": [-11.0, 95.0, 6.1, 141.0], "IRN": [25.0, 44.0, 40.0, 63.3], "ITA": [35.5, 6.6, 47.1, 18.5], 
    "JPN": [24.0, 122.9, 45.6, 154.0], "MYS": [0.8, 98.4, 7.4, 119.3], "MEX": [14.5, -118.4, 32.7, -86.7], 
    "NLD": [50.7, 3.3, 53.6, 7.2], "RUS": [41.2, 19.6, 81.9, 190.5], "SGP": [1.1, 103.6, 1.5, 104.1], 
    "ESP": [36.0, -9.3, 43.8, 3.3], "GBR": [49.8, -8.7, 60.9, 1.8], "USA": [24.4, -124.8, 49.4, -66.9], 
    "VNM": [8.5, 102.1, 23.4, 109.5]
}

COUNTRY_NAMES = {
    "AFG": "Afghanistan", "DZA": "Algeria", "AUS": "Australia", "BRA": "Brazil", "CAN": "Canada", 
    "CHN": "China", "FRA": "France", "DEU": "Germany", "IND": "India", "IDN": "Indonesia", 
    "IRN": "Iran", "ITA": "Italy", "JPN": "Japan", "MYS": "Malaysia", "MEX": "Mexico", 
    "NLD": "Netherlands", "RUS": "Russia", "SGP": "Singapore", "ESP": "Spain", "GBR": "United Kingdom", 
    "USA": "United States", "VNM": "Vietnam"
}

OPENSKY_URL = os.getenv("OPENSKY_API_BASE", "https://opensky-network.org/api/states/all")

@app.route('/api/sky/countries')
def get_countries():
    meta = [{"code": c, "name": COUNTRY_NAMES.get(c, c), "coords": [(b[0]+b[2])/2, (b[1]+b[3])/2]} for c, b in COUNTRY_BOUNDS.items()]
    return jsonify(sorted(meta, key=lambda x: x['name']))

@app.route('/api/sky/aircraft/<country_code>')
def get_aircraft(country_code):
    bounds = COUNTRY_BOUNDS.get(country_code.upper())
    if not bounds: return jsonify({"error": "Bounds not found"}), 404
    
    params = {"lamin": bounds[0], "lomin": bounds[1], "lamax": bounds[2], "lomax": bounds[3]}
    try:
        resp = requests.get(OPENSKY_URL, params=params, timeout=10)
        data = resp.json()
        states = data.get("states", [])
        formatted = []
        if states:
            for s in states:
                if s[5] and s[6]:
                    formatted.append({
                        "icao24": s[0], "callsign": (s[1] or "").strip(), "origin_country": s[2], "lng": s[5], "lat": s[6],
                        "alt": s[7], "spd": round((s[9] or 0) * 3.6, 1), "track": s[10]
                    })
        return jsonify({"states": formatted, "total": len(formatted)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sky/route/<callsign>')
def get_route(callsign):
    url = f"https://opensky-network.org/api/routes?callsign={callsign.strip()}"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return jsonify(resp.json())
        return jsonify({"error": "Route not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("Starting Sky/Aviation Service on port 5002...")
    app.run(host=os.getenv('API_HOST', '0.0.0.0'), debug=True, port=5002, use_reloader=False)
