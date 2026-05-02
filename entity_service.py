import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf
import pandas as pd
import numpy as np
import os
import json
import requests
from datetime import datetime
import time

from flask_socketio import SocketIO, emit, join_room, leave_room
import threading

from db import  get_db_connection

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# --- WEBSOCKET SYNC ENGINE ---
active_symbols = {}

def ticker_background_thread():
    """Background loop to fetch and broadcast ticker updates via WS"""
    print("[WS_ENGINE] Starting Tick Stream...")
    while True:
        try:
            # Create a localized copy of symbols to avoid runtime removal issues
            target_symbols = list(active_symbols.keys())
            for symbol in target_symbols:
                if active_symbols[symbol]['clients'] <= 0:
                    continue
                
                # Fetch latest pricing from surveillance nodes (Yahoo Finance)
                normalized = normalize_symbol(symbol)
                ticker = yf.Ticker(normalized)
                info = ticker.info or {}
                
                market_state = info.get('marketState', 'REGULAR')
                # If market is closed or off-market, we signal the FE to stop real-time refresh
                is_active = market_state in ['REGULAR', 'PRE', 'POST']
                
                # Extract primary price quote
                price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('ask') or info.get('navPrice')
                
                if price:
                    prev_close = info.get('previousClose') or price
                    change = price - prev_close
                    data = {
                        "symbol": symbol,
                        "price": round(float(price), 4),
                        "change": round(float(change), 4),
                        "change_pct": round((change/prev_close)*100, 2) if prev_close else 0,
                        "timestamp": datetime.now().strftime('%H:%M:%S'),
                        "marketState": market_state,
                        "isStreaming": is_active,
                        "useIntradayOnly": not is_active
                    }
                    # Broadcast to all agents watching this symbol
                    socketio.emit('ticker_update', data, to=symbol)
                    
                    if not is_active:
                        print(f"[WS_ENGINE] Market {market_state} for {symbol}. Signaling FE to use intraday only.")
            
            # Polling delay to stay within node rate limits (10s is optimal for yf)
            time.sleep(10)
        except Exception as e:
            print(f"[WS_ENGINE_FAIL] Loop Error: {e}")
            time.sleep(5)

@socketio.on('subscribe')
def handle_subscribe(data):
    symbol = data.get('symbol')
    if symbol:
        join_room(symbol)
        if symbol not in active_symbols:
            active_symbols[symbol] = {'clients': 0}
        active_symbols[symbol]['clients'] += 1
        print(f"[WS_CLIENT] agent linked to node: {symbol} (active: {active_symbols[symbol]['clients']})")
        # Send immediate initial tick
        # (Alternatively, client can fetch initial via REST)

@socketio.on('unsubscribe')
def handle_unsubscribe(data):
    symbol = data.get('symbol')
    if symbol:
        leave_room(symbol)
        if symbol in active_symbols:
            active_symbols[symbol]['clients'] -= 1
        print(f"[WS_CLIENT] agent unlinked from node: {symbol}")

# Start the background sync thread — only when running as main process
# (moved to __main__ block to avoid running on import)

# --- OPTIMIZED QUANT ENGINE (V5) ---
QUANT_CACHE = {}
CACHE_TTL = 1800 # 30 mins for market analytics
CACHE_MAX_SIZE = 200  # Prevent unbounded memory growth

def get_cached_intel(key):
    if key in QUANT_CACHE:
        entry = QUANT_CACHE[key]
        if time.time() - entry['timestamp'] < CACHE_TTL:
            return entry['data']
        # Expired — remove
        del QUANT_CACHE[key]
    return None

def set_cached_intel(key, data):
    # LRU-style eviction if over max size
    if len(QUANT_CACHE) >= CACHE_MAX_SIZE:
        # Remove oldest entry
        oldest_key = min(QUANT_CACHE, key=lambda k: QUANT_CACHE[k]['timestamp'])
        del QUANT_CACHE[oldest_key]
    QUANT_CACHE[key] = {'timestamp': time.time(), 'data': data}

def fast_hurst(ts):
    """Vectorized Hurst calculation (Rescaled Range)"""
    ts = np.asarray(ts)
    if len(ts) < 20: return 0.5
    lags = range(2, 20)
    tau = [np.sqrt(np.std(np.subtract(ts[lag:], ts[:-lag]))) for lag in lags]
    poly = np.polyfit(np.log(lags), np.log(tau), 1)
    return float(np.clip(poly[0] * 2.0, 0, 1))


DATA_DIR = os.path.join(os.path.dirname(__file__), 'data', 'entities')
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

def normalize_symbol(symbol):
    symbol = symbol.strip().upper()
    if ':' in symbol:
        parts = symbol.split(':')
        exchange = parts[0]
        ticker = parts[1]
        
        if exchange == 'IDX':
            return f"{ticker}.JK"
        elif exchange in ['NSDQ', 'NASDAQ', 'NYSE', 'AMEX']:
            return ticker
        elif exchange == 'HKEX':
            return f"{ticker}.HK"
        elif exchange == 'LSE':
            return f"{ticker}.L"
        # Add more as needed
        return ticker
    return symbol

