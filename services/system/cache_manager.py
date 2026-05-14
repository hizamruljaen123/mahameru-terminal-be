import sqlite3
import json
import os
import time
from functools import lru_cache
from typing import Optional, Dict, Any, List

CACHE_DB = os.path.join(os.path.dirname(__file__), 'data', 'news_cache.db')

# --- Reference Data Caching (TTL 5 minutes) ---
_REFERENCE_CACHE = {
    "countries": {"data": None, "ts": 0},
    "feedsource": {"data": None, "ts": 0},
    "idx_entity": {"data": None, "ts": 0},
}
REFERENCE_CACHE_TTL = 300  # 5 minutes

def get_cache_conn():
    os.makedirs(os.path.dirname(CACHE_DB), exist_ok=True)
    conn = sqlite3.connect(CACHE_DB, timeout=30)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.row_factory = sqlite3.Row
    return conn

def init_cache():
    conn = get_cache_conn()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS hot_news (
            link_hash TEXT PRIMARY KEY,
            category TEXT,
            data TEXT,
            timestamp REAL
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_cat_time ON hot_news(category, timestamp DESC)')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS system_status (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS metadata (
            id TEXT PRIMARY KEY,
            val_int INTEGER,
            val_text TEXT
        )
    ''')
    conn.execute("INSERT OR IGNORE INTO metadata (id, val_int) VALUES ('new_items_count', 0)")
    conn.commit()
    conn.close()

def save_to_hot_cache(articles):
    """Batch-save news articles. Single connection per call for SQLite safety."""
    import hashlib
    if not isinstance(articles, list):
        articles = [articles]
    if not articles:
        return

    conn = get_cache_conn()
    try:
        new_adds = 0
        for art in articles:
            link = art.get('link', '')
            if not link:
                continue
            link_hash = hashlib.sha1(link.encode()).hexdigest()
            cat = (art.get('category') or 'UNCATEGORIZED').upper()
            conn.execute('''
                INSERT OR IGNORE INTO hot_news (link_hash, category, data, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (link_hash, cat, json.dumps(art, default=str), art.get('timestamp', 0)))
            new_adds += 1

        if new_adds > 0:
            conn.execute(
                "UPDATE metadata SET val_int = val_int + ? WHERE id = 'new_items_count'",
                (new_adds,)
            )

        # Per-category cap: keep latest 200 per category
        conn.execute('''
            DELETE FROM hot_news WHERE link_hash NOT IN (
                SELECT link_hash FROM (
                    SELECT link_hash,
                           ROW_NUMBER() OVER (PARTITION BY category ORDER BY timestamp DESC) as rn
                    FROM hot_news
                ) ranked WHERE rn <= 200
            )
        ''')
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_hot_news(category=None, limit=1000):
    """
    Retrieve news from fast SQLite cache. 
    Optimization: Reduced default limit from 5000 to 1000 to prevent 
    excessive JSON parsing overhead on the main thread.
    """
    conn = get_cache_conn()
    try:
        if category:
            rows = conn.execute(
                'SELECT category, data FROM hot_news WHERE category = ? ORDER BY timestamp DESC LIMIT 200',
                (category.upper(),)
            ).fetchall()
        else:
            # We fetch a reasonable pool to cover most priority categories
            rows = conn.execute(
                f'SELECT category, data FROM hot_news ORDER BY timestamp DESC LIMIT {limit}'
            ).fetchall()

        result = {}
        for row in rows:
            cat = row['category']
            if cat not in result:
                result[cat] = []
            
            # Optimization: Only parse JSON if we haven't reached a reasonable limit per category
            # in the combined result set to save CPU cycles.
            if len(result[cat]) < 20:
                result[cat].append(json.loads(row['data']))
        return result
    finally:
        conn.close()


def get_new_articles_since(since_ts):
    """Return all articles inserted after the given Unix timestamp. Used for live streaming."""
    conn = get_cache_conn()
    try:
        rows = conn.execute(
            'SELECT category, data FROM hot_news WHERE timestamp > ? ORDER BY timestamp DESC LIMIT 500',
            (since_ts,)
        ).fetchall()
        result = {}
        for row in rows:
            cat = row['category']
            if cat not in result:
                result[cat] = []
            result[cat].append(json.loads(row['data']))
        return result
    finally:
        conn.close()

