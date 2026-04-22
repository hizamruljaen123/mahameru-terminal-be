from flask import Flask, Response, stream_with_context, jsonify, request
from flask_cors import CORS
import time
import json
import threading
import calendar
import feedparser
import requests
import hashlib
import logging
import os
import sys
import random
import urllib.parse
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import concurrent.futures

load_dotenv()

sys.path.append(os.path.join(os.path.dirname(__file__), 'utils'))
try:
    from country_detector import count_country_mentions
except ImportError:
    count_country_mentions = None

from db import get_db_connection
import cache_manager

# ============================================================
# LOGGING SETUP (Fix Kritis #6 — silent except: pass)
# ============================================================
LOG_DIR = os.getenv('LOG_DIR', os.path.join(os.path.dirname(__file__), 'logs'))
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, 'news_service.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger('news_service')

# ============================================================
# CRAWL SETTINGS FROM ENV (Fix Kritis #11 — hardcoded values)
# ============================================================
GNEWS_MIN_DELAY      = float(os.getenv('GNEWS_MIN_DELAY', '1.5'))
GNEWS_MAX_DELAY      = float(os.getenv('GNEWS_MAX_DELAY', '3.5'))
OTHER_FEED_MIN_DELAY = float(os.getenv('OTHER_FEED_MIN_DELAY', '0.3'))
OTHER_FEED_MAX_DELAY = float(os.getenv('OTHER_FEED_MAX_DELAY', '0.8'))
MAX_CACHE_PER_CAT    = int(os.getenv('MAX_CACHE_PER_CATEGORY', '200'))
MAX_ARTICLES_PER_FEED = int(os.getenv('MAX_ARTICLES_PER_FEED', '30'))
CONCURRENT_WORKERS   = int(os.getenv('CONCURRENT_FETCH_WORKERS', '8'))
SYNC_INTERVAL_HIGH   = int(os.getenv('SYNC_INTERVAL_HIGH_PRIORITY', '300'))
SYNC_INTERVAL_LOW    = int(os.getenv('SYNC_INTERVAL_LOW_PRIORITY', '1800'))
BACKUP_SERVICE_URL   = os.getenv('BACKUP_SERVICE_URL', 'http://localhost:5004')

# ============================================================
# FLASK APP
# ============================================================
cache_manager.init_cache()
app = Flask(__name__)
CORS(app)

# ============================================================
# GLOBAL STATE
# ============================================================
news_cache      = {}
news_cache_lock = threading.Lock()
fetch_status    = {"message": "IDLE", "last_source": "", "count": 0, "total": 0, "categories": []}
status_lock     = threading.Lock()
manual_refresh_event  = threading.Event()
sync_lock             = threading.Lock()
stop_requested_event  = threading.Event()

# ============================================================
# PRIORITY CATEGORIES — Tiered (sync dengan frontend)
# ============================================================
PRIORITY_CATEGORIES = [
    # TIER 1: BREAKING & CORE NATIONAL
    'INDONESIA', 'BUSINESS', 'EKONOMI', 'ECONOMY', 'INVESTASI', 'POLITICS', 'PEMERINTAHAN', 'UPDATES',
    # TIER 2: STRATEGIC INTELLIGENCE & RISK
    'INTELLIGENCE', 'GEOPOLITICS', 'INDUSTRIAL INTEL', 'RISK MANAGEMENT', 'BUSINESS RISK',
    'CYBER SECURITY', 'CYBER INTEL', 'SUPPLY CHAIN', 'ECONOMIC INTEL',
    # TIER 3: LEGAL & HUKUM
    'ARBITRATION', 'LEGAL COMPLIANCE', 'LEGAL RISK', 'HUKUM INTERNASIONAL', 'HUKUM BISNIS',
    'HUKUM PIDANA', 'TRADE LAW', 'OFFICIAL DOCUMENTATION', 'OFFICIAL SPEECHES',
    # TIER 4: MILITARY & INDUSTRIAL
    'MILITARY NEWS', 'DEFENSE NEWS', 'NAVAL NEWS', 'ARMY NEWS', 'ENERGY', 'ENERGI',
    'MINING', 'MANUFACTURING', 'INDUSTRIAL', 'INDUSTRI', 'INFRASTRUKTUR', 'LOGISTICS',
    'LOGISTIK', 'AVIATION', 'PERDAGANGAN', 'BUSINESS/CONTRACTS',
    # TIER 5: TEKNOLOGI, FINANSIAL & LINGKUNGAN
    'TECHNOLOGY', 'TEKNOLOGI', 'FINANCE', 'KEUANGAN', 'CRYPTO ANALISIS', 'CRYPTO',
    'CRYPTO INDONESIA', 'UTILITY', 'REAL ESTATE', 'PROPERTY', 'AGRICULTURE',
    'ESG COMPLIANCE', 'ENVIRONMENTAL', 'ENVIRONMENT', 'LINGKUNGAN',
    # TIER 6: SOSIAL, KESEHATAN & UMUM
    'INTERNATIONAL', 'WORLD', 'SCIENCE', 'HEALTHCARE', 'HEALTH', 'HEALTH LAW',
    'SOCIAL RISK', 'SOSIAL', 'TENAGA KERJA', 'HUMAN RESOURCES', 'PRESS RELEASES',
    'INFORMATION', 'PRESS', 'DOCUMENTATION', 'MAGAZINE', 'CONSUMER GOODS', 'CONSUMER',
    'RETAIL', 'SERVICE',
    # TIER 7: LOW RELEVANCE
    'HISTORY', 'PODCAST', 'SPORTS', 'ENTERTAINMENT', 'GALLERY'
]

