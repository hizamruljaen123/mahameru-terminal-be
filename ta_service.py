"""
================================================================================
  ASETPEDIA TECHNICAL ANALYSIS SERVICE
  Port: 5007
  Provides full technical analysis via REST API
================================================================================
"""

import os
from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf
import pandas as pd
import numpy as np
import warnings

warnings.filterwarnings('ignore')

# Try importing talib, fall back to manual calculations if not available
try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False

app = Flask(__name__)
CORS(app)

# ============================================================================
#  HELPERS
# ============================================================================
def normalize_symbol(symbol):
    symbol = symbol.strip().upper()
    if ':' in symbol:
        parts = symbol.split(':')
        exchange, ticker = parts[0], parts[1]
        if exchange == 'IDX': return f"{ticker}.JK"
        elif exchange in ['NSDQ', 'NASDAQ', 'NYSE', 'AMEX']: return ticker
        elif exchange == 'HKEX': return f"{ticker}.HK"
        elif exchange == 'LSE': return f"{ticker}.L"
        return ticker
    return symbol

def clean(obj):
    if isinstance(obj, (float, int, np.floating, np.integer)):
        if np.isnan(obj) or np.isinf(obj): return None
        return float(obj)
    elif isinstance(obj, dict): return {k: clean(v) for k, v in obj.items()}
    elif isinstance(obj, list): return [clean(x) for x in obj]
    elif isinstance(obj, (np.ndarray, pd.Series)): return clean(obj.tolist())
    return obj

# ============================================================================
#  MANUAL TA FUNCTIONS (fallback or primary)
# ============================================================================
def _sma(series, period): return series.rolling(period).mean()
def _ema(series, period): return series.ewm(span=period, adjust=False).mean()

def _rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    # Wilder's Smoothing is EMA with alpha = 1/period
    avg_gain = gain.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    
    rs = avg_gain / (avg_loss.replace(0, 1e-10))
    return 100 - (100 / (1 + rs))

def _macd(series, fast=12, slow=26, signal=9):
    ema_fast = _ema(series, fast)
    ema_slow = _ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def _bbands(series, period=20, std_dev=2):
    middle = _sma(series, period)
    # TradingView and Frontend use Population Standard Deviation (ddof=0)
    std = series.rolling(period).std(ddof=0)
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    return upper, middle, lower

def _stoch(high, low, close, k_period=14, d_period=3):
    low_min = low.rolling(k_period).min()
    high_max = high.rolling(k_period).max()
    k = 100 * (close - low_min) / (high_max - low_min + 1e-10)
    d = k.rolling(d_period).mean()
    return k, d

def _atr(high, low, close, period=14):
    tr = pd.DataFrame({
        'hl': high - low,
        'hc': (high - close.shift(1)).abs(),
        'lc': (low - close.shift(1)).abs()
    }).max(axis=1)
    # Wilder's Smoothing for ATR
    return tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean()

def _cci(high, low, close, period=20):
    typical = (high + low + close) / 3
    mean_tp = typical.rolling(period).mean()
    # Use raw=True to pass numpy array for massive speedup over pandas objects
    mean_dev = typical.rolling(period).apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True)
    return (typical - mean_tp) / (0.015 * mean_dev + 1e-10)

def _willr(high, low, close, period=14):
    high_max = high.rolling(period).max()
    low_min = low.rolling(period).min()
    return -100 * (high_max - close) / (high_max - low_min + 1e-10)

def _obv(close, volume):
    direction = np.sign(close.diff())
    direction.iloc[0] = 0
    return (direction * volume).cumsum()

def _mfi(high, low, close, volume, period=14):
    typical = (high + low + close) / 3
    money_flow = typical * volume
    pos_flow = money_flow.where(typical > typical.shift(1), 0).rolling(period).sum()
    neg_flow = money_flow.where(typical <= typical.shift(1), 0).rolling(period).sum()
    mfr = pos_flow / (neg_flow + 1e-10)
    return 100 - (100 / (1 + mfr))

