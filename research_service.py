import os
import json
import time
import requests
import traceback
import codecs
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
        "endpoint": "https://api.asetpedia.online/sentiment/api/sentiment/summary-all",
        "service": "sentiment_service (Port 5008)",
        "method": "GET"
    },
    {
        "category": "AI Analysis (DIT)",
        "description": "Multi-model AI synthesis engine via DIT.ai",
        "endpoint": "https://api.dit.ai/v1/responses",
        "service": "research_service (External)",
        "method": "POST"
    }
]

CAVEMAN_PROMPT = "RESPOND TERSE LIKE SMART CAVEMAN. ALL TECHNICAL SUBSTANCE STAY. ONLY FLUFF DIE. NO ARTICLES, NO FILLER, NO PLEASANTRIES, NO HEDGING. USE SENTENCE FRAGMENTS. CODE BLOCKS UNTOUCHED."

# ============================================================================
# MASTER SYSTEM PROMPT — Banking Sector Analysis Rules (from audit_mendalam.txt)
# Applied automatically for banking sector symbols to prevent hallucination,
# proxy data, wrong valuation models, and cross-stage contradictions.
# ============================================================================
MASTER_SYSTEM_PROMPT = """[SYSTEM INSTRUCTION - WAJIB DITAATI SAMPAI STAGE 8 SELESAI]
Anda adalah Senior Equity Research Analyst bersertifikat CFA Level III yang spesialis menganalisis sektor perbankan Indonesia. Anda sedang menulis laporan komparatif institusional.

LAKUKAN HAL BERIKUT SECARA MUTLAK:
1. TAKSONOMI SEKTOR: BBRI dan BMRI adalah bank umum nasional berstatus SIFI (Systemically Important Financial Institutions). DILARANG KERAS menyebut mereka sebagai "Banks - Regional".
2. ANALISIS ARUS KAS: Untuk bank, Operating Cash Flow (OCF) negatif adalah NORMAL saat Loan Growth tinggi. DILARANG KERAS menggunakan rasio OCF/Net Income untuk menilai "kualitas pendapatan", "akrual", atau "tekanan likuiditas".
3. METODOLOGI VALUASI: DILARANG KERAS menggunakan EV/Revenue (karena Deposit bukanlah utang korporasi). DILARANG KERAS menggunakan model DuPont tradisional (Revenue/Total Assets) jika data Total Assets tidak tersedia. Jika diminta menganalisis DuPont tapi data Total Assets kosong, TULIS: "[DATA TIDAK TERSEDIA]". Valuasi wajib hanya menggunakan P/B adjusted ROE atau Dividend Discount Model.
4. ATURAN KEKOSONGAN DATA (ZERO PROXY): Jika diminta menganalisis indikator (Volume, SMA20, Stochastic, Skor Kepemimpinan) tetapi datanya TIDAK ADA di tabel yang saya berikan, Anda WAJIB menulis '[DATA TIDAK TERSEDIA - TIDAK DAPAT DINILAI]'. DILARANG menggunakan MFI sebagai proxy Volume. DILARANG menggunakan Parabolic SAR sebagai proxy SMA. DILARANG menebak skor 1-10 untuk kualitas direksi jika hanya diberi data nama dan umur.
5. ATURAN ANOMALI (RED FLAG): Jika Anda menemukan anomali data (misal: 1 orang menjabat direksi di 2 bank BUMN kompetitor sekaligus, atau Dividend Yield > 10%), Anda WAJIB menghentikan analisis standar dan menempatkan anomali tersebut sebagai "RED FLAG RISIKO TATA KELOLA" yang wajib dibahas mendalam di bagian risiko. DILARANG MENGABAIKANNYA dengan alasan "kesalahan data".
6. KETEPATAN MATEMATIKA: Hitung semua persentase dan rasio dengan presisi 100%. (Contoh: 453T / 409T = 1.1x, BUKAN 2.2x). Total bobot dalam Scorecard WAJIB tepat 100%, dilarang melebihiinya.
7. GAYA BAHASA: Tulis sesingkat, padat, dan sarat informasi mungkin. HINDARI kalimat meta seperti "Sekarang kita akan menganalisis..." atau "Karena data tidak tersedia, kita akan menggunakan asumsi...". Langsung masuk ke data dan kesimpulan.
"""

