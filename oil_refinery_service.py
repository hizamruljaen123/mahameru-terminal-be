import os
import sys
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional, Dict, Any
from datetime import datetime
from db_utils import get_db_connection

# Add the local GNews library to path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GNEWS_DIR = os.path.join(BASE_DIR, "asset", "library", "GNews")
if GNEWS_DIR not in sys.path:
    sys.path.insert(0, GNEWS_DIR)

try:
    from gnews import GNews
    print("=:: GNEWS_LIBRARY_LOADED_SUCCESSFULLY ::=")
except ImportError as e:
    print(f"=:: ERROR_LOADING_GNEWS_LIBRARY: {e} ::=")
    raise

app = FastAPI(debug=True, title="Oil Refinery Intelligence Service")

# Enable CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize GNews readers
news_id = GNews(language='id', country='ID', max_results=10)
news_en = GNews(language='en', country='US', max_results=10)

@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "Oil Refinery Intelligence",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/refineries")
def get_refineries(
    q: Optional[str] = Query(None, description="Search refinery name"),
    country: Optional[str] = Query(None, description="Filter by country")
):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = "SELECT * FROM oil_refineries WHERE 1=1"
        params = []
        
        if q:
            query += " AND nama_kilang LIKE %s"
            params.append(f"%{q}%")
        
        if country:
            query += " AND negara LIKE %s"
            params.append(f"%{country}%")
            
        cursor.execute(query, tuple(params))
        results = cursor.fetchall()
        
        cursor.close()
        conn.close()
        return {"status": "success", "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/lng-facilities")
def get_lng_facilities(
    q: Optional[str] = Query(None, description="Search facility name"),
    country: Optional[str] = Query(None, description="Filter by country"),
    limit: int = Query(100, description="Limit records"),
    offset: int = Query(0, description="Offset records")
):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = "SELECT * FROM lng_facilities WHERE 1=1"
        params = []
        
        if q:
            query += " AND fac_name LIKE %s"
            params.append(f"%{q}%")
        
        if country:
            query += " AND country LIKE %s"
            params.append(f"%{country}%")
            
        # Add sorting and pagination
        query += " ORDER BY country ASC, fac_name ASC LIMIT %s OFFSET %s"
        params.append(limit)
        params.append(offset)
            
        cursor.execute(query, tuple(params))
        results = cursor.fetchall()
        
        # Get total count for pagination
        cursor.execute("SELECT COUNT(*) as total FROM lng_facilities")
        total = cursor.fetchone()['total']
        
        cursor.close()
        conn.close()
        return {"status": "success", "data": results, "total": total}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/offshore-platforms")
def get_offshore_platforms(
    q: Optional[str] = Query(None, description="Search platform name"),
    country: Optional[str] = Query(None, description="Filter by country"),
    limit: int = Query(100, description="Limit records"),
    offset: int = Query(0, description="Offset records")
):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = "SELECT * FROM offshore_platforms WHERE 1=1"
        params = []
        
        if q:
            query += " AND fac_name LIKE %s"
            params.append(f"%{q}%")
        
        if country:
            query += " AND country LIKE %s"
            params.append(f"%{country}%")
            
        # Add sorting and pagination
        query += " ORDER BY country ASC, fac_name ASC LIMIT %s OFFSET %s"
        params.append(limit)
        params.append(offset)
            
        cursor.execute(query, tuple(params))
        results = cursor.fetchall()
        
        # Get total count
        cursor.execute("SELECT COUNT(*) as total FROM offshore_platforms")
        total = cursor.fetchone()['total']
        
        cursor.close()
        conn.close()
        return {"status": "success", "data": results, "total": total}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/petroleum-terminals")
def get_petroleum_terminals(
    q: Optional[str] = Query(None, description="Search terminal name"),
    country: Optional[str] = Query(None, description="Filter by country"),
    limit: int = Query(100, description="Limit records"),
    offset: int = Query(0, description="Offset records")
):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = "SELECT * FROM petroleum_terminals WHERE 1=1"
        params = []
        
        if q:
            query += " AND fac_name LIKE %s"
            params.append(f"%{q}%")
        
        if country:
            query += " AND country LIKE %s"
            params.append(f"%{country}%")
            
        # Add sorting and pagination
        query += " ORDER BY country ASC, fac_name ASC LIMIT %s OFFSET %s"
        params.append(limit)
        params.append(offset)
            
        cursor.execute(query, tuple(params))
        results = cursor.fetchall()
        
        # Get total count
        cursor.execute("SELECT COUNT(*) as total FROM petroleum_terminals")
        count_row = cursor.fetchone()
        total = count_row['total'] if count_row else 0
        
        cursor.close()
        conn.close()
        return {"status": "success", "data": results, "total": total}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/petroleum-terminals/{terminal_id}")