# High-priority categories — synced more frequently
HIGH_PRIORITY_CATS = set(PRIORITY_CATEGORIES[:24])  # Tier 1-3

# ============================================================
# SOURCE REGISTRY: Database (Primary) + Google News Fallback
# ============================================================
def build_source_list(assigned_categories=None):
    """
    Build source list exclusively from MySQL feedsource table.
    Google News RSS is injected as fallback ONLY for categories
    that have zero coverage in the database.

    Priority order:
      1. DB sources (active=1) — sorted by priority DESC
      2. Google News dynamic injection for uncovered categories
    """
    sources = []
    covered_categories = set()  # Track which cats have at least 1 DB source

    # --- Step 1: Load ALL active sources from feedsource table ---
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if assigned_categories:
            # Case-insensitive category match using UPPER()
            placeholders = ', '.join(['%s'] * len(assigned_categories))
            cursor.execute(
                f"SELECT * FROM feedsource WHERE active = 1 AND UPPER(category) IN ({placeholders}) ORDER BY priority DESC, id ASC",
                tuple(c.upper() for c in assigned_categories)
            )
        else:
            cursor.execute("SELECT * FROM feedsource WHERE active = 1 ORDER BY priority DESC, id ASC")

        db_rows = cursor.fetchall()
        cursor.close()
        conn.close()

        for row in db_rows:
            cat = (row.get('category') or 'UNCATEGORIZED').strip().upper()
            url = row.get('url', '')
            is_google = 'news.google.com' in url

            sources.append({
                'id': row.get('id'),
                'name': row.get('name', 'Unknown'),
                'url': url,
                'category': cat,
                'active': 1,
                'priority': row.get('priority', 0),
                'trust': 8 if not is_google else 5,  # DB sources assumed to be curated
                'is_primary': not is_google,
                'is_google': is_google,
                'source': 'db',
            })
            covered_categories.add(cat)

        log.info(f"DB_SOURCES: Loaded {len(sources)} active sources from feedsource table")

    except Exception as e:
        log.error(f"DB feedsource load failed: {e}")

    # --- Step 2: Google News fallback ONLY for uncovered categories ---
    target_cats = set(
        c.upper() for c in (assigned_categories or PRIORITY_CATEGORIES)
    )

    injected = 0
    for cat in target_cats:
        if cat not in covered_categories:
            query_encoded = urllib.parse.quote(cat)
            sources.append({
                'id': None,
                'name': f"GNews_Fallback_{cat.replace(' ', '_')}",
                'url': f"https://news.google.com/rss/search?q={query_encoded}&hl=en-ID&gl=ID&ceid=ID:en",
                'category': cat,
                'active': 1,
                'priority': 0,
                'trust': 4,
                'is_primary': False,
                'is_google': True,
                'source': 'gnews_fallback',
            })
            covered_categories.add(cat)
            injected += 1

    db_count   = sum(1 for s in sources if s['source'] == 'db' and not s['is_google'])
    gnews_db   = sum(1 for s in sources if s['source'] == 'db' and s['is_google'])
    gnews_fall = injected

    log.info(
        f"SOURCE_REGISTRY: {len(sources)} total | "
        f"{db_count} primary DB | {gnews_db} GNews-in-DB | {gnews_fall} GNews fallback injected"
    )
    return sources


