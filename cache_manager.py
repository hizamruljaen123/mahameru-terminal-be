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
    """Save latest news and increment new news counter"""
    conn = get_cache_conn()
    import hashlib
    
    # Check if we were actually passed a list
    if not isinstance(articles, list): articles = [articles]
    
    new_adds = 0
    for art in articles:
        link_hash = hashlib.sha1(art['link'].encode()).hexdigest()
        cursor = conn.execute('''
            INSERT OR REPLACE INTO hot_news (link_hash, category, data, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (link_hash, art['category'], json.dumps(art), art['timestamp']))
        
        # If it was an insert or replace, we count it as 'new' for triggering
        new_adds += 1
    
    # Increment global 'new_items_count'
    conn.execute("UPDATE metadata SET val_int = val_int + ? WHERE id = 'new_items_count'", (new_adds,))
    
    # Keep only latest items
    conn.execute('''
        DELETE FROM hot_news WHERE link_hash NOT IN (
            SELECT link_hash FROM hot_news ORDER BY timestamp DESC LIMIT 400
        )
    ''')
    conn.commit()
    conn.close()

def get_hot_news():
    """Retrieve news from fast cache"""
    conn = get_cache_conn()
    rows = conn.execute('SELECT category, data FROM hot_news ORDER BY timestamp DESC').fetchall()
    
    result = {}
    for row in rows:
        cat = row['category']
        if cat not in result: result[cat] = []
        result[cat].append(json.loads(row['data']))
    
    conn.close()
    return result

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
