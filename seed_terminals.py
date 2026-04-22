import sqlite3
import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "asetpedia")
    )

def seed_terminals():
    # 1. Connect to GeoPackage (SQLite)
    gpkg_path = "OGIM_v2.7.gpkg"
    if not os.path.exists(gpkg_path):
        print(f"Error: {gpkg_path} not found.")
        return

    lite_conn = sqlite3.connect(gpkg_path)
    lite_conn.row_factory = sqlite3.Row
    lite_cursor = lite_conn.cursor()

    # 2. Connect to MySQL
    try:
        my_conn = get_db_connection()
        my_cursor = my_conn.cursor()
    except Exception as e:
        print(f"Error connecting to MySQL: {e}")
        return

    # 3. Create table if not exists
    create_table_query = """
    CREATE TABLE IF NOT EXISTS petroleum_terminals (
        id INT AUTO_INCREMENT PRIMARY KEY,
        ogim_id INT,
        category VARCHAR(255),
        region VARCHAR(255),
        country VARCHAR(255),
        state_prov VARCHAR(255),
        src_ref_id VARCHAR(255),
        src_date VARCHAR(255),
        on_offshore VARCHAR(100),
        fac_name VARCHAR(255),
        fac_id VARCHAR(100),
        fac_type VARCHAR(255),
        fac_status VARCHAR(100),
        ogim_status VARCHAR(100),
        operator VARCHAR(255),
        install_date VARCHAR(100),
        commodity VARCHAR(255),
        liq_capacity_bpd DOUBLE,
        liq_throughput_bpd DOUBLE,
        gas_capacity_mmcfd DOUBLE,
        gas_throughput_mmcfd DOUBLE,
        num_storage_tanks INT,
        latitude DOUBLE,
        longitude DOUBLE,
        INDEX (country),
        INDEX (fac_name)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """
    my_cursor.execute(create_table_query)
    my_conn.commit()

    # 4. Fetch data from SQLite
    print("Fetching data from GeoPackage...")
    lite_cursor.execute("SELECT * FROM Petroleum_Terminals")
    rows = lite_cursor.fetchall()
    print(f"Found {len(rows)} records.")

    # 5. Insert into MySQL
    insert_query = """
    INSERT INTO petroleum_terminals (
        ogim_id, category, region, country, state_prov, src_ref_id, src_date,
        on_offshore, fac_name, fac_id, fac_type, fac_status, ogim_status,
        operator, install_date, commodity, liq_capacity_bpd, liq_throughput_bpd,
        gas_capacity_mmcfd, gas_throughput_mmcfd, num_storage_tanks, latitude, longitude
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    data_to_insert = []
    for row in rows:
        data_to_insert.append((
            row['OGIM_ID'], row['CATEGORY'], row['REGION'], row['COUNTRY'], row['STATE_PROV'], row['SRC_REF_ID'], row['SRC_DATE'],
            row['ON_OFFSHORE'], row['FAC_NAME'], row['FAC_ID'], row['FAC_TYPE'], row['FAC_STATUS'], row['OGIM_STATUS'],
            row['OPERATOR'], row['INSTALL_DATE'], row['COMMODITY'], row['LIQ_CAPACITY_BPD'], row['LIQ_THROUGHPUT_BPD'],
            row['GAS_CAPACITY_MMCFD'], row['GAS_THROUGHPUT_MMCFD'], row['NUM_STORAGE_TANKS'], row['LATITUDE'], row['LONGITUDE']
        ))

    # Clear existing data if any (optional, but keep it clean for seeding)
    my_cursor.execute("DELETE FROM petroleum_terminals")
    
    # Batch insert
    batch_size = 500
    for i in range(0, len(data_to_insert), batch_size):
        batch = data_to_insert[i:i+batch_size]
        my_cursor.executemany(insert_query, batch)
        my_conn.commit()
        print(f"Inserted {min(i+batch_size, len(data_to_insert))} records...")

    lite_conn.close()
    my_cursor.close()
    my_conn.close()
    print("Seeding completed successfully.")

if __name__ == "__main__":
    seed_terminals()