def update_status_cache(status):
    conn = get_cache_conn()
    conn.execute('INSERT OR REPLACE INTO system_status (key, value) VALUES ("main", ?)', (json.dumps(status),))
    conn.commit()
    conn.close()

def get_status_cache():
    conn = get_cache_conn()
    row = conn.execute('SELECT value FROM system_status WHERE key="main"').fetchone()
    conn.close()
    return json.loads(row['value']) if row else {}

def get_new_items_count():
    conn = get_cache_conn()
    row = conn.execute("SELECT val_int FROM metadata WHERE id = 'new_items_count'").fetchone()
    conn.close()
    return row['val_int'] if row else 0

def reset_new_items_count():
    conn = get_cache_conn()
    conn.execute("UPDATE metadata SET val_int = 0 WHERE id = 'new_items_count'")
    conn.commit()
    conn.close()


# ============================================================
# REFERENCE DATA CACHE (TTL-based)
# ============================================================

def get_countries_cached() -> List[Dict[str, Any]]:
    """Get countries list from MySQL with 5-minute TTL cache."""
    global _REFERENCE_CACHE
    cache = _REFERENCE_CACHE["countries"]

    if cache["data"] is not None and (time.time() - cache["ts"]) < REFERENCE_CACHE_TTL:
        return cache["data"]

    # Cache miss - fetch from DB
    conn = get_db_connection_reference()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, code, name, continent, latitude, longitude FROM countries ORDER BY name")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        # Update cache
        _REFERENCE_CACHE["countries"] = {"data": rows, "ts": time.time()}
        return rows
    except Exception as e:
        print(f"[CACHE] Error fetching countries: {e}")
        if conn:
            conn.close()
        return cache["data"] if cache["data"] is not None else []


def get_feedsource_cached(active_only: bool = True) -> List[Dict[str, Any]]:
    """Get feedsource list from MySQL with 5-minute TTL cache."""
    global _REFERENCE_CACHE
    cache = _REFERENCE_CACHE["feedsource"]

    if cache["data"] is not None and (time.time() - cache["ts"]) < REFERENCE_CACHE_TTL:
        rows = cache["data"]
        if active_only:
            return [r for r in rows if r.get('active') == 1]
        return rows

    # Cache miss - fetch from DB
    conn = get_db_connection_reference()
    try:
        cursor = conn.cursor(dictionary=True)
        if active_only:
            cursor.execute("SELECT * FROM feedsource WHERE active = 1 ORDER BY priority DESC, id ASC")
        else:
            cursor.execute("SELECT * FROM feedsource ORDER BY priority DESC, id ASC")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        # Update cache
        _REFERENCE_CACHE["feedsource"] = {"data": rows, "ts": time.time()}
        return rows if active_only else rows
    except Exception as e:
        print(f"[CACHE] Error fetching feedsource: {e}")
        if conn:
            conn.close()
        return cache["data"] if cache["data"] is not None else []


def get_idx_entity_cached() -> List[Dict[str, Any]]:
    """Get idx_entity reference data from MySQL with 5-minute TTL cache."""
    global _REFERENCE_CACHE
    cache = _REFERENCE_CACHE["idx_entity"]

    if cache["data"] is not None and (time.time() - cache["ts"]) < REFERENCE_CACHE_TTL:
        return cache["data"]

    conn = get_db_connection_reference()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT kode, nama_perusahaan, sektor, sub_sektor FROM idx_entity")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        _REFERENCE_CACHE["idx_entity"] = {"data": rows, "ts": time.time()}
        return rows
    except Exception as e:
        print(f"[CACHE] Error fetching idx_entity: {e}")
        if conn:
            conn.close()
        return cache["data"] if cache["data"] is not None else []


def get_db_connection_reference():
    """Get a DB connection for reference data cache (uses main pool)."""
    from services.system import db_utils
    return db_utils.get_db_connection()