def _sar(high, low, af=0.02, max_af=0.2):
    """Optimized Parabolic SAR using NumPy for performance"""
    h_arr = high.values
    l_arr = low.values
    size = len(h_arr)
    sar_arr = np.zeros(size)
    
    bull = True
    isar = l_arr[0]
    ep = h_arr[0]
    current_af = af
    
    for i in range(1, size):
        prev_sar = isar
        if bull:
            isar = prev_sar + current_af * (ep - prev_sar)
            # Boundary protection
            isar = min(isar, l_arr[i-1], l_arr[max(0, i-2)])
            if l_arr[i] < isar:
                bull = False
                isar = ep
                ep = l_arr[i]
                current_af = af
            else:
                if h_arr[i] > ep:
                    ep = h_arr[i]
                    current_af = min(current_af + af, max_af)
        else:
            isar = prev_sar + current_af * (ep - prev_sar)
            # Boundary protection
            isar = max(isar, h_arr[i-1], h_arr[max(0, i-2)])
            if h_arr[i] > isar:
                bull = True
                isar = ep
                ep = h_arr[i]
                current_af = af
            else:
                if l_arr[i] < ep:
                    ep = l_arr[i]
                    current_af = min(current_af + af, max_af)
        sar_arr[i] = isar
        
    return pd.Series(sar_arr, index=high.index)

def _adx(high, low, close, period=14):
    tr = pd.DataFrame({
        'hl': high - low,
        'hc': (high - close.shift(1)).abs(),
        'lc': (low - close.shift(1)).abs()
    }).max(axis=1)
    
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
    
    # Standard ADX uses Wilder's Smoothing (alpha = 1/period)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / (atr + 1e-10))
    minus_di = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / (atr + 1e-10))
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-10)
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    return adx, plus_di, minus_di

# ============================================================================
#  SUPPORT & RESISTANCE DETECTION
# ============================================================================
def find_support_resistance(df, window=15, num_levels=5):
    highs = df['High'].values
    lows = df['Low'].values
    close_price = float(df['Close'].iloc[-1])
    
    supports, resistances = [], []
    size = len(highs)
    
    for i in range(window, size - window):
        # Optimization: Use NumPy argmax/argmin or direct comparison
        if highs[i] == np.max(highs[i-window : i+window+1]):
            resistances.append(round(float(highs[i]), 4))
        if lows[i] == np.min(lows[i-window : i+window+1]):
            supports.append(round(float(lows[i]), 4))

    supports = sorted(set(supports))
    resistances = sorted(set(resistances), reverse=True)
    
    # Filter to relevant levels around current price
    supports = [s for s in supports if s < close_price][-num_levels:]
    resistances = [r for r in resistances if r > close_price][:num_levels]
    return supports, resistances

# ============================================================================
#  FIBONACCI RETRACEMENT
# ============================================================================
def fibonacci_levels(df):
    hi = float(df['High'].max())
    lo = float(df['Low'].min())
    diff = hi - lo
    return {
        "high": hi, "low": lo,
        "levels": {
            "0.000": hi, "0.236": hi - 0.236 * diff,
            "0.382": hi - 0.382 * diff, "0.500": hi - 0.500 * diff,
            "0.618": hi - 0.618 * diff, "0.786": hi - 0.786 * diff,
            "1.000": lo
        }
    }

