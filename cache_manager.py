import sqlite3
import json
import os
import time

CACHE_DB = os.path.join(os.path.dirname(__file__), 'data', 'news_cache.db')

def get_cache_conn():
    os.makedirs(os.path.dirname(CACHE_DB), exist_ok=True)
    conn = sqlite3.connect(CACHE_DB, timeout=30)
    # WAL Mode for high concurrency (many readers, one writer)
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
