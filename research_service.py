import os
import json
import time
import requests
import traceback
from flask import Flask, render_template, request, jsonify, Response
from flask_cors import CORS
import yfinance as yf
from openai import OpenAI
import pandas as pd
import numpy as np
from gnews import GNews
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

# Import modular services
from services.fundamental_service import get_fundamental_data
from services.search_service import search_entities

app = Flask(__name__)
CORS(app)

# Available APIs list for info panel
AVAILABLE_APIS = [
    {
        "category": "Historical Data",
        "description": "Fetch OHLCV history for any yfinance symbol.",
        "endpoint": "https://api.asetpedia.online/market/api/market/history?symbol={SYMBOL}&range=1M",
        "service": "market_service (Port 8088)",
        "method": "GET"
    },
    {
        "category": "Fundamental Data",
        "description": "Fetch comprehensive fundamental data for a symbol.",
        "endpoint": "https://api.asetpedia.online/market/api/market/fundamental?symbol={SYMBOL}",
        "service": "market_service (Port 8088)",
        "method": "GET"
    },
    {
        "category": "News",
        "description": "Search recent Google News for a given query.",
        "endpoint": "https://api.asetpedia.online/gnews/api/gnews/search?q={SYMBOL}",
        "service": "gnews_service (Port 5006)",
        "method": "GET"
    },
    {
        "category": "Sentiment",
        "description": "Analyze sentiment for a specific keyword/ticker.",
        "endpoint": "https://api.asetpedia.online/sentiment/api/sentiment/summary-all",
        "service": "sentiment_service (Port 5008)",
        "method": "GET"
    }
]

CAVEMAN_PROMPT = "RESPOND TERSE LIKE SMART CAVEMAN. ALL TECHNICAL SUBSTANCE STAY. ONLY FLUFF DIE. NO ARTICLES, NO FILLER, NO PLEASANTRIES, NO HEDGING. USE SENTENCE FRAGMENTS. CODE BLOCKS UNTOUCHED."

def clean_data(val):
    import numpy as np
    import pandas as pd
    if val is None:
        return None
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return None
        return f
    except:
        return None

@app.route('/')
@app.route('/research')
@app.route('/research/')
def index():
    return jsonify({"status": "active", "service": "Research Service API"})

@app.route('/api/search', methods=['GET'])
@app.route('/research/api/search', methods=['GET'])
def search():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"status": "success", "data": []})
    results = search_entities(query)
    return jsonify({"status": "success", "data": results})

