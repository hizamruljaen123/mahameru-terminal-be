import asyncio
import websockets
import json
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import List, Dict, Any
import os
from db_utils import execute_query

from utils.ais_utils import get_country_from_mmsi

# AIS Metadata Mappings
VESSEL_TYPES = {
    0: "Not Available",
    30: "Fishing",
    31: "Towing",
    32: "Towing (Large)",
    33: "Dredging/Underwater Ops",
    35: "Military",
    36: "Sailing",
    37: "Pleasure Craft",
    50: "Pilot Vessel",
    51: "Search and Rescue",
    52: "Tug",
    53: "Port Tender",
    55: "Law Enforcement",
    58: "Medical Transport",
    60: "Passenger",
    70: "Cargo",
    80: "Tanker",
    90: "Other"
}

NAV_STATUS = {
    0: "Under Way (Engine)",
    1: "At Anchor",
    2: "Not Under Command",
    3: "Restricted Maneuverability",
    4: "Constrained by Draught",
    5: "Moored",
    6: "Aground",
    7: "Engaged in Fishing",
    8: "Under Way (Sailing)",
    15: "Undefined"
}

def get_vessel_type(code):
    if code in VESSEL_TYPES: return VESSEL_TYPES[code]
    if 40 <= code <= 49: return "High Speed Craft"
    if 60 <= code <= 69: return "Passenger"
    if 70 <= code <= 79: return "Cargo"
    if 80 <= code <= 89: return "Tanker"
    if 90 <= code <= 99: return "Other"
    return "Unknown"

def get_nav_status(code):
    return NAV_STATUS.get(code, "Unknown")

# Updated API Key from User
AIS_API_KEY = os.getenv("AIS_API_KEY", "d4764a763a57c99a2cc62f3562c0ef6a4b4043de")