# ============================================================================
#  MAIN CALCULATION ENGINE
# ============================================================================
def calculate_all(df, include=None):
    """
    Optimized calculation engine with inclusion filtering.
    If include is None, all indicators are calculated.
    """
    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume'].astype(float)
    
    out = {}
    
    def should_calc(key):
        if include is None: return True
        return key in include

    # --- Moving Averages ---
    if should_calc('sma'):
        out['sma'] = {
            'sma10':  _sma(close, 10).tolist(),
            'sma20':  _sma(close, 20).tolist(),
            'sma50':  _sma(close, 50).tolist(),
            'sma100': _sma(close, 100).tolist(),
            'sma200': _sma(close, 200).tolist(),
        }
    if should_calc('ema'):
        out['ema'] = {
            'ema9':   _ema(close, 9).tolist(),
            'ema12':  _ema(close, 12).tolist(),
            'ema21':  _ema(close, 21).tolist(),
            'ema26':  _ema(close, 26).tolist(),
            'ema50':  _ema(close, 50).tolist(),
            'ema200': _ema(close, 200).tolist(),
        }

    # --- Bollinger Bands ---
    if should_calc('bb'):
        bb_up, bb_mid, bb_low = _bbands(close, 20)
        bb_width = (bb_up - bb_low) / (bb_mid + 1e-10)
        bb_pct = (close - bb_low) / (bb_up - bb_low + 1e-10)
        out['bb'] = {
            'upper': bb_up.tolist(), 'middle': bb_mid.tolist(), 'lower': bb_low.tolist(),
            'width': bb_width.tolist(), 'pct': bb_pct.tolist()
        }

    # --- RSI ---
    if should_calc('rsi'):
        out['rsi'] = {
            'rsi6':  _rsi(close, 6).tolist(),
            'rsi14': _rsi(close, 14).tolist(),
            'rsi21': _rsi(close, 21).tolist(),
        }

    # --- MACD ---
    if should_calc('macd'):
        macd_line, macd_sig, macd_hist = _macd(close)
        out['macd'] = {
            'line': macd_line.tolist(), 'signal': macd_sig.tolist(), 'hist': macd_hist.tolist()
        }

    # --- Stochastic ---
    stoch_k, stoch_d = _stoch(high, low, close)
    out['stoch'] = {'k': stoch_k.tolist(), 'd': stoch_d.tolist()}

    # --- ADX ---
    if should_calc('adx'):
        adx, plus_di, minus_di = _adx(high, low, close)
        out['adx'] = {'adx': adx.tolist(), 'plus_di': plus_di.tolist(), 'minus_di': minus_di.tolist()}

    # --- ATR ---
    if should_calc('atr'):
        atr14 = _atr(high, low, close, 14)
        out['atr'] = atr14.tolist()
        out['atr_pct'] = (atr14 / (close + 1e-10) * 100).tolist()

    # --- CCI ---
    if should_calc('cci'):
        out['cci'] = _cci(high, low, close, 20).tolist()

    # --- Williams %R ---
    if should_calc('willr'):
        out['willr'] = _willr(high, low, close, 14).tolist()

    # --- OBV ---
    if should_calc('obv'):
        obv = _obv(close, volume)
        out['obv'] = obv.tolist()
        out['obv_ema'] = _ema(obv, 20).tolist()

    # --- MFI ---
    if should_calc('mfi'):
        out['mfi'] = _mfi(high, low, close, volume, 14).tolist()

    # --- Parabolic SAR ---
    if should_calc('sar'):
        out['sar'] = _sar(high, low).tolist()

    # --- Ichimoku ---
    if should_calc('ichimoku'):
        tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
        kijun  = (high.rolling(26).max() + low.rolling(26).min()) / 2
        senkou_a = ((tenkan + kijun) / 2).shift(26)
        senkou_b = pd.Series((high.rolling(52).max().values + low.rolling(52).min().values) / 2, index=df.index).shift(26)
        chikou = close.shift(-26)
        out['ichimoku'] = {
            'tenkan': tenkan.tolist(), 'kijun': kijun.tolist(),
            'senkou_a': senkou_a.tolist(), 'senkou_b': senkou_b.tolist(),
            'chikou': chikou.tolist()
        }

    # --- VWAP ---
    if should_calc('vwap'):
        tp = (high + low + close) / 3
        vwap = (volume * tp).cumsum() / (volume.cumsum() + 1e-10)
        out['vwap'] = vwap.tolist()

    # --- Volume ---
    if should_calc('volume'):
        vol_sma20 = _sma(volume, 20)
        vol_ratio = volume / (vol_sma20 + 1e-10)
        out['volume'] = {
            'raw': volume.tolist(),
            'sma20': vol_sma20.tolist(),
            'ratio': vol_ratio.tolist()
        }

    # --- Historical Volatility ---
    if should_calc('hv20'):
        log_ret = np.log(close / close.shift(1).replace(0, np.nan))
        hv20 = log_ret.rolling(20).std() * np.sqrt(252) * 100
        out['hv20'] = hv20.tolist()

    # --- Returns ---
    out['returns'] = {
        'r1d':  clean(float(close.pct_change(1).iloc[-1]) * 100),
        'r5d':  clean(float(close.pct_change(5).iloc[-1]) * 100),
        'r20d': clean(float(close.pct_change(20).iloc[-1]) * 100),
        'r60d': clean(float(close.pct_change(60).iloc[-1]) * 100) if len(close) > 60 else None,
        'r6mo': clean(float((close.iloc[-1] / (close.iloc[0] or 1) - 1) * 100))
    }

    return out