@app.route('/api/models', methods=['GET'])
@app.route('/research/api/models', methods=['GET'])
def get_deepseek_models():
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    if not api_key:
        return jsonify({"status": "error", "message": "DeepSeek API Key not found"}), 500
    try:
        response = requests.get(
            'https://api.deepseek.com/models',
            headers={
                'Accept': 'application/json',
                'Authorization': f'Bearer {api_key}'
            },
            timeout=10
        )
        return jsonify(response.json())
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/data/fundamental', methods=['GET'])
@app.route('/research/api/data/fundamental', methods=['GET'])
def get_fundamental():
    symbol = request.args.get('symbol', '').strip().upper()
    try:
        data = get_fundamental_data(symbol)
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/gnews/search', methods=['GET'])
def search_gnews():
    q = request.args.get('q', '')
    lang = request.args.get('lang', 'id')
    country = request.args.get('country', 'ID')
    period = request.args.get('period')
    
    if period == 'None' or not period:
        period = None

    if not q:
        return jsonify({"status": "success", "data": []})
        
    try:
        # Direct library usage in main BE
        google_news = GNews(language=lang, country=country, period=period, max_results=100)
        gn_results = google_news.get_news(q)
        
        news_normalized = []
        if gn_results:
            for item in gn_results:
                title = item.get("title")
                if not title or title == "No Title": continue
                
                try:
                    pub_date = item.get('published date') or item.get('publishedAt')
                    if pub_date:
                        dt = datetime.strptime(pub_date, '%a, %d %b %Y %H:%M:%S %Z')
                        ts = int(dt.timestamp())
                    else:
                        ts = int(time.time())
                except: 
                    ts = int(time.time())
                
                news_normalized.append({
                    "title": title,
                    "publisher": item.get("publisher", {}).get("title") if isinstance(item.get("publisher"), dict) else item.get("publisher", "INFRA_SOURCE"),
                    "time": ts,
                    "link": item.get("url", item.get("link", "#")),
                    "description": item.get("description", item.get("snippet", ""))
                })
        
        news_normalized.sort(key=lambda x: x['time'], reverse=True)
        return jsonify({"status": "success", "data": news_normalized})
    except Exception as e:
        print(f"GNews BE Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/data/market', methods=['GET'])
@app.route('/research/api/data/market', methods=['GET'])
def get_market():
    symbol = request.args.get('symbol', '').strip().upper()
    try:
        ticker = yf.Ticker(symbol)
        historical_prices = []
        # AI DeepSeek parity requirement: always 1 year
        hist_df = ticker.history(period="1y", interval="1d")
        if not hist_df.empty:
            for ts, row in hist_df.iterrows():
                close_val = clean_data(row.get("Close"))
                if close_val and close_val > 0:
                    historical_prices.append({
                        "date": str(ts)[:10],
                        "open": clean_data(row.get("Open")),
                        "high": clean_data(row.get("High")),
                        "low": clean_data(row.get("Low")),
                        "close": close_val,
                        "volume": int(row.get("Volume")) if pd.notna(row.get("Volume")) else 0
                    })

        intraday_prices = []
        intraday_df = ticker.history(period="1d", interval="5m")
        if intraday_df.empty:
            intraday_df = ticker.history(period="1d", interval="15m")
        if not intraday_df.empty:
            for ts, row in intraday_df.iterrows():
                close_val = clean_data(row.get("Close"))
                if close_val and close_val > 0:
                    intraday_prices.append({
                        "time": str(ts)[11:16],
                        "close": close_val
                    })
        
        return jsonify({"status": "success", "data": {"historical": historical_prices, "intraday": intraday_prices}})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/data/chart', methods=['GET'])
@app.route('/research/api/data/chart', methods=['GET'])
def get_scalable_chart():
    symbol = request.args.get('symbol', '').strip().upper()
    period = request.args.get('period', '1y').strip()
    try:
        ticker = yf.Ticker(symbol)
        historical_prices = []
        hist_df = ticker.history(period=period, interval="1d")
        if not hist_df.empty:
            for ts, row in hist_df.iterrows():
                historical_prices.append({
                    "date": str(ts)[:10],
                    "open": clean_data(row.get("Open")),
                    "high": clean_data(row.get("High")),
                    "low": clean_data(row.get("Low")),
                    "close": clean_data(row.get("Close")),
                    "volume": int(row.get("Volume")) if pd.notna(row.get("Volume")) else 0
                })
        return jsonify({"status": "success", "data": historical_prices})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/data/news', methods=['GET'])
@app.route('/research/api/data/news', methods=['GET'])
def get_news():
    symbol = request.args.get('symbol', '').strip().upper()
    news_list = []
    
    try:
        query = f"{symbol} Company News developments"
        gnews_res = requests.get(f"https://api.asetpedia.online/gnews/api/gnews/search?q={query}&lang=en&country=US", timeout=5)
        if gnews_res.status_code == 200:
            news_list = gnews_res.json().get('data', [])
    except:
        pass

    if not news_list:
        try:
            yf_news = yf.Ticker(symbol).news
            if yf_news:
                for item in yf_news:
                    news_list.append({
                        "title": item.get("title"),
                        "publisher": item.get("publisher"),
                        "time": item.get("providerPublishTime"),
                        "link": item.get("link")
                    })
        except:
            pass

    sentiment_summary = {}
    try:
        sent_res = requests.get(f"https://api.asetpedia.online/sentiment/api/sentiment/research?keyword={symbol}", timeout=5)
        if sent_res.status_code == 200:
            sentiment_summary = sent_res.json().get('data', {})
    except:
        pass

    return jsonify({"status": "success", "data": {"news": news_list[:10], "sentiment": sentiment_summary}})

@app.route('/api/data/exec-news', methods=['GET'])
@app.route('/research/api/data/exec-news', methods=['GET'])
def get_exec_news():
    name = request.args.get('name', '').strip()
    if not name:
        return jsonify({"status": "success", "data": []})
    
    news_list = []
    try:
        query = f"{name} Leadership Board Management news"
        gnews_res = requests.get(f"https://api.asetpedia.online/gnews/api/gnews/search?q={query}&lang=en&country=US", timeout=5)
        if gnews_res.status_code == 200:
            news_list = gnews_res.json().get('data', [])
    except:
        pass
        
    return jsonify({"status": "success", "data": news_list[:5]})

@app.route('/api/analyze/report', methods=['POST'])
@app.route('/research/api/analyze/report', methods=['POST'])
def analyze_report():
    data = request.json or {}
    symbol = data.get('symbol', '').strip().upper()
    api_key = data.get('api_key', '').strip()
    model = data.get('model', 'deepseek-v4-flash').strip()
    stage = int(data.get('stage', 1))
    full_data = data.get('full_data', {})
    generated_stages = data.get('generated_stages', {})
    caveman = data.get('caveman', False)

    if not api_key:
        api_key = os.environ.get('DEEPSEEK_API_KEY')

    if not api_key:
        return jsonify({"status": "error", "message": "DeepSeek API Key wajib diisi."}), 400

    def generate():
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        
        prompts = {
            1: f"Fokus pada: **1. Ringkasan Emiten & Analisis Sektor**. Jelaskan model bisnisnya, tren industrinya, dan profil umum perusahaan.",
            2: f"Fokus pada: **2. Bedah Fundamental Keuangan**. Analisis laporan keuangan historis, rasio margin, valuasi, kas, dan utang. Apakah valuasi saat ini premium atau murah?",
            3: f"Fokus pada: **3. Analisis Pergerakan Harga & Teknis**. Bahas indikator teknis terkini, level support/resistance, Fibonacci, dan pola harga saham.",
            4: f"Fokus pada: **4. Sorotan Berita & Prospek Sentimen**. Tinjau berita terhangat, pergerakan sentimen publik, dan sentimen pengurus manajemen.",
            5: f"Fokus pada: **5. Kesimpulan & Rekomendasi Investasi**. Berikan kesimpulan dan keputusan investasi tegas (Strong Buy/Buy/Hold/Sell/Strong Sell), target harga, dan profil risikonya."
        }
        
        stage_prompt = prompts.get(stage, prompts[1])
        
        system_msg = "Anda adalah asisten AI Analis Keuangan Profesional dari Asetpedia Hub."
        if caveman:
            system_msg += f" {CAVEMAN_PROMPT}"
            
        messages = [
            {"role": "system", "content": system_msg}
        ]
        
        # Inject previously written stage responses for continuity
        for s_num in range(1, stage):
            s_key = str(s_num)
            if s_key in generated_stages and generated_stages[s_key]:
                messages.append({"role": "user", "content": prompts.get(s_num, "")})
                messages.append({"role": "assistant", "content": generated_stages[s_key]})

        prompt = f"""
        Anda adalah Analis Keuangan Profesional tingkat institusional dari Asetpedia.
        Tuliskan analisis lanjutan yang komprehensif untuk emiten '{symbol}'.
        
        Berikut adalah sub-bagian yang harus Anda tulis sekarang:
        {stage_prompt}

        Data Agregat yang Tersedia untuk Konteks Anda (Gunakan jika relevan):
        {json.dumps(full_data, indent=2)}

        Tuliskan dengan gaya bahasa profesional selayaknya riset dana lindung nilai (hedge fund).
        PENTING: Gunakan format penulisan normal (Proper Case / Sentence Case). DILARANG menggunakan huruf besar semua (ALL CAPS) untuk teks paragraf. Jika menyajikan metrik dalam tabel, WAJIB gunakan format Tabel Markdown valid (`|` dan `|---|`). Gunakan hanya heading tingkat 3 atau 4 (### atau ####) untuk merinci laporan.
        """
        
        messages.append({"role": "user", "content": prompt})

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
                max_tokens=8192
            )
            for chunk in response:
                content = chunk.choices[0].delta.content
                if content is not None:
                    yield f"data: {json.dumps({'content': content})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/analyze/compare', methods=['POST'])