# ============================================================
# FETCH RSS FEED (Fix: timestamp asli, retry, proper error handling)
# ============================================================
def fetch_rss_feed(source, retry_count=2):
    """
    Fetch RSS with:
    - Real publication timestamp (not crawl time)
    - Retry + exponential backoff for 429/5xx
    - Proper error logging
    """
    url = source['url']
    is_google = source.get('is_google', 'news.google.com' in url)

    # Adaptive delay based on source type
    if is_google:
        time.sleep(random.uniform(GNEWS_MIN_DELAY, GNEWS_MAX_DELAY))
    else:
        time.sleep(random.uniform(OTHER_FEED_MIN_DELAY, OTHER_FEED_MAX_DELAY))

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*',
        'Accept-Language': 'en-US,en;q=0.9,id;q=0.8',
        'Cache-Control': 'no-cache',
    }

    for attempt in range(retry_count + 1):
        try:
            response = requests.get(url, timeout=12, headers=headers)

            # Handle rate limiting with exponential backoff
            if response.status_code == 429:
                wait = (2 ** attempt) * 5
                log.warning(f"RATE_LIMITED [{source['name']}] — waiting {wait}s (attempt {attempt+1})")
                time.sleep(wait)
                continue

            if response.status_code != 200:
                log.warning(f"FETCH_ERROR [{source['name']}] HTTP {response.status_code}")
                return []

            feed = feedparser.parse(response.content)
            items = []

            for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
                # === FIX KRITIS #2: Use real publication timestamp ===
                published_parsed = entry.get('published_parsed') or entry.get('updated_parsed')
                if published_parsed:
                    real_timestamp = float(calendar.timegm(published_parsed))
                else:
                    # Fallback only if no publish date — mark as crawl time
                    real_timestamp = time.time()

                # Skip very old articles (> 7 days) to maintain freshness
                if time.time() - real_timestamp > 7 * 86400:
                    continue

                # Title cleaning for Google News (strips " - Source Name")
                raw_title = entry.get('title', 'Unknown Title')
                display_title = raw_title
                detected_source = source['name']
                if is_google and ' - ' in raw_title:
                    parts = raw_title.rsplit(' - ', 1)
                    display_title = parts[0].strip()
                    detected_source = parts[1].strip()

                # Image extraction
                image_url = None
                if hasattr(entry, 'media_content') and entry.media_content:
                    image_url = entry.media_content[0].get('url')
                elif hasattr(entry, 'links'):
                    for link in entry.links:
                        if 'image' in link.get('type', ''):
                            image_url = link.get('href')
                            break

                # Full content if available
                full_content = None
                if hasattr(entry, 'content') and entry.content:
                    full_content = entry.content[0].get('value')

                article_link = entry.get('link', '')
                if not article_link:
                    continue

                items.append({
                    'title': display_title,
                    'link': article_link,
                    'description': entry.get('summary', entry.get('description', '')),
                    'content': full_content,
                    'author': entry.get('author'),
                    'imageUrl': image_url,
                    'published': entry.get('published', entry.get('updated', '')),
                    'source': detected_source,
                    'sourceId': source.get('id'),
                    'category': (source['category'] or 'UNCATEGORIZED').upper(),
                    'timestamp': real_timestamp,           # ← Real publish time
                    'crawled_at': time.time(),             # ← When we actually fetched
                    'trust': source.get('trust', 5),
                    'is_primary': source.get('is_primary', False),
                })

            return items

        except Exception as e:
            log.error(f"FETCH_EXCEPTION [{source['name']}] attempt {attempt+1}: {e}")
            if attempt < retry_count:
                time.sleep(2 ** attempt)

    return []