# Banking sector symbols that trigger the Master System Prompt
BANKING_SYMBOLS = {"BBRI", "BMRI", "BBTN", "BNGA", "BNII", "BNLI", "AGRO", "MAYA", "NISP", "BJBR", "BJTM", "BDMN", "MEGA", "PNBN", "SDRA", "BTPN", "NOBU", "INPC", "BACA", "BBYB", "BBSI", "BEKS", "BGTG", "BINA", "BKSW", "BMSR", "BNBA", "BNLI", "BSIM", "BTPN", "BVIC", "DNAR", "MASB", "MCOR", "NICL", "NOBU", "PNBS", "YULE"}

# Banking-specific metrics that should be requested when sector is banking
BANKING_METRICS = ["NIM", "NPL_Gross", "NPL_Net", "LDR", "CASA_Ratio", "BOPO", "Total_Aset"]

# Chain prompting templates for banking analysis (from audit_mendalam.txt)
PROMPT_A_TEMPLATE = """Berdasarkan [SYSTEM INSTRUCTION] di atas, dan menggunakan DATA pada tabel di bawah ini, buatlah Stage 1 (Model Bisnis & Moat), Stage 2 (Teknikal), dan Stage 3 (Fundamental).

[TABLE DATA HERE]

ATURAN KHUSUS STAGE INI:
- Stage 2: Jika tidak ada data Volume, DILARANG menganalisis Wyckoff (Akumulasi/Distribusi). Batasi hanya pada Support/Resistance, RSI, ADX, dan Risk/Reward.
- Stage 3: Fokus analisis pada NIM, NPL, LDR, BOPO, dan P/B vs ROE. Abaikan analisis DuPont jika tidak ada Total Aset."""

PROMPT_B_TEMPLATE = """Baca kembali output Anda yang tersimpan di Bagian_A.txt. Sekarang buatlah Stage 4 (Scorecard Komparatif) dan Stage 5 (Analisis Sentimen Berita).

ATURAN KHUSUS STAGE INI:
- Stage 4: Buat tabel scorecard dengan total bobot PASTI 100%. Jangan memberikan skor numerik pada variabel yang datanya kosong (beri tanda strip "-"). Pastikan skor ESG konsisten dengan sentimen hukum/berita negatif yang ada.
- Stage 5: Ekstrak hanya fakta spesifik dari berita (misal: denda regulasi, skandal spesifik), jangan membuat generalisasi luas."""

PROMPT_C_TEMPLATE = """Baca kembali Bagian_A.txt dan Bagian_B.txt. Sekarang buatlah Stage 6 (Jejak Kepemimpinan & Intelijen Risiko Hukum) berdasarkan DATA DIREKSI yang saya berikan di bawah ini:

[DIRECTOR DATA HERE]

ATURAN KHUSUS STAGE INI:
- Terapkan ATURAN ANOMALI dari System Instruction. Jika ada nama yang sama di dua perusahaan, wajib jadikan Red Flag utama.
- Jika tidak ada data kompensasi atau buyback, tulis "[DATA TIDAK TERSEDIA]". Jangan mengarang skor Kualitas Kepemimpinan."""

PROMPT_D_TEMPLATE = """Anda telah menyelesaikan Bagian_A (Stage 1-3), Bagian_B (Stage 4-5), dan Bagian_C (Stage 6).

TUGAS ANDA SEKARANG adalah membuat STAGE 8 (One-Pager Institusional & Putusan Akhir).
Sebelum menulis, Anda HARUS melakukan REKONSILIASI untuk menghilangkan kontradiksi:
1. Jika Stage 2 (Teknikal) mendukung BMRI, tapi Stage 3 (Fundamental) mendukung BBRI, Anda TIDAK BOLEH memaksa memilih salah satu secara buta.
2. Anda harus menciptakan SINTESIS: Misalnya, "BBRI untuk akumulasi jangka panjang (Core Holding), namun karena teknikalnya bearish, lakukan averaging down bertahap. Sementara BMRI untuk trading jangka pendek (Tactical Position) karena R:R teknikal yang superior."
3. Jika di Stage 6 ada Red Flag Hukum pada BBRI, hal itu WAJIB menurunkan rekomendasi akhir BBRI atau menambahkan syarat (kondisi) dalam putusan.

Format Stage 8:
- Snapshot 3 kalimat per saham.
- Matriks Rekomendasi Final (Tabel: Harga, Target, Potensi Return, Profil Risiko, Peran di Portofolio).
- Putusan Komparatif Akhir (1 paragraf definitif yang menyebutkan kedua skenario di atas)."""

# Symbols that are Indonesian banking stocks
INDONESIAN_BANK_SYMBOLS = {"BBRI", "BMRI", "BBTN", "BNGA", "BNII", "BDMN", "MEGA", "PNBN", "BJBR", "BJTM", "BTPN", "AGRO", "MAYA", "NISP", "SDRA"}

def is_banking_symbol(symbol):
    """Check if a symbol is an Indonesian banking stock."""
    return symbol.upper() in INDONESIAN_BANK_SYMBOLS

def get_system_prompt(symbol, caveman=False):
    """Get the appropriate system prompt based on symbol sector.
    For banking symbols, uses the Master System Prompt with banking-specific rules.
    """
    if is_banking_symbol(symbol):
        base = MASTER_SYSTEM_PROMPT
    else:
        base = "Anda adalah asisten AI Analis Keuangan Profesional dari Asetpedia Hub."
    
    if caveman:
        base += f"\n{CAVEMAN_PROMPT}"
    return base

DIT_API_URL = "https://api.dit.ai"

DIT_MODELS = [
    {"id": "gpt-5.1", "name": "GPT 5.1", "provider": "OpenAI"},
    {"id": "gpt-5.2", "name": "GPT 5.2", "provider": "OpenAI"},
    {"id": "gpt-5.3", "name": "GPT 5.3", "provider": "OpenAI"},
    {"id": "gpt-5.4", "name": "GPT 5.4", "provider": "OpenAI"},
    {"id": "gpt-5.5", "name": "GPT 5.5", "provider": "OpenAI"},
    {"id": "gpt-5.4-mini", "name": "GPT 5.4-Mini", "provider": "OpenAI"},
    {"id": "kimi-k2.5", "name": "Kimi k2.5", "provider": "Moonshot AI"},
]

GEMINI_MODELS = [
    {"id": "gemini-flash-latest", "name": "Gemini 1.5 Flash", "provider": "Google"},
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

@app.route('/api/models', methods=['GET'])
@app.route('/research/api/models', methods=['GET'])
def get_models():
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    model_map = {}
    
    # 1. Add Official DeepSeek models (Direct API)
    model_map["deepseek-v4-flash"] = {"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash", "provider": "DeepSeek"}
    model_map["deepseek-v4-pro"] = {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro", "provider": "DeepSeek"}
    model_map["deepseek-chat"] = {"id": "deepseek-chat", "name": "DeepSeek Chat", "provider": "DeepSeek"}
    model_map["deepseek-reasoner"] = {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner (R1)", "provider": "DeepSeek"}
    model_map["deepseek-r1"] = {"id": "deepseek-r1", "name": "DeepSeek R1", "provider": "DeepSeek"}
    
    if api_key:
        try:
            response = requests.get(
                'https://api.deepseek.com/models',
                headers={
                    'Accept': 'application/json',
                    'Authorization': f'Bearer {api_key}'
                },
                timeout=5
            )
            if response.status_code == 200:
                ds_models = response.json().get('data', [])
                for m in ds_models:
                    m_id = m['id']
                    if m_id not in model_map:
                        model_map[m_id] = {"id": m_id, "name": f"DeepSeek {m_id}", "provider": "DeepSeek"}
        except:
            pass
            
    # 2. Add Gemini Models
    for m in GEMINI_MODELS:
        model_map[m['id']] = m

    # 3. Add DIT Models (Overwrite if ID matches to ensure correct provider/name)
    for m in DIT_MODELS:
        model_map[m['id']] = m
    
    # Convert map to list while maintaining order (Tiers)
    sorted_models = list(model_map.values())
    
    return jsonify({"status": "success", "data": sorted_models})

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

    # Use Master System Prompt for banking symbols, standard prompt otherwise
    system_prompt = get_system_prompt(symbol, caveman)

    prompts = {
        1: f"Fokus pada: **1. Ringkasan Emiten & Analisis Sektor**. Jelaskan model bisnisnya, tren industrinya, dan profil umum perusahaan.",
        2: f"Fokus pada: **2. Bedah Fundamental Keuangan**. Analisis laporan keuangan historis, rasio margin, valuasi, kas, dan utang. Apakah valuasi saat ini premium atau murah?",
        3: f"Fokus pada: **3. Analisis Pergerakan Harga & Teknis**. Bahas indikator teknis terkini, level support/resistance, Fibonacci, dan pola harga saham.",
        4: f"Fokus pada: **4. Sorotan Berita & Prospek Sentimen**. Tinjau berita terhangat, pergerakan sentimen publik, dan sentimen pengurus manajemen.",
        5: f"Fokus pada: **5. Kesimpulan & Rekomendasi Investasi**. Berikan kesimpulan dan keputusan investasi tegas (Strong Buy/Buy/Hold/Sell/Strong Sell), target harga, dan profil risikonya."
    }
    stage_prompt = prompts.get(stage, prompts[1])

    is_dit = any(m['id'] == model for m in DIT_MODELS)
    is_gemini = any(m['id'] == model for m in GEMINI_MODELS)

    def generate():
        if is_gemini:
            # Gemini API Logic
            gemini_key = os.environ.get('GEMINI_API_KEY')
            if not gemini_key:
                yield f"data: {json.dumps({'error': 'Gemini API Key not found'})}\n\n"
                return

            system_instruction = system_prompt
            
            contents = []
            for s_num in range(1, stage):
                s_key = str(s_num)
                if s_key in generated_stages and generated_stages[s_key]:
                    contents.append({"role": "user", "parts": [{"text": prompts.get(s_num, " ")}]})
                    contents.append({"role": "model", "parts": [{"text": generated_stages[s_key]}]})

            prompt_text = f"""
            Anda adalah Analis Keuangan Profesional tingkat institusional dari Asetpedia.
            Tuliskan analisis lanjutan yang komprehensif untuk emiten '{symbol}'.
            
            Berikut adalah sub-bagian yang harus Anda tulis sekarang:
            {stage_prompt}

            Data Agregat yang Tersedia untuk Konteks Anda (Gunakan jika relevan):
            {json.dumps(full_data, indent=2)}

            Tuliskan dengan gaya bahasa profesional selayaknya riset dana lindung nilai (hedge fund).
            PENTING: Gunakan format penulisan normal (Proper Case / Sentence Case). DILARANG menggunakan huruf besar semua (ALL CAPS) untuk teks paragraf. Jika menyajikan metrik dalam tabel, WAJIB gunakan format Tabel Markdown valid (`|` dan `|---|`). Gunakan hanya heading tingkat 3 atau 4 (### atau ####) untuk merinci laporan.
            """
            contents.append({"role": "user", "parts": [{"text": prompt_text}]})

            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?key={gemini_key}"
            payload = {
                "contents": contents,
                "system_instruction": {"parts": [{"text": system_instruction}]},
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 8192
                }
            }

            try:
                res = requests.post(url, json=payload, stream=True, timeout=120)
                if res.status_code == 200:
                    import re
                    decoder = codecs.getincrementaldecoder('utf-8')()
                    for chunk in res.iter_content(chunk_size=None):
                        if not chunk: continue
                        chunk_str = decoder.decode(chunk, final=False)
                        texts = re.findall(r'"text":\s*"(.*?)"', chunk_str)
                        for t in texts:
                            try:
                                t_clean = t.encode('utf-8').decode('unicode_escape')
                                yield f"data: {json.dumps({'content': t_clean})}\n\n"
                            except:
                                yield f"data: {json.dumps({'content': t})}\n\n"
                else:
                    yield f"data: {json.dumps({'error': f'Gemini API Error: {res.status_code} - {res.text}'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        if is_dit:
            # DIT API Logic
            dit_api_key = os.environ.get('DIT_API_KEY')
            if not dit_api_key:
                yield f"data: {json.dumps({'error': 'DIT API Key not found'})}\n\n"
                return

            url = f"{DIT_API_URL}/v1/chat/completions"
            
            # Prepare OpenAI-style messages
            system_msg = system_prompt
                
            messages = [{"role": "system", "content": system_msg}]
            
            # Context messages
            for s_num in range(1, stage):
                s_key = str(s_num)
                if s_key in generated_stages and generated_stages[s_key]:
                    messages.append({"role": "user", "content": prompts.get(s_num, "")})
                    messages.append({"role": "assistant", "content": generated_stages[s_key]})
            
            # Final prompt
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
            
            payload = {
                "model": model,
                "stream": True,
                "temperature": 0.3,
                "messages": messages
            }
            
            try:
                res = requests.post(url, json=payload, headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {dit_api_key}"
                }, timeout=120, stream=True)
                
                if res.status_code == 200:
                    for line in res.iter_lines():
                        if not line: continue
                        line_str = line.decode('utf-8')
                        if line_str.startswith('data: '):
                            data_chunk = line_str[6:]
                            if data_chunk == '[DONE]': break
                            try:
                                chunk_json = json.loads(data_chunk)
                                delta = chunk_json.get('choices', [{}])[0].get('delta', {})
                                content = delta.get('content', '')
                                reasoning = delta.get('reasoning_content', '')
                                if reasoning:
                                    yield f"data: {json.dumps({'thinking': reasoning})}\n\n"
                                if content:
                                    yield f"data: {json.dumps({'content': content})}\n\n"
                            except:
                                continue
                else:
                    yield f"data: {json.dumps({'error': f'DIT API Error: {res.status_code} - {res.text}'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        # DeepSeek Logic
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        
        system_msg = system_prompt
            
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
                delta = chunk.choices[0].delta
                content = getattr(delta, 'content', None)
                reasoning = getattr(delta, 'reasoning_content', None)
                if reasoning:
                    yield f"data: {json.dumps({'thinking': reasoning})}\n\n"
                if content:
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

    is_dit = any(m['id'] == model for m in DIT_MODELS)
    is_gemini = any(m['id'] == model for m in GEMINI_MODELS)

    # NOTE: MASTER_SYSTEM_PROMPT injection is handled on the FE side (enhancedPrompt.ts).
    # The FE already sends the banking-specific system prompt in system_prompt.
    # Removing duplicate injection here to avoid double-prompting the AI.

    def generate():
        if is_gemini:
            # Gemini API Logic for Comparison
            gemini_key = os.environ.get('GEMINI_API_KEY')
            if not gemini_key:
                yield f"data: {json.dumps({'error': 'Gemini API Key not found'})}\n\n"
                return

            sys_content = system_prompt or "You are a Senior Institutional Research Analyst at Asetpedia Intelligence."
            if caveman:
                sys_content += f"\n{CAVEMAN_PROMPT}"
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?key={gemini_key}"
            payload = {
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "system_instruction": {"parts": [{"text": sys_content}]},
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": 8192
                }
            }

            try:
                res = requests.post(url, json=payload, stream=True, timeout=120)
                if res.status_code == 200:
                    import re
                    decoder = codecs.getincrementaldecoder('utf-8')()
                    for chunk in res.iter_content(chunk_size=None):
                        if not chunk: continue
                        chunk_str = decoder.decode(chunk, final=False)
                        texts = re.findall(r'"text":\s*"(.*?)"', chunk_str)
                        for t in texts:
                            try:
                                t_clean = t.encode('utf-8').decode('unicode_escape')
                                yield f"data: {json.dumps({'content': t_clean})}\n\n"
                            except:
                                yield f"data: {json.dumps({'content': t})}\n\n"
                else:
                    yield f"data: {json.dumps({'error': f'Gemini API Error: {res.status_code} - {res.text}'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        if is_dit:
            # DIT API Logic for Comparison
            dit_api_key = os.environ.get('DIT_API_KEY')
            if not dit_api_key:
                yield f"data: {json.dumps({'error': 'DIT API Key not found'})}\n\n"
                return

            url = f"{DIT_API_URL}/v1/chat/completions"
            
            sys_content = system_prompt or "You are a Senior Institutional Research Analyst at Asetpedia Intelligence."
            if caveman:
                sys_content += f" {CAVEMAN_PROMPT}"
                
            messages = [
                {"role": "system", "content": sys_content},
                {"role": "user", "content": user_prompt}
            ]
            
            payload = {
                "model": model,
                "stream": True,
                "temperature": 0.3,
                "messages": messages
            }
            
            try:
                res = requests.post(url, json=payload, headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {dit_api_key}"
                }, timeout=120, stream=True)
                
                if res.status_code == 200:
                    for line in res.iter_lines():
                        if not line: continue
                        line_str = line.decode('utf-8')
                        if line_str.startswith('data: '):
                            data_chunk = line_str[6:]
                            if data_chunk == '[DONE]': break
                            try:
                                chunk_json = json.loads(data_chunk)
                                delta = chunk_json.get('choices', [{}])[0].get('delta', {})
                                content = delta.get('content', '')
                                reasoning = delta.get('reasoning_content', '')
                                if reasoning:
                                    yield f"data: {json.dumps({'thinking': reasoning})}\n\n"
                                if content:
                                    yield f"data: {json.dumps({'content': content})}\n\n"
                            except:
                                continue
                else:
                    yield f"data: {json.dumps({'error': f'DIT API Error: {res.status_code} - {res.text}'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

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
                delta = chunk.choices[0].delta
                content = getattr(delta, 'content', None)
                reasoning = getattr(delta, 'reasoning_content', None)
                if reasoning:
                    yield f"data: {json.dumps({'thinking': reasoning})}\n\n"
                if content:
                    yield f"data: {json.dumps({'content': content})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'X-Accel-Buffering': 'no', 'Cache-Control': 'no-cache'})

# ============================================================================
# 3.4 AI NARRATIVE ANALYSIS UPGRADE
# Market Narrative Extraction, Morning Briefing, Anomaly Detection
# ============================================================================

NARRATIVE_SYSTEM_PROMPT = """You are a Senior Market Narrative Analyst at Asetpedia Intelligence.
Your task is to extract the dominant market narrative from the provided data context.
Focus on:
1. The single most important macro theme driving markets right now
2. Key catalysts (earnings, data releases, geopolitical events)
3. Market regime assessment (risk-on, risk-off, rotation)
4. Sector-level implications
5. What narratives are being priced in vs. ignored

Be concise, data-driven, and avoid generic statements. Output in JSON format."""

BRIEFING_SYSTEM_PROMPT = """You are an institutional morning briefing analyst. Create a concise pre-market briefing.
Cover:
1. Overnight market action (Asia, Europe, US futures)
2. Key levels to watch (SPX, VIX, 10Y yield, DXY)
3. Today's economic calendar highlights
4. Sector rotation signals
5. Geopolitical watch items

Keep to 5-7 bullet points maximum. No fluff."""

ANOMALY_SYSTEM_PROMPT = """You are an anomaly detection specialist. Analyze the provided time-series data
and identify unusual patterns, divergences, or statistically significant events.
Flag:
1. Volume spikes vs 20-day average
2. RSI divergences (price making new high but RSI lower)
3. Unusual volatility expansion
4. Gap fills and breakouts
5. Correlation breakdowns with the broader market

Output as structured JSON with anomaly type, severity (1-5), and description."""


