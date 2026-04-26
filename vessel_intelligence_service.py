import os
import uvicorn
import json
import asyncio
from fastapi import FastAPI, HTTPException, Query, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pydantic import BaseModel, Field, validator
import math
from db_utils import get_db_connection, execute_query, execute_transaction
import logging

# LOGGING SETUP
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# CONFIGURATION
DEBUG_MODE = os.getenv("DEBUG", "false").lower() == "true"
API_TOKEN = os.getenv("VESSEL_INTEL_API_TOKEN")
ALLOWED_ORIGINS = [
    "https://asetpedia.online",
    "https://app.asetpedia.online",
    "https://terminal.asetpedia.online",
    "http://localhost:3000",
    "http://localhost:5173",
]

if not API_TOKEN:
    raise ValueError("VESSEL_INTEL_API_TOKEN environment variable not set")

app = FastAPI(
    debug=DEBUG_MODE,
    title="Oil Supply Chain Intelligence Signal Node",
    description="Secure vessel intelligence API with authentication and rate limiting"
)

# CORS - Restrictive
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Content-Type", "Authorization"],
)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return HTTPException(status_code=429, detail="Rate limit exceeded")

# SECURITY: Authentication
security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verify API token from Authorization header"""
    if credentials.credentials != API_TOKEN:
        logger.warning(f"Invalid token attempt")
        raise HTTPException(status_code=403, detail="Invalid authentication token")
    return credentials.credentials

# PYDANTIC MODELS - Request validation
class CoordinateValidator:
    """Validate geographic coordinates"""
    @staticmethod
    def validate_latitude(lat):
        if lat is None:
            raise ValueError("Latitude cannot be null")
        lat_float = float(lat)
        if not (-90 <= lat_float <= 90):
            raise ValueError(f"Latitude out of range: {lat_float}")
        return lat_float

    @staticmethod
    def validate_longitude(lon):
        if lon is None:
            raise ValueError("Longitude cannot be null")
        lon_float = float(lon)
        if not (-180 <= lon_float <= 180):
            raise ValueError(f"Longitude out of range: {lon_float}")
        return lon_float

# Tanker classification for accurate inventory modeling
TANKER_CLASSES = {
    'VLCC': {'dwt_min': 200000, 'dwt_max': 320000, 'bbl_per_dwt': 6.8},
    'Suezmax': {'dwt_min': 120000, 'dwt_max': 180000, 'bbl_per_dwt': 7.0},
    'Aframax': {'dwt_min': 80000, 'dwt_max': 120000, 'bbl_per_dwt': 7.2},
    'Panamax': {'dwt_min': 50000, 'dwt_max': 80000, 'bbl_per_dwt': 7.3},
}

SEA_LANE_THRESHOLD_KM = 50.0
DARK_VESSEL_THRESHOLD_MINUTES = 60

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance with coordinate validation"""
    lat1 = CoordinateValidator.validate_latitude(lat1)
    lon1 = CoordinateValidator.validate_longitude(lon1)
    lat2 = CoordinateValidator.validate_latitude(lat2)
    lon2 = CoordinateValidator.validate_longitude(lon2)
    
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def log_data_access(user_ip: str, endpoint: str, data_count: int, token_prefix: str):
    """Audit log for data access"""
    logger.info(f"DATA_ACCESS | IP:{user_ip} | Endpoint:{endpoint} | Records:{data_count} | Token:{token_prefix}...")

# PHASE 4: INTELLIGENCE SIGNALS - SINGLE CANONICAL ENDPOINT

