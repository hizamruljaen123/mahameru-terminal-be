import os
import mysql.connector
from mysql.connector import pooling
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "asetpedia")

import time

# Create a connection pool with optimized size
# 5 connections per service is plenty for 40+ microservices (5 * 40 = 200 total)
try:
    db_pool = pooling.MySQLConnectionPool(
        pool_name="asetpedia_pool",
        pool_size=5, 
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset='utf8mb4',
        collation='utf8mb4_unicode_ci'
    )
    print(f"[DB_UTILS] Initialized Pool (size:5) for {DB_HOST}/{DB_NAME}")
except Exception as e:
    print(f"[DB_UTILS] CRITICAL Error creating MySQL pool: {e}")
    db_pool = None

def get_db_connection(retries=3, delay=1):
    """
    Acquires a connection from the pool with retry logic for high-concurrency safety.
    """
    for i in range(retries):
        try:
            if db_pool:
                return db_pool.get_connection()
            # If pool failed, try direct connection
            return mysql.connector.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                charset='utf8mb4',
                collation='utf8mb4_unicode_ci'
            )
        except Exception as e:
            if "Too many connections" in str(e) or "Pool exhausted" in str(e):
                if i < retries - 1:
                    print(f"[DB_UTILS] High load detected. Retrying connection ({i+1}/{retries})...")
                    time.sleep(delay)
                    continue
            raise e

def execute_query(query, params=None, commit=False):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(query, params or ())
        if commit:
            conn.commit()
            return cursor.rowcount
        return cursor.fetchall()
    except Exception as e:
        print(f"[DB_UTILS] Query Error: {e}")
        if commit: conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()