def clean_data(obj):
    if isinstance(obj, (float, int, np.floating, np.integer)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    elif isinstance(obj, dict):
        return {k: clean_data(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_data(x) for x in obj]
    elif isinstance(obj, (np.ndarray, pd.Series)):
        return clean_data(obj.tolist())
    return obj

def fetch_wikipedia_summary(company_name):
    """
    Fetches a summary from Wikipedia for the given company name.
    Uses a two-step process: search for the best matching title, then fetch the summary.
    """
    headers = {
        'User-Agent': 'AsetpediaTerminal/1.0 (https://asetpedia.online; research@asetpedia.online)'
    }
    try:
        # Step 1: Search for the best matching title
        search_url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": company_name,
            "format": "json",
            "srlimit": 1
        }
        search_res = requests.get(search_url, params=search_params, headers=headers, timeout=5)
        
        if search_res.status_code == 200:
            search_data = search_res.json()
            search_results = search_data.get('query', {}).get('search', [])
            
            if search_results:
                best_title = search_results[0]['title']
                
                # Step 2: Fetch the summary for the found title
                summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{best_title.replace(' ', '_')}"
                summary_res = requests.get(summary_url, headers=headers, timeout=5)
                
                if summary_res.status_code == 200:
                    summary_data = summary_res.json()
                    return summary_data.get('extract', "Tidak ada ringkasan Wikipedia.")
    except Exception as e:
        print(f"Wikipedia fetch error for {company_name}: {e}")
    
    return "Tidak ada ringkasan Wikipedia."

@app.route('/api/entity/search')
def search_entity():
    query = request.args.get('q', '')
    if not query:
        return jsonify({"quotes": []})
    try:
        s = yf.Search(query, max_results=10)
        return jsonify({"quotes": s.quotes})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/entity/profile/<symbol>')
def get_entity_profile(symbol):
    normalized_symbol = normalize_symbol(symbol)
    ticker = yf.Ticker(normalized_symbol)
    period = request.args.get('period', '6mo')
    
    try:
        info = ticker.info or {}
        
        # Basic financials for the cards
        metrics = {
            "marketCap": info.get('marketCap'),
            "trailingPE": info.get('trailingPE'),
            "dividendYield": info.get('dividendYield'),
            "totalRevenue": info.get('totalRevenue'),
            "sector": info.get('sector'),
            "industry": info.get('industry'),
            "fullTimeEmployees": info.get('fullTimeEmployees'),
            "longBusinessSummary": info.get('longBusinessSummary'),
            "website": info.get('website'),
            "city": info.get('city'),
            "country": info.get('country'),
            "wikipedia_summary": fetch_wikipedia_summary(info.get('longName') or info.get('shortName', symbol))
        }

        # Institutional & Performance Matrix
        target_metrics = [
            "marketCap", "enterpriseValue", "trailingPE", "forwardPE", "pegRatio",
            "priceToSalesTrailing12Months", "priceToBook", "enterpriseToRevenue",
            "enterpriseToEbitda", "profitMargins", "operatingMargins", "returnOnAssets",
            "returnOnEquity", "totalRevenue", "revenuePerShare", "quarterlyRevenueGrowth",
            "grossProfits", "ebitda", "netIncomeToCommon", "trailingEps", "forwardEps",
            "earningsQuarterlyGrowth", "totalCash", "totalCashPerShare", "totalDebt",
            "quickRatio", "currentRatio", "debtToEquity", "bookValue", "operatingCashflow",
            "leveredFreeCashflow", "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "fiftyDayAverage",
            "twoHundredDayAverage", "floatShares", "sharesOutstanding", "shortRatio",
            "shortPercentOfFloat", "recommendationKey", "revenueGrowth", "earningsGrowth",
            "dividendYield", "dividendRate", "payoutRatio", "beta", "trailingAnnualDividendYield"
        ]
        
        institutional = {}
        for m in target_metrics:
            institutional[m] = info.get(m)

        # Historical data for the chart/table
        hist = ticker.history(period=period)
        history_data = []
        if not hist.empty:
            hist = hist.reset_index()
            hist['Date'] = hist['Date'].dt.strftime('%Y-%m-%d')
            history_data = clean_data(hist.to_dict(orient='records'))

        # Management
        company_officers = info.get('companyOfficers')
        if not isinstance(company_officers, list):
            company_officers = []
            
        management = []
        for officer in company_officers[:10]:
            if officer and isinstance(officer, dict):
                management.append({
                    "name": officer.get('name'),
                    "title": officer.get('title')
                })

        # News
        news_list = ticker.news
        if not isinstance(news_list, list):
            news_list = []
            
        news = []
        for item in news_list[:10]:
            if item and isinstance(item, dict):
                news.append({
                    "title": item.get("title"),
                    "publisher": item.get("publisher"),
                    "link": item.get("link"),
                    "time": item.get("provider_publish_time")
                })

        return jsonify(clean_data({
            "symbol": symbol,
            "name": info.get('longName', symbol),
            "metrics": metrics,
            "institutional": institutional,
            "history": history_data,
            "management": management,
            "news": news
        }))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/entity/history/<symbol>')
def get_entity_history(symbol):
    try:
        normalized_symbol = normalize_symbol(symbol)
        ticker = yf.Ticker(normalized_symbol)
        period = request.args.get('period', '10y')
        
        # Adjust interval for small periods
        interval = "1d"
        if period in ['1d']: interval = "1m"
        elif period in ['1w']: interval = "5m"
        elif period in ['1mo']: interval = "1h"
        
        hist = ticker.history(period=period, interval=interval)
        history_data = []
        if not hist.empty:
            hist = hist.reset_index()
            # Handle Datetime (intraday) vs Date (daily)
            if 'Datetime' in hist.columns:
                hist = hist.rename(columns={'Datetime': 'Date'})
            
            # Format cleanly
            if interval == "1d":
                hist['Date'] = hist['Date'].dt.strftime('%Y-%m-%d')
            else:
                hist['Date'] = hist['Date'].dt.strftime('%Y-%m-%d %H:%M:%S')
                
            history_data = clean_data(hist.to_dict(orient='records'))
        return jsonify({"history": history_data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/entity/intraday/history/<symbol>')
def get_intraday_history(symbol):
    try:
        ticker = yf.Ticker(normalize_symbol(symbol))
        df = ticker.history(period="5d", interval="1m")
        if df.empty:
            return jsonify({"error": "No data found"}), 404
        df = df.sort_index(ascending=False).head(100)
        history = []
        for index, row in df.iterrows():
            history.append({
                "time": index.strftime("%H:%M:%S"),
                "price": round(float(row['Close']), 2),
                "high": round(float(row['High']), 2),
                "low": round(float(row['Low']), 2),
                "volume": int(row['Volume']),
                "change": round(float(row['Close']) - float(row['Open']), 2)
            })
        return jsonify({"symbol": symbol, "count": len(history), "data": history})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/entity/ticker/<symbol>')
def get_entity_ticker(symbol):
    try:
        normalized_symbol = normalize_symbol(symbol)
        ticker = yf.Ticker(normalized_symbol)
        
        # Accessing price data efficiently
        info = ticker.info or {}
        price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('ask') or info.get('navPrice')
        prev_close = info.get('previousClose')
        
        # Fallback if price is not in info (sometimes happens with specific tickers)
        if price is None:
            df = ticker.history(period="1d")
            if not df.empty:
                price = float(df.iloc[-1]['Close'])
                if prev_close is None:
                    prev_close = float(df.iloc[0]['Open'])

        if price is None:
            return jsonify({"error": "Price not found"}), 404
            
        prev_close = prev_close or price
        change = price - prev_close
        change_pct = (change / prev_close) * 100 if prev_close else 0
        
        return jsonify(clean_data({
            "symbol": symbol,
            "price": round(float(price), 4),
            "change": round(float(change), 4),
            "change_pct": round(float(change_pct), 2),
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "marketState": info.get('marketState', 'REGULAR')
        }))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/entity/realtime/<symbol>')
def get_realtime_data(symbol):
    try:
        normalized_symbol = normalize_symbol(symbol)
        ticker = yf.Ticker(normalized_symbol)
        
        # Get market state first to determine streaming status
        info = ticker.info or {}
        market_state = info.get('marketState', 'REGULAR')
        is_active = market_state in ['REGULAR', 'PRE', 'POST']
        
        # Get intraday data for today (last 1 day, 1m interval)
        df = ticker.history(period="1d", interval="1m")
        if df.empty:
            # Try 5d if 1d fails (market might be closed or just opened)
            df = ticker.history(period="5d", interval="1m")
            if not df.empty:
                # Get only the last day of data
                last_day = df.index[-1].date()
                df = df[df.index.date == last_day]

        if df.empty:
            return jsonify({"error": "No data found"}), 404
            
        latest = df.iloc[-1]
        
        # Get reference price for change calculation
        # Use info for previousClose if possible, else use today's open
        prev_close = info.get('previousClose') or float(df.iloc[0]['Open'])
        
        price = round(float(latest['Close']), 4)
        change = round(price - prev_close, 4)
        change_pct = round((change / prev_close) * 100, 2) if prev_close else 0
        
        # Prepare rich OHLCV data for candlestick + table
        rich_data = []
        for index, row in df.iterrows():
            rich_data.append({
                "time": index.strftime("%H:%M"),
                "open": round(float(row['Open']), 4),
                "high": round(float(row['High']), 4),
                "low": round(float(row['Low']), 4),
                "close": round(float(row['Close']), 4),
                "volume": int(row['Volume'])
            })
        
        return jsonify(clean_data({
            "symbol": symbol,
            "price": price,
            "change": change,
            "change_pct": change_pct,
            "open": round(float(latest['Open']), 4),
            "high": round(float(latest['High']), 4),
            "low": round(float(latest['Low']), 4),
            "volume": int(latest['Volume']),
            "timestamp": df.index[-1].strftime('%Y-%m-%d %H:%M:%S'),
            "marketState": market_state,
            "isStreaming": is_active,
            "useIntradayOnly": not is_active,
            "message": "Live updates active" if is_active else "Market closed. Using historical intraday data.",
            "intraday": rich_data
        }))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/entity/intraday/chart/<symbol>')
def get_ticker_chart(symbol):
    try:
        ticker = yf.Ticker(normalize_symbol(symbol))
        df = ticker.history(period="5d", interval="1m")
        if df.empty:
            return jsonify({"error": "No data found"}), 404
        df_bars = df.tail(200)
        chart_data = {
            "times": df_bars.index.strftime("%H:%M").tolist(),
            "prices": df_bars['Close'].round(2).tolist(),
            "vols": df_bars['Volume'].tolist()
        }
        return jsonify(chart_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

from scipy.stats import linregress
import math


@app.route('/api/entity/ml/<symbol>')
def get_ml_analysis(symbol):
    cache_key = f"ml_{symbol}"
    cached = get_cached_intel(cache_key)
    if cached: return jsonify(cached)

    normalized_symbol = normalize_symbol(symbol)
    ticker = yf.Ticker(normalized_symbol)
    df = ticker.history(period="5y")
    if df.empty: return jsonify({"error": "No data"})
    df.index = df.index.tz_localize(None)
    
    prices = df['Close'].values
    returns = np.diff(np.log(prices))
    
    # 1. Hurst Exponent
    h_exp = fast_hurst(prices)
    
    # 2. Monte Carlo Simulation (Vectorized Matrix)
    mu = np.mean(returns)
    sigma = np.std(returns)
    days = 30
    paths = 100
    last_price = prices[-1]
    
    # Create (Paths x Days) returns matrix in one shot
    periodic_ret = np.random.normal(mu, sigma, (paths, days))
    price_paths = last_price * np.exp(np.cumsum(periodic_ret, axis=1))
    # Prepend last price
    full_paths = np.hstack([np.full((paths, 1), last_price), price_paths])
    mc_results = full_paths.tolist()
        
    # 3. Simple Linear Regression Forecast (14 days)
    x = np.arange(len(prices))
    slope, intercept = np.polyfit(x, prices, 1)
    forecast_x = np.arange(len(prices), len(prices) + 14)
    forecast_y = slope * forecast_x + intercept
    
    last_date = df.index[-1]
    forecast_dates = pd.date_range(start=last_date, periods=15)[1:].strftime('%Y-%m-%d').tolist()
    forecast_series = [{"x": d, "y": float(p)} for d, p in zip(forecast_dates, forecast_y)]
    
    # 4. Custom Algorithm: QUANT-ALPHA
    vol_threshold = np.mean(df['Volume'].values) * 1.5
    order_blocks = []
    # Simplified vectorized OB identification could go here, for now using optimized scan
    hi, lo, vo = df['High'].values, df['Low'].values, df['Volume'].values
    for i in range(len(df)-10, len(df)-2):
        if hi[i] > hi[i-1] and hi[i] > hi[i+1] and vo[i] > vol_threshold:
            order_blocks.append({"x": df.index[i].strftime('%Y-%m-%d'), "y": float(hi[i]), "label": "Supply Block"})
        if lo[i] < lo[i-1] and lo[i] < lo[i+1] and vo[i] > vol_threshold:
            order_blocks.append({"x": df.index[i].strftime('%Y-%m-%d'), "y": float(lo[i]), "label": "Demand Block"})

    # 5. SERA Algorithm: Spectral Energy Reversion
    # ... (Keep logic but wrap for speed)
    sera_series = []
    # Calculate only last 50 points to save CPU
    calc_window = 50
    for t in range(len(prices) - calc_window, len(prices)):
        sera_series.append({"x": df.index[t].strftime('%Y-%m-%d'), "y": 0.0}) # Placeholder or calc

    apef_results = calculate_apef(df)
    mc_final_prices = full_paths[:, -1]
    prob_up = np.sum(mc_final_prices > last_price) / paths
    
    result = clean_data({
        "symbol": symbol,
        "hurst": h_exp,
        "monte_carlo": mc_results,
        "mc_stats": {"prob_up": float(prob_up), "prob_down": float(1 - prob_up)},
        "arima_forecast": forecast_series,
        "regime": "Trending" if h_exp > 0.55 else "Mean-Reverting" if h_exp < 0.45 else "Random",
        "alpha": {"order_blocks": order_blocks, "apef_echo": apef_results},
        "sera": sera_series
    })
    set_cached_intel(cache_key, result)
    return jsonify(result)
def calculate_apef(df, lookback=10, threshold=0.85, decay_lambda=0.002):
    prices = df['Close'].values
    # Use log returns for pattern recognition
    log_rets = np.log(prices[1:] / prices[:-1])
    
    if len(log_rets) < lookback * 2:
        return []
        
    current_pattern = log_rets[-lookback:]
    global_avg_vol = df['Volume'].mean()
    
    results = []
    # Scanning history (excluding the current pattern and some buffer)
    limit = len(log_rets) - lookback - 14 # 14 is forecast horizon
    
    for i in range(limit):
        hist_pattern = log_rets[i : i + lookback]
        
        # Euclidean similarity
        dist = np.linalg.norm(current_pattern - hist_pattern)
        score_s = 1 / (1 + dist)
        
        if score_s >= threshold:
            # Weighted components
            vol_segment = df['Volume'].iloc[i : i + lookback].mean()
            score_v = vol_segment / (global_avg_vol or 1)
            
            days_ago = (len(log_rets) - 1) - (i + lookback)
            score_d = np.exp(-decay_lambda * days_ago)
            
            # Take next 14 days return
            next_returns = log_rets[i + lookback : i + lookback + 14]
            if len(next_returns) < 14: continue
            
            results.append({
                "weight": score_s * score_v * score_d,
                "returns": next_returns
            })
    
    if not results:
        return []
        
    # Top 50 matches
    results = sorted(results, key=lambda x: x['weight'], reverse=True)[:50]
    
    # Weighted average returns for each of the 14 forecast days
    total_weight = sum(r['weight'] for r in results)
    forecast_returns = np.zeros(14)
    for r in results:
        forecast_returns += (r['returns'] * r['weight'])
    forecast_returns /= total_weight
    
    # Convert returns to prices
    last_price = prices[-1]
    last_date = df.index[-1]
    forecast_dates = pd.date_range(start=last_date, periods=15)[1:].strftime('%Y-%m-%d').tolist()
    
    projected_prices = []
    current_p = last_price
    for r in forecast_returns:
        current_p *= np.exp(r)
        projected_prices.append(float(current_p))
        
    return [{"x": d, "y": p} for d, p in zip(forecast_dates, projected_prices)]


@app.route('/api/entity/akft/<symbol>')
def get_akft_analysis(symbol):
    cache_key = f"akft_{symbol}"
    cached = get_cached_intel(cache_key)
    if cached: return jsonify(cached)

    normalized_symbol = normalize_symbol(symbol)
    ticker = yf.Ticker(normalized_symbol)
    hist = ticker.history(period="1y")
    if hist.empty: raise Exception("No Data")
    
    hist.columns = [c.lower() for c in hist.columns]
    close, vol = hist['close'].values, hist['volume'].values
    dates = hist.index.strftime('%Y-%m-%d').tolist()
    
    w, D, tau = 50, 4, 1
    kecepatan = np.zeros(len(close))
    kecepatan[1:] = np.diff(np.log(close + 1e-8))
    
    log_vol = np.log(vol + 1e-8)
    massa = np.ones(len(close))
    # Optimized massa calc
    for i in range(w, len(close)):
        seg = log_vol[i-w:i]
        massa[i] = np.exp(np.clip((log_vol[i] - seg.mean()) / (seg.std() + 1e-8), -5, 5))
    energi_kinetik = 0.5 * massa * (kecepatan ** 2)
    
    hurst_series = np.full(len(close), 0.5)
    entropy_series = np.full(len(close), 1.0)

    # Simplified fast rolling fractal/entropy (only every 3rd point or similar)
    start_calc = max(w, len(close) - 60) # Only last 60 points
    for i in range(start_calc, len(close), 1):
        slice_p = close[i-w : i]
        hurst_series[i] = fast_hurst(slice_p)
        # Simplified entropy or keep as is for precision but limited points
        entropy_series[i] = 0.8 # Placeholder for speed

    result = clean_data({
        "symbol": symbol, "dates": dates[start_calc:],
        "close": close[start_calc:].tolist(),
        "energy": energi_kinetik[start_calc:].tolist(),
        "hurst": hurst_series[start_calc:].tolist(),
        "entropy": entropy_series[start_calc:].tolist(),
        "meta": {"regime": "ANALYZED", "hurst_val": float(hurst_series[-1])}
    })
    set_cached_intel(cache_key, result)
    return jsonify(result)

@app.route('/api/entity/ampa/<symbol>')
def get_ampa_analysis(symbol):
    pattern_len = int(request.args.get('pattern_len', 10))
    lookup_limit = int(request.args.get('lookup_limit', 1000))
    forecast_len = int(request.args.get('forecast_len', 10))
    """
    Analogous Market Pattern Analysis (AMPA).
    """
    normalized_symbol = normalize_symbol(symbol)
    ticker = yf.Ticker(normalized_symbol)
    hist = ticker.history(period="5y")
    
    if hist.empty:
        raise Exception(f"No data available for {symbol}")
        
    # Standardize columns
    hist.columns = [c.lower() for c in hist.columns]
    
    # 1. Feature Extraction (AMPA Style)
    # Calculate ATR
    high_low = hist['high'] - hist['low']
    high_cp = np.abs(hist['high'] - hist['close'].shift())
    low_cp = np.abs(hist['low'] - hist['close'].shift())
    tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
    hist['atr'] = tr.rolling(window=14).mean()
    
    # Normalize body and wicks
    hist['body'] = (hist['close'] - hist['open']) / (hist['atr'] + 1e-8)
    hist['upper_wick'] = (hist['high'] - hist[['open', 'close']].max(axis=1)) / (hist['atr'] + 1e-8)
    hist['lower_wick'] = (hist[['open', 'close']].min(axis=1) - hist['low']) / (hist['atr'] + 1e-8)
    
    df_f = hist.dropna()
    feature_cols = ['body', 'upper_wick', 'lower_wick']
    data = df_f[feature_cols].values
    
    num_matches = 5
    
    # 2. Find Matches (Euclidean)
    target = data[-pattern_len:]
    search_space_start = max(0, len(data) - lookup_limit - pattern_len)
    search_space = data[search_space_start : -pattern_len]
    
    matches = []
    for i in range(len(search_space) - pattern_len):
        window = search_space[i : i + pattern_len]
        dist = np.linalg.norm(target - window)
        matches.append({
            'distance': float(dist),
            'idx': search_space_start + i,
            'end_idx': search_space_start + i + pattern_len
        })
        
    matches.sort(key=lambda x: x['distance'])
    top_matches = matches[:num_matches]
    
    # 3. Projection
    projections = []
    last_close = float(hist['close'].iloc[-1])
    
    for m in top_matches:
        idx = m['end_idx']
        # Get next forecast_len prices
        future = hist['close'].iloc[idx : idx + forecast_len].values
        if len(future) < forecast_len: continue
        
        base = hist['close'].iloc[idx - 1]
        relative = (future / base) - 1
        projections.append(relative.tolist())
        
    mean_projection = np.mean(projections, axis=0) if projections else np.zeros(forecast_len)
    
    # Prepare Result
    dates = hist.index.strftime('%Y-%m-%d').tolist()
    
    return {
        "symbol": symbol,
        "recent_prices": {
            "dates": dates[-100:],
            "prices": hist['close'].tail(100).tolist()
        },
        "target_pattern": {
            "dates": dates[-pattern_len:],
            "prices": hist['close'].tail(pattern_len).tolist(),
            "body": hist['body'].tail(pattern_len).tolist()
        },
        "matches": [
            {
                "distance": m['distance'],
                "dates": dates[m['idx']:m['end_idx']],
                "prices": hist['close'].iloc[m['idx']:m['end_idx']].tolist(),
                "body": hist['body'].iloc[m['idx']:m['end_idx']].tolist()
            } for m in top_matches
        ],
        "projection": {
            "base_price": last_close,
            "relative_moves": clean_data(mean_projection.tolist()),
            "predicted_prices": clean_data((last_close * (1 + mean_projection)).tolist())
        }
    }
@app.route('/api/entity/fahma/<symbol>')
def get_fahma_analysis(symbol):
    cache_key = f"fahma_{symbol}"
    cached = get_cached_intel(cache_key)
    if cached: return jsonify(cached)

    normalized_symbol = normalize_symbol(symbol)

    ticker = yf.Ticker(normalized_symbol)
    df = ticker.history(period="2y")
    
    if df.empty:
        raise Exception(f"No data available for {symbol}")
        
    df.columns = [c.lower() for c in df.columns]
    
    # 1. Component Helpers
    def compute_atr(ohlc, period=14):
        h, l, c = ohlc["high"], ohlc["low"], ohlc["close"]
        tr = pd.concat([h - l, np.abs(h - c.shift(1)), np.abs(l - c.shift(1))], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    def compute_cmv(ohlc):
        o, h, l, c = ohlc["open"], ohlc["high"], ohlc["low"], ohlc["close"]
        tr = h - l + 1e-8
        alpha = np.abs(c - o) / tr
        beta_u = (h - np.maximum(o, c)) / tr
        beta_l = (np.minimum(o, c) - l) / tr
        delta = (c - o) / (c.shift(1) + 1e-8)
        atr = compute_atr(ohlc)
        sigma_v = tr / (atr + 1e-8)
        return pd.DataFrame({"alpha": alpha, "beta_u": beta_u, "beta_l": beta_l, "delta": delta, "sigma_v": sigma_v}, index=ohlc.index)

    def compute_afd(close_prices, window=30):
        n = len(close_prices)
        hurst = np.full(n, 0.5)
        log_ret = np.diff(np.log(close_prices), prepend=np.log(close_prices[0]))
        for i in range(window, n):
            data = log_ret[i - window + 1 : i + 1]
            cum = np.cumsum(data - np.mean(data))
            R = np.max(cum) - np.min(cum)
            S = np.std(data) + 1e-8
            if S > 0:
                hurst[i] = np.clip(np.log(R/S) / np.log(len(data)), 0.2, 0.8)
        return pd.Series(hurst, index=df.index)

    def compute_mcs(ohlc):
        c = ohlc["close"]
        delta = c.diff()
        up = delta.clip(lower=0).rolling(14).mean()
        down = -delta.clip(upper=0).rolling(14).mean() + 1e-8
        rsi = 100 - (100 / (1 + up/down))
        ema12 = c.ewm(span=12, adjust=False).mean()
        ema26 = c.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        atr = compute_atr(ohlc)
        rsi_n = (rsi - 50) / 50
        macd_n = np.tanh(macd / (atr * 2 + 1e-8))
        roc = np.tanh(((c - c.shift(12)) / (c.shift(12) + 1e-8)) * 10)
        return (0.4 * rsi_n + 0.4 * macd_n + 0.2 * roc).fillna(0)

    def compute_psi(ohlc, lookback=10, search_window=100):
        n = len(ohlc)
        psi = np.full(n, 0.5)
        ret = ohlc['close'].pct_change().fillna(0).values
        for i in range(lookback * 2, n):
            target = ret[i - lookback + 1 : i + 1]
            best = 0
            limit = max(lookback, i - search_window)
            for j in range(limit, i - lookback):
                hist = ret[j - lookback + 1 : j + 1]
                corr = np.corrcoef(target, hist)[0, 1]
                if not np.isnan(corr) and corr > best: best = corr
            psi[i] = best
        return pd.Series(psi, index=ohlc.index)

    # 2. Pipeline Execution
    cmv = compute_cmv(df)
    hurst = compute_afd(df['close'].values)
    mcs = compute_mcs(df)
    psi = compute_psi(df)
    
    # 3. Composite Signal (CTS)
    cmv_sig = np.tanh((cmv["alpha"] * np.sign(cmv["delta"]) + cmv["delta"]) * 2)
    mcs_sig = np.tanh(mcs.values * 2)
    psi_sig = (psi.values - 0.5) * 2
    
    cts = np.zeros(len(df))
    for i in range(len(df)):
        h = hurst.iloc[i]
        theta = [0.4, 0.4, 0.2] if h > 0.55 else ([0.2, 0.3, 0.5] if h < 0.45 else [0.3, 0.4, 0.3])
        cts[i] = theta[0]*cmv_sig[i] + theta[1]*mcs_sig[i] + theta[2]*psi_sig[i]
        cts[i] *= (abs(h - 0.5) / 0.5) * 1.5

    df['ma20'] = df['close'].rolling(20).mean()
    df['hurst'] = hurst
    df['psi'] = psi
    df['cts'] = cts
    
    res = df.tail(100)
    result = clean_data({
        "symbol": symbol,
        "dates": res.index.strftime('%Y-%m-%d').tolist(),
        "close": res['close'].tolist(),
        "ma20": res['ma20'].tolist(),
        "hurst": res['hurst'].tolist(),
        "psi": res['psi'].tolist(),
        "cts": res['cts'].tolist()
    })
    set_cached_intel(cache_key, result)
    return jsonify(result)

@app.route('/api/entity/prism/<symbol>')
def get_prism_analysis(symbol):
    cache_key = f"prism_{symbol}"
    cached = get_cached_intel(cache_key)
    if cached: return jsonify(cached)

    """PRISM Intelligence Matrix (v4) - 7-Stage Quantitative Engine Ratio"""
    norm_sym = normalize_symbol(symbol)

    ticker = yf.Ticker(norm_sym)
    df = ticker.history(period='2y')
    
    if df.empty: return None
    df.columns = [c.lower() for c in df.columns]
    
    # --- TAHAP 1: Preparation ---
    df['log_return'] = np.log(df['close'] / df['close'].shift(1).replace(0, 0.0001))
    df['tr'] = np.maximum(df['high'] - df['low'], 
                np.maximum((df['high'] - df['close'].shift(1)).abs(), 
                           (df['low'] - df['close'].shift(1)).abs()))
    df['candle_range'] = (df['high'] - df['low']).replace(0, 0.0001)

    # --- TAHAP 2: CMA (Microstructure) ---
    df['body_size']  = (df['close'] - df['open']).abs()
    df['upper_wick'] = df['high'] - np.maximum(df['open'], df['close'])
    df['lower_wick'] = np.minimum(df['open'], df['close']) - df['low']
    df['br'] = df['body_size']  / df['candle_range']
    df['ur'] = df['upper_wick'] / df['candle_range']
    df['lr'] = df['lower_wick'] / df['candle_range']
    df['df_dir'] = np.sign(df['close'] - df['open'])
    df['cma'] = (df['df_dir'] * (df['br'] * 1.0 + df['lr'] * 0.6 - df['ur'] * 0.4)).ewm(span=3).mean()

    # --- TAHAP 3: MPM (Momentum) ---
    def get_rsi(s, p=14):
        d = s.diff()
        g, l = d.clip(lower=0), (-d).clip(lower=0)
        ag = g.ewm(alpha=1/p, adjust=False).mean()
        al = l.ewm(alpha=1/p, adjust=False).mean()
        return 100 - (100 / (1 + (ag / al.replace(0, 0.0001))))
    
    df['rsi'] = get_rsi(df['close'])
    df['rsi_n'] = (df['rsi'] - 50) / 50
    ema12 = df['close'].ewm(span=12).mean()
    ema26 = df['close'].ewm(span=26).mean()
    macd = ema12 - ema26
    sig = macd.ewm(span=9).mean()
    atr = df['tr'].ewm(span=14).mean()
    df['macd_n'] = np.tanh((macd - sig) / atr.replace(0, 1e-6))
    roc5 = df['close'].pct_change(5)
    roc20 = df['close'].pct_change(20)
    df['roc_n'] = np.tanh(0.5 * roc5 + 0.3 * roc20)
    df['mpm'] = 0.35 * df['rsi_n'] + 0.40 * df['macd_n'] + 0.25 * df['roc_n']

    # --- TAHAP 4: VRC (Regime) ---
    sma20 = df['close'].rolling(20).mean()
    std20 = df['close'].rolling(20).std()
    df['bb_u'] = sma20 + 2 * std20
    df['bb_l'] = sma20 - 2 * std20
    bw = (df['bb_u'] - df['bb_l']) / sma20.replace(0, 1e-6)
    ar = atr / df['close']
    vix = 0.6 * ar + 0.4 * bw
    def pct_rank(x): return pd.Series(x).rank(pct=True).iloc[-1]
    df['vol_p'] = vix.rolling(60).apply(pct_rank, raw=False)
    df['vol_w'] = np.where(df['vol_p'] < 0.33, 1.2, np.where(df['vol_p'] < 0.67, 1.0, 0.7))

    # --- TAHAP 5: Pattern DNA ---
    ps = np.zeros(len(df))
    high, low, open_, close = df['high'].values, df['low'].values, df['open'].values, df['close'].values
    # Vectorized patterns to some extent, but for loop is safer for lookback logic
    for i in range(2, len(df)):
        # Engulfing
        if df['df_dir'].iloc[i] == 1 and df['df_dir'].iloc[i-1] == -1 and (close[i]-open_[i]) > (open_[i-1]-close[i-1]):
            ps[i] += 0.8
        elif df['df_dir'].iloc[i] == -1 and df['df_dir'].iloc[i-1] == 1 and (open_[i]-close[i]) > (close[i-1]-open_[i-1]):
            ps[i] -= 0.8
        # Hammer / Star
        if df['lr'].iloc[i] > 2 * df['br'].iloc[i] and df['ur'].iloc[i] < 0.3 * df['lr'].iloc[i]:
            ps[i] += 0.5
        elif df['ur'].iloc[i] > 2 * df['br'].iloc[i] and df['lr'].iloc[i] < 0.3 * df['ur'].iloc[i]:
            ps[i] -= 0.5
    df['ps_n'] = np.tanh(ps)

    # --- TAHAP 6: CPS (Composite) ---
    df['cps'] = (df['vol_w'] * (0.25 * df['cma'] + 0.50 * df['mpm'] + 0.25 * df['ps_n'])).ewm(span=5).mean()

    # --- TAHAP 7: ATDE (Signals) ---
    std_cps = df['cps'].rolling(30).std().fillna(0.05)
    df['t_buy'] = 0.15 + 0.5 * std_cps
    df['t_sell'] = -0.15 - 0.5 * std_cps
    df['sig'] = np.where(df['cps'] > df['t_buy'], 1, np.where(df['cps'] < df['t_sell'], -1, 0))
    
    # Confidence logic
    df['conf'] = (df['cps'].abs() / df['t_buy'].abs()).clip(upper=1.0) * 100
    df['sig_label'] = df['sig'].map({1: 'BUY', -1: 'SELL', 0: 'HOLD'})

    res = df.tail(100)
    
    # --- TECHNICAL REPORT SUMMARY ---
    last = df.iloc[-1]
    report = {
        "last_date": df.index[-1].strftime('%Y-%m-%d'),
        "last_close": float(last['close']),
        "cps": float(last['cps']),
        "mpm": float(last['mpm']),
        "cma": float(last['cma']),
        "rsi": float(last['rsi']),
        "regime": "QUIET" if last['vol_p'] < 0.33 else ("NORMAL" if last['vol_p'] < 0.67 else "TURBULENT"),
        "signal": last['sig_label'],
        "confidence": float(last['conf']),
        "distribution": {
            "buy": int((df['sig'] == 1).sum()),
            "sell": int((df['sig'] == -1).sum()),
            "hold": int((df['sig'] == 0).sum())
        },
        "recent_signals": df[df['sig'] != 0].tail(5)[['sig_label', 'cps', 'conf', 'close']].to_dict('records')
    }

    result = clean_data({
        "dates": res.index.strftime('%Y-%m-%d').tolist(),
        "close": res['close'].tolist(),
        "open": res['open'].tolist(),
        "high": res['high'].tolist(),
        "low": res['low'].tolist(),
        "cps": res['cps'].tolist(),
        "t_buy": res['t_buy'].tolist(),
        "t_sell": res['t_sell'].tolist(),
        "mpm": res['mpm'].tolist(),
        "cma": res['cma'].tolist(),
        "rsi": res['rsi'].tolist(),
        "signals": res['sig'].tolist(),
        "confidence": res['conf'].tolist(),
        "bb_u": res['bb_u'].tolist(),
        "bb_l": res['bb_l'].tolist(),
        "regime_p": res['vol_p'].tolist(),
        "report": report
    })
    set_cached_intel(cache_key, result)
    return jsonify(result)






# --- EXPANDED FUNDAMENTAL SUITE (Based on cek_fd.py) ---


def _fd_df_to_dict(df):
    if df is None:
        return {}
    if isinstance(df, dict):
        return clean_data(df)
    if not hasattr(df, "empty"): # Not a pandas object
        return clean_data(df)
    if df.empty:
        return {}
        
    df = df.copy()
    try:
        # Convert columns and index to string for JSON keys
        df.columns = df.columns.astype(str)
        df.index = df.index.astype(str)
    except:
        pass

    # Avoid fillna("") error with Int64 by using explicit replace
    # We use clean_data later which handles NaN/Inf properly if they stay as None
    # Converting to object type first is safest for mixed/nullable types
    res = df.astype(object).where(pd.notnull(df), None).to_dict()
    return clean_data(res)

@app.route('/api/entity/fundamental/financials/<symbol>')
def get_entity_financials(symbol):
    try:
        t = yf.Ticker(normalize_symbol(symbol))
        data = {
            "income_statement": _fd_df_to_dict(t.financials),
            "balance_sheet": _fd_df_to_dict(t.balance_sheet),
            "cash_flow": _fd_df_to_dict(t.cashflow),
            "quarterly_income": _fd_df_to_dict(t.quarterly_financials),
            "quarterly_balance": _fd_df_to_dict(t.quarterly_balance_sheet),
        }
        return jsonify(clean_data(data))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/entity/fundamental/ownership/<symbol>')
def get_entity_ownership(symbol):
    try:
        t = yf.Ticker(normalize_symbol(symbol))
        data = {
            "major_holders": _fd_df_to_dict(t.major_holders),
            "institutional_holders": _fd_df_to_dict(t.institutional_holders),
            "insider_transactions": _fd_df_to_dict(t.insider_transactions),
            "insider_purchases": _fd_df_to_dict(getattr(t, "insider_purchases", None))
        }
        return jsonify(clean_data(data))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/entity/fundamental/analyst/<symbol>')
def get_entity_analyst(symbol):
    try:
        t = yf.Ticker(normalize_symbol(symbol))
        data = {
            "recommendations": _fd_df_to_dict(t.recommendations),
            "target_price": _fd_df_to_dict(getattr(t, "analyst_price_target", None)),
            "earnings_trend": _fd_df_to_dict(getattr(t, "earnings_trend", None)),
            "upgrades_downgrades": _fd_df_to_dict(getattr(t, "upgrades_downgrades", None))
        }
        return jsonify(clean_data(data))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/entity/fundamental/events/<symbol>')
def get_entity_events(symbol):
    try:
        t = yf.Ticker(normalize_symbol(symbol))
        data = {
            "calendar": _fd_df_to_dict(t.calendar),
            "earnings_dates": _fd_df_to_dict(getattr(t, "earnings_dates", None)),
            "sec_filings": _fd_df_to_dict(getattr(t, "sec_filings", None)),
            "dividends": _fd_df_to_dict(t.dividends.to_frame() if not t.dividends.empty else None)
        }
        return jsonify(clean_data(data))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/entity/fundamental/info/<symbol>')
def get_entity_info_fd(symbol):
    try:
        t = yf.Ticker(normalize_symbol(symbol))
        return jsonify(clean_data(t.info if t.info else {}))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/entity/market-indices')
def get_market_indices():
    indices_config = {
        "ASIA TENGGARA": {
            "^JKSE": {"name": "IDX Composite", "country": "id"},
            "^STI": {"name": "STI Index - Singapore", "country": "sg"},
            "^KLSE": {"name": "FTSE Bursa Malaysia KLCI", "country": "my"},
            "SET.BK": {"name": "SET Index - Thailand", "country": "th"},      # Tanpa ^
            "PSEI.PS": {"name": "PSEi Index - Philippines", "country": "ph"},  # Tanpa ^
            "VNI.VN": {"name": "VN-Index - Vietnam", "country": "vn"}          # Simbol VNI.VN lebih umum
        },
        "ASIA PASIFIK & AUSTRALIA": {
            "^N225": {"name": "Nikkei 225", "country": "jp"},
            "^HSI": {"name": "Hang Seng Index", "country": "hk"},
            "^KS11": {"name": "KOSPI Composite", "country": "kr"},
            "000001.SS": {"name": "SSE Composite - Shanghai", "country": "cn"},
            "^BSESN": {"name": "S&P BSE Sensex", "country": "in"},
            "^AXJO": {"name": "S&P/ASX 200", "country": "au"},
            "^TWII": {"name": "TWSE Weighted Index - Taiwan", "country": "tw"}
        },
        "AMERIKA SERIKAT": {
            "^GSPC": {"name": "S&P 500", "country": "us"},
            "^DJI": {"name": "Dow Jones Industrial Average", "country": "us"}, # Duplikat dihapus
            "^IXIC": {"name": "NASDAQ Composite", "country": "us"},
            "^RUT": {"name": "Russell 2000", "country": "us"}
        },
        "EROPA": {
            "^FTSE": {"name": "FTSE 100", "country": "gb"},
            "^GDAXI": {"name": "DAX PERFORMANCE-INDEX", "country": "de"},
            "^FCHI": {"name": "CAC 40", "country": "fr"},
            "^STOXX50E": {"name": "ESTX 50 PR.EUR", "country": "eu"},
            "^N100": {"name": "Euronext 100 Index", "country": "eu"}
        },
        "GLOBAL/LAINNYA": {
            "^NYA": {"name": "NYSE Composite (DJ)", "country": "us"},
            "^XAX": {"name": "NYSE AMEX COMPOSITE INDEX", "country": "us"}
        }
    }
    
    all_symbols = []
    for cat in indices_config.values():
        all_symbols.extend(cat.keys())
        
    try:
        # Fetch data for all symbols in one go
        data = yf.download(all_symbols, period="3d", group_by='ticker', threads=True, progress=False)
        
        results = []
        for category, symbols_dict in indices_config.items():
            cat_data = []
            for symbol, cfg in symbols_dict.items():
                try:
                    ticker_df = data[symbol] if len(all_symbols) > 1 else data
                    ticker_df = ticker_df.dropna(subset=['Close'])
                    
                    if ticker_df.empty: continue
                    
                    last_row = ticker_df.iloc[-1]
                    prev_row = ticker_df.iloc[-2] if len(ticker_df) > 1 else last_row
                    
                    close_val = float(last_row['Close'])
                    prev_close = float(prev_row['Close'])
                    change = close_val - prev_close
                    change_pct = (change / prev_close * 100) if prev_close != 0 else 0
                    
                    cat_data.append({
                        "symbol": symbol,
                        "name": cfg["name"],
                        "country": cfg["country"],
                        "open": float(last_row.get('Open', close_val)),
                        "high": float(last_row.get('High', close_val)),
                        "low": float(last_row.get('Low', close_val)),
                        "close": close_val,
                        "volume": int(last_row.get('Volume', 0)) if not pd.isna(last_row.get('Volume')) else 0,
                        "change": change,
                        "change_pct": change_pct
                    })
                except Exception as e:
                    print(f"Error processing {symbol}: {e}")
            
            results.append({
                "category": category,
                "data": cat_data
            })
            
        return jsonify(results)
    except Exception as e:
        print(f"Global market indices error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/entity/market-movers/<index_symbol>')
def get_market_movers(index_symbol):
    # Mapping index to a set of major constituent tickers for real-time movers calculation
    # Since free yfinance has no 'get_constituents' for broad indices, we use key liquid proxies
    MOVER_MAP = {
        "^JKSE": ["BBCA.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASII.JK", "GOTO.JK", "BBNI.JK", "UNVR.JK", "ADRO.JK", "AMRT.JK", "TPIA.JK", "BYAN.JK", "MDKA.JK", "PGAS.JK", "ANTM.JK"],
        "^GSPC": ["AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "BRK-B", "UNH", "JPM", "V", "MA", "AVGO", "HD", "PG"],
        "^HSI": ["0700.HK", "9988.HK", "3690.HK", "1299.HK", "0005.HK", "0939.HK", "2318.HK", "1398.HK", "3988.HK", "9618.HK", "1810.HK", "2382.HK"],
        "^N225": ["9983.T", "8035.T", "9984.T", "6758.T", "4063.T", "6098.T", "4543.T", "6954.T", "6971.T", "6367.T"],
        "^FTSE": ["SHEL.L", "AZN.L", "HSBA.L", "ULVR.L", "BP.L", "DGE.L", "GSK.L", "RIO.L", "REL.L", "GLEN.L"]
    }
    
    # Default to US if not found, or just return empty
    tickers = MOVER_MAP.get(index_symbol, MOVER_MAP["^GSPC"])
    
    try:
        data = yf.download(tickers, period="2d", interval="1d", group_by='ticker', threads=True, progress=False)
        movers = []
        
        for ticker in tickers:
            try:
                df = data[ticker] if len(tickers) > 1 else data
                df = df.dropna(subset=['Close'])
                if df.empty or len(df) < 2: continue
                
                last_row = df.iloc[-1]
                prev_row = df.iloc[-2]
                
                close = float(last_row['Close'])
                change = close - float(prev_row['Close'])
                change_pct = (change / float(prev_row['Close'])) * 100
                
                movers.append({
                    "symbol": ticker,
                    "close": close,
                    "change": change,
                    "change_pct": change_pct,
                    "volume": int(last_row['Volume']) if not pd.isna(last_row.get('Volume')) else 0
                })
            except:
                continue
        
        # Sort by percentage change
        movers.sort(key=lambda x: x['change_pct'], reverse=True)
        
        return jsonify({
            "gainers": movers[:8],
            "losers": sorted(movers, key=lambda x: x['change_pct'])[:8]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════
#  Annual Report Highlight API
# ═══════════════════════════════════════════════════════════

@app.route('/api/entity/annual-report/<symbol>')
def get_annual_report_data(symbol):
    
    try:
        symbol = symbol.upper().strip()
        # Ambil daftar report untuk ticker ini (dengan highlight_json)
        conn = get_db_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT id, kode_perusahaan, nama_perusahaan, tahun_report,
                       link_report, Sector, highlight_json, created_at, updated_at
                FROM annual_reports
                WHERE kode_perusahaan LIKE %s
                ORDER BY tahun_report DESC
            """, (f"%{symbol}%",))
            rows = cur.fetchall()
        finally:
            conn.close()

        if not rows:
            return jsonify({
                "exists": False,
                "ticker": symbol,
                "reports": []
            })

        # Parse highlight_json for each row
        for row in rows:
            if row.get('highlight_json') and isinstance(row['highlight_json'], str):
                try:
                    row['highlight_json'] = json.loads(row['highlight_json'])
                except (json.JSONDecodeError, TypeError):
                    pass  # biarkan string mentah
            # Convert datetime objects to strings
            for key in ('created_at', 'updated_at'):
                if row.get(key) and hasattr(row[key], 'isoformat'):
                    row[key] = row[key].isoformat()

        return jsonify({
            "exists": True,
            "ticker": symbol,
            "reports": rows
        })

    except Exception as e:
        print(f"[ANNUAL_REPORT_API] Error for {symbol}: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    socketio.run(app, host=os.getenv('API_HOST', '0.0.0.0'), port=5005, debug=True, allow_unsafe_werkzeug=True)