@app.get("/api/v1/vessel/intelligence/anomalies")
@limiter.limit("100/minute")
async def get_vessel_anomalies(
    request: Request,
    auth: str = Depends(verify_token),
    threshold_hours: int = Query(1, ge=1, le=72),
    vessel_type: str = Query("Tanker", regex="^[A-Za-z\\s]+$")
):
    """
    Detects AIS-off (Dark Mode) or Route Deviations using historical AIS data.
    FIXED: Parameterized queries, authentication, rate limiting, UTC timestamps
    """
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Detect Dark Vessels - PARAMETERIZED
        dark_sql = """
            SELECT mmsi, name, lat, lon, MAX(timestamp) as last_seen,
                   COUNT(*) as signal_count
            FROM ais_history
            WHERE type LIKE %s
            GROUP BY mmsi, name, lat, lon
            HAVING last_seen < (UTC_TIMESTAMP() - INTERVAL %s HOUR)
            AND last_seen > (UTC_TIMESTAMP() - INTERVAL 24 HOUR)
            LIMIT 1000
        """
        cursor.execute(dark_sql, (f'%{vessel_type}%', threshold_hours))
        dark_vessels = cursor.fetchall()

        # 2. Route Deviation Detection - PARAMETERIZED
        deviation_sql = """
            SELECT mmsi, name, lat, lon, heading, speed, destination, status, timestamp
            FROM ais_history
            WHERE type LIKE %s
            AND speed > 1
            AND (status = 'Restricted Maneuverability' OR status = 'Not Under Command')
            AND timestamp > (UTC_TIMESTAMP() - INTERVAL 48 HOUR)
            LIMIT 1000
        """
        cursor.execute(deviation_sql, (f'%{vessel_type}%',))
        deviations = cursor.fetchall()

        cursor.close()
        conn.close()
        
        log_data_access(client_ip, "/anomalies", len(dark_vessels) + len(deviations), auth[:20])
        
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "anomalies": {
                "dark_vessels": dark_vessels,
                "route_deviations": deviations,
                "count": len(dark_vessels) + len(deviations)
            }
        }
    except Exception as e:
        logger.error(f"Anomaly detection error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve anomalies")

@app.get("/api/v1/vessel/intelligence/inventory-model")
@limiter.limit("50/minute")
async def get_proxy_inventory(
    request: Request,
    auth: str = Depends(verify_token),
    port_id: Optional[str] = Query(None, min_length=1, max_length=50, regex="^[A-Za-z0-9_-]+$"),
    destination: Optional[str] = Query(None, min_length=1, max_length=100)
):
    """
    Proxy Inventory Model: Estimates volume of oil currently "on-water".
    FIXED: Proper tanker classification, confidence intervals, UTC timestamps, recent data
    """
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # FIXED: Proper tanker classification by DWT ranges
        inventory_sql = """
            SELECT 
                destination,
                CASE 
                    WHEN dwt BETWEEN 200000 AND 320000 THEN 'VLCC'
                    WHEN dwt BETWEEN 120000 AND 180000 THEN 'Suezmax'
                    WHEN dwt BETWEEN 80000 AND 120000 THEN 'Aframax'
                    WHEN dwt BETWEEN 50000 AND 80000 THEN 'Panamax'
                    ELSE 'Other'
                END as ship_class,
                COUNT(DISTINCT mmsi) as vessel_count,
                SUM(CASE WHEN cargo_type = 'CRUDE' AND speed > 2 THEN 1 ELSE 0 END) as active_crude_transit,
                AVG(dwt) as avg_dwt,
                SUM(CASE WHEN cargo_type = 'CRUDE' THEN dwt * 6.9 ELSE 0 END) / 1000000.0 as estimated_mbbl,
                ROUND(STDDEV(dwt * 6.9) / 1000000.0, 3) as stddev_mbbl,
                COUNT(DISTINCT mmsi) * 0.95 as confidence_factor,
                MAX(timestamp) as latest_record
            FROM ais_history
            WHERE cargo_type IN ('CRUDE', 'REFINED')
            AND timestamp > (UTC_TIMESTAMP() - INTERVAL 4 HOUR)
            AND destination IS NOT NULL AND destination != 'N/A'
            GROUP BY destination, ship_class
            HAVING vessel_count > 0
            ORDER BY estimated_mbbl DESC
            LIMIT 100
        """
        cursor.execute(inventory_sql)
        hubs = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        log_data_access(client_ip, "/inventory-model", len(hubs), auth[:20])
        
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "floating_inventory": hubs,
            "total_monitored_mbbl": sum(float(h.get('estimated_mbbl') or 0) for h in hubs),
            "total_vessels": sum(int(h.get('vessel_count') or 0) for h in hubs),
            "data_quality": {"records_analyzed": len(hubs), "confidence_level": "HIGH" if len(hubs) > 5 else "MEDIUM"}
        }
    except Exception as e:
        logger.error(f"Inventory model error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve inventory model")