@app.route('/api/analyze/narrative', methods=['POST'])
def analyze_market_narrative():
    """
    AI-powered market narrative extraction.
    Accepts market data context and returns the dominant narrative.
    """
    data = request.json or {}
    market_context = data.get('market_context', '')
    api_key = data.get('api_key', '').strip() or os.environ.get('DEEPSEEK_API_KEY')
    model = data.get('model', 'deepseek-chat').strip()

    if not api_key:
        return jsonify({"status": "error", "message": "API Key required."}), 400

    try:
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

        prompt = f"""Extract the current market narrative from this context:

{market_context}

Respond with a JSON object containing:
- primary_narrative: string (one sentence describing the main theme)
- confidence: float (0-1 how confident you are in this assessment)
- catalysts: list of strings (key events driving this narrative)
- risk_factors: list of strings (what could break this narrative)
- sector_implications: dict mapping sector names to "bullish"/"bearish"/"neutral"
- regime: "RISK_ON" | "RISK_OFF" | "ROTATION" | "MIXED"
"""

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": NARRATIVE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=2000
        )

        content = response.choices[0].message.content

        # Try to parse as JSON, fallback to raw text
        try:
            # Extract JSON from potential markdown code block
            if '```json' in content:
                json_str = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                json_str = content.split('```')[1].split('```')[0].strip()
            else:
                json_str = content
            narrative = json.loads(json_str)
        except:
            narrative = {"raw_analysis": content}

        return jsonify({"status": "success", "data": narrative, "model": model})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/analyze/morning-briefing', methods=['GET'])
def get_morning_briefing():
    """
    AI-generated pre-market briefing using live market data + yfinance.
    Requires DEEPSEEK_API_KEY environment variable.
    """
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    if not api_key:
        return jsonify({"status": "error", "message": "DeepSeek API Key not configured on server."}), 400

    model = request.args.get('model', 'deepseek-chat').strip()

    try:
        # Gather pre-market data
        tickers = {
            "SPY": "S&P 500",
            "QQQ": "Nasdaq",
            "DIA": "Dow Jones",
            "IWM": "Russell 2000",
            "^VIX": "VIX",
            "^TNX": "10Y Yield",
            "DX-Y.NYB": "DXY",
            "GC=F": "Gold",
            "CL=F": "Crude Oil",
            "BTC-USD": "Bitcoin"
        }

        market_snapshot = {}
        for sym, name in tickers.items():
            try:
                tk = yf.Ticker(sym)
                info = tk.info
                price = info.get("regularMarketPrice") or info.get("previousClose")
                chg = info.get("regularMarketChangePercent", 0)
                if price:
                    market_snapshot[name] = {
                        "price": float(price),
                        "change_pct": float(chg or 0)
                    }
            except:
                continue

        # Check for today's economic events (simplified — from yfinance calendar)
        today_events = []
        try:
            spy = yf.Ticker("SPY")
            cal = spy.calendar
            if cal:
                today_events = [{"date": str(k)[:10], "event": str(v)} for k, v in cal.items()]
        except:
            pass

        context = f"""Pre-Market Data Snapshot:
{json.dumps(market_snapshot, indent=2)}

Economic Calendar:
{json.dumps(today_events[:5], indent=2)}

Generate a concise pre-market briefing.
"""

        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": BRIEFING_SYSTEM_PROMPT},
                {"role": "user", "content": context}
            ],
            temperature=0.3,
            max_tokens=1500
        )

        briefing = response.choices[0].message.content

        return jsonify({
            "status": "success",
            "data": {
                "briefing": briefing,
                "market_snapshot": market_snapshot,
                "timestamp": time.time()
            },
            "model": model
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/analyze/anomaly', methods=['POST'])
def detect_anomalies():
    """
    AI-powered anomaly detection on price time-series.
    Accepts historical price data and returns detected anomalies.
    """
    data = request.json or {}
    symbol = data.get('symbol', '').strip().upper()
    api_key = data.get('api_key', '').strip() or os.environ.get('DEEPSEEK_API_KEY')
    model = data.get('model', 'deepseek-chat').strip()
    price_data = data.get('price_data', [])

    if not symbol and not price_data:
        return jsonify({"status": "error", "message": "symbol or price_data required."}), 400

    try:
        # Fetch price data if only symbol provided
        if not price_data:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="3mo")
            if hist.empty:
                return jsonify({"status": "error", "message": "No price data found."}), 404

            price_data = []
            for ts, row in hist.iterrows():
                price_data.append({
                    "date": str(ts.date()),
                    "open": clean_data(row.get("Open")),
                    "high": clean_data(row.get("High")),
                    "low": clean_data(row.get("Low")),
                    "close": clean_data(row.get("Close")),
                    "volume": int(row.get("Volume")) if pd.notna(row.get("Volume")) else 0
                })

        # Compute basic technical indicators
        closes = [p["close"] for p in price_data if p.get("close")]
        volumes = [p["volume"] for p in price_data if p.get("volume")]

        technical_context = ""
        if len(closes) > 20:
            import numpy as np
            arr = np.array(closes)
            vol_arr = np.array(volumes)

            # RSI
            deltas = np.diff(arr)
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            avg_gain = np.mean(gains[-14:]) if len(gains) >= 14 else np.mean(gains)
            avg_loss = np.mean(losses[-14:]) if len(losses) >= 14 else np.mean(losses)
            rsi = 50 if avg_loss == 0 else round(100 - (100 / (1 + avg_gain / avg_loss)), 2)

            # Volume spike
            avg_vol = np.mean(vol_arr[-20:]) if len(vol_arr) >= 20 else np.mean(vol_arr)
            last_vol = vol_arr[-1] if len(vol_arr) > 0 else 0
            vol_ratio = round(last_vol / avg_vol, 2) if avg_vol > 0 else 0

            # Volatility
            daily_returns = np.diff(arr) / arr[:-1]
            volatility = float(np.std(daily_returns[-20:]) * 100) if len(daily_returns) >= 20 else 0

            technical_context = f"""
Technical Indicators (computed):
- Current Price: {closes[-1]:.2f}
- RSI(14): {rsi}
- Volume Ratio (last/avg20): {vol_ratio}x
- 20-day Volatility: {volatility:.2f}%
- 20d MA: {np.mean(arr[-20:]):.2f}
"""

        if api_key and model:
            # Use AI for sophisticated analysis
            context = f"""Symbol: {symbol}
Number of data points: {len(price_data)}
Price Range: {min(closes):.2f} - {max(closes):.2f}
{technical_context}

Analyze this data for anomalies.
"""

            client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": ANOMALY_SYSTEM_PROMPT},
                    {"role": "user", "content": context}
                ],
                temperature=0.2,
                max_tokens=2000
            )

            content = response.choices[0].message.content

            try:
                if '```json' in content:
                    json_str = content.split('```json')[1].split('```')[0].strip()
                elif '```' in content:
                    json_str = content.split('```')[1].split('```')[0].strip()
                else:
                    json_str = content
                anomalies = json.loads(json_str)
            except:
                anomalies = {"raw_analysis": content}

            return jsonify({
                "status": "success",
                "data": {
                    "anomalies": anomalies,
                    "technical_context": technical_context,
                    "symbol": symbol
                },
                "model": model
            })
        else:
            # Rule-based fallback
            anomalies = []
            if len(closes) > 20:
                arr = np.array(closes)
                vol_arr = np.array(volumes)

                # Volume anomaly
                avg_vol = np.mean(vol_arr[-20:])
                last_vol = vol_arr[-1]
                if avg_vol > 0 and last_vol > avg_vol * 3:
                    anomalies.append({
                        "type": "VOLUME_SPIKE",
                        "severity": 4,
                        "description": f"Volume is {last_vol/avg_vol:.1f}x the 20-day average"
                    })

                # Price deviation from MA
                ma20 = np.mean(arr[-20:])
                last_price = arr[-1]
                deviation = abs(last_price - ma20) / ma20 * 100
                if deviation > 10:
                    anomalies.append({
                        "type": "PRICE_EXTENSION",
                        "severity": 3,
                        "description": f"Price is {deviation:.1f}% away from 20-day MA"
                    })

            return jsonify({
                "status": "success",
                "data": {
                    "anomalies": anomalies if anomalies else [{"type": "NONE", "severity": 0, "description": "No significant anomalies detected"}],
                    "technical_context": technical_context,
                    "symbol": symbol
                }
            })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/analyze/sector-narrative', methods=['GET'])
def get_sector_narrative():
    """
    Brief narrative summary for each major sector using yfinance performance data.
    No AI required — data-driven sector narrative.
    """
    try:
        sectors = {
            "XLK": "Technology", "XLC": "Communication", "XLY": "Consumer Cyclical",
            "XLP": "Consumer Defensive", "XLE": "Energy", "XLF": "Financials",
            "XLV": "Healthcare", "XLI": "Industrials", "XLB": "Materials",
            "XLRE": "Real Estate", "XLU": "Utilities"
        }

        narratives = []
        for ticker, name in sectors.items():
            try:
                tk = yf.Ticker(ticker)
                hist = tk.history(period="3mo")
                if hist.empty or len(hist) < 5:
                    continue

                prices = hist['Close']
                current = prices.iloc[-1]
                p1m = prices.iloc[-21] if len(prices) >= 21 else prices.iloc[0]
                p3m = prices.iloc[0]

                perf_1m = ((current / p1m) - 1) * 100
                perf_3m = ((current / p3m) - 1) * 100

                # Determine momentum label
                if perf_1m > 5:
                    momentum = "STRONG_BULLISH"
                elif perf_1m > 1:
                    momentum = "BULLISH"
                elif perf_1m > -1:
                    momentum = "NEUTRAL"
                elif perf_1m > -5:
                    momentum = "BEARISH"
                else:
                    momentum = "STRONG_BEARISH"

                narratives.append({
                    "sector": name,
                    "ticker": ticker,
                    "perf_1m_pct": round(perf_1m, 2),
                    "perf_3m_pct": round(perf_3m, 2),
                    "momentum": momentum,
                    "current_price": round(float(current), 2)
                })
            except:
                continue
            time.sleep(0.05)

        narratives.sort(key=lambda x: x['perf_1m'], reverse=True)

        # Determine leadership
        leading = narratives[:3] if len(narratives) >= 3 else narratives
        lagging = narratives[-3:] if len(narratives) >= 3 else narratives

        return jsonify({
            "status": "success",
            "data": {
                "sectors": narratives,
                "leading_sectors": leading,
                "lagging_sectors": lagging,
                "timestamp": time.time()
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    import sys
    port = 5202
    if "--port" in sys.argv:
        try:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        except:
            pass
    app.run(host='0.0.0.0', port=port, debug=True)
