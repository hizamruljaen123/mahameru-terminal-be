import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool
from dotenv import load_dotenv

# Konfigurasi Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
# Load environment variables - search in project root (two levels up from services/system)
env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    # Fallback to standard search if path above doesn't exist
    load_dotenv()


DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# Inisialisasi Engine SQLAlchemy dengan QueuePool
import urllib.parse

try:
    encoded_password = urllib.parse.quote_plus(DB_PASSWORD) if DB_PASSWORD else ""
    database_url = f"mysql+mysqlconnector://{DB_USER}:{encoded_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    engine = create_engine(
        database_url,
        pool_size=100,           # Pool dasar 100 koneksi persisten
        max_overflow=50,         # Tambahan hingga 50 koneksi saat beban tinggi
        pool_pre_ping=True,      # Validasi koneksi sebelum digunakan (cegah 'MySQL has gone away')
        pool_recycle=3600,       # Reset koneksi setiap 1 jam
        pool_timeout=30,         # Timeout menunggu koneksi dari pool
        connect_args={"charset": "utf8mb4"},
    )

    logger.info(f"[DB_UTILS] Initialized SQLAlchemy QueuePool (size=100, overflow=50) for {DB_HOST}/{DB_NAME}")
except Exception as e:
    logger.error(f"[DB_UTILS] CRITICAL Error creating SQLAlchemy engine: {e}")
    engine = None

def get_db_connection():
    """
    Mengambil raw connection dari SQLAlchemy pool.
    Menggunakan MySQL Connector/Python dengan dukungan dictionary cursor.
    """
    if engine is None:
        raise Exception("Database engine not initialized")
    
    return engine.raw_connection()

def execute_query(query, params=None, commit=False):
    """
    Menjalankan query tunggal (SELECT atau INSERT/UPDATE/DELETE).
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
    Menjalankan banyak query secara atomik dalam satu transaksi.
    Menerima list berupa tuple [(query, params), ...].
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        conn.start_transaction()
        results = []

        for query, params in queries_and_params:
            cursor.execute(query, params or ())
            # Cek jika query adalah SELECT
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