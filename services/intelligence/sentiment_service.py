import os
import pandas as pd
import numpy as np
import time
import json
import logging
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
except ImportError as _import_err:
    MODELS_AVAILABLE = False
    print(f"Warning: langdetect or transformers missing. Sentiment service will work in degraded mode. Error: {_import_err}")

import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='pandas')

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("sentiment_service")

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
EN_MODEL_ID = "ProsusAI/finbert"

# --- Module Constants ---
TIER_1_ENTITIES = ['fed', 'powell', 'fomc', 'opec', 'israel', 'iran', 'russia', 'china', 'biden', 'sec', 'ecb', 'war', 'strike']
CACHE_FILE = os.path.join(os.path.dirname(__file__), "sentiment_snapshots.json")

# Background analyzer config
BG_BATCH_SIZE = int(os.getenv("SENTIMENT_BG_BATCH_SIZE", "500"))
BG_INTERVAL_SECONDS = int(os.getenv("SENTIMENT_BG_INTERVAL", "1800"))
BG_MAX_CONSECUTIVE_FAILURES = int(os.getenv("SENTIMENT_BG_MAX_FAILURES", "5"))
BG_FAILURE_BACKOFF_SECONDS = int(os.getenv("SENTIMENT_BG_FAILURE_BACKOFF", "300"))

# Bulk labeling config
BULK_BATCH_SIZE = int(os.getenv("SENTIMENT_BULK_BATCH_SIZE", "500"))

app = FastAPI(
    debug=os.getenv("FASTAPI_DEBUG", "false").lower() == "true",
    title="Asetpedia Sentiment Analysis Service"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Sentiment Analyzer ---

class SentimentAnalyzer:
    def __init__(self):
        self.id_pipeline = None
        self.en_pipeline = None
        self.id_label_map = {}
        self.en_label_map = {}
        self._model_load_error = None

        if MODELS_AVAILABLE:
            logger.info("Loading Transformers models (BERT Indonesian & FinBERT)...")
            self.load_models()

    def load_models(self):
        try:
            self.id_pipeline = pipeline("sentiment-analysis", model=ID_MODEL_ID)
            self.en_pipeline = pipeline("sentiment-analysis", model=EN_MODEL_ID)

            # Build robust label maps from model configs
            if hasattr(self.id_pipeline, 'model') and hasattr(self.id_pipeline.model, 'config'):
                self.id_label_map = self._build_label_map(self.id_pipeline.model.config)
            if hasattr(self.en_pipeline, 'model') and hasattr(self.en_pipeline.model, 'config'):
                self.en_label_map = self._build_label_map(self.en_pipeline.model.config)

            logger.info("Models loaded successfully.")
        except Exception as e:
            self._model_load_error = str(e)
            logger.error(f"Error loading models: {e}")

    def _build_label_map(self, config) -> Dict[str, str]:
        """Build a mapping from model label IDs to normalized sentiment strings."""
        label_map = {}
        id2label = getattr(config, 'id2label', {})
        for idx, label in id2label.items():
            label_upper = str(label).upper()
            if 'NEG' in label_upper or 'LABEL_0' in label_upper:
                label_map[str(idx)] = "NEGATIVE"
            elif 'POS' in label_upper or 'LABEL_2' in label_upper:
                label_map[str(idx)] = "POSITIVE"
            else:
                label_map[str(idx)] = "NEUTRAL"
        return label_map

    def is_healthy(self) -> Dict[str, Any]:
        return {
            "models_available": MODELS_AVAILABLE,
            "id_model_loaded": self.id_pipeline is not None,
            "en_model_loaded": self.en_pipeline is not None,
            "model_load_error": self._model_load_error,
        }

    def lang_detect(self, text: str) -> str:
        if not MODELS_AVAILABLE or not text or not text.strip():
            return "en"
        try:
            detected = detect(text)
            return detected if detected in ('id', 'en') else 'en'
        except Exception as e:
            logger.warning(f"Language detection failed: {e}")
            return "en"

    def analyze_batch(self, articles: List[Dict], force: bool = False, save_db: bool = True) -> List[Dict]:
        if not MODELS_AVAILABLE:
            logger.warning("Models not available, skipping analysis")
            return articles

        processed_articles = []
        updates = []
        failure_count = 0

        for art in articles:
            art_id = art.get('id', 'unknown')

            if not force and art.get('sentiment'):
                processed_articles.append(art)
                continue

            text = (art.get('title', '') + " " + (art.get('description') or ""))[:512]
            if not text.strip():
                logger.warning(f"Article {art_id} has empty text, skipping")
                processed_articles.append(art)
                continue

            lang = self.lang_detect(text)
            pipe = self.id_pipeline if lang == 'id' else self.en_pipeline
            label_map = self.id_label_map if lang == 'id' else self.en_label_map

            if not pipe:
                logger.warning(f"Pipeline not available for lang={lang}, article {art_id}")
                processed_articles.append(art)
                failure_count += 1
                continue

            sentiment = None
            try:
                res = pipe(text)[0]
                label = str(res.get('label', '')).upper()
                score = res.get('score', 0.0)

                # Try robust label mapping first
                sentiment = label_map.get(str(res.get('label', '')), None)
                if not sentiment:
                    # Fallback to string matching
                    if 'NEG' in label or 'LABEL_0' in label:
                        sentiment = "NEGATIVE"
                    elif 'POS' in label or 'LABEL_2' in label:
                        sentiment = "POSITIVE"
                    else:
                        sentiment = "NEUTRAL"

                art['sentiment'] = sentiment
                art['sentiment_lang'] = lang
                art['sentiment_score'] = round(float(score), 4)

                if art.get('id'):
                    updates.append((sentiment, lang, art['id']))

                processed_articles.append(art)
            except Exception as e:
                logger.error(f"Sentiment analysis failed for article {art_id}: {e}")
                failure_count += 1
                # Retry once with truncated text if it might be a length issue
                if len(text) > 256:
                    try:
                        short_text = text[:256]
                        res = pipe(short_text)[0]
                        label = str(res.get('label', '')).upper()
                        sentiment = label_map.get(str(res.get('label', '')), None)
                        if not sentiment:
                            if 'NEG' in label or 'LABEL_0' in label:
                                sentiment = "NEGATIVE"
                            elif 'POS' in label or 'LABEL_2' in label:
                                sentiment = "POSITIVE"
                            else:
                                sentiment = "NEUTRAL"
                        art['sentiment'] = sentiment
                        art['sentiment_lang'] = lang
                        art['sentiment_score'] = round(float(res.get('score', 0.0)), 4)
                        if art.get('id'):
                            updates.append((sentiment, lang, art['id']))
                        processed_articles.append(art)
                        logger.info(f"Retry with truncated text succeeded for article {art_id}")
                        continue
                    except Exception as retry_err:
                        logger.error(f"Retry also failed for article {art_id}: {retry_err}")
                processed_articles.append(art)

        if save_db and updates:
            self.save_bulk_to_db(updates)

        if failure_count > 0:
            logger.warning(f"Batch completed with {failure_count}/{len(articles)} failures")

        return processed_articles

    def save_bulk_to_db(self, updates: List[tuple]):
        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            query = """
                UPDATE article 
                SET sentiment = %s, sentiment_lang = %s
                WHERE id = %s
            """
            cursor.executemany(query, updates)
            conn.commit()
            logger.info(f"Bulk saved {len(updates)} sentiment labels")
        except Exception as e:
            logger.error(f"Bulk save error: {e}")
            if conn:
                conn.rollback()
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def save_to_db(self, article_id, sentiment, lang):
        self.save_bulk_to_db([(sentiment, lang, article_id)])


# Global singleton
analyzer = SentimentAnalyzer()

# --- Background Analyzer with Circuit Breaker ---

def background_analyzer():
    if not MODELS_AVAILABLE:
        logger.warning("Models not available, background analyzer will not start")
        return

    logger.info(f"Background scheduler initialized ({BG_INTERVAL_SECONDS}s interval, batch={BG_BATCH_SIZE})")
    consecutive_failures = 0

    while True:
        conn = None
        try:
            conn = get_db_connection()
            from datetime import timezone
            today_start = datetime.now(timezone.utc).strftime('%Y-%m-%d 00:00:00')

            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, title, description FROM article WHERE sentiment IS NULL AND (createdAt >= %s OR pubDate >= %s) LIMIT %s",
                (today_start, today_start, BG_BATCH_SIZE)
            )
            articles = cursor.fetchall()
            cursor.close()

            if articles:
                logger.info(f"Background analyzer processing {len(articles)} articles")
                analyzer.analyze_batch(articles)
                consecutive_failures = 0  # Reset on success
            else:
                logger.debug("No new articles to process")

            # Generate summary
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
            consecutive_failures += 1
            logger.error(f"Scheduler error ({consecutive_failures}/{BG_MAX_CONSECUTIVE_FAILURES}): {e}")

            if consecutive_failures >= BG_MAX_CONSECUTIVE_FAILURES:
                logger.critical(f"Too many consecutive failures ({consecutive_failures}). Pausing for {BG_FAILURE_BACKOFF_SECONDS}s")
                time.sleep(BG_FAILURE_BACKOFF_SECONDS)
                consecutive_failures = 0
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        time.sleep(BG_INTERVAL_SECONDS)


