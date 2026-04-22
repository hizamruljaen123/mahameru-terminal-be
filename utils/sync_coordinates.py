import sys
import os

# Add parent dir to path to import db_utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_utils import execute_query

def sync_coordinates():
    print("[DB] Synchronizing coordinates from countries master table...")
    
    # Query untuk update koordinat berdasarkan nama yang cocok
    # Menggunakan COLLATE agar tidak kena error "Illegal mix of collations"
    sql = """
    UPDATE oil_trade_countries otc
    JOIN countries c ON otc.origin_name COLLATE utf8mb4_0900_ai_ci = c.name
    SET otc.lat = c.lat,
        otc.lon = c.lon
    WHERE otc.lat IS NULL OR otc.lat = 0;
    """
    
    try:
        rows = execute_query(sql, commit=True)
        print(f"[DB] Success! {rows} rows updated with precise coordinates.")
    except Exception as e:
        print(f"[DB] Error during sync: {e}")

if __name__ == "__main__":
    sync_coordinates()
