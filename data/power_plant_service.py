import sys
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import uvicorn

# Add be directory to path to import db_utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from db_utils import execute_query
except ImportError:
    # If not found, try adding one more level if needed or relative
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from be.db_utils import execute_query

app = FastAPI(title="Power Plant Intelligence Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/power-plants")
async def get_power_plants(
    country: Optional[str] = None, 
    fuel: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 100
):
    try:
        where_clauses = ["1=1"]
        params = []
        
        if country:
            where_clauses.append("country_long = %s")
            params.append(country)
        
        if fuel:
            where_clauses.append("primary_fuel = %s")
            params.append(fuel)

        if q:
            where_clauses.append("(name LIKE %s OR owner LIKE %s)")
            params.extend([f"%{q}%", f"%{q}%"])

        where_str = " AND ".join(where_clauses)
        
        # Count total for pagination
        count_query = f"SELECT COUNT(*) as total FROM power_plants WHERE {where_str}"
        total_res = execute_query(count_query, params)
        total = total_res[0]['total'] if total_res else 0
        
        # Pagination
        offset = (page - 1) * page_size
        query = f"SELECT * FROM power_plants WHERE {where_str} ORDER BY name ASC LIMIT %s OFFSET %s"
        data_params = params + [page_size, offset]
            
        results = execute_query(query, data_params)
        return {
            "status": "success", 
            "total": total,
            "page": page,
            "page_size": page_size,
            "data": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/power-plants/countries")
async def get_countries():
    try:
        # Fast query: just get all countries from the countries table
        # We also want their coordinates for the initial map view
        query = "SELECT code, name, lat, lon, airport_count as hub_power FROM countries ORDER BY name ASC"
        results = execute_query(query)
        return {"status": "success", "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/power-plants/stats")
async def get_stats(country: Optional[str] = None):
    try:
        where_clause = "WHERE 1=1"
        params = []
        if country:
            where_clause += " AND country_long = %s"
            params.append(country)

        # 1. Fuel Distribution (Count & Total Capacity)
        fuel_stats = execute_query(f"SELECT primary_fuel, COUNT(*) as count, SUM(capacity_mw) as total_capacity, AVG(capacity_mw) as avg_capacity FROM power_plants {where_clause} GROUP BY primary_fuel ORDER BY total_capacity DESC", params)
        
        # 2. Capacity Categorization
        capacity_query = f"""
            SELECT 
                CASE 
                    WHEN capacity_mw < 100 THEN 'MICRO (<100MW)'
                    WHEN capacity_mw BETWEEN 100 AND 500 THEN 'MODERATE (100-500MW)'
                    WHEN capacity_mw BETWEEN 500 AND 2000 THEN 'HEAVY (500-2000MW)'
                    ELSE 'ULTRA (>2000MW)'
                END as category,
                COUNT(*) as count
            FROM power_plants
            {where_clause}
            GROUP BY category
            ORDER BY count DESC
        """
        capacity_stats = execute_query(capacity_query, params)

        # 3. Commissioning Year Trend (decades)
        commission_query = f"""
            SELECT 
                FLOOR(commissioning_year / 10) * 10 as decade,
                COUNT(*) as count
            FROM power_plants
            {where_clause} AND commissioning_year IS NOT NULL
            GROUP BY decade
            ORDER BY decade ASC
        """
        commission_stats = execute_query(commission_query, params)

        # 4. Top Owners (Share Dominance)
        owner_stats = execute_query(f"SELECT owner, COUNT(*) as count, SUM(capacity_mw) as total_capacity FROM power_plants {where_clause} AND owner != '' GROUP BY owner ORDER BY count DESC LIMIT 15", params)
        
        # 5. Commissioning Trend by Top Fuel Types (Stacked)
        # We'll get the matrix of Year x Fuel
        matrix_query = f"""
            SELECT 
                FLOOR(commissioning_year / 10) * 10 as decade,
                primary_fuel,
                COUNT(*) as count
            FROM power_plants
            {where_clause} AND commissioning_year IS NOT NULL
            GROUP BY decade, primary_fuel
            ORDER BY decade ASC
        """
        matrix_stats = execute_query(matrix_query, params)

        return {
            "status": "success",
            "fuel_distribution": fuel_stats,
            "capacity_segments": capacity_stats,
            "commissioning_trend": commission_stats,
            "top_owners": owner_stats,
            "fuel_year_matrix": matrix_stats,
            "is_global": country is None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/power-plants/proximity")
async def get_nearby_power_plants(
    lat: float, 
    lon: float, 
    radius: float = 100.0
):
    try:
        # Haversine formula in SQL (6371 is Earth's radius in KM)
        query = """
            SELECT *, (
                6371 * acos(
                    cos(radians(%s)) * cos(radians(latitude)) * 
                    cos(radians(longitude) - radians(%s)) + 
                    sin(radians(%s)) * sin(radians(latitude))
                )
            ) AS distance_km
            FROM power_plants
            HAVING distance_km <= %s
            ORDER BY distance_km ASC
            LIMIT 50
        """
        results = execute_query(query, [lat, lon, lat, radius])
        return {"status": "success", "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {"service": "power_plant_service", "status": "online"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8093)
