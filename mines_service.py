from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import mysql.connector
from mysql.connector import pooling
import uvicorn
import math
from typing import Optional, List

from db_utils import get_db_connection

# Global filter for "Active Mines" only
# Users specifically asked for active ones (Producer/Plant) 
# RELAXED: Ensuring data with score or known status is shown, but not hiding others if they have coords
ACTIVE_FILTER = "site_name IS NOT NULL AND latitude != 0 AND longitude != 0"

app = FastAPI(debug=True, title="Mines Data Microservice")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection is imported from db_utils

@app.get("/api/mines")
def get_mines(
    page: int = 1,
    page_size: int = 100,
    search: Optional[str] = None,
    country: Optional[str] = None,
    commodity: Optional[str] = None,
    dev_stat: Optional[str] = None,
    region: Optional[str] = None,
    oper_type: Optional[str] = None,
    prod_size: Optional[str] = None,
    com_type: Optional[str] = None,
    score: Optional[str] = None
):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        offset = (page - 1) * page_size
        
        # Base Query
        query = f"SELECT * FROM mines_data WHERE {ACTIVE_FILTER}"
        params: List = []
        
        # Filter Logic
        if search:
            query += " AND (site_name LIKE %s OR country LIKE %s OR commod1 LIKE %s)"
            search_val = f"%{search}%"
            params.extend([search_val, search_val, search_val])
        
        if country:
            query += " AND country = %s"
            params.append(country)
            
        if commodity:
            query += " AND (commod1 = %s OR commod2 = %s OR commod3 = %s)"
            params.extend([commodity, commodity, commodity])
            
        if dev_stat:
            query += " AND dev_stat = %s"
            params.append(dev_stat)

        if region:
            query += " AND region = %s"
            params.append(region)

        if oper_type:
            query += " AND oper_type = %s"
            params.append(oper_type)

        if prod_size:
            query += " AND prod_size = %s"
            params.append(prod_size)

        if com_type:
            query += " AND com_type = %s"
            params.append(com_type)

        if score:
            query += " AND score = %s"
            params.append(score)
            
        # 1. Hitung Total Data (Count Query)
        count_query = query.replace("SELECT *", "SELECT COUNT(*) as total_count", 1)
        cursor.execute(count_query, params)
        total_result = cursor.fetchone()
        total = total_result["total_count"] if total_result else 0
        
        # 2. Tambahkan Sorting & Pagination
        query += " ORDER BY site_name ASC LIMIT %s OFFSET %s"
        final_params = params + [page_size, offset]

        # --- BAGIAN PRINT QUERY LENGKAP ---
        # Membuat representasi string dari query dengan parameter terisi
        debug_query = query
        for p in final_params:
            # Jika string beri tanda kutip, jika angka biarkan saja
            val = f"'{p}'" if isinstance(p, str) else str(p)
            debug_query = debug_query.replace("%s", val, 1)
        
        print("\n" + "="*50)
        print("EXECUTING FULL QUERY:")
        print(debug_query)
        print("="*50 + "\n")
        # ----------------------------------
        
        # 3. Eksekusi Query Utama
        cursor.execute(query, final_params)
        data = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return {
            "query": debug_query,
            "status": "success",
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": math.ceil(total / page_size) if total > 0 else 0,
            "data": data
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/mines/filters")
def get_filters():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    filters = {}
    
    cursor.execute(f"SELECT DISTINCT country FROM mines_data WHERE country IS NOT NULL AND {ACTIVE_FILTER} ORDER BY country")
    filters["countries"] = [r["country"] for r in cursor.fetchall()]
    
    cursor.execute(f"""
        SELECT DISTINCT commod1 FROM mines_data WHERE commod1 IS NOT NULL AND {ACTIVE_FILTER}
        UNION
        SELECT DISTINCT commod2 FROM mines_data WHERE commod2 IS NOT NULL AND {ACTIVE_FILTER}
        UNION
        SELECT DISTINCT commod3 FROM mines_data WHERE commod3 IS NOT NULL AND {ACTIVE_FILTER}
        ORDER BY commod1
    """)
    filters["commodities"] = [r["commod1"] for r in cursor.fetchall()]
    
    cursor.execute(f"SELECT DISTINCT dev_stat FROM mines_data WHERE dev_stat IS NOT NULL AND {ACTIVE_FILTER} ORDER BY dev_stat")
    filters["dev_status"] = [r["dev_stat"] for r in cursor.fetchall()]
    
    cursor.execute(f"SELECT DISTINCT region FROM mines_data WHERE region IS NOT NULL AND {ACTIVE_FILTER} ORDER BY region")
    filters["regions"] = [r["region"] for r in cursor.fetchall()]

    cursor.execute(f"SELECT DISTINCT oper_type FROM mines_data WHERE oper_type IS NOT NULL AND {ACTIVE_FILTER} ORDER BY oper_type")
    filters["oper_types"] = [r["oper_type"] for r in cursor.fetchall()]

    cursor.execute(f"SELECT DISTINCT prod_size FROM mines_data WHERE prod_size IS NOT NULL AND {ACTIVE_FILTER} ORDER BY prod_size")
    filters["prod_sizes"] = [r["prod_size"] for r in cursor.fetchall()]

    cursor.execute(f"SELECT DISTINCT com_type FROM mines_data WHERE com_type IS NOT NULL AND {ACTIVE_FILTER} ORDER BY com_type")
    filters["com_types"] = [r["com_type"] for r in cursor.fetchall()]

    cursor.execute(f"SELECT DISTINCT score FROM mines_data WHERE score IS NOT NULL AND {ACTIVE_FILTER} ORDER BY score")
    filters["scores"] = [r["score"] for r in cursor.fetchall()]
    
    cursor.close()
    conn.close()
    
    return {"status": "success", "data": filters}

@app.get("/api/mines/stats/overview")
def get_overview_stats(commodity: Optional[str] = None, region: Optional[str] = None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    where_clause = ACTIVE_FILTER
    params = []
    if commodity:
        where_clause += " AND (commod1 = %s OR commod2 = %s OR commod3 = %s)"
        params.extend([commodity, commodity, commodity])
    if region:
        where_clause += " AND region = %s"
        params.append(region)

    stats = {}
    
    cursor.execute(f"""
        SELECT commod1 as name, COUNT(*) as count 
        FROM mines_data 
        WHERE commod1 IS NOT NULL 
        AND {where_clause}
        GROUP BY commod1 
        ORDER BY count DESC 
        LIMIT 10
    """, params)
    stats["top_commodities"] = cursor.fetchall()
    
    cursor.execute(f"SELECT dev_stat as status, COUNT(*) as count FROM mines_data WHERE dev_stat IS NOT NULL AND {where_clause} GROUP BY dev_stat ORDER BY count DESC", params)
    stats["dev_status"] = cursor.fetchall()
    
    cursor.execute(f"SELECT prod_size as size, COUNT(*) as count FROM mines_data WHERE prod_size IS NOT NULL AND {where_clause} GROUP BY prod_size ORDER BY count DESC", params)
    stats["prod_size"] = cursor.fetchall()
    
    cursor.execute(f"SELECT region, COUNT(*) as count FROM mines_data WHERE region IS NOT NULL AND {where_clause} GROUP BY region ORDER BY count DESC", params)
    stats["region_distribution"] = cursor.fetchall()
    
    cursor.execute(f"SELECT oper_type as type, COUNT(*) as count FROM mines_data WHERE oper_type IS NOT NULL AND {where_clause} GROUP BY oper_type ORDER BY count DESC", params)
    stats["oper_type_distribution"] = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return {"status": "success", "data": stats}

@app.get("/api/mines/stats/countries")
def get_country_stats(commodity: Optional[str] = None, region: Optional[str] = None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    where_clause = ACTIVE_FILTER
    params = []
    if commodity:
        where_clause += " AND (commod1 = %s OR commod2 = %s OR commod3 = %s)"
        params.extend([commodity, commodity, commodity])
    if region:
        where_clause += " AND region = %s"
        params.append(region)
        
    query = f"SELECT country, COUNT(*) as count, AVG(latitude) as lat, AVG(longitude) as lon FROM mines_data WHERE country IS NOT NULL AND latitude != 0 AND longitude != 0 AND {where_clause} GROUP BY country ORDER BY count DESC"
    cursor.execute(query, params)
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return {"status": "success", "data": data}

@app.get("/api/mines/stats/countries/detailed")
def get_detailed_country_stats(commodity: Optional[str] = None, region: Optional[str] = None):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    where_clause = ACTIVE_FILTER
    params = []
    if commodity:
        where_clause += " AND (commod1 = %s OR commod2 = %s OR commod3 = %s)"
        params.extend([commodity, commodity, commodity])
    if region:
        where_clause += " AND region = %s"
        params.append(region)

    query = f"""
        SELECT country, COUNT(*) as total_mines,
        SUM(CASE WHEN 'Gold' IN (commod1, commod2, commod3) OR commod1 LIKE '%Gold%' OR commod2 LIKE '%Gold%' OR commod3 LIKE '%Gold%' THEN 1 ELSE 0 END) as gold,
        SUM(CASE WHEN 'Copper' IN (commod1, commod2, commod3) OR commod1 LIKE '%Copper%' OR commod2 LIKE '%Copper%' OR commod3 LIKE '%Copper%' THEN 1 ELSE 0 END) as copper,
        SUM(CASE WHEN 'Nickel' IN (commod1, commod2, commod3) OR commod1 LIKE '%Nickel%' OR commod2 LIKE '%Nickel%' OR commod3 LIKE '%Nickel%' THEN 1 ELSE 0 END) as nickel,
        SUM(CASE WHEN 'Lithium' IN (commod1, commod2, commod3) OR commod1 LIKE '%Lithium%' OR commod2 LIKE '%Lithium%' OR commod3 LIKE '%Lithium%' THEN 1 ELSE 0 END) as lithium,
        SUM(CASE WHEN 'Iron' IN (commod1, commod2, commod3) OR commod1 LIKE '%Iron%' OR commod2 LIKE '%Iron%' OR commod3 LIKE '%Iron%' THEN 1 ELSE 0 END) as iron,
        SUM(CASE WHEN 'Silver' IN (commod1, commod2, commod3) OR commod1 LIKE '%Silver%' OR commod2 LIKE '%Silver%' OR commod3 LIKE '%Silver%' THEN 1 ELSE 0 END) as silver,
        SUM(CASE WHEN 'Uranium' IN (commod1, commod2, commod3) OR commod1 LIKE '%Uranium%' OR commod2 LIKE '%Uranium%' OR commod3 LIKE '%Uranium%' THEN 1 ELSE 0 END) as uranium,
        SUM(CASE WHEN 'Coal' IN (commod1, commod2, commod3) OR commod1 LIKE '%Coal%' OR commod2 LIKE '%Coal%' OR commod3 LIKE '%Coal%' THEN 1 ELSE 0 END) as coal
        FROM mines_data m1 WHERE country IS NOT NULL AND {where_clause} GROUP BY country ORDER BY total_mines DESC LIMIT 100
    """
    cursor.execute(query, params)
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return {"status": "success", "data": data}

@app.get("/api/mines/stats/country/{country_name}/commodities")
def get_country_commodity_stats(country_name: str):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT commod1, commod2, commod3 FROM mines_data WHERE country = %s AND {ACTIVE_FILTER}", (country_name,))
    raw_rows = cursor.fetchall()
    commodity_counter: dict = {}
    for row in raw_rows:
        for c_field in ["commod1", "commod2", "commod3"]:
            if row[c_field]:
                parts = [p.strip() for p in str(row[c_field]).split(",") if p.strip()]
                for part in parts:
                    commodity_counter[part] = commodity_counter.get(part, 0) + 1
    cursor.close()
    conn.close()
    return {"status": "success", "data": [{"name": k, "count": v} for k, v in sorted(commodity_counter.items(), key=lambda x: -x[1])]}

@app.get("/api/mines/stats/country/{country_name}/dev-status")
def get_country_dev_status(country_name: str):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT dev_stat as status, COUNT(*) as count FROM mines_data WHERE country = %s AND dev_stat IS NOT NULL AND {ACTIVE_FILTER} GROUP BY dev_stat ORDER BY count DESC", (country_name,))
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return {"status": "success", "data": data}

@app.get("/api/mines/stats/country/{country_name}/prod-size")
def get_country_prod_size(country_name: str):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT prod_size as size, COUNT(*) as count FROM mines_data WHERE country = %s AND prod_size IS NOT NULL AND {ACTIVE_FILTER} GROUP BY prod_size ORDER BY count DESC", (country_name,))
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return {"status": "success", "data": data}

@app.get("/api/mines/stats/country/{country_name}/oper-type")
def get_country_oper_type(country_name: str):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT oper_type as type, COUNT(*) as count FROM mines_data WHERE country = %s AND oper_type IS NOT NULL AND {ACTIVE_FILTER} GROUP BY oper_type ORDER BY count DESC", (country_name,))
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return {"status": "success", "data": data}

@app.get("/api/mines/stats/country/{country_name}/top-deposits")
def get_country_top_deposits(country_name: str):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT site_name, commod1, dev_stat, prod_size, region, oper_type FROM mines_data WHERE country = %s AND {ACTIVE_FILTER} ORDER BY prod_size DESC LIMIT 1000", (country_name,))
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return {"status": "success", "data": data}

@app.get("/api/mines/{mine_id}")
def get_mine_detail(mine_id: int):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SELECT * FROM mines_data WHERE id = %s AND {ACTIVE_FILTER}", (mine_id,))
    data = cursor.fetchone()
    cursor.close()
    conn.close()
    if not data:
        return {"status": "error", "message": "Mine not found"}
    return {"status": "success", "data": data}

@app.get("/")
async def root():
    """Root handler for avoiding 404 on service heartbeat probes."""
    return {"status": "online", "service": "mines_data_service"}

if __name__ == "__main__":
    print("=:: MEMULAI SERVICE PYTHON MINES DATA (FULLY EXTENDED) ::=")
    uvicorn.run("mines_service:app", host="0.0.0.0", log_level="debug", port=8082, reload=False)
