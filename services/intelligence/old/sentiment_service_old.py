import os
import pandas as pd
import numpy as np
import time
import json
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import multiprocessing
from typing import Dict, Any, List
# Try importing models, safely handle absence
try:
    from langdetect import detect, DetectorFactory
    DetectorFactory.seed = 0
    from transformers import pipeline
    MODELS_AVAILABLE = True
except ImportError:
    MODELS_AVAILABLE = False
    print("Warning: langdetect or transformers missing. Sentiment service will work in degraded mode.")

import warnings

warnings.filterwarnings('ignore', category=UserWarning, module='pandas')

# --- Path Injection for shared DB and Utils ---
import sys
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from services.system import db_utils
get_db_connection = db_utils.get_db_connection

# Models IDs (HF)
ID_MODEL_ID = "poerwiyanto/bert-base-indonesian-522M-finetuned-sentiment"
# Replaced SST-2 (Movie Reviews) with FinBERT (Financial/Geopolitical Context)
EN_MODEL_ID = "ProsusAI/finbert"

app = FastAPI(debug=True, title="Asetpedia Sentiment Analysis Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SentimentAnalyzer:
    def __init__(self):
        self.id_pipeline = None
        self.en_pipeline = None
        
        if MODELS_AVAILABLE:
            print(f"[SENTIMENT_SERVICE] Loading Transformers models (BERT Indonesian & DistilBERT)...")
            self.load_models()

    def load_models(self):
        try:
            self.id_pipeline = pipeline("sentiment-analysis", model=ID_MODEL_ID)
            self.en_pipeline = pipeline("sentiment-analysis", model=EN_MODEL_ID)
            print("[SENTIMENT_SERVICE] Models loaded successfully.")
        except Exception as e:
            print(f"[SENTIMENT_SERVICE] Error loading models: {e}")

    def lang_detect(self, text: str) -> str:
        if not MODELS_AVAILABLE: return "en"
        try: return detect(text)
        except: return "en"

    def analyze_batch(self, articles: List[Dict], force: bool = False, save_db: bool = True):
        if not MODELS_AVAILABLE: return articles
        
        processed_articles = []
        updates = []
        
        for art in articles:
            if not force and art.get('sentiment'):
                processed_articles.append(art)
                continue
            
            text = (art['title'] + " " + (art['description'] or ""))[:512]
            lang = self.lang_detect(text)
            
            try:
                pipe = self.id_pipeline if lang == 'id' else self.en_pipeline
                if not pipe:
                    processed_articles.append(art)
                    continue
                    
                res = pipe(text)[0]
                label = res['label'].upper()
                
                sentiment = "NEUTRAL"
                if 'LABEL_0' in label or 'NEGATIVE' in label: sentiment = "NEGATIVE"
                elif 'LABEL_1' in label or 'NEUTRAL' in label: sentiment = "NEUTRAL"
                elif 'LABEL_2' in label or 'POSITIVE' in label: sentiment = "POSITIVE"
                
                art['sentiment'] = sentiment
                art['sentiment_lang'] = lang
                
                if art.get('id'):
                    updates.append((sentiment, lang, art['id']))
                
                processed_articles.append(art)
            except Exception as e:
                processed_articles.append(art)
                
        if save_db and updates:
            self.save_bulk_to_db(updates)
            
        return processed_articles

    def save_bulk_to_db(self, updates: List[tuple]):
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            query = """
                UPDATE article 
                SET sentiment = %s, sentiment_lang = %s
                WHERE id = %s
            """
            cursor.executemany(query, updates)
            conn.commit()
        except Exception as e:
            print(f"[SENTIMENT_SERVICE] Bulk save error: {e}")
        finally:
            cursor.close()
            conn.close()

    def save_to_db(self, article_id, sentiment, lang):
        self.save_bulk_to_db([(sentiment, lang, article_id)])


analyzer = SentimentAnalyzer()

# --- PARALLEL WORKER SYSTEM ---
def process_chunk_worker(articles_chunk):
    # Global 'analyzer' is already initialized during module import in child processes on Windows
    return analyzer.analyze_batch(articles_chunk, force=True, save_db=True)

import threading

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sentiment_snapshots.json")
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sentiment_snapshots.json")

def background_analyzer():
    if not MODELS_AVAILABLE: return
    print("[SENTIMENT_SERVICE] Background scheduler initialized (30m interval).")
    while True:
        conn = None
        try:
            conn = get_db_connection()
            from datetime import timezone
            today_start = datetime.now(timezone.utc).strftime('%Y-%m-%d 00:00:00')
            # Process new articles for sentiment analysis
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, title, description FROM article WHERE sentiment IS NULL AND (createdAt >= %s OR pubDate >= %s) LIMIT 100",
                (today_start, today_start)
            )
            articles = cursor.fetchall()
            cursor.close()

            if articles:
                analyzer.analyze_batch(articles)

            # Generate summary without pandas
            cursor = conn.cursor(dictionary=True)
            summary_query = """
                SELECT f.category, a.sentiment, COUNT(a.id) as count
                FROM article a JOIN feedsource f ON a.sourceId = f.id
                WHERE a.sentiment IS NOT NULL
                GROUP BY f.category, a.sentiment
            """
            cursor.execute(summary_query)
            rows = cursor.fetchall()
            cursor.close()

            if rows:
                # Build pivot manually
                pivot = {}
                for row in rows:
                    cat = row['category']
                    sent = row['sentiment']
                    cnt = row['count']
                    if cat not in pivot:
                        pivot[cat] = {'POSITIVE': 0, 'NEGATIVE': 0, 'NEUTRAL': 0}
                    pivot[cat][sent] = cnt

                snapshot = {
                    "last_updated": time.ctime(),
                    "total_categories": len(pivot),
                    "data": [{"category": cat, **pivot[cat]} for cat in pivot]
                }
                with open(CACHE_FILE, 'w') as f:
                    json.dump(snapshot, f)

        except Exception as e:
            print(f"[SENTIMENT_SERVICE] Scheduler error: {e}")
        finally:
            if conn:
                conn.close()

        time.sleep(1800)

