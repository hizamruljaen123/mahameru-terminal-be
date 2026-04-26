"""
ASETPEDIA BACKUP & ARCHIVER SERVICE
====================================
Port: 5004
Fungsi:
  1. Terima artikel dari news_service nodes via /api/backup/push
  2. Arsipkan ke MySQL artikel table (INSERT IGNORE by link uniqueness)
  3. Background worker polling SQLite hot-cache → MySQL setiap 90 detik
  4. Emit SocketIO event 'new_articles' ke semua connected clients real-time
  5. Endpoint diagnostics: stats, cleanup, health check
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import time
import os
import hashlib
import threading
import logging
from datetime import datetime
from dotenv import load_dotenv
import dateutil.parser
from db import get_db_connection
import cache_manager

load_dotenv()

# ============================================================
# LOGGING
# ============================================================
LOG_DIR = os.getenv('LOG_DIR', os.path.join(os.path.dirname(__file__), 'logs'))
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'backup_service.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger('backup_service')

# ============================================================
# APP + SOCKETIO (CORS open for local dev)
# ============================================================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'asetpedia-backup-secret')
CORS(app, origins=[os.getenv('FRONTEND_URL', 'https://terminal.asetpedia.online'), os.getenv('FRONTEND_URL_ALT', 'https://asetpedia.online'), os.getenv('DASHBOARD_API_URL', 'https://monitoring.asetpedia.online')])
socketio = SocketIO(
    app,
    cors_allowed_origins='*',
    async_mode=None, # Auto-detect (eventlet, gevent, or threading)
    logger=True,
    engineio_logger=True,
    ping_timeout=60,
    ping_interval=25,
    always_connect=True
)

# Stats counter (in-memory)
_stats = {'archived': 0, 'skipped': 0, 'errors': 0, 'last_sync': None}
_stats_lock = threading.Lock()

# ============================================================
# CORE: MIGRATE ARTICLES TO MYSQL
# ============================================================
def migrate_articles(articles, emit_realtime=True):
    """
    Persist articles to MySQL with full deduplication.
    After successful insert, broadcast via SocketIO.

    Args:
        articles: list of article dicts
        emit_realtime: if True, emit socket event with new articles
    """
    if not articles:
        return 0, []

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        batch_links = [art['link'] for art in articles if art.get('link')]
        if not batch_links:
            cursor.close()
            conn.close()
            return 0, []

        placeholders = ', '.join(['%s'] * len(batch_links))
        cursor.execute(
            f"SELECT link FROM article WHERE link IN ({placeholders})",
            tuple(batch_links)
        )
        existing_links = {row[0] for row in cursor.fetchall()}

        # --- Filter out duplicates ---
        unique_articles = [
            art for art in articles
            if art.get('link') and art['link'] not in existing_links
        ]

        skipped = len(articles) - len(unique_articles)

        if not unique_articles:
            cursor.close()
            conn.close()
            with _stats_lock:
                _stats['skipped'] += skipped
            return 0, []

        # --- INSERT IGNORE batch ---
        sql = """
        INSERT IGNORE INTO article (
            id, title, description, content, link, pubDate,
            imageUrl, author, sourceId, sourceName, category,
            sentiment, sentimentScore, sentiment_lang, impactScore,
            summary, keywords, entities
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        inserted = 0
        newly_inserted = []

        for art in unique_articles:
            # Generate stable ID from link hash
            id_val = art.get('id') or hashlib.sha1(art['link'].encode()).hexdigest()

            # Parse publish date — use real pubDate if available
            pub_dt = None
            for date_field in ['published', 'pubDate']:
                date_str = art.get(date_field)
                if date_str:
                    try:
                        pub_dt = dateutil.parser.parse(str(date_str))
                        break
                    except Exception:
                        pass

            # Fallback: convert unix timestamp to datetime
            if pub_dt is None:
                ts = art.get('timestamp')
                if ts:
                    try:
                        pub_dt = datetime.fromtimestamp(float(ts))
                    except Exception:
                        pass

            if pub_dt is None:
                pub_dt = datetime.now()

            val = (
                id_val,
                (art.get('title') or '')[:990],                     # cap at column size
                art.get('description'),
                art.get('content'),
                art.get('link'),
                pub_dt,
                art.get('imageUrl'),
                art.get('author'),
                art.get('sourceId'),
                (art.get('sourceName') or art.get('source') or '')[:250],
                (art.get('category') or 'UNCATEGORIZED')[:99],
                art.get('sentiment'),
                art.get('sentimentScore'),
                art.get('sentiment_lang'),
                art.get('impactScore'),
                art.get('summary'),
                art.get('keywords'),
                art.get('entities'),
            )

            try:
                cursor.execute(sql, val)
                if cursor.rowcount > 0:
                    inserted += 1
                    newly_inserted.append({
                        'id': id_val,
                        'title': art.get('title', ''),
                        'link': art.get('link', ''),
                        'source': art.get('sourceName') or art.get('source', ''),
                        'category': art.get('category', ''),
                        'timestamp': art.get('timestamp') or pub_dt.timestamp(),
                        'sentiment': art.get('sentiment'),
                    })
            except Exception as e:
                log.warning(f"INSERT row error [{art.get('link', '?')}]: {e}")

        conn.commit()
        cursor.close()
        conn.close()

        with _stats_lock:
            _stats['archived'] += inserted
            _stats['skipped']  += skipped
            _stats['last_sync'] = time.strftime('%Y-%m-%d %H:%M:%S')

        if inserted > 0:
            log.info(f"ARCHIVED: +{inserted} new | {skipped} skipped | total={_stats['archived']}")

        return inserted, newly_inserted

    except Exception as e:
        log.error(f"migrate_articles error: {e}", exc_info=True)
        with _stats_lock:
            _stats['errors'] += 1
        return 0, []


# ============================================================
# CLEANUP: Remove duplicate articles by link
# ============================================================
def run_global_cleanup():
    log.info("CLEANUP: Starting global deduplication...")
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Remove duplicate links — keep newest
        cursor.execute("""
            DELETE a FROM article a
            INNER JOIN (
                SELECT link, MAX(createdAt) as latest
                FROM article
                GROUP BY link
                HAVING COUNT(*) > 1
            ) dup ON a.link = dup.link AND a.createdAt < dup.latest
        """)
        removed = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        log.info(f"CLEANUP: Removed {removed} duplicate articles")
        return removed
    except Exception as e:
        log.error(f"Cleanup error: {e}")
        return 0


# ============================================================
# BACKGROUND WORKER: Poll SQLite cache → MySQL every 90s
# ============================================================
def background_archiver():
    """
    Independent daemon that continuously polls the hot SQLite cache
    and persists unseen articles to MySQL.
    Emits SocketIO events for each batch of new inserts.
    """
    log.info("ARCHIVER_ENGINE: ONLINE — polling every 90s")

    while True:
        try:
            hot_news = cache_manager.get_hot_news()
            all_articles = []
            for cat_items in hot_news.values():
                all_articles.extend(cat_items)

            if all_articles:
                inserted_count, newly_inserted = migrate_articles(all_articles, emit_realtime=False)
                if inserted_count > 0 and newly_inserted:
                    # Broadcast in background
                    socketio.start_background_task(
                        broadcast_new_articles, 
                        inserted_count, 
                        newly_inserted
                    )

        except Exception as e:
            log.error(f"Background archiver loop error: {e}")

        time.sleep(90)


# ============================================================
# SOCKETIO EVENTS
# ============================================================
@socketio.on('connect')
def on_client_connect():
    log.info(f"WS_CLIENT_CONNECTED: {request.sid}")
    emit('status', {'message': 'Connected to Asetpedia Live Stream', 'timestamp': time.time()})

@socketio.on('disconnect')
def on_client_disconnect():
    log.info(f"WS_CLIENT_DISCONNECTED: {request.sid}")

@socketio.on('subscribe')
def on_subscribe(data):
    """Client can filter which categories it wants"""
    categories = data.get('categories', [])
    log.info(f"CLIENT {request.sid} subscribed to: {categories}")
    emit('subscribed', {'categories': categories})

def broadcast_new_articles(count, articles):
    """Helper to broadcast articles safely in a background task"""
    try:
        socketio.emit('new_articles', {
            'count': count,
            'articles': articles[:50]  # limit payload
        })
        log.info(f"SOCKET_EMIT: Broadcasted {len(articles)} articles to clients")
    except Exception as e:
        log.warning(f"SocketIO broadcast task failed: {e}")


# ============================================================
# REST ENDPOINTS
# ============================================================
@app.route('/api/backup/push', methods=['POST'])
def push_articles():
    """Receive batch articles from news_service nodes"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No payload"}), 400
        
        articles = data.get('articles', [])
        count, newly_inserted = migrate_articles(articles, emit_realtime=False)
        
        if count > 0 and newly_inserted:
            # Important: start broadcast in background to avoid interfering with HTTP response
            socketio.start_background_task(
                broadcast_new_articles, 
                count, 
                newly_inserted
            )
            
        return jsonify({"success": True, "inserted": count})
    except Exception as e:
        log.error(f"API_PUSH_ERROR: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not Found"}), 404

@app.errorhandler(500)
def server_error(e):
    log.error(f"Internal Server Error: {e}", exc_info=True)
    return jsonify({"error": "Internal Server Error"}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    log.error(f"Unhandled Exception: {e}", exc_info=True)
    return jsonify({"error": str(e)}), 500


@app.route('/api/backup/cleanup', methods=['POST'])
def cleanup():
    removed = run_global_cleanup()
    return jsonify({"success": True, "removed": removed})


@app.route('/api/backup/stats', methods=['GET'])
def get_stats():
    with _stats_lock:
        stats = dict(_stats)
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) as total FROM article")
        stats['db_total'] = cursor.fetchone()['total']
        cursor.execute("SELECT COUNT(*) as total FROM article WHERE DATE(pubDate) = CURDATE()")
        stats['db_today'] = cursor.fetchone()['total']
        cursor.execute("""
            SELECT category, COUNT(*) as cnt
            FROM article
            GROUP BY category
            ORDER BY cnt DESC
            LIMIT 20
        """)
        stats['by_category'] = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        stats['db_error'] = str(e)
    return jsonify(stats)


@app.route('/api/backup/health', methods=['GET'])
def health():
    with _stats_lock:
        last_sync = _stats.get('last_sync')
    return jsonify({
        "status": "ok",
        "service": "backup_service",
        "port": 5004,
        "last_sync": last_sync,
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
    })


@app.route('/api/backup/latest', methods=['GET'])
def get_latest():
    """Return last N articles from MySQL — useful for diagnostics"""
    n = min(int(request.args.get('n', 50)), 200)
    category = request.args.get('category', '').strip().upper()
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        if category:
            cursor.execute("""
                SELECT id, title, link, pubDate, sourceName, category, sentiment, impactScore
                FROM article WHERE UPPER(category) LIKE %s
                ORDER BY pubDate DESC LIMIT %s
            """, (f'%{category}%', n))
        else:
            cursor.execute("""
                SELECT id, title, link, pubDate, sourceName, category, sentiment, impactScore
                FROM article ORDER BY pubDate DESC LIMIT %s
            """, (n,))
        rows = cursor.fetchall()
        for row in rows:
            if row.get('pubDate'):
                row['pubDate'] = row['pubDate'].isoformat()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "count": len(rows), "articles": rows})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============================================================
# ENTRYPOINT
# ============================================================
if __name__ == '__main__':
    log.info("BACKUP_SERVICE: Starting on port 5004 with SocketIO...")
    
    # Use socketio.start_background_task for better compatibility with async modes
    socketio.start_background_task(background_archiver)
    
    # In Python 3.13+, Werkzeug 3.x is stricter. 
    # Ensuring we run in a way that minimizes context interference.
    socketio.run(
        app, 
        host='0.0.0.0', 
        port=5004, 
        debug=False, 
        use_reloader=False, 
        allow_unsafe_werkzeug=True
    )