# ============================================================
# CONCURRENT FULL SYNC (Fix Kritis #4 — single-threaded)
# ============================================================
def run_full_sync(assigned_categories=None):
    """
    Concurrent synchronization using ThreadPoolExecutor.
    High-priority categories are fetched first.
    """
    if sync_lock.locked():
        log.warning("Sync already in progress — skipping")
        return {"error": "Another sync is already in progress"}

    with sync_lock:
        global news_cache
        start_time = time.time()
        node_id = f"NODE_{os.getpid()}"
        try:
            sources = build_source_list(assigned_categories)
            total = len(sources)

            if total == 0:
                log.info(f"{node_id}: No sources. Standing by.")
                return {"success": True, "message": "NO_SOURCES_ASSIGNED"}

            # Sort: primary sources and high-priority categories first
            def sort_key(s):
                cat = s['category']
                priority = 0 if cat in HIGH_PRIORITY_CATS else 1
                primary = 0 if s.get('is_primary') else 1
                trust = 10 - s.get('trust', 5)
                return (priority, primary, trust)

            sources.sort(key=sort_key)

            with status_lock:
                fetch_status.update({
                    "total": total,
                    "count": 0,
                    "message": f"INIT_STREAMS_{node_id}",
                    "categories": PRIORITY_CATEGORIES if not assigned_categories else assigned_categories
                })

            # Reset cache
            with news_cache_lock:
                if assigned_categories:
                    for cat in assigned_categories:
                        news_cache.pop(cat.upper(), None)
                else:
                    news_cache = {}

            completed_count = 0
            completed_lock = threading.Lock()

            def process_source(source):
                nonlocal completed_count

                if stop_requested_event.is_set():
                    return

                with status_lock:
                    fetch_status["message"] = f"SCANNING: {source['name'].upper()}"
                    fetch_status["last_source"] = source['name']

                items = fetch_rss_feed(source)

                if items:
                    cache_manager.save_to_hot_cache(items)
                    with news_cache_lock:
                        cat = (source['category'] or 'UNCATEGORIZED').upper()
                        if cat not in news_cache:
                            news_cache[cat] = []
                        news_cache[cat].extend(items)
                        # Dedup within category by link hash
                        seen = set()
                        deduped = []
                        for item in news_cache[cat]:
                            key = hashlib.sha1((item.get('link') or '').encode()).hexdigest()
                            if key not in seen:
                                seen.add(key)
                                deduped.append(item)
                        # Sort by real publish time, cap at MAX_CACHE_PER_CAT
                        news_cache[cat] = sorted(deduped, key=lambda x: x['timestamp'], reverse=True)[:MAX_CACHE_PER_CAT]

                with completed_lock:
                    completed_count += 1

                with status_lock:
                    fetch_status["count"] = completed_count

            # Execute concurrently — Google News sources get fewer workers to avoid throttle
            with ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as executor:
                futures = {executor.submit(process_source, src): src for src in sources}
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        src = futures[future]
                        log.error(f"Worker error [{src['name']}]: {e}")

            if stop_requested_event.is_set():
                log.info(f"{node_id} SYNC_ABORTED")
                stop_requested_event.clear()
                return {"success": False, "message": "ABORTED_BY_NEW_REQUEST"}

            # Finalize — push to backup service
            all_collected = []
            with news_cache_lock:
                for cat in news_cache:
                    all_collected.extend(news_cache[cat])

            if all_collected:
                with status_lock:
                    fetch_status["message"] = f"PERSISTING_{node_id}"
                try:
                    requests.post(
                        f"{BACKUP_SERVICE_URL}/api/backup/push",
                        json={'articles': all_collected},
                        timeout=15
                    )
                    requests.post(f"{BACKUP_SERVICE_URL}/api/backup/cleanup", timeout=15)
                except Exception as e:
                    log.error(f"Backup push failed: {e}")  # Fix #6 — no more silent pass

            with status_lock:
                fetch_status["message"] = "READY"
                cache_manager.update_status_cache(fetch_status)

            duration = round(time.time() - start_time, 2)
            log.info(f"{node_id} SYNC_COMPLETE: {len(all_collected)} articles in {duration}s")
            return {
                "success": True,
                "total_sources": total,
                "news_count": len(all_collected),
                "duration_seconds": duration
            }

        except Exception as e:
            with status_lock:
                fetch_status["message"] = f"SYNC_ERROR: {str(e)}"
            log.error(f"run_full_sync fatal: {e}", exc_info=True)
            return {"error": str(e)}