# Will be started in __main__ to avoid running in sub-processes
# threading.Thread(target=background_analyzer, daemon=True).start()

@app.get("/api/sentiment/init")
def get_categories_init():
    """Provides initial category metadata and counts (no pandas)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT f.category, COUNT(a.id) as count
            FROM article a
            JOIN feedsource f ON a.sourceId = f.id
            GROUP BY f.category
            ORDER BY count DESC
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return {"status": "success", "data": rows, "source": "live_mysql"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sentiment/summary-all")
def get_all_summaries():
    """
    Calculates the sentiment dominance matrix per category by joining
    article and feedsource tables. Focuses strictly on analyzed items.
    Optimized: manual aggregation (no pandas) for lower CPU.
    """
    conn = get_db_connection()
    try:
        today = datetime.utcnow().strftime('%Y-%m-%d')
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT f.category as category, a.sentiment, COUNT(a.id) as cnt
            FROM article a
            INNER JOIN feedsource f ON a.sourceId = f.id
            WHERE a.sentiment IS NOT NULL
              AND f.category IS NOT NULL
              AND (DATE(a.pubDate) = %s OR DATE(a.createdAt) = %s)
            GROUP BY f.category, a.sentiment
        """, (today, today))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        if not rows:
            return {"status": "success", "data": []}

        # Manual pivot (no pandas)
        TIER_1_ENTITIES = ['fed', 'powell', 'fomc', 'opec', 'israel', 'iran', 'russia', 'china', 'biden', 'sec', 'ecb', 'war', 'strike']

        result_map = {}
        for row in rows:
            cat = row['category']
            sentiment = row['sentiment']
            count = row['cnt']
            if cat not in result_map:
                result_map[cat] = {'POSITIVE': 0, 'NEGATIVE': 0, 'NEUTRAL': 0}
            result_map[cat][sentiment] = count

        # Build final list with scores
        output = []
        for cat, counts in result_map.items():
            total = sum(counts.values())
            pos_pct = (counts['POSITIVE'] / total * 100) if total else 0
            neg_pct = (counts['NEGATIVE'] / total * 100) if total else 0
            neu_pct = (counts['NEUTRAL'] / total * 100) if total else 0
            score = ((counts['POSITIVE'] - counts['NEGATIVE']) / total * 100) if total else 0
            status = "bullish" if score > 5 else ("bearish" if score < -5 else "neutral")
            output.append({
                "category": cat,
                "POSITIVE": counts['POSITIVE'],
                "NEGATIVE": counts['NEGATIVE'],
                "NEUTRAL": counts['NEUTRAL'],
                "total": total,
                "positive_pct": round(pos_pct, 2),
                "neutral_pct": round(neu_pct, 2),
                "negative_pct": round(neg_pct, 2),
                "score": round(score, 2),
                "sentiment_status": status,
            })

        return {
            "status": "success",
            "data": output,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        print(f"[SENTIMENT_MATRIX_ERR] {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sentiment/policy-divergence")
def get_policy_divergence():
    """Analyze Hawkish vs Dovish sentiment for Central Banks."""
    conn = get_db_connection()
    try:
        query = """
        SELECT a.sentiment, a.title, a.description, a.pubDate 
        FROM article a
        WHERE (a.title LIKE '%Fed%' OR a.title LIKE '%Powell%' OR a.title LIKE '%ECB%' OR a.title LIKE '%Lagarde%' OR a.title LIKE '%Bank Indonesia%' OR a.title LIKE '%Perry Warjiyo%')
        AND a.sentiment IS NOT NULL
        ORDER BY a.pubDate DESC
        LIMIT 200
        """
        df = pd.read_sql(query, conn)
        
        results = {"FED": {"hawkish": 0, "dovish": 0, "neutral": 0}, 
                   "ECB": {"hawkish": 0, "dovish": 0, "neutral": 0}, 
                   "BI": {"hawkish": 0, "dovish": 0, "neutral": 0}}
        
        for _, row in df.iterrows():
            t = str(row['title']).lower()
            d = str(row['description']).lower()
            s = row['sentiment']
            
            cb = None
            if "fed" in t or "powell" in t: cb = "FED"
            elif "ecb" in t or "lagarde" in t: cb = "ECB"
            elif "bank indonesia" in t or "perry" in t: cb = "BI"
            
            if cb:
                if "hike" in t or "hike" in d or "hawkish" in t or "hawkish" in d or s == "POSITIVE":
                    results[cb]["hawkish"] += 1
                elif "cut" in t or "cut" in d or "dovish" in t or "dovish" in d or s == "NEGATIVE":
                    results[cb]["dovish"] += 1
                else:
                    results[cb]["neutral"] += 1
        
        formatted = []
        for bank, data in results.items():
            total = sum(data.values())
            if total == 0: total = 1
            formatted.append({
                "bank": bank,
                "hawkish_pct": round((data["hawkish"] / total) * 100, 2),
                "dovish_pct": round((data["dovish"] / total) * 100, 2),
                "neutral_pct": round((data["neutral"] / total) * 100, 2),
                "total_articles": total
            })
            
        return {"status": "success", "data": formatted}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/api/sentiment/search")
def search_sentiment(q: str, days: int = 7):
    """Alias endpoint — gateway calls /api/sentiment/search?q=...&days=...
    Delegates to the research_sentiment logic using 'q' as keyword."""
    return research_sentiment(keyword=q)


@app.get("/api/sentiment/research")
def research_sentiment(keyword: str):
    """Keyword-based sentiment research using FULLTEXT index."""
    try:
        time_gate = (datetime.utcnow() - timedelta(hours=24*30)).strftime('%Y-%m-%d %H:%M:%S')
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Use FULLTEXT for efficient search
        cursor.execute("""
            SELECT a.id, a.link, a.title, a.description, a.pubDate, a.sentiment,
                   COALESCE(f.category, 'General') as category
            FROM article a
            LEFT JOIN feedsource f ON a.sourceId = f.id
            WHERE MATCH(a.title, a.description) AGAINST(%s IN NATURAL LANGUAGE MODE)
              AND (a.pubDate >= %s OR a.createdAt >= %s)
            ORDER BY a.pubDate DESC
            LIMIT 500
        """, (keyword, time_gate, time_gate))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        if not rows:
            return {
                "status": "success",
                "data": { "keyword": keyword, "total": 0, "sentiment_dist": {"POSITIVE": 0, "NEGATIVE": 0, "NEUTRAL": 0}, "articles": [] }
            }

        TIER_1_ENTITIES = ['fed', 'powell', 'fomc', 'opec', 'israel', 'iran', 'russia', 'china', 'biden', 'sec', 'ecb', 'war', 'strike']

        dist = {'POSITIVE': 0, 'NEGATIVE': 0, 'NEUTRAL': 0}
        total_weight = 0
        raw_total = len(rows)
        articles_out = []

        for row in rows:
            sentiment = row['sentiment'] or 'NEUTRAL'
            title = str(row['title']).lower()
            weight = 3.0 if any(ent in title for ent in TIER_1_ENTITIES) else 1.0
            if sentiment in dist:
                dist[sentiment] += weight
            total_weight += weight

            # Include article (with parsed pubDate)
            row['pubDate'] = row['pubDate'].strftime('%Y-%m-%d %H:%M:%S') if row['pubDate'] else ''
            articles_out.append(row)

        # Normalize distribution to raw_total to keep proportions
        if total_weight > 0:
            dist = {k: int((v / total_weight) * raw_total) for k, v in dist.items()}

        return {
            "status": "success",
            "data": {
                "keyword": keyword,
                "total": raw_total,
                "sentiment_dist": {k: int(v) for k, v in dist.items()},
                "articles": articles_out[:100],
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def root():
    return {"status": "online", "service": "sentiment_service"}


@app.post("/api/sentiment/analyze")
async def analyze_sentiment_endpoint(articles: List[Dict[str, Any]]):
    """
    Synchronous endpoint for real-time sentiment analysis.
    Takes a list of articles (dict with 'title' and optional 'description') 
    and returns them with 'sentiment', 'sentimentScore', and 'impactScore'.
    """
    if not MODELS_AVAILABLE:
        # Fallback if models are not loaded
        for art in articles:
            art['sentiment'] = "NEUTRAL"
            art['sentimentScore'] = 0.5
            art['impactScore'] = 0.5
        return articles
        
    try:
        # Process the articles using the internal analyzer
        results = analyzer.analyze_batch(articles, force=True, save_db=False)
        return results
    except Exception as e:
        print(f"[SENTIMENT_ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- BULK LABELING SYSTEM ---
TASK_PROGRESS = {"status": "idle", "processed": 0, "total": 0, "start_time": None}

def run_bulk_labeling(query: str, params: tuple = None):
    global TASK_PROGRESS
    TASK_PROGRESS["status"] = "running"
    TASK_PROGRESS["processed"] = 0
    start_time_val = time.time()
    TASK_PROGRESS["start_time"] = time.ctime()
    
    print("\n" + "="*60)
    print(f"[BULK_LABEL] INITIALIZING PARALLEL CONDUCTOR: {TASK_PROGRESS['start_time']}")
    
    conn = get_db_connection()
    try:
        # Get total count first
        count_query = f"SELECT COUNT(*) FROM ({query}) as t"
        cursor = conn.cursor()
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]
        TASK_PROGRESS["total"] = total
        cursor.close()
        
        print(f"[BULK_LABEL] TOTAL ARTICLES TO PROCESS: {total}")
        print(f"[BULK_LABEL] CONFIG: 5 SUB-PROCESSES | 300 ARTICLES PER BATCH (1500 parallel)")
        print("="*60 + "\n")
        
        # Parallel Execution with Conductor
        num_workers = 1
        batch_size = 10 # Per process
        total_batch_size = num_workers * batch_size # 1500 total
        offset = 0
        
        with multiprocessing.Pool(processes=num_workers) as pool:
            while offset < total:
                # Fetch a large chunk for the conductor to distribute
                fetch_query = f"{query} LIMIT {total_batch_size} OFFSET {offset}"
                df = pd.read_sql(fetch_query, conn, params=params)
                if df.empty: break
                
                # Split the large chunk into sub-batches for individual processes
                articles_list = df.to_dict('records')
                sub_batches = [articles_list[i:i + batch_size] for i in range(0, len(articles_list), batch_size)]
                
                # Distribute tasks to workers
                print(f"[CONDUCTOR] Distributing {len(articles_list)} articles across {len(sub_batches)} workers...")
                pool.map(process_chunk_worker, sub_batches)
                
                offset += len(articles_list)
                TASK_PROGRESS["processed"] = min(offset, total)
                
                # Calculate stats
                elapsed = time.time() - start_time_val
                speed = TASK_PROGRESS["processed"] / elapsed if elapsed > 0 else 0
                remaining = total - TASK_PROGRESS["processed"]
                eta_seconds = remaining / speed if speed > 0 else 0
                eta_str = str(timedelta(seconds=int(eta_seconds)))
                percent = (TASK_PROGRESS["processed"] / total) * 100 if total > 0 else 0
                
                # Detailed terminal report
                print(f"[BULK_LABEL] [{percent:6.2f}%] | Processed: {TASK_PROGRESS['processed']}/{total}")
                print(f"             | Speed: {speed:6.2f} art/sec | Elapsed: {int(elapsed)}s | ETA: {eta_str}")
                print("-" * 50)
            
        print("\n" + "="*60)
        print(f"[BULK_LABEL] TASK COMPLETED SUCCESSFULLY AT {time.ctime()}")
        print(f"[BULK_LABEL] TOTAL PROCESSED: {total} in {int(time.time() - start_time_val)}s")
        print("="*60 + "\n")
        TASK_PROGRESS["status"] = "completed"
    except Exception as e:
        print(f"\n[BULK_LABEL] !!! TASK FAILED: {e}")
        TASK_PROGRESS["status"] = f"error: {str(e)}"
    finally:
        conn.close()

@app.get("/api/sentiment/label/status")
def get_label_status():
    return TASK_PROGRESS

@app.get("/api/sentiment/label/missing")
def label_missing(bg: BackgroundTasks):
    if TASK_PROGRESS["status"] == "running":
        return {"status": "error", "message": "Task already running"}
    query = "SELECT id, title, description, sentiment FROM article WHERE sentiment IS NULL"
    bg.add_task(run_bulk_labeling, query)
    return {"status": "success", "message": "Bulk labeling started for articles with MISSING labels"}

@app.get("/api/sentiment/label/all")
def label_all(bg: BackgroundTasks):
    if TASK_PROGRESS["status"] == "running":
        return {"status": "error", "message": "Task already running"}
    query = "SELECT id, title, description, sentiment FROM article"
    bg.add_task(run_bulk_labeling, query)
    return {"status": "success", "message": "Bulk labeling started for ALL articles"}

@app.get("/api/sentiment/label/now")
def label_now(bg: BackgroundTasks):
    if TASK_PROGRESS["status"] == "running":
        return {"status": "error", "message": "Task already running"}
    today = datetime.utcnow().strftime('%Y-%m-%d')
    query = "SELECT id, title, description, sentiment FROM article WHERE DATE(pubDate) = %s OR DATE(createdAt) = %s"
    bg.add_task(run_bulk_labeling, query, (today, today))
    return {"status": "success", "message": f"Labeling started for articles on {today}"}

@app.get("/api/sentiment/label/{date_str}")
def label_date(date_str: str, bg: BackgroundTasks):
    if TASK_PROGRESS["status"] == "running":
        return {"status": "error", "message": "Task already running"}
    try:
        dt = datetime.strptime(date_str, "%d%m%Y")
        fmt_date = dt.strftime('%Y-%m-%d')
        query = "SELECT id, title, description, sentiment FROM article WHERE DATE(pubDate) = %s OR DATE(createdAt) = %s"
        bg.add_task(run_bulk_labeling, query, (fmt_date, fmt_date))
        return {"status": "success", "message": f"Labeling started for date {fmt_date}"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use DDMMYYYY")

@app.get("/api/sentiment/label/range/{start_str}/{end_str}")
def label_range(start_str: str, end_str: str, bg: BackgroundTasks):
    if TASK_PROGRESS["status"] == "running":
        return {"status": "error", "message": "Task already running"}
    try:
        start_dt = datetime.strptime(start_str, "%d%m%Y")
        end_dt = datetime.strptime(end_str, "%d%m%Y")
        start_fmt = start_dt.strftime('%Y-%m-%d')
        end_fmt = end_dt.strftime('%Y-%m-%d')
        
        query = "SELECT id, title, description, sentiment FROM article WHERE (pubDate BETWEEN %s AND %s) OR (createdAt BETWEEN %s AND %s)"
        bg.add_task(run_bulk_labeling, query, (start_fmt, end_fmt, start_fmt, end_fmt))
        return {"status": "success", "message": f"Labeling started for range {start_fmt} to {end_fmt}"}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use DDMMYYYY")

if __name__ == "__main__":
    # Start background scheduler only in the main process
    print("[SENTIMENT_SERVICE] Starting background analyzer thread...")
    threading.Thread(target=background_analyzer, daemon=True).start()
    
    # Run uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5008)
