import os
import mysql.connector
from mysql.connector import pooling
from dotenv import load_dotenv
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# Create connection pool with INCREASED SIZE
# Calculate: (40 services * 3 concurrent requests) * 1.5 safety margin = ~180 needed
# Using 50 for reasonable balance
try:
    db_pool = pooling.MySQLConnectionPool(
        pool_name="asetpedia_pool",
        pool_size=50,  # INCREASED from 5 to 50
        pool_reset_session=True,
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset='utf8mb4',
        collation='utf8mb4_unicode_ci',
        autocommit=False
    )
    logger.info(f"[DB_UTILS] Initialized Pool (size:50) for {DB_HOST}/{DB_NAME}")
except Exception as e:
    logger.error(f"[DB_UTILS] CRITICAL Error creating MySQL pool: {e}")
    db_pool = None

def get_db_connection(retries=3, delay=1):
    """
    Acquires a connection from the pool with retry logic for high-concurrency safety.
    """
    for i in range(retries):
        try:
            if db_pool:
                return db_pool.get_connection()
            # Fallback to direct connection
            return mysql.connector.connect(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                charset='utf8mb4',
                collation='utf8mb4_unicode_ci',
                autocommit=False
            )
        except Exception as e:
            if "Too many connections" in str(e) or "Pool exhausted" in str(e):
                if i < retries - 1:
                    logger.warning(f"[DB_UTILS] High load detected. Retrying ({i+1}/{retries})...")
                    time.sleep(delay)
                    continue
            raise e

def execute_query(query, params=None, commit=False):
    """
    Execute a single query with proper error handling and rollback on failure.
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(query, params or ())
        if commit:
            conn.commit()
            return cursor.rowcount
        return cursor.fetchall()
    except Exception as e:
        logger.error(f"[DB_UTILS] Query Error: {e}")
        if commit:
            conn.rollback()
        raise e
    finally:
        cursor.close()
        conn.close()

def execute_transaction(queries_and_params):
    """
    Execute multiple queries atomically with transaction support.
    queries_and_params: List of tuples (query, params)
    Returns: List of results for each query
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        results = []
        
        for query, params in queries_and_params:
            cursor.execute(query, params or ())
            # Check if it's a SELECT query
            if query.strip().upper().startswith('SELECT'):
                results.append(cursor.fetchall())
            else:
                results.append(cursor.rowcount)
        
        conn.commit()
        logger.info(f"[DB_UTILS] Transaction committed: {len(queries_and_params)} queries")
        return results
        
    except Exception as e:
        conn.rollback()
        logger.error(f"[DB_UTILS] Transaction failed, rolled back: {e}")
        raise e
    finally:
        cursor.close()
        conn.close()