# ============================================================
# BACKGROUND SYNC LOOP — Tiered Intervals
# ============================================================
def update_news_cache_loop(assigned_categories=None):
    # Cache-Aware Startup
    existing = cache_manager.get_hot_news()
    if existing:
        log.info(f"CACHE_FOUND: Delaying first sync cycle by 30s")
        manual_refresh_event.wait(30)
        manual_refresh_event.clear()

    cycle = 0
    while True:
        # Determine which categories to sync this cycle
        # High-priority: every cycle. Low-priority: every 6 cycles (~30 min)
        if assigned_categories:
            cats_this_cycle = assigned_categories
        elif cycle % 6 == 0:
            cats_this_cycle = None  # Sync ALL
        else:
            cats_this_cycle = list(HIGH_PRIORITY_CATS)  # Sync only Tier 1-3

        log.info(f"SYNC CYCLE {cycle}: {'ALL' if cats_this_cycle is None else len(cats_this_cycle)} categories")
        run_full_sync(cats_this_cycle)
        cycle += 1
        manual_refresh_event.wait(SYNC_INTERVAL_HIGH)
        manual_refresh_event.clear()


# ============================================================
# API ROUTES
# ============================================================

@app.route('/api/news/data', methods=['GET'])
def get_current_data():
    """Retrieve hot news with MySQL archive fallback"""
    current_news = cache_manager.get_hot_news()
    priority_cats = [c.upper() for c in PRIORITY_CATEGORIES]

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        for cat in priority_cats:
            if cat not in current_news or len(current_news[cat]) == 0:
                cursor.execute("""
                    SELECT id, title, link, description, pubDate as timestamp,
                           sourceName as source, imageUrl, category,
                           sentiment, sentimentScore, impactScore
                    FROM article WHERE UPPER(category) LIKE %s
                    ORDER BY pubDate DESC LIMIT 100
                """, (f"%{cat}%",))
                archive_items = cursor.fetchall()
                if archive_items:
                    for item in archive_items:
                        if hasattr(item.get('timestamp'), 'timestamp'):
                            item['timestamp'] = item['timestamp'].timestamp()
                    current_news[cat] = archive_items
        cursor.close()
        conn.close()
    except Exception as e:
        log.error(f"Archive fallback error: {e}")

    current_status = cache_manager.get_status_cache()
    cache_manager.reset_new_items_count()
    return jsonify({"news": current_news, "status": current_status})


@app.route('/api/news/search', methods=['GET'])
def search_news():
    query_term = request.args.get('q', '').strip()
    if not query_term:
        return jsonify({"success": False, "error": "No query provided"}), 400
    try:
        results = []
        seen_links = set()
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, title, link, description, pubDate as timestamp,
                   sourceName as source, imageUrl, category, sentiment, sentimentScore, impactScore
            FROM article WHERE title LIKE %s OR description LIKE %s
            ORDER BY pubDate DESC LIMIT 200
        """, (f"%{query_term}%", f"%{query_term}%"))
        for item in cursor.fetchall():
            if hasattr(item.get('timestamp'), 'timestamp'):
                item['timestamp'] = item['timestamp'].timestamp()
            results.append(item)
            seen_links.add(item['link'])
        cursor.close()
        conn.close()

        # Merge live cache hits
        for cat, items in cache_manager.get_hot_news().items():
            for item in items:
                qt = query_term.lower()
                if (qt in item.get('title', '').lower() or qt in item.get('description', '').lower()):
                    if item['link'] not in seen_links:
                        results.append(item)
                        seen_links.add(item['link'])

        results.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
        return jsonify({"success": True, "query": query_term, "results": results})
    except Exception as e:
        log.error(f"Search error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/news/archive/<category>', methods=['GET'])
def get_news_archive(category):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, title, link, description, pubDate as timestamp,
                   sourceName as source, imageUrl, category, sentiment, sentimentScore, impactScore
            FROM article WHERE UPPER(category) LIKE %s
            ORDER BY pubDate DESC LIMIT 150
        """, (f"%{category.upper()}%",))
        items = cursor.fetchall()
        for item in items:
            if hasattr(item.get('timestamp'), 'timestamp'):
                item['timestamp'] = item['timestamp'].timestamp()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "category": category, "news": items})
    except Exception as e:
        log.error(f"Archive [{category}] error: {e}")
        return jsonify({"success": False, "error": str(e), "news": []}), 500