def archive_ship_to_db(ship):
    """Saves vessel state to MySQL for historical audit."""
    sql = """
        INSERT INTO ais_history (mmsi, name, type, lat, lon, speed, heading, status, destination)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    params = (
        ship.get("mmsi"), ship.get("name"), ship.get("type"),
        ship.get("lat"), ship.get("lon"), ship.get("speed"),
        ship.get("heading"), ship.get("status"), ship.get("destination")
    )
    try:
        execute_query(sql, params, commit=True)
    except Exception as e:
        print(f"Archive Error: {e}")

# In-memory storage for ship tracking
ships_cache = {}
active_ports_cache = []
msg_count = 0
is_connected = False
connected_clients: List[Dict[str, Any]] = []
dynamic_aois: Dict[str, List[List[float]]] = {} # { "key": [ [lat_min, lon_min], [lat_max, lon_max] ] }
current_bbox = [[-90, -180], [90, 180]]

async def get_combined_bbox():
    """
    Combines BBoxes from all connected clients and active dynamic AOIs.
    """
    lat_min, lon_min = 90.0, 180.0
    lat_max, lon_max = -90.0, -180.0
    any_bbox = False
    
    # 1. From Connected WebSocket Clients
    for c in connected_clients:
        if c.get("bbox"):
            any_bbox = True
            b = c["bbox"]
            lat_min = min(lat_min, b[0][0]); lon_min = min(lon_min, b[0][1])
            lat_max = max(lat_max, b[1][0]); lon_max = max(lon_max, b[1][1])
            
    # 2. From Dynamic REST AOIs (Automated Radar)
    for b in dynamic_aois.values():
        any_bbox = True
        lat_min = min(lat_min, b[0][0]); lon_min = min(lon_min, b[0][1])
        lat_max = max(lat_max, b[1][0]); lon_max = max(lon_max, b[1][1])

    if not any_bbox:
        return [[-90, -180], [90, 180]]
        
    return [[lat_min - 0.1, lon_min - 0.1], [lat_max + 0.1, lon_max + 0.1]]

async def connect_ais_stream():
    global msg_count, is_connected, ships_cache, current_bbox
    url = "wss://stream.aisstream.io/v0/stream"
    while True:
        if not connected_clients and not dynamic_aois:
            is_connected = False
            await asyncio.sleep(5)
            continue
        try:
            current_bbox = await get_combined_bbox()
            print(f"Connecting to AIS Stream with BBox: {current_bbox}")
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as websocket:
                is_connected = True
                subscribe_msg = {
                    "APIKey": AIS_API_KEY,
                    "BoundingBoxes": [current_bbox], 
                    "FilterMessageTypes": ["PositionReport", "ShipStaticData"] 
                }
                await websocket.send(json.dumps(subscribe_msg))
                while connected_clients or dynamic_aois:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        data = json.loads(message)
                        meta = data.get("MetaData", {})
                        mmsi = meta.get("MMSI")
                        lat = meta.get("latitude")
                        lon = meta.get("longitude")
                        if mmsi and lat is not None and lon is not None:
                            msg_type = data.get("MessageType")
                            
                            # Retrieve or initialize ship state
                            c_name, c_code = get_country_from_mmsi(mmsi)
                            ship_data = ships_cache.get(mmsi, {
                                "mmsi": mmsi,
                                "name": "UNKNOWN",
                                "type": "Unknown",
                                "country_name": c_name,
                                "country_code": c_code,
                                "infra_type": "vessel",
                                "status": "Unknown",
                                "destination": "N/A",
                                "eta": "N/A",
                                "heading": 0,
                                "speed": 0
                            })
                            
                            # Update base telemetry
                            ship_data["lat"] = lat
                            ship_data["lon"] = lon
                            ship_data["timestamp"] = meta.get("time_utc", "")
                            if meta.get("ShipName"):
                                ship_data["name"] = meta.get("ShipName").strip()

                            # Extract Message-Specific Data
                            message_payload = data.get("Message", {})
                            
                            if msg_type == "PositionReport":
                                pos = message_payload.get("PositionReport", {})
                                ship_data["heading"] = pos.get("TrueHeading", 0)
                                ship_data["speed"] = pos.get("Sog", 0)
                                ship_data["status"] = get_nav_status(pos.get("NavigationalStatus", 15))
                                ship_data["rot"] = pos.get("RateOfTurn", 0)
                                ship_data["pos_accuracy"] = "HIGH" if pos.get("PositionAccuracy", False) else "LOW"
                                
                            elif msg_type == "ShipStaticData":
                                stat = message_payload.get("ShipStaticData", {})
                                ship_data["type"] = get_vessel_type(stat.get("Type", 0))
                                ship_data["destination"] = stat.get("Destination", "N/A")
                                ship_data["eta"] = f"{stat.get('EtaMonth', 0)}/{stat.get('EtaDay', 0)} {stat.get('EtaHour', 0)}:{stat.get('EtaMinute', 0)}"
                                ship_data["fix_type"] = stat.get("FixType", "Unknown")
                                if stat.get("CallSign"):
                                    ship_data["callsign"] = stat.get("CallSign").strip()
                                if stat.get("Imo"):
                                    ship_data["imo"] = stat.get("Imo")
                                ship_data["draught"] = stat.get("MaximumStaticDraught", 0) / 10.0
                                dim = stat.get("Dimension", {})
                                ship_data["length"] = dim.get("A", 0) + dim.get("B", 0)
                                ship_data["width"] = dim.get("C", 0) + dim.get("D", 0)

                            msg_count += 1
                            ships_cache[mmsi] = ship_data
                            
                            # Archive to DB every 50 messages to prevent flooding, 
                            # or specifically for Tankers of interest.
                            if msg_count % 50 == 0 or "Tanker" in ship_data.get("type", ""):
                                archive_ship_to_db(ship_data)
                            
                            payload = json.dumps({"type": "update", "data": ship_data})
                            for client_obj in connected_clients[:]:
                                try:
                                    bbox = client_obj.get("bbox")
                                    if bbox:
                                        if not (bbox[0][0] <= lat <= bbox[1][0] and bbox[0][1] <= lon <= bbox[1][1]):
                                            continue
                                    await client_obj["ws"].send_text(payload)
                                except:
                                    if client_obj in connected_clients:
                                        connected_clients.remove(client_obj)
                    except asyncio.TimeoutError:
                        new_bbox = await get_combined_bbox()
                        if new_bbox != current_bbox:
                            print("BBOX shifted. Re-subscribing...")
                            break
                        continue
                    if len(ships_cache) > 2000:
                        ships_cache.pop(next(iter(ships_cache)))
        except websockets.exceptions.ConnectionClosed as e:
            is_connected = False
            print(f"[AIS-STREAM] Connection Closed: {e.code} - {e.reason if hasattr(e, 'reason') else 'No reason'}")
            if not AIS_API_KEY:
                print("[AIS-STREAM] WARNING: AIS_API_KEY is missing. Check your .env file.")
            await asyncio.sleep(8)
        except Exception as e:
            is_connected = False
            print(f"[AIS-STREAM] Unexpected Error: {e}")
            await asyncio.sleep(10)

async def background_port_intelligence_task():
    """Periodically updates port intelligence."""
    while True:
        await update_port_intelligence()
        await asyncio.sleep(30) # Refresh every 30 seconds

@asynccontextmanager
async def lifespan(app: FastAPI):
    ais_task = asyncio.create_task(connect_ais_stream())
    intel_task = asyncio.create_task(background_port_intelligence_task())
    yield
    ais_task.cancel()
    intel_task.cancel()

app = FastAPI(debug=True, title="AIS Naval Microservice", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.websocket("/ws/port-intelligence")
@app.websocket("/ais/ws/port-intelligence")
async def websocket_port_intel(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json({
                "type": "PORT_UPDATE",
                "status": "success",
                "data": active_ports_cache
            })
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[PORT_INTEL_WS_ERROR] {e}")

@app.websocket("/ws/ships")
@app.websocket("/ais/ws/ships")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    client_data = {"ws": websocket, "bbox": None}
    connected_clients.append(client_data)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "subscribe":
                bbox = msg.get("bbox")
                client_data["bbox"] = bbox
                filtered_cache = []
                if bbox:
                    for s in list(ships_cache.values()):
                        if bbox[0][0] <= s["lat"] <= bbox[1][0] and bbox[0][1] <= s["lon"] <= bbox[1][1]:
                            filtered_cache.append(s)
                else:
                    filtered_cache = list(ships_cache.values())
                await websocket.send_text(json.dumps({"type": "initial", "data": filtered_cache}))
    except WebSocketDisconnect:
        pass
    finally:
        if client_data in connected_clients:
            connected_clients.remove(client_data)

@app.get("/api/ships")
@app.get("/ais/api/ships")
def get_live_ships():
    return {
        "status": "online" if is_connected else "idle",
        "msg_count": msg_count,
        "active_clients": len(connected_clients),
        "total_cached": len(ships_cache),
        "ships": list(ships_cache.values())
    }

@app.get("/api/ais/anomalies")
@app.get("/ais/api/ais/anomalies")
def get_ais_anomalies():
    """
    Detects vessels with unusual status or behaviors:
    - Status: Aground, Not Under Command, Restricted Maneuverability
    - High Speed for non-fast vessels
    - Unusual ROT (Rate of Turn)
    """
    anomalies = []
    for mmsi, ship in list(ships_cache.items()):
        reasons = []
        status = ship.get("status", "Unknown")
        speed = ship.get("speed", 0)
        v_type = ship.get("type", "Unknown")
        rot = ship.get("rot", 0)

        # 1. Critical Status
        if status in ["Aground", "Not Under Command", "Restricted Maneuverability"]:
            reasons.append(f"Critical Status: {status}")
        
        # 2. Speed Anomaly (e.g., Fishing boat > 25 knots)
        if "Fishing" in v_type and speed > 25:
            reasons.append(f"High Speed for Fishing Vessel: {speed} knots")
        elif "Cargo" in v_type and speed > 35:
            reasons.append(f"High Speed for Cargo: {speed} knots")
        
        # 3. ROT Anomaly
        if abs(rot) > 700: # Very sharp turn/spinning
            reasons.append(f"Excessive Rate of Turn: {rot}")

        if reasons:
            anomaly_data = ship.copy()
            anomaly_data["anomaly_reasons"] = reasons
            anomalies.append(anomaly_data)
            
    return {
        "status": "success",
        "count": len(anomalies),
        "data": anomalies
    }

@app.get("/api/proximity/vessels")
@app.get("/ais/api/proximity/vessels")
async def get_nearby_vessels(
    lat: float = Query(..., description="Center Latitude"),
    lon: float = Query(..., description="Center Longitude"),
    radius: float = Query(100.0, description="Scanning radius in KM")
):
    """
    Scans the live ships_cache for vessels within a specific radius.
    Also registers the area for dynamic AIS tracking if not already active.
    """
    import math

    # 1. Register AOI for dynamic background scanning (BBox ±0.5 deg ~ 50-60km)
    aoi_key = f"{round(lat,1)}_{round(lon,1)}"
    dynamic_aois[aoi_key] = [[lat - 0.5, lon - 0.5], [lat + 0.5, lon + 0.5]]

    def haversine(lat1, lon1, lat2, lon2):
        R = 6371  # Earth radius in KM
        dLat = math.radians(lat2 - lat1)
        dLon = math.radians(lon2 - lon1)
        a = (math.sin(dLat / 2) * math.sin(dLat / 2) +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
             math.sin(dLon / 2) * math.sin(dLon / 2))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    nearby_vessels = []
    for mmsi, ship in list(ships_cache.items()):
        ship_lat = ship.get("lat")
        ship_lon = ship.get("lon")
        if ship_lat is not None and ship_lon is not None:
            dist = haversine(lat, lon, ship_lat, ship_lon)
            if dist <= radius:
                vessel_data = ship.copy()
                vessel_data["distance"] = dist
                vessel_data["infra_type"] = "vessel"
                nearby_vessels.append(vessel_data)
    
    nearby_vessels.sort(key=lambda x: x["distance"])
    
    return {
        "status": "success",
        "acquisition": "tracking_active",
        "count": len(nearby_vessels),
        "data": nearby_vessels
    }

# ============================================================
# PORT INTELLIGENCE (SQL MATCHING)
# ============================================================

async def update_port_intelligence():
    """
    Correlates live ships_cache with wpi_import ports.
    Runs periodically to identify ports with active vessel presence.
    """
    global active_ports_cache
    try:
        # 1. Fetch all ports (or filter by bounding box if needed)
        # We fetch minimal data to keep it fast
        sql = "SELECT world_port_index_number as id, main_port_name as name, latitude, longitude, wpi_country_code FROM wpi_import WHERE latitude IS NOT NULL"
        ports = execute_query(sql)
        
        current_ships = list(ships_cache.values())
        if not current_ships:
            active_ports_cache = []
            return

        active_map = {}
        
        # 2. Match ships to ports (Radius ~2km)
        for p in ports:
            p_lat = float(p['latitude'])
            p_lon = float(p['longitude'])
            
            vessels_at_port = []
            for s in current_ships:
                s_lat = s.get('lat')
                s_lon = s.get('lon')
                if s_lat is None or s_lon is None: continue
                
                # Fast distance check (approx 2km)
                if abs(s_lat - p_lat) < 0.02 and abs(s_lon - p_lon) < 0.02:
                    vessels_at_port.append({
                        "mmsi": s.get("mmsi"),
                        "name": s.get("name")
                    })
            
            if vessels_at_port:
                active_map[p['id']] = {
                    "id": p['id'],
                    "name": p['name'],
                    "latitude": p_lat,
                    "longitude": p_lon,
                    "country": p['wpi_country_code'],
                    "vessel_count": len(vessels_at_port),
                    "vessels": vessels_at_port
                }
        
        active_ports_cache = list(active_map.values())
        print(f"[PORT_INTEL] Detected {len(active_ports_cache)} active ports")
    except Exception as e:
        print(f"[PORT_INTEL_ERROR] {e}")

@app.get("/api/intelligence/active-ports")
async def get_active_ports(country: str = None):
    """Returns ports with detected vessels."""
    data = active_ports_cache
    if country:
        data = [p for p in data if p['country'] == country]
    return {"status": "success", "data": data}

@app.get("/")
@app.get("/ais")
async def root():
    return {"status": "online", "service": "ais_tracking_service"}

if __name__ == "__main__":
    uvicorn.run("ais_service:app", host="0.0.0.0", port=8080)