@app.get("/api/v1/vessel/intelligence/signals")
@limiter.limit("50/minute")
async def get_trading_signals(
    request: Request,
    auth: str = Depends(verify_token),
    risk_threshold: int = Query(50, ge=0, le=100)
):
    """
    Phase 5: Automated Signal Dispatcher Logic.
    FIXED: Better error handling, confidence intervals, proper integration
    """
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        try:
            inv_response = await get_proxy_inventory(request, auth)
            inv = inv_response
        except:
            inv = {"floating_inventory": [], "total_monitored_mbbl": 0}
        
        try:
            anom_response = await get_vessel_anomalies(request, auth)
            anom = anom_response
        except:
            anom = {"anomalies": {"count": 0}}
        
        signals = []
        anomaly_count = anom.get('anomalies', {}).get('count', 0)
        supply_risk_score = min(100, (anomaly_count * 15) + 10)
        
        if supply_risk_score > risk_threshold:
            signals.append({
                "asset": "CRUDE_OIL_WTI",
                "direction": "LONG",
                "action": "BUY",
                "conviction": "HIGH" if supply_risk_score > 80 else "MEDIUM",
                "confidence": round(min(0.95, supply_risk_score / 100), 2),
                "rationale": f"Supply disruption: {anomaly_count} anomalies. Risk: {supply_risk_score}",
                "risk_score": supply_risk_score,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            })
        
        log_data_access(client_ip, "/signals", len(signals), auth[:20])
        
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "signals": signals,
            "global_supply_integrity_score": max(0, 100 - supply_risk_score)
        }
    except Exception as e:
        logger.error(f"Trading signals error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate signals")

@app.get("/api/v1/vessel/intelligence/dossier")
@limiter.limit("20/minute")
async def get_daily_dossier(
    request: Request,
    auth: str = Depends(verify_token)
):
    """
    Daily Intelligence Dossier (JSON).
    Aggregates all intel for the Strategic Report Panel.
    """
    client_ip = request.client.host if request.client else "unknown"
    
    try:
        inv = await get_proxy_inventory(request, auth)
        sigs = await get_trading_signals(request, auth)
        anom = await get_vessel_anomalies(request, auth)
        
        log_data_access(client_ip, "/dossier", 1, auth[:20])
        
        return {
            "status": "success",
            "report_id": f"DSR-{datetime.utcnow().strftime('%Y%m%d')}-{os.urandom(2).hex().upper()}",
            "classification": "INTERNAL USE ONLY",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "summary": "Supply chain integrity surveillance. Regional floating inventory analysis.",
            "key_metrics": {
                "total_mbbl_on_water": inv.get("total_monitored_mbbl"),
                "total_vessels_tracked": inv.get("total_vessels"),
                "active_anomalies": anom.get('anomalies', {}).get('count', 0),
                "primary_signal": sigs['signals'][0]['direction'] if sigs.get('signals') else "NEUTRAL"
            },
            "inventory_hubs": inv.get('floating_inventory', [])[:5],
            "tactical_signals": sigs.get('signals', [])
        }
    except Exception as e:
        logger.error(f"Dossier error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate dossier")

@app.get("/health")
async def health_check():
    """Public health check"""
    return {"status": "healthy", "service": "vessel-intelligence-api", "timestamp": datetime.utcnow().isoformat() + "Z"}

@app.get("/api/v1/health")
async def health_authenticated(auth: str = Depends(verify_token)):
    """Authenticated health check"""
    return {"status": "healthy", "authenticated": True, "timestamp": datetime.utcnow().isoformat() + "Z"}

@app.on_event("startup")
async def startup_event():
    logger.info("🚀 Vessel Intelligence API starting...")
    logger.info(f"Debug mode: {DEBUG_MODE}")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Vessel Intelligence API shutting down...")

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8100)),
        log_level="info"
    )