@app.route('/api/news/signal', methods=['GET'])
def check_signal():
    timeout, start = 30, time.time()
    while time.time() - start < timeout:
        count = cache_manager.get_new_items_count()
        if count >= 20:
            cache_manager.reset_new_items_count()
            return jsonify({"signal": True, "new_count": count})
        time.sleep(1)
    return jsonify({"signal": False, "timeout": True})


@app.route('/stream')
def stream():
    def event_stream():
        while True:
            payload = json.dumps({
                "news": cache_manager.get_hot_news(),
                "status": cache_manager.get_status_cache()
            })
            yield f"data: {payload}\n\n"
            time.sleep(3)
    return Response(stream_with_context(event_stream()), mimetype="text/event-stream")


@app.route('/api/news/refresh', methods=['POST', 'GET'])
def trigger_refresh():
    """Trigger manual full sync"""
    stop_requested_event.set()
    time.sleep(0.5)
    stop_requested_event.clear()
    result = run_full_sync(assigned_cats if assigned_cats else None)
    return jsonify(result)


@app.route('/api/news/sources', methods=['GET'])
def list_sources():
    """Expose source registry for diagnostics"""
    sources = build_source_list()
    return jsonify({
        "total": len(sources),
        "primary": sum(1 for s in sources if s.get('is_primary')),
        "google": sum(1 for s in sources if s.get('is_google')),
        "db": sum(1 for s in sources if not s.get('is_primary') and not s.get('is_google')),
        "sources": [{"name": s["name"], "category": s["category"], "trust": s.get("trust", 5), "type": "primary" if s.get("is_primary") else ("google" if s.get("is_google") else "db")} for s in sources]
    })


@app.route('/api/news/cyber-intel', methods=['GET'])
def get_cyber_intel_dedicated():
    """Dedicated endpoint for real-time cyber intelligence from global RSS feeds"""
    try:
        limit = int(request.args.get('limit', 100))
        
        # Daftar sumber OSINT terpilih
        rss_feeds = [
            "https://www.cisa.gov/cybersecurity-advisories/all.xml",
            "https://www.ncsc.gov.uk/api/1/services/reporting/rss/all-alerts-advisories",
            "https://www.enisa.europa.eu/news/enisa-news/RSS",
            "https://www.mandiant.com/resources/blog/rss.xml",
            "https://securelist.com/feed/",
            "https://www.crowdstrike.com/blog/feed/",
            "https://unit42.paloaltonetworks.com/feed/",
            "https://ccdcoe.org/news/rss",
            "https://feeds.feedburner.com/TheHackersNews",
            "https://www.bleepingcomputer.com/feed/",
            "https://isc.sans.edu/rssfeed.xml"
        ]

        all_news = []

        # Worker function untuk memproses feed secara individu
        def fetch_data(url):
            try:
                f = feedparser.parse(url)
                source = f.feed.title if hasattr(f.feed, 'title') else url.split('/')[2]
                entries = []
                for entry in f.entries:
                    # Parsing waktu ke Unix Timestamp
                    dt = entry.get('published_parsed') or entry.get('updated_parsed')
                    ts = time.mktime(dt) if dt else time.time()
                    
                    entries.append({
                        "id": entry.get('id', entry.get('link')),
                        "title": entry.get('title'),
                        "link": entry.get('link'),
                        "description": entry.get('summary', entry.get('description', ''))[:300] + "...",
                        "timestamp": ts,
                        "source": source,
                        "imageUrl": None, # RSS standar jarang menyertakan image tag yang konsisten
                        "category": "CYBER INTEL",
                        "sentiment": "NEUTRAL",
                        "sentimentScore": 0.5,
                        "impactScore": 0.8 if any(word in entry.get('title', '').lower() for word in ['apt', 'critical', 'attack', 'national']) else 0.4
                    })
                return entries
            except:
                return []

        # Eksekusi paralel untuk kecepatan maksimal
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = executor.map(fetch_data, rss_feeds)
            for result in results:
                all_news.extend(result)

        # Sortir: Berita terbaru di atas
        all_news.sort(key=lambda x: x['timestamp'], reverse=True)
        items = all_news[:limit]

        return jsonify({
            "success": True, 
            "category": "CYBER INTEL", 
            "news": items, 
            "count": len(items)
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/news/country-intel', methods=['GET'])
def get_country_intel_news():
    country_name = request.args.get('country', '').strip()
    if not country_name:
        return jsonify({"success": False, "results": []})
    date_str = request.args.get('date', '').strip()
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        where = "(title LIKE %s OR description LIKE %s)"
        params = [f"%{country_name}%", f"%{country_name}%"]
        if date_str:
            where += " AND DATE(pubDate) = %s"
            params.append(date_str)
        cursor.execute(f"""
            SELECT id, title, link, description, pubDate as timestamp,
                   sourceName as source, imageUrl, category, sentiment, sentimentScore, impactScore
            FROM article WHERE {where} ORDER BY pubDate DESC LIMIT 100
        """, tuple(params))
        items = cursor.fetchall()
        for item in items:
            if hasattr(item.get('timestamp'), 'timestamp'):
                item['timestamp'] = item['timestamp'].timestamp()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "country": country_name, "results": items})
    except Exception as e:
        log.error(f"Country intel error: {e}")
        return jsonify({"success": False, "error": str(e), "results": []}), 500