# --- API Endpoints ---

@app.get("/api/sentiment/health")
def health_check():
    """Health check endpoint that verifies model and DB status."""
    model_status = analyzer.is_healthy()
    db_ok = False
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        db_ok = True
    except Exception as e:
        logger.error(f"Health check DB error: {e}")

    status = "healthy" if (model_status["models_available"] and db_ok) else "degraded"
    if not model_status["models_available"]:
        status = "unhealthy"

    return {
        "status": status,
        "models": model_status,
        "database": "connected" if db_ok else "disconnected",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/sentiment/init")
def get_categories_init():
    """Provides initial category metadata and counts (no pandas)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT f.category, a.sentiment, COUNT(a.id) as count
            FROM article a JOIN feedsource f ON a.sourceId = f.id
            WHERE a.sentiment IS NOT NULL
            GROUP BY f.category, a.sentiment
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        result_map = {}
        for row in rows:
            cat = row['category']
            sent = row['sentiment']
            if cat not in result_map:
                result_map[cat] = {'POSITIVE': 0, 'NEGATIVE': 0, 'NEUTRAL': 0}
            result_map[cat][sent] = row['count']

        output = []
        for cat, counts in result_map.items():
            total = sum(counts.values())
            output.append({
                "category": cat,
                "POSITIVE": counts['POSITIVE'],
                "NEGATIVE": counts['NEGATIVE'],
                "NEUTRAL": counts['NEUTRAL'],
                "total": total,
            })

        return {"status": "success", "data": output}
    except Exception as e:
        logger.error(f"Init endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sentiment/summary-all")
def get_all_summaries():
    """
    Returns a comprehensive sentiment summary for all categories.
    Calculates percentages and a composite score for each category.
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT f.category, a.sentiment, COUNT(a.id) as count
            FROM article a JOIN feedsource f ON a.sourceId = f.id
            WHERE a.sentiment IS NOT NULL
            GROUP BY f.category, a.sentiment
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        result_map = {}
        for row in rows:
            cat = row['category']
            sent = row['sentiment']
            if cat not in result_map:
                result_map[cat] = {'POSITIVE': 0, 'NEGATIVE': 0, 'NEUTRAL': 0}
            result_map[cat][sent] = row['count']

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
        logger.error(f"Summary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sentiment/policy-divergence")
def get_policy_divergence():
    """Analyze Hawkish vs Dovish sentiment for Central Banks."""
    conn = None
    try:
        conn = get_db_connection()
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
            s = row['sentiment']

            cb = None
            if "fed" in t or "powell" in t: cb = "FED"
            elif "ecb" in t or "lagarde" in t: cb = "ECB"
            elif "bank indonesia" in t or "perry" in t: cb = "BI"

            if cb:
                if s == "POSITIVE": results[cb]["dovish"] += 1
                elif s == "NEGATIVE": results[cb]["hawkish"] += 1
                else: results[cb]["neutral"] += 1

        return {"status": "success", "data": results}
    except Exception as e:
        logger.error(f"Policy divergence error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@app.get("/api/sentiment/search")
def search_sentiment(q: str, days: int = 7):
    """Alias endpoint — gateway calls /api/sentiment/search?q=...&days=...
    Delegates to the research_sentiment logic using 'q' as keyword."""
    return research_sentiment(keyword=q)


@app.get("/api/sentiment/research")
def research_sentiment(keyword: str):
    """Keyword-based sentiment research using FULLTEXT index with LIKE fallback."""
    try:
        time_gate = (datetime.utcnow() - timedelta(hours=24*30)).strftime('%Y-%m-%d %H:%M:%S')
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        rows = []
        use_fulltext = True

        # Try FULLTEXT first
        try:
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
        except Exception as ft_err:
            logger.warning(f"FULLTEXT search failed, falling back to LIKE: {ft_err}")
            use_fulltext = False

        # Fallback to LIKE if FULLTEXT failed or returned nothing
        if not use_fulltext or not rows:
            like_pattern = f"%{keyword}%"
            cursor.execute("""
                SELECT a.id, a.link, a.title, a.description, a.pubDate, a.sentiment,
                       COALESCE(f.category, 'General') as category
                FROM article a
                LEFT JOIN feedsource f ON a.sourceId = f.id
                WHERE (a.title LIKE %s OR a.description LIKE %s)
                  AND (a.pubDate >= %s OR a.createdAt >= %s)
                ORDER BY a.pubDate DESC
                LIMIT 500
            """, (like_pattern, like_pattern, time_gate, time_gate))
            rows = cursor.fetchall()

        cursor.close()
        conn.close()

        if not rows:
            return {
                "status": "success",
                "data": { "keyword": keyword, "total": 0, "sentiment_dist": {"POSITIVE": 0, "NEGATIVE": 0, "NEUTRAL": 0}, "articles": [] }
            }

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

            row['pubDate'] = row['pubDate'].strftime('%Y-%m-%d %H:%M:%S') if row['pubDate'] else ''
            articles_out.append(row)

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
        logger.error(f"Research sentiment error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sentiment/analyze")
async def analyze_sentiment_endpoint(articles: List[Dict[str, Any]]):
    """
    Synchronous endpoint for real-time sentiment analysis.
    Takes a list of articles (dict with 'title' and optional 'description')
    and returns them with 'sentiment', 'sentimentScore', and 'impactScore'.
    """
    if not MODELS_AVAILABLE:
        logger.warning("Analyze endpoint called but models not available")
        for art in articles:
            art['sentiment'] = "NEUTRAL"
            art['sentimentScore'] = 0.5
            art['impactScore'] = 0.5
        return articles

    try:
        results = analyzer.analyze_batch(articles, force=True, save_db=False)
        return results
    except Exception as e:
        logger.error(f"Analyze endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- BULK LABELING SYSTEM (Fixed: No Multiprocessing) ---
TASK_PROGRESS = {"status": "idle", "processed": 0, "total": 0, "start_time": None}


def run_bulk_labeling(query: str, params: tuple = None):
    global TASK_PROGRESS
    TASK_PROGRESS["status"] = "running"
    TASK_PROGRESS["processed"] = 0
    start_time_val = time.time()
    TASK_PROGRESS["start_time"] = time.ctime()

    logger.info("=" * 60)
    logger.info(f"[BULK_LABEL] INITIALIZING: {TASK_PROGRESS['start_time']}")

    conn = None
    try:
        conn = get_db_connection()
        # Get total count first
        count_query = f"SELECT COUNT(*) FROM ({query}) as t"
        cursor = conn.cursor()
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]
        TASK_PROGRESS["total"] = total
        cursor.close()

        logger.info(f"[BULK_LABEL] TOTAL ARTICLES TO PROCESS: {total}")
        logger.info(f"[BULK_LABEL] CONFIG: sequential processing | batch_size={BULK_BATCH_SIZE}")
        logger.info("=" * 60)

        offset = 0
        while offset < total:
            fetch_query = f"{query} LIMIT {BULK_BATCH_SIZE} OFFSET {offset}"
            df = pd.read_sql(fetch_query, conn, params=params)
            if df.empty:
                break

            articles_list = df.to_dict('records')
            logger.info(f"[BULK_LABEL] Processing batch of {len(articles_list)} articles (offset={offset})")

            # Process sequentially in the main process (models already loaded here)
            analyzer.analyze_batch(articles_list, force=True, save_db=True)

            offset += len(articles_list)
            TASK_PROGRESS["processed"] = min(offset, total)

            elapsed = time.time() - start_time_val
            speed = TASK_PROGRESS["processed"] / elapsed if elapsed > 0 else 0
            remaining = total - TASK_PROGRESS["processed"]
            eta_seconds = remaining / speed if speed > 0 else 0
            eta_str = str(timedelta(seconds=int(eta_seconds)))
            percent = (TASK_PROGRESS["processed"] / total) * 100 if total > 0 else 0

            logger.info(f"[BULK_LABEL] [{percent:6.2f}%] | Processed: {TASK_PROGRESS['processed']}/{total}")
            logger.info(f"             | Speed: {speed:6.2f} art/sec | Elapsed: {int(elapsed)}s | ETA: {eta_str}")

        logger.info("=" * 60)
        logger.info(f"[BULK_LABEL] TASK COMPLETED SUCCESSFULLY AT {time.ctime()}")
        logger.info(f"[BULK_LABEL] TOTAL PROCESSED: {total} in {int(time.time() - start_time_val)}s")
        logger.info("=" * 60)
        TASK_PROGRESS["status"] = "completed"
    except Exception as e:
        logger.error(f"[BULK_LABEL] TASK FAILED: {e}")
        TASK_PROGRESS["status"] = f"error: {str(e)}"
    finally:
        if conn:
            conn.close()


@app.get("/api/sentiment/label/status")
def label_status():
    return TASK_PROGRESS


@app.get("/api/sentiment/label/missing")
def label_missing(bg: BackgroundTasks):
    query = "SELECT id, title, description FROM article WHERE sentiment IS NULL"
    bg.add_task(run_bulk_labeling, query)
    return {"status": "started", "task": "label_missing"}


@app.get("/api/sentiment/label/all")
def label_all(bg: BackgroundTasks):
    query = "SELECT id, title, description FROM article"
    bg.add_task(run_bulk_labeling, query)
    return {"status": "started", "task": "label_all"}


@app.get("/api/sentiment/label/now")
def label_now(bg: BackgroundTasks):
    from datetime import timezone
    today_start = datetime.now(timezone.utc).strftime('%Y-%m-%d 00:00:00')
    query = "SELECT id, title, description FROM article WHERE (createdAt >= %s OR pubDate >= %s)"
    bg.add_task(run_bulk_labeling, query, (today_start, today_start))
    return {"status": "started", "task": "label_now"}


@app.get("/api/sentiment/label/{date_str}")
def label_date(date_str: str, bg: BackgroundTasks):
    if TASK_PROGRESS["status"] == "running":
        return {"status": "error", "message": "A labeling task is already running."}
    query = "SELECT id, title, description FROM article WHERE DATE(pubDate) = %s OR DATE(createdAt) = %s"
    bg.add_task(run_bulk_labeling, query, (date_str, date_str))
    return {"status": "started", "task": f"label_{date_str}"}


@app.get("/api/sentiment/label/range/{start_str}/{end_str}")
def label_range(start_str: str, end_str: str, bg: BackgroundTasks):
    if TASK_PROGRESS["status"] == "running":
        return {"status": "error", "message": "A labeling task is already running."}
    query = "SELECT id, title, description FROM article WHERE (DATE(pubDate) BETWEEN %s AND %s) OR (DATE(createdAt) BETWEEN %s AND %s)"
    bg.add_task(run_bulk_labeling, query, (start_str, end_str, start_str, end_str))
    return {"status": "started", "task": f"label_range_{start_str}_{end_str}"}


# --- Main Entrypoint ---
if __name__ == "__main__":
    import threading
    if MODELS_AVAILABLE:
        t = threading.Thread(target=background_analyzer, daemon=True)
        t.start()
    uvicorn.run(app, host="0.0.0.0", port=5008)