@app.route('/research/api/analyze/compare', methods=['POST'])
def analyze_compare():
    """
    Institutional Comparative Analysis Engine
    Accepts multi-symbol data and streams DeepSeek AI analysis for one stage.
    Frontend provides pre-built system_prompt + user_prompt from promptTemplates.js
    """
    data = request.json or {}
    symbols = data.get('symbols', [])
    stage = int(data.get('stage', 1))
    model = data.get('model', 'deepseek-v4-flash').strip()
    system_prompt = data.get('system_prompt', '')
    user_prompt = data.get('user_prompt', '')
    caveman = data.get('caveman', False)
    api_key = data.get('api_key', '').strip() or os.environ.get('DEEPSEEK_API_KEY')

    if not api_key:
        return jsonify({"status": "error", "message": "DeepSeek API Key required."}), 400

    if not symbols or len(symbols) < 2:
        return jsonify({"status": "error", "message": "At least 2 symbols required for comparison."}), 400

    if not user_prompt:
        return jsonify({"status": "error", "message": "Prompt not provided."}), 400

    def generate():
        try:
            client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
            
            sys_content = system_prompt or "You are a Senior Institutional Research Analyst at Asetpedia Intelligence."
            if caveman:
                sys_content += f" {CAVEMAN_PROMPT}"
                
            messages = [
                {"role": "system", "content": sys_content},
                {"role": "user", "content": user_prompt}
            ]
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
                max_tokens=8192,
                temperature=0.3,  # Lower temperature for more precise institutional analysis
            )
            for chunk in response:
                content = chunk.choices[0].delta.content
                if content is not None:
                    yield f"data: {json.dumps({'content': content})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'X-Accel-Buffering': 'no', 'Cache-Control': 'no-cache'})

if __name__ == '__main__':
    import sys
    port = 5202
    if "--port" in sys.argv:
        try:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        except:
            pass
    app.run(host='0.0.0.0', port=port, debug=True)