def get_petroleum_terminal_detail(terminal_id: int):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT * FROM petroleum_terminals WHERE id = %s", (terminal_id,))
        result = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if not result:
            raise HTTPException(status_code=404, detail="Petroleum terminal not found")
            
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/offshore-platforms/{platform_id}")
def get_offshore_platform_detail(platform_id: int):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT * FROM offshore_platforms WHERE id = %s", (platform_id,))
        result = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if not result:
            raise HTTPException(status_code=404, detail="Offshore platform not found")
            
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/refineries/{refinery_id}")
def get_refinery_detail(refinery_id: int):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT * FROM oil_refineries WHERE id = %s", (refinery_id,))
        result = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if not result:
            raise HTTPException(status_code=404, detail="Refinery not found")
            
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/refineries/{refinery_id}/news")
def get_refinery_news(
    refinery_id: int,
    period: str = Query("1m", description="News period (1h, 24h, 7d, 1m, 3m, 1y, 3y)")
):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM oil_refineries WHERE id = %s", (refinery_id,))
        refinery = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not refinery:
            raise HTTPException(status_code=404, detail="Refinery not found")
            
        country_name = refinery['negara'].upper()
        
        # 1. Asset Local Activity Query
        refinery_query = f"{refinery['nama_kilang']} {refinery['negara']}"
        
        # 2. Country Macro Intelligence Query
        # Refine macro query for better political/economic context
        macro_query = f"{refinery['negara']} politics economy news"
        if country_name == "INDONESIA":
            macro_query = f"politik ekonomi indonesia terkini"

        # 3. Oil Trade & Transaction Scan (Triangulation)
        trade_query = f"{refinery['negara']} crude oil export import transactions trade cargo shipment"
        if country_name == "INDONESIA":
            trade_query = f"ekspor impor minyak mentah indonesia transaksi cargo"
            
        # Select reader based on country
        lang_code = "id" if country_name == "INDONESIA" else "en"
        reader = news_id if lang_code == "id" else news_en
        reader.period = period
        
        print(f"=:: REFINERY_INTEL_SEARCH: {refinery_query} [lang={lang_code}, period={period}] ::=")
        refinery_news_raw = reader.get_news(refinery_query)
        
        print(f"=:: COUNTRY_MACRO_SEARCH: {macro_query} [lang={lang_code}, period={period}] ::=")
        macro_news_raw = reader.get_news(macro_query)

        print(f"=:: TRADE_INTEL_SEARCH: {trade_query} [lang={lang_code}, period={period}] ::=")
        trade_news_raw = reader.get_news(trade_query)
        
        def format_news(results):
            formatted = []
            for item in results:
                formatted.append({
                    "title": item.get("title", ""),
                    "description": item.get("description", ""),
                    "pubDate": item.get("published date", ""),
                    "url": item.get("url", ""),
                    "publisher": item.get("publisher", {}).get("title", "Unknown") if isinstance(item.get("publisher"), dict) else item.get("publisher", "Unknown")
                })
            return formatted

        return {
            "status": "success",
            "refinery_id": refinery_id,
            "refinery_name": refinery['nama_kilang'],
            "country": refinery['negara'],
            "lang": lang_code,
            "data": {
                "refinery": format_news(refinery_news_raw),
                "macro": format_news(macro_news_raw),
                "trade": format_news(trade_news_raw)
            }
        }
    except Exception as e:
        print(f"=:: SERVICE_ERROR: {str(e)} ::=")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/infrastructure/nearby")
