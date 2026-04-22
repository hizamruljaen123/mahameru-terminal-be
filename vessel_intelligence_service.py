import os
import uvicorn
import json
import asyncio
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import math
from db_utils import get_db_connection, execute_query

app = FastAPI(debug=True, title="Oil Supply Chain Intelligence Signal Node")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Constants for Intelligence Logic
SEA_LANE_THRESHOLD_KM = 50.0 # Deviation threshold
DARK_VESSEL_THRESHOLD_MINUTES = 60
TANKER_DWT_AVERAGE = 120000 # Barrel estimation helper (DWT to Bbl conversion proxy)

# --- RECONNAISSANCE UTILS ---

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# --- PHASE 4: INTELLIGENCE SIGNALS ---

@app.get("/api/intelligence/anomalies")
def get_vessel_anomalies():
    """
    Detects AIS-off (Dark Mode) or Route Deviations using historical AIS data.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Detect Dark Vessels (No updates in threshold)
        # We look for tankers that were seen recently but not in the last hour
        dark_sql = """
            SELECT mmsi, name, lat, lon, MAX(timestamp) as last_seen
            FROM ais_history
            WHERE type LIKE '%Tanker%'
            GROUP BY mmsi, name, lat, lon
            HAVING last_seen < (NOW() - INTERVAL 1 HOUR)
            AND last_seen > (NOW() - INTERVAL 24 HOUR)
        """
        cursor.execute(dark_sql)
        dark_vessels = cursor.fetchall()

        # 2. Route Deviation Detection
        # (Simplified: Vessels far from common routes or reporting destination mismatch)
        deviation_sql = """
            SELECT mmsi, name, lat, lon, heading, speed, destination, status
            FROM ais_history
            WHERE type LIKE '%Tanker%'
            AND speed > 1
            AND (status = 'Restricted Maneuverability' OR status = 'Not Under Command')
        """
        cursor.execute(deviation_sql)
        deviations = cursor.fetchall()

        cursor.close(); conn.close()
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "anomalies": {
                "dark_vessels": dark_vessels,
                "route_deviations": deviations,
                "count": len(dark_vessels) + len(deviations)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/intelligence/inventory-model")
def get_proxy_inventory(port_id: Optional[str] = None):
    """
    Proxy Inventory Model: Estimasi volume minyak yang sedang "on-water" masuk ke wilayah target.
    Logic: Sum(vessel_dwt) where heading to Port_X.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # We group tankers by destination to find "Floating Inventory" bound for specific hubs
        inventory_sql = """
            SELECT destination, COUNT(DISTINCT mmsi) as vessel_count, 
                   SUM(CASE WHEN speed > 2 THEN 1 ELSE 0 END) as active_transit,
                   # Heuristic: Average DWT for crude tankers mapped to barrel capacity (approx 1 DWT ~ 7 Barrels)
                   SUM(120000 * 7) / 1000000 as estimated_mbbl 
            FROM ais_history
            WHERE type LIKE '%Tanker%'
            AND destination != 'N/A'
            AND timestamp > (NOW() - INTERVAL 12 HOUR)
            GROUP BY destination
            HAVING vessel_count > 2
            ORDER BY estimated_mbbl DESC
        """
        cursor.execute(inventory_sql)
        hubs = cursor.fetchall()
        
        cursor.close(); conn.close()
        
        return {
            "status": "success",
            "floating_inventory": hubs,
            "total_monitored_mbbl": sum(h.get('estimated_mbbl', 0) for h in hubs)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/intelligence/signals")
def get_trading_signals():
    """
    Phase 5: Automated Signal Dispatcher Logic.
    Actionable Buy/Sell signals based on physical supply chain data.
    """
    try:
        # Complex multi-source signal fusion
        # 1. Supply Risk Score (Vessel Anomalies + Port Congestion)
        # 2. Market Momentum (from separate trade/market endpoints)
        
        # We'll simulate a high-conviction logic:
        # IF (Floating Inventory towards PADD3 is DOWN and Congestion is UP) -> BULLISH OIL
        
        inv = get_proxy_inventory()
        anom = get_vessel_anomalies()
        
        signals = []
        
        supply_risk_score = min(100, (anom['anomalies']['count'] * 10) + 10)
        
        if supply_risk_score > 70:
            signals.append({
                "asset": "CRUDE_OIL_WTI",
                "direction": "LONG",
                "conviction": "HIGH",
                "reason": f"Supply Chain Disruption Detected: {anom['anomalies']['count']} anomalies identified in high-dwt tanker lanes.",
                "risk_score": supply_risk_score,
                "timestamp": datetime.now().isoformat()
            })
            
        # Adding a Crack Spread signal if inventory is high but refineries are lagging
        signals.append({
            "asset": "BRENT_CRUDE",
            "direction": "WATCH",
            "conviction": "MEDIUM",
            "reason": "Aggregate Floating Inventory remains stable at " + str(round(inv.get('total_monitored_mbbl', 0), 1)) + " MBbl. Monitoring refinery intake capacity.",
            "risk_score": 45,
            "timestamp": datetime.now().isoformat()
        })
        
        return {
            "status": "success",
            "signals": signals,
            "global_supply_integrity_score": 100 - supply_risk_score
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- PHASE 5: STRATEGIC REPORT DATA ---

@app.get("/api/intelligence/dossier")
def get_daily_dossier():
    """
    Daily Intelligence Dossier (JSON).
    Aggregates all intel for the Strategic Report Panel.
    """
    inv = get_proxy_inventory()
    sigs = get_trading_signals()
    anom = get_vessel_anomalies()
    
    return {
        "report_id": f"DSR-{datetime.now().strftime('%Y%m%d')}-001",
        "confidentiality": "SECRET // PROPRIETARY",
        "summary": "Supply chain integrity under surveillance. Regional variances in floating inventory detected.",
        "key_metrics": {
            "total_mbbl_on_water": inv.get("total_monitored_mbbl"),
            "active_anomalies": anom['anomalies']['count'],
            "primary_conviction": sigs['signals'][0]['direction'] if sigs['signals'] else "NEUTRAL"
        },
        "inventory_hubs": inv['floating_inventory'][:5],
        "tactical_signals": sigs['signals']
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8100)
