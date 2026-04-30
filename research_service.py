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

@app.route('/api/data/fundamental', methods=['GET'])
@app.route('/research/api/data/fundamental', methods=['GET'])
def get_fundamental():
    symbol = request.args.get('symbol', '').strip().upper()
    try:
        data = get_fundamental_data(symbol)
        return jsonify({"status": "success", "data": data})
    except Exception as e:
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
                historical_prices.append({
                    "date": str(ts)[:10],
                    "open": clean_data(row.get("Open")),
                    "high": clean_data(row.get("High")),
                    "low": clean_data(row.get("Low")),
                    "close": clean_data(row.get("Close")),
                    "volume": int(row.get("Volume")) if pd.notna(row.get("Volume")) else 0
                })

        intraday_prices = []
        intraday_df = ticker.history(period="1d", interval="5m")
        if intraday_df.empty:
            intraday_df = ticker.history(period="1d", interval="15m")
        if not intraday_df.empty:
            for ts, row in intraday_df.iterrows():
                intraday_prices.append({
                    "time": str(ts)[11:16],
                    "close": clean_data(row.get("Close"))
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
        gnews_res = requests.get(f"https://api.asetpedia.online/gnews/api/gnews/search?q={symbol}", timeout=5)
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
        gnews_res = requests.get(f"https://api.asetpedia.online/gnews/api/gnews/search?q={name}", timeout=5)
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
        
        messages = [
            {"role": "system", "content": "Anda adalah asisten AI Analis Keuangan Profesional dari Asetpedia Hub."}
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
                stream=True
            )
            for chunk in response:
                content = chunk.choices[0].delta.content
                if content is not None:
                    yield f"data: {json.dumps({'content': content})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    import sys
    port = 5202
    if "--port" in sys.argv:
        try:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        except:
            pass
    app.run(host='0.0.0.0', port=port, debug=True)