def get_nearby_infrastructure(
    lat: float = Query(..., description="Target Latitude"),
    lon: float = Query(..., description="Target Longitude"),
    radius: float = Query(100.0, description="Search radius in kilometers")
):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Haversine formula in SQL
        distance_sql = f"(6371 * acos(cos(radians({lat})) * cos(radians(latitude)) * cos(radians(longitude) - radians({lon})) + sin(radians({lat})) * sin(radians(latitude))))"
        
        facilities = []

        # 1. Ports (WPI)
        cursor.execute(f"SELECT 'port' as infra_type, main_port_name as name, latitude, longitude, {distance_sql} AS distance FROM wpi_import HAVING distance <= %s ORDER BY distance", (radius,))
        facilities.extend(cursor.fetchall())

        # 2. Airports
        # Note: airports table uses latitude_deg / longitude_deg
        dist_sql_air = f"(6371 * acos(cos(radians({lat})) * cos(radians(latitude_deg)) * cos(radians(longitude_deg) - radians({lon})) + sin(radians({lat})) * sin(radians(latitude_deg))))"
        cursor.execute(f"SELECT 'airport' as infra_type, name, latitude_deg as latitude, longitude_deg as longitude, {dist_sql_air} AS distance FROM airports HAVING distance <= %s ORDER BY distance", (radius,))
        facilities.extend(cursor.fetchall())

        # 3. Industrial Zones
        cursor.execute(f"SELECT 'industrial' as infra_type, name, latitude, longitude, {distance_sql} AS distance FROM industrial_zones HAVING distance <= %s ORDER BY distance", (radius,))
        facilities.extend(cursor.fetchall())

        # 4. Refineries
        cursor.execute(f"SELECT 'refinery' as infra_type, nama_kilang as name, latitude, longitude, {distance_sql} AS distance FROM oil_refineries HAVING distance <= %s ORDER BY distance", (radius,))
        facilities.extend(cursor.fetchall())

        # 5. LNG
        cursor.execute(f"SELECT 'lng' as infra_type, fac_name as name, latitude, longitude, {distance_sql} AS distance FROM lng_facilities HAVING distance <= %s ORDER BY distance", (radius,))
        facilities.extend(cursor.fetchall())

        # 6. Terminals
        cursor.execute(f"SELECT 'terminal' as infra_type, fac_name as name, latitude, longitude, {distance_sql} AS distance FROM petroleum_terminals HAVING distance <= %s ORDER BY distance", (radius,))
        facilities.extend(cursor.fetchall())

        # 7. Offshore
        cursor.execute(f"SELECT 'offshore' as infra_type, fac_name as name, latitude, longitude, {distance_sql} AS distance FROM offshore_platforms HAVING distance <= %s ORDER BY distance", (radius,))
        facilities.extend(cursor.fetchall())

        cursor.close()
        conn.close()
        
        # Sort all combined by distance
        facilities.sort(key=lambda x: x['distance'])
        
        return {"status": "success", "data": facilities}
    except Exception as e:
        print(f"=:: NEARBY_ERROR: {str(e)} ::=")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stats/combined")
def get_combined_stats():
    """
    Get aggregated facility counts (Refineries, LNG, Offshore) per country
    directly via standard SQL joins and grouping.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # SQL with LEFT JOIN to aggregate counts from different tables by country
        # Using COLLATE utf8mb4_general_ci to prevent errors when joining tables with mixed collations
        query = """
            SELECT 
                c.name as country,
                COUNT(DISTINCT r.id) as refinery_count,
                COUNT(DISTINCT l.id) as lng_count,
                COUNT(DISTINCT o.id) as offshore_count,
                COUNT(DISTINCT p.id) as terminal_count,
                (COUNT(DISTINCT r.id) + COUNT(DISTINCT l.id) + COUNT(DISTINCT o.id) + COUNT(DISTINCT p.id)) as total_assets
            FROM countries c
            LEFT JOIN oil_refineries r ON c.name = r.negara COLLATE utf8mb4_general_ci
            LEFT JOIN lng_facilities l ON c.name = l.country COLLATE utf8mb4_general_ci
            LEFT JOIN offshore_platforms o ON c.name = o.country COLLATE utf8mb4_general_ci
            LEFT JOIN petroleum_terminals p ON c.name = p.country COLLATE utf8mb4_general_ci
            GROUP BY c.name
            ORDER BY c.name ASC
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        
        # Calculate grand totals
        total_refineries = sum(row['refinery_count'] for row in results)
        total_lng = sum(row['lng_count'] for row in results)
        total_offshore = sum(row['offshore_count'] for row in results)
        total_terminals = sum(row['terminal_count'] for row in results)
        total_grand = total_refineries + total_lng + total_offshore + total_terminals

        cursor.close()
        conn.close()
        
        return {
            "status": "success",
            "data": results,
            "totals": {
                "refinery": total_refineries,
                "lng": total_lng,
                "offshore": total_offshore,
                "terminal": total_terminals,
                "grand_total": total_grand
            }
        }
    except Exception as e:
        print(f"=:: STATS_QUERY_ERROR: {str(e)} ::=")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    print("=:: STARTING_OIL_REFINERY_SERVICE_ON_PORT_8089 ::=")
    uvicorn.run(app, log_level="debug",  port=8089)
