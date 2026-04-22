import math
from datetime import datetime, timedelta

def haversine_km(lat1, lon1, lat2, lon2):
    """Distance between two points in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def calculate_smart_eta(current_lat, current_lon, dest_lat, dest_lon, speed_knots, weather_penalty=1.0):
    """
    Calculates ETA based on speed, distance, and weather impact.
    weather_penalty: 1.0 = normal, < 1.0 = slower (e.g. 0.8 during storm)
    """
    dist_km = haversine_km(current_lat, current_lon, dest_lat, dest_lon)
    dist_nm = dist_km * 0.539957

    if speed_knots < 0.2:
        return {
            "status": "STATIONARY", 
            "hours": None, 
            "distance_km": round(dist_km, 2),
            "weather_impact": "0% (Stationary)"
        }
    
    # Adjust speed by weather penalty
    effective_speed = speed_knots * weather_penalty
    if effective_speed <= 0: return {"status": "BLOCKED", "hours": None}
    
    hours = dist_nm / effective_speed
    arrival_time = datetime.now() + timedelta(hours=hours)
    
    return {
        "status": "EN_ROUTE",
        "distance_km": round(dist_km, 2),
        "hours": round(hours, 1),
        "eta": arrival_time.isoformat(),
        "weather_impact": f"{int((1-weather_penalty)*100)}% speed reduction"
    }

def detect_vessel_clustering(vessels, target_lat, target_lon, radius_km=10, min_speed=1.0):
    """
    Detects clusters of vessels (queues) near a facility.
    """
    cluster = []
    for v in vessels:
        v_lat = v.get("lat") or v.get("latitude")
        v_lon = v.get("lon") or v.get("longitude")
        if v_lat is None or v_lon is None: continue
        
        dist = haversine_km(v_lat, v_lon, target_lat, target_lon)
        v_speed = float(v.get("speed", 0))
        
        if dist <= radius_km and v_speed < min_speed:
            cluster.append({
                "mmsi": v.get("mmsi"),
                "name": v.get("name"),
                "distance": round(dist, 2),
                "speed": v_speed
            })
    
    return {
        "count": len(cluster),
        "vessels": cluster,
        "intensity": "HIGH" if len(cluster) > 5 else ("MEDIUM" if len(cluster) > 2 else "LOW")
    }

def calculate_crack_spread(crude_price, gasoline_price, diesel_price):
    """
    Simulated 3-2-1 Crack Spread Logic:
    (3 barrels of crude -> 2 gasoline + 1 diesel)
    """
    if not all([crude_price, gasoline_price, diesel_price]):
        return None
        
    # Standard formula: ( (2 * Gasoline) + (1 * Diesel) - (3 * Crude) ) / 3
    # Prices should be in same units ($/bbl)
    spread = ((2 * gasoline_price) + (1 * diesel_price) - (3 * crude_price)) / 3
    
    return {
        "spread_value": round(spread, 2),
        "margin_status": "HIGH" if spread > 15 else ("NORMAL" if spread > 8 else "THIN"),
        "timestamp": datetime.now().isoformat()
    }

def check_storm_proximity(vessel_lat, vessel_lon, storm_center_lat, storm_center_lon, radius_km=200):
    """Checks if a vessel is within a storm's danger radius."""
    dist = haversine_km(vessel_lat, vessel_lon, storm_center_lat, storm_center_lon)
    
    if dist < radius_km:
        risk_score = (1 - (dist / radius_km)) * 100
        return {
            "in_danger": True,
            "distance_km": round(dist, 2),
            "risk_score": round(risk_score, 1),
            "alert": "CRITICAL" if dist < 50 else "WARNING"
        }
    return {"in_danger": False, "distance_km": round(dist, 2)}