def generate_signals(df, indicators):
    last_idx = -1
    close = df['Close']
    
    def get(key_path):
        keys = key_path.split('.')
        d = indicators
        for k in keys:
            if isinstance(d, list): d = d[last_idx]
            elif isinstance(d, dict): d = d.get(k)
            else: return None
        if isinstance(d, list): return d[last_idx]
        return d

    def safe(val):
        if val is None or (isinstance(val, float) and np.isnan(val)): return 0.0
        return float(val)

    # --- MARKET REGIME DETECTION (The Brain) ---
    adx_val = safe(get('adx.adx'))
    plus_di = safe(get('adx.plus_di'))
    minus_di = safe(get('adx.minus_di'))
    
    # Thresholds: > 25 is trending, < 20 is ranging/sideways
    is_trending = adx_val > 25
    is_ranging = adx_val < 20
    trend_dir = 1 if plus_di > minus_di else -1

    sigs = {}
    price = float(close.iloc[-1])

    # 1. TREND FOLLOWERS
    # SMA
    sma20 = safe(get('sma.sma20')); sma50 = safe(get('sma.sma50'))
    sma_sig = 1 if price > sma20 > sma50 else (-1 if price < sma20 < sma50 else 0)
    
    # EMA
    ema9 = safe(get('ema.ema9')); ema21 = safe(get('ema.ema21')); ema50 = safe(get('ema.ema50'))
    ema_sig = 1 if ema9 > ema21 > ema50 else (-1 if ema9 < ema21 < ema50 else 0)
    
    # MACD
    macd = safe(get('macd.line')); macd_sig = safe(get('macd.signal'))
    macd_val = 1 if macd > macd_sig else -1
    
    # SAR & VWAP
    sar = safe(indicators['sar'][-1]) if isinstance(indicators.get('sar'), list) else price
    vwap = safe(indicators['vwap'][-1]) if isinstance(indicators.get('vwap'), list) else price
    sar_sig = 1 if price > sar else -1
    vwap_sig = 1 if price > vwap else -1

    # Ichimoku
    sa = safe(indicators['ichimoku']['senkou_a'][-1])
    sb = safe(indicators['ichimoku']['senkou_b'][-1])
    tk = safe(indicators['ichimoku']['tenkan'][-1])
    kj = safe(indicators['ichimoku']['kijun'][-1])
    ichimoku_sig = 1 if price > max(sa, sb) and tk > kj else (-1 if price < min(sa, sb) and tk < kj else 0)

    # 2. OSCILLATORS
    # RSI
    rsi14 = safe(get('rsi.rsi14'))
    rsi_sig = 1 if rsi14 < 30 else (-1 if rsi14 > 70 else 0)
    
    # STOCH
    stoch_k = safe(get('stoch.k')); stoch_d = safe(get('stoch.d'))
    stoch_sig = 1 if stoch_k < 20 and stoch_k > stoch_d else (-1 if stoch_k > 80 and stoch_k < stoch_d else 0)
    
    # CCI & Williams %R
    cci = safe(indicators['cci'][-1]) if isinstance(indicators.get('cci'), list) else 0
    willr = safe(indicators['willr'][-1]) if isinstance(indicators.get('willr'), list) else 0
    cci_sig = 1 if cci < -100 else (-1 if cci > 100 else 0)
    willr_sig = 1 if willr < -80 else (-1 if willr > -20 else 0)

    # --- AGGREGATION LOGIC (Strict Regime Filtering) ---
    weights = {}
    
    if is_trending:
        # 1. TRENDING REGIME: Discard oscillators, rely on structure and momentum
        weights = {
            'SMA_CONFIRM': sma_sig * 2.0,
            'EMA_CONFIRM': ema_sig * 2.0,
            'MACD_TREND': macd_val * 1.5,
            'SAR_POS': sar_sig * 1.0,
            'VWAP_POS': vwap_sig * 1.0,
            'ICHIMOKU_CLOUD': ichimoku_sig * 2.0,
            'ADX_STRENGTH': trend_dir * 3.0 
        }
    elif is_ranging:
        # 2. RANGING REGIME: Discard trend followers, buy low / sell high
        weights = {
            'RSI_OSC': rsi_sig * 3.0,
            'STOCH_OSC': stoch_sig * 3.0,
            'CCI_OSC': cci_sig * 2.0,
            'WILLIAMS_R': willr_sig * 2.0,
            'BB_BOUND': (1 if safe(get('bb.pct')) < 0.05 else (-1 if safe(get('bb.pct')) > 0.95 else 0)) * 2.0
        }
    else:
        # 3. TRANSITIONAL / NEUTRAL: Use high-level convergence of all signals
        weights = {
            'SMA': sma_sig * 1.0,
            'EMA': ema_sig * 1.0,
            'MACD': macd_val * 1.0,
            'RSI': rsi_sig * 1.0,
            'STOCH': stoch_sig * 1.5,
            'SAR': sar_sig * 1.0
        }

    total_score = sum(weights.values())
    max_score = sum(abs(v) for v in weights.values()) or 1.0
    pct = (total_score / max_score) * 100 # From -100 to 100

    # Adjust perspective for the user (transform -100/100 to 0/100)
    display_pct = (pct + 100) / 2

    if pct > 60: verdict = "STRONG BUY"
    elif pct > 20: verdict = "BUY"
    elif pct < -60: verdict = "STRONG SELL"
    elif pct < -20: verdict = "SELL"
    else: verdict = "NEUTRAL"

    return {
        "signals": weights, 
        "score": round(display_pct, 1), 
        "pct": round(display_pct, 1), 
        "verdict": verdict, 
        "regime": "TRENDING" if is_trending else ("RANGING" if is_ranging else "NEUTRAL")
    }