@app.route('/api/news/archive-by-date', methods=['GET'])
def get_news_by_date():
    date_str = request.args.get('date', '').strip()
    if not date_str:
        return jsonify({"success": False, "error": "No date provided"}), 400
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, title, link, description, pubDate as timestamp,
                   sourceName as source, imageUrl, category, sentiment, sentimentScore, impactScore
            FROM article WHERE DATE(pubDate) = %s ORDER BY pubDate DESC LIMIT 500
        """, (date_str,))
        items = cursor.fetchall()
        for item in items:
            if hasattr(item.get('timestamp'), 'timestamp'):
                item['timestamp'] = item['timestamp'].timestamp()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "date": date_str, "results": items})
    except Exception as e:
        log.error(f"Archive by date error: {e}")
        return jsonify({"success": False, "error": str(e), "results": []}), 500


@app.route('/api/news/geo-trending', methods=['GET'])
def get_geo_trending():
    date_str = request.args.get('date', time.strftime('%Y-%m-%d')).strip()
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT title, description, category FROM article WHERE DATE(pubDate) = %s", (date_str,))
        articles = cursor.fetchall()
        cursor.close()
        conn.close()
        if count_country_mentions is None:
            return jsonify({"success": False, "error": "country_detector not available"}), 500
        mentions = count_country_mentions(articles)
        return jsonify({"success": True, "date": date_str, "data": {"mentions": mentions, "totalArticles": len(articles)}})
    except Exception as e:
        log.error(f"Geo trending error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/news/rss-proxy', methods=['GET'])
def rss_proxy():
    target_url = request.args.get('url')
    if not target_url:
        return jsonify({"error": "No URL provided"}), 400
    try:
        response = requests.get(target_url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36'
        })
        res = Response(response.content, mimetype='text/xml')
        res.headers['Access-Control-Allow-Origin'] = '*'
        return res
    except Exception as e:
        return jsonify({"error": str(e)}), 500





# ============================================================
# MAIN ENTRYPOINT
# ============================================================
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Asetpedia News Service')
    parser.add_argument('--port', type=int, default=int(os.getenv('NEWS_SERVICE_PORT_1', '5101')))
    parser.add_argument('--categories', type=str, help='Comma-separated category filter')
    args = parser.parse_args()

    assigned_cats = []
    if args.categories:
        assigned_cats = [c.strip() for c in args.categories.split(',')]
        log.info(f"NODE port={args.port} categories={assigned_cats}")
    else:
        log.info(f"MASTER NODE port={args.port} — ALL categories")

    threading.Thread(target=update_news_cache_loop, args=(assigned_cats or None,), daemon=True).start()
    app.run(debug=False, port=args.port, use_reloader=False)