# ============================================================================
#  MAIN ANALYZE ENDPOINT
# ============================================================================
@app.route('/api/ta/analyze/<symbol>')
def analyze(symbol):
    period = request.args.get('period', '6mo')
    
    valid_periods = ['1mo', '3mo', '6mo', '1y', '2y', '5y']
    if period not in valid_periods:
        period = '6mo'

    norm = normalize_symbol(symbol)
    try:
        ticker = yf.Ticker(norm)
        df = ticker.history(period=period, interval='1d')
        if df.empty:
            return jsonify({"error": f"No data for {symbol}"}), 404

        info = ticker.info or {}
        df.index = df.index.tz_localize(None)

        # Handle include parameter
        include_param = request.args.get('include', '')
        include_list = [i.strip().lower() for i in include_param.split(',')] if include_param else None

        # Calculate indicators (on-demand)
        indicators = calculate_all(df, include=include_list)

        # Generate signals (requires core indicators)
        score = generate_signals(df, indicators) if (not include_list or 'adx' in include_list) else {"verdict": "DATA_LIMITED"}

        # Support & Resistance
        supports, resistances = find_support_resistance(df)

        # Fibonacci
        fib = fibonacci_levels(df)

        # OHLCV for chart (return dates + arrays)
        dates = df.index.strftime('%Y-%m-%d').tolist()
        
        # Latest values extraction logic
        def last(indicator_group, key=None):
            try:
                data = indicator_group
                if key and isinstance(indicator_group, dict): data = indicator_group.get(key)
                if isinstance(data, list) and data:
                    val = data[-1]
                    if val is None or (isinstance(val, float) and np.isnan(val)): return None
                    return round(float(val), 4)
            except: pass
            return None

        last_close = float(df['Close'].iloc[-1])
        
        # Build current view safely
        current = {
            "price": last_close,
            "rsi14":    last(indicators.get('rsi', {}), 'rsi14'),
            "macd":     last(indicators.get('macd', {}), 'line'),
            "adx":      last(indicators.get('adx', {}), 'adx'),
            "sar":      last(indicators.get('sar')),
            "mfi":      last(indicators.get('mfi')),
            "bb_pct":   last(indicators.get('bb', {}), 'pct'),
            "atr":      last(indicators.get('atr')),
            "atr_pct":  last(indicators.get('atr_pct')),
            "hv20":     last(indicators.get('hv20'))
        }

        # Moving averages table
        ma_table = {}
        all_mas = {**indicators.get('sma', {}), **indicators.get('ema', {})}
        for k, v in all_mas.items():
            lv = last(v)
            if lv:
                ma_table[k] = {"value": lv, "diff": round(last_close - lv, 4), "pct": round((last_close - lv) / lv * 100, 2), "above": last_close > lv}

        return jsonify(clean({
            "symbol": symbol,
            "period": period,
            "trading_days": len(df),
            "period_start": df.index[0].strftime('%Y-%m-%d'),
            "period_end":   df.index[-1].strftime('%Y-%m-%d'),
            "info": {
                "name":     info.get('longName', symbol),
                "sector":   info.get('sector') or ('CRYPTOCURRENCY' if '-USD' in norm or 'USDT' in norm else 'N/A'),
                "industry": info.get('industry', 'N/A'),
                "market_cap": info.get('marketCap'),
                "currency": info.get('currency', 'USD'),
            },
            "dates": dates,
            "ohlcv": {
                "open":   df['Open'].tolist(),
                "high":   df['High'].tolist(),
                "low":    df['Low'].tolist(),
                "close":  df['Close'].tolist(),
                "volume": df['Volume'].tolist()
            },
            "indicators": indicators,
            "current": current,
            "ma_table": ma_table,
            "returns": indicators['returns'],
            "signals": score,
            "support_resistance": {
                "supports": supports,
                "resistances": resistances
            },
            "fibonacci": fib
        }))

    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()}), 500


@app.route('/api/ta/health')
def health():
    return jsonify({"status": "online", "port": 5007, "talib": TALIB_AVAILABLE})


if __name__ == '__main__':
    print("=" * 60)
    print("  ASETPEDIA TA SERVICE — PORT 5007")
    print(f"  TA-Lib: {'ENABLED' if TALIB_AVAILABLE else 'FALLBACK MODE'}")
    print("=" * 60)
    app.run(host=os.getenv('API_HOST', '0.0.0.0'), port=5007, debug=False)
