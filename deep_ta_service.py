import os, sys, io, time, json, traceback, threading, uuid
from datetime import datetime
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

# ── Pastikan path library benar ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# ── Import Library Lokal ──
from asetpediadeepta.deep_analysis_core import (
    validate_ohlcv, TAEnhanced,
    detect_volume_price_divergence, volume_flow_intensity,
    multi_period_rsi_entropy, hurst_exponent_rolling, fractal_dimension,
    market_regime_detector, detect_head_shoulders, detect_double_top_bottom,
    detect_wedge_patterns, zscore_dynamic_support_resistance,
    spectral_cycle_analysis, wavelet_trend_decomposition,
    sequential_entropy_index, mutual_information_price_volume,
    volume_profile_poc, vwap_deviation_bands, volume_delta_imbalance,
    polynomial_trend_momentum, adaptive_macd, composite_momentum_score,
    regime_adaptive_signal, detect_price_anomalies, tail_risk_indicator,
    multi_indicator_divergence, price_manifold_embedding,
    normalized_rolling_deviation, volume_zscore_mean_reversion,
    elliott_wave_detector, detect_order_blocks, detect_fair_value_gaps,
    detect_liquidity_sweeps, smart_money_concepts, dynamic_position_sizer,
    spectral_momentum_score, price_volume_impulse, momentum_divergence_index,
    adaptive_momentum_oscillator, volatility_regime_classifier,
    fractal_volatility_index, bollinger_squeeze_intensity,
    yang_zhang_volatility, triple_ema_confluence_score,
    supertrend_dynamic, multi_ma_ribbon_score,
    volume_price_momentum_divergence, vwap_bands_lib3,
    cumulative_delta_proxy, volume_weighted_rsi, on_balance_momentum,
    candlestick_composite_signal, relative_vigor_index_enhanced,
    stochastic_rsi_divergence, chande_kroll_stop,
    dmi_crossover_quality, dominant_cycle_detector,
    spectral_band_filter, instantaneous_phase_indicator,
    price_entropy_score, hurst_lib3, permutation_entropy,
    market_inefficiency_index, master_signal_score,
)

from asetpediadeepta.deep_analysis_ohlcv import (
    build_deep_technical_frame, add_core_indicators,
    add_candlestick_patterns, add_statistical_structure,
    detect_market_regime as regime_lib2, support_resistance_features,
    divergence_features, similarity_engine, composite_scoring,
    scan_signal_events, AnalysisConfig,
)


# ═══════════════════════════════════════════════════════════════════════════════
# APP SETUP
# ═══════════════════════════════════════════════════════════════════════════════

app = Flask(__name__)
CORS(app)

@app.route("/api/debug/inspect", methods=["GET"])
def api_inspect():
    return jsonify({
        "sessions": list(SESSIONS.keys()),
        "registry_keys": list(FUNCTION_REGISTRY.keys()),
        "sys_path": sys.path,
        "cwd": os.getcwd()
    })


# Folder output
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Penyimpanan sesi sementara (di memori)
SESSIONS = {}
SESSION_TTL = 7200  # 2 jam

@app.before_request
def log_request_info():
    sid = request.args.get("session_id")
    print(f"[DEBUG] Request: {request.method} {request.url} | Session ID: {sid} | Known Sessions: {list(SESSIONS.keys())}")
    if sid and sid not in SESSIONS:
        print(f"[DEBUG] SESSION NOT FOUND: {sid}")

def _session_cleanup_worker():

    """Background daemon: purge sessions older than SESSION_TTL."""
    while True:
        now = time.time()
        expired = [
            sid for sid, sess in list(SESSIONS.items())
            if now - datetime.fromisoformat(sess.get("created_at", datetime.now().isoformat())).timestamp() > SESSION_TTL
        ]
        for sid in expired:
            SESSIONS.pop(sid, None)
        import time as _t; _t.sleep(600)  # Check every 10 minutes


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER: Konversi hasil ke JSON-safe
# ═══════════════════════════════════════════════════════════════════════════════

def df_to_dict(df):
    """Konversi DataFrame ke list of dict (JSON-safe)."""
    if df is None:
        return None
    if isinstance(df, pd.Series):
        df = df.to_frame()
    # Handle non-numeric index
    df = df.copy()
    if not isinstance(df.index, pd.RangeIndex):
        df.index = [str(i) for i in df.index]
    # Ensure all column names are strings for JSON compatibility
    df.columns = [str(c) for c in df.columns]
    
    data = df.reset_index().to_dict(orient="records")
    return recursive_clean(data)


def recursive_clean(obj):
    """Bersihkan NaN, inf, -inf secara rekursif agar aman di-serialize ke JSON."""
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return obj
    elif isinstance(obj, dict):
        return {str(k): recursive_clean(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [recursive_clean(x) for x in obj]
    elif isinstance(obj, np.ndarray):
        return recursive_clean(obj.tolist())
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def safe_call(func, *args, **kwargs):
    """Wrapper aman untuk menjalankan fungsi analisa."""
    t0 = time.time()
    try:
        result = func(*args, **kwargs)
        # Jika hasil adalah DataFrame/Series, konversi ke dict
        if isinstance(result, (pd.DataFrame, pd.Series)):
            result = df_to_dict(result)
        else:
            # Bersihkan dari NaN/Inf jika berupa dict/list mentah
            result = recursive_clean(result)
            
        elapsed = round(time.time() - t0, 3)
        return {"status": "success", "elapsed_sec": elapsed, "data": result}
    except Exception as e:
        elapsed = round(time.time() - t0, 3)
        return {"status": "error", "elapsed_sec": elapsed, "error": str(e), "traceback": traceback.format_exc()}


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRY: Daftar semua fungsi analisa yang tersedia
# ═══════════════════════════════════════════════════════════════════════════════

FUNCTION_REGISTRY = {
    # ── 1. CORE TA-LIB ──
    "core_indicators": {
        "name": "Core TA-Lib Indicators (80+ indikator)",
        "category": "core",
        "description": "RSI, MACD, ADX, Bollinger Bands, EMA, Stochastic, CCI, OBV, dll",
        "run": lambda df: df_to_dict(TAEnhanced.all_indicators(df))
    },

    # ── 2. VOLUME ANALYSIS ──
    "volume_divergence": {
        "name": "Volume-Price Divergence (Spearman)",
        "category": "volume",
        "description": "Deteksi divergensi volume-harga menggunakan korelasi rolling",
        "run": lambda df: df_to_dict(detect_volume_price_divergence(df))
    },
    "volume_acceleration": {
        "name": "Volume Flow Intensity (Momentum)",
        "category": "volume",
        "description": "Velocity and impact force of liquidity flow (replaces naive kinematics)",
        "run": lambda df: df_to_dict(volume_flow_intensity(df))
    },
    "volume_profile": {
        "name": "Volume Profile (POC & Value Area)",
        "category": "volume",
        "description": "Point of Control, Value Area High/Low",
        "run": lambda df: df_to_dict(volume_profile_poc(df))
    },
    "vwap_bands": {
        "name": "VWAP Deviation Bands",
        "category": "volume",
        "description": "VWAP cumulative dengan standard deviation bands",
        "run": lambda df: df_to_dict(vwap_deviation_bands(df))
    },
    "vwap_rolling": {
        "name": "Rolling VWAP + σ Bands (Lib3)",
        "category": "volume",
        "description": "VWAP rolling window dengan deviation bands",
        "run": lambda df: df_to_dict(vwap_bands_lib3(df["high"].values, df["low"].values, df["close"].values, df["volume"].values))
    },
    "volume_delta": {
        "name": "Volume Delta Imbalance",
        "category": "volume",
        "description": "Buy vs sell volume estimation, cumulative delta",
        "run": lambda df: df_to_dict(volume_delta_imbalance(df))
    },
    "cumulative_delta": {
        "name": "Cumulative Delta Proxy (Lib3)",
        "category": "volume",
        "description": "Order flow delta approximation + MACD pada delta",
        "run": lambda df: df_to_dict(cumulative_delta_proxy(df["open"].values, df["high"].values, df["low"].values, df["close"].values, df["volume"].values))
    },
    "ob_momentum": {
        "name": "On-Balance Momentum (Lib3)",
        "category": "volume",
        "description": "MACD-like structure pada OBV",
        "run": lambda df: df_to_dict(on_balance_momentum(df["close"].values, df["volume"].values))
    },
    "vpmd": {
        "name": "Volume-Price Momentum Divergence (Lib3)",
        "category": "volume",
        "description": "MACD OBV vs MACD Price — hidden divergence",
        "run": lambda df: df_to_dict(volume_price_momentum_divergence(df["close"].values, df["volume"].values))
    },
    "vol_zscore_reversion": {
        "name": "Volume Z-Score Mean Reversion",
        "category": "volume",
        "description": "Sinyal buy/sell berdasarkan volume z-score ekstrem",
        "run": lambda df: df_to_dict(volume_zscore_mean_reversion(df))
    },

    # ── 3. MOMENTUM ──
    "rsi_entropy": {
        "name": "Multi-Period RSI Entropy",
        "category": "momentum",
        "description": "Shannon entropy dari distribusi RSI multi-period",
        "run": lambda df: df_to_dict(multi_period_rsi_entropy(df))
    },
    "spectral_momentum": {
        "name": "Spectral Momentum Score (Lib3)",
        "category": "momentum",
        "description": "RSI+CCI+WillR+MFI digabung, dimodulasi spectral volume",
        "run": lambda df: safe_call(spectral_momentum_score, df["close"].values, df["volume"].values)
    },
    "kinetic_energy": {
        "name": "Price-Volume Impulse (Intensity)",
        "category": "momentum",
        "description": "Standardized activity magnitude based on log-returns and volume efficiency",
        "run": lambda df: safe_call(price_volume_impulse, df["open"].values, df["close"].values, df["volume"].values)
    },
    "mom_divergence": {
        "name": "Momentum Divergence Index (Lib3)",
        "category": "momentum",
        "description": "Price momentum vs volume momentum (z-score)",
        "run": lambda df: safe_call(momentum_divergence_index, df["close"].values, df["volume"].values)
    },
    "adaptive_mom_osc": {
        "name": "Adaptive Momentum Oscillator (Lib3)",
        "category": "momentum",
        "description": "RSI dengan period adaptif berdasarkan Kaufman ER",
        "run": lambda df: safe_call(adaptive_momentum_oscillator, df["close"].values)
    },
    "vw_rsi": {
        "name": "Volume-Weighted RSI (Lib3)",
        "category": "momentum",
        "description": "RSI where gain/loss is weighted by volume",
        "run": lambda df: safe_call(volume_weighted_rsi, df["close"].values, df["volume"].values)
    },
    "composite_momentum": {
        "name": "Composite Momentum (PCA Fusion)",
        "category": "momentum",
        "description": "11 indikator momentum direduksi via PCA menjadi 1 skor",
        "run": lambda df: df_to_dict(composite_momentum_score(df))
    },
    "poly_momentum": {
        "name": "Polynomial Trend Momentum",
        "category": "momentum",
        "description": "Derivative 1 (momentum) & 2 (curvature) dari polynomial fit",
        "run": lambda df: df_to_dict(polynomial_trend_momentum(df))
    },
    "adaptive_macd": {
        "name": "Adaptive MACD (Auto Cycle)",
        "category": "momentum",
        "description": "MACD dengan perioda fast/slow menyesuaikan siklus market",
        "run": lambda df: df_to_dict(adaptive_macd(df))
    },

    # ── 4. TREND & REGIME ──
    "hurst_exponent": {
        "name": "Hurst Exponent (R/S Analysis)",
        "category": "trend",
        "description": "H>0.5 trending, H<0.5 mean-reverting, H=0.5 random walk",
        "run": lambda df: df_to_dict(pd.DataFrame({"hurst_exponent": hurst_exponent_rolling(df["close"].values)}, index=df.index))
    },
    "fractal_dimension": {
        "name": "Fractal Dimension (Box-Counting)",
        "category": "trend",
        "description": "FD~1 smooth trend, FD~2 chaotic/random",
        "run": lambda df: df_to_dict(fractal_dimension(df))
    },
    "market_regime": {
        "name": "Market Regime Detector",
        "category": "trend",
        "description": "0=Ranging, 1=TrendUp, 2=TrendDown, 3=Volatile",
        "run": lambda df: df_to_dict(market_regime_detector(df))
    },
    "triple_ema": {
        "name": "Triple EMA Confluence Score (Lib3)",
        "category": "trend",
        "description": "Alignment, spread, slope dari 3 EMA (8,21,55)",
        "run": lambda df: df_to_dict(triple_ema_confluence_score(df["close"].values))
    },
    "supertrend": {
        "name": "SuperTrend Dynamic (Lib3)",
        "category": "trend",
        "description": "ATR-adaptive multiplier SuperTrend",
        "run": lambda df: df_to_dict(supertrend_dynamic(df["high"].values, df["low"].values, df["close"].values))
    },
    "ma_ribbon": {
        "name": "Multi-MA Ribbon Score (Lib3)",
        "category": "trend",
        "description": "8 EMA (5-144) alignment, slope, spread",
        "run": lambda df: df_to_dict(multi_ma_ribbon_score(df["close"].values))
    },
    "vol_regime": {
        "name": "Volatility Regime Classifier (Lib3)",
        "category": "trend",
        "description": "LowVol/HighVol × Trend/Chop (4 state)",
        "run": lambda df: df_to_dict(volatility_regime_classifier(df["close"].values))
    },
    "fractal_vol_idx": {
        "name": "Fractal Volatility Index (Lib3)",
        "category": "trend",
        "description": "Hurst-like scaling ATR multi-timeframe",
        "run": lambda df: {
            "fvi": (
                lambda r: r["data"].tolist() if r.get("status") == "success" and r.get("data") is not None
                else []
            )(safe_call(fractal_volatility_index, df["close"].values))
        }
    },

    # ── 5. PATTERN RECOGNITION ──
    "head_shoulders": {
        "name": "Head & Shoulders Detection",
        "category": "pattern",
        "description": "H&S dan Inverse H&S via peak detection + geometric validation",
        "run": lambda df: df_to_dict(detect_head_shoulders(df))
    },
    "double_top_bottom": {
        "name": "Double Top/Bottom Detection",
        "category": "pattern",
        "description": "Clustering harga untuk deteksi double top/bottom",
        "run": lambda df: df_to_dict(detect_double_top_bottom(df))
    },
    "wedge_patterns": {
        "name": "Wedge Patterns (Rising/Falling)",
        "category": "pattern",
        "description": "Linear regression pada highs/lows untuk deteksi wedge",
        "run": lambda df: df_to_dict(detect_wedge_patterns(df))
    },
    "candlestick_composite": {
        "name": "Candlestick Composite (61 Patterns)",
        "category": "pattern",
        "description": "Semua 61 TA-Lib candlestick pattern digabung",
        "run": lambda df: df_to_dict(candlestick_composite_signal(df["open"].values, df["high"].values, df["low"].values, df["close"].values))
    },
    "stochrsi_div": {
        "name": "StochRSI + Divergence (Lib3)",
        "category": "pattern",
        "description": "Stochastic RSI dengan deteksi divergence otomatis",
        "run": lambda df: df_to_dict(stochastic_rsi_divergence(df["close"].values))
    },
    "elliott_wave": {
        "name": "Elliott Wave Detector",
        "category": "pattern",
        "description": "Simplified Elliott wave 5-wave counting",
        "run": lambda df: df_to_dict(elliott_wave_detector(df))
    },

    # ── 6. COMPLEXITY & INFORMATION THEORY ──
    "kolmogorov": {
        "name": "Sequential Entropy Index",
        "category": "complexity",
        "description": "Normalized Shannon entropy on 5-level quantized returns (replaces naive LZ complexity)",
        "run": lambda df: df_to_dict(sequential_entropy_index(df))
    },
    "mutual_info": {
        "name": "Mutual Information (Price ↔ Volume)",
        "category": "complexity",
        "description": "Berapa banyak informasi volume berikan tentang harga",
        "run": lambda df: df_to_dict(mutual_information_price_volume(df))
    },
    "price_entropy": {
        "name": "Price Entropy Score (Lib3)",
        "category": "complexity",
        "description": "Shannon entropy dari return bins (0=structured, 1=chaotic)",
        "run": lambda df: df_to_dict(pd.DataFrame({"price_entropy": price_entropy_score(df["close"].values)}, index=df.index))
    },
    "perm_entropy": {
        "name": "Permutation Entropy (Lib3)",
        "category": "complexity",
        "description": "Ordinal pattern entropy — lebih stabil dari sample entropy",
        "run": lambda df: df_to_dict(pd.DataFrame({"perm_entropy": permutation_entropy(df["close"].values)}, index=df.index))
    },
    "market_inefficiency": {
        "name": "Market Inefficiency Index (Lib3)",
        "category": "complexity",
        "description": "Autocorrelation + variance ratio + entropy → exploitability score",
        "run": lambda df: df_to_dict(pd.DataFrame({"mii": market_inefficiency_index(df["close"].values, df["volume"].values)}, index=df.index))
    },
    "manifold_embedding": {
        "name": "Price Manifold Embedding (Takens)",
        "category": "complexity",
        "description": "NN distance & recurrence rate dari phase space reconstruction",
        "run": lambda df: df_to_dict(price_manifold_embedding(df))
    },
    "persistence_homology": {
        "name": "Normalized Rolling Deviation",
        "category": "complexity",
        "description": "Normalized volatility-adjusted range (replaces pseudo-scientific Homology claims)",
        "run": lambda df: df_to_dict(normalized_rolling_deviation(df))
    },

    # ── 7. SPECTRAL & CYCLE ──
    "spectral_cycle": {
        "name": "Spectral Cycle (Detrended FFT)",
        "category": "spectral",
        "description": "Dominant spectral power index using detrended fluctuations (robust cycle detection)",
        "run": lambda df: df_to_dict(spectral_cycle_analysis(df))
    },
    "wavelet_decomp": {
        "name": "Wavelet Trend Decomposition",
        "category": "spectral",
        "description": "Memisahkan komponen tren, siklus, dan noise via CWT",
        "run": lambda df: df_to_dict(wavelet_trend_decomposition(df))
    },
    "dominant_cycle": {
        "name": "Dominant Cycle Detector (Lib3)",
        "category": "spectral",
        "description": "Rolling FFT — period, power, phase dari siklus dominan",
        "run": lambda df: df_to_dict(pd.DataFrame(dominant_cycle_detector(df["close"].values), index=df.index))
    },
    "spectral_band": {
        "name": "Spectral Band Filter (Lib3)",
        "category": "spectral",
        "description": "FFT bandpass filter — isolasi komponen siklus tertentu",
        "run": lambda df: df_to_dict(pd.DataFrame(spectral_band_filter(df["close"].values), index=df.index))
    },
    "inst_phase": {
        "name": "Instantaneous Phase (Lib3)",
        "category": "spectral",
        "description": "Hilbert Transform — phase, velocity, DC period",
        "run": lambda df: df_to_dict(pd.DataFrame(instantaneous_phase_indicator(df["close"].values), index=df.index))
    },

    # ── 8. VOLATILITY & RISK ──
    "yang_zhang_vol": {
        "name": "Yang-Zhang Volatility (Lib3)",
        "category": "risk",
        "description": "Vol estimator terbaik untuk assets dengan overnight gaps",
        "run": lambda df: safe_call(yang_zhang_volatility, df["open"].values, df["high"].values, df["low"].values, df["close"].values)
    },
    "bollinger_squeeze": {
        "name": "Bollinger Squeeze Intensity (Lib3)",
        "category": "risk",
        "description": "BB inside Keltner = coiled spring (squeeze ON)",
        "run": lambda df: safe_call(bollinger_squeeze_intensity, df["close"].values)
    },
    "tail_risk": {
        "name": "Tail Risk (Cornish-Fisher VaR)",
        "category": "risk",
        "description": "CVaR 95% dan 99% dengan skewness/kurtosis correction",
        "run": lambda df: df_to_dict(tail_risk_indicator(df))
    },
    "price_anomalies": {
        "name": "Price Anomalies (Isolation Forest)",
        "category": "risk",
        "description": "Deteksi flash crash, spike, unusual behavior",
        "run": lambda df: df_to_dict(detect_price_anomalies(df))
    },
    "position_sizer": {
        "name": "Dynamic Position Sizer",
        "category": "risk",
        "description": "Ukuran posisi adaptif berdasarkan ATR z-score",
        "run": lambda df: df_to_dict(dynamic_position_sizer(df))
    },

    # ── 9. SMART MONEY CONCEPTS ──
    "order_blocks": {
        "name": "Order Blocks Detection",
        "category": "smart_money",
        "description": "Bullish & bearish institutional order blocks",
        "run": lambda df: df_to_dict(detect_order_blocks(df))
    },
    "fair_value_gaps": {
        "name": "Fair Value Gaps (FVG)",
        "category": "smart_money",
        "description": "Imbalance gaps antara candle 1 dan 3",
        "run": lambda df: df_to_dict(detect_fair_value_gaps(df))
    },
    "liquidity_sweeps": {
        "name": "Liquidity Sweeps",
        "category": "smart_money",
        "description": "Deteksi stop hunting / liquidity grab",
        "run": lambda df: df_to_dict(detect_liquidity_sweeps(df))
    },
    "smc_concepts": {
        "name": "Smart Money Concepts (BOS/CHoCH)",
        "category": "smart_money",
        "description": "Break of Structure & Change of Character",
        "run": lambda df: df_to_dict(smart_money_concepts(df))
    },

    # ── 10. OSCILLATORS & DIVERGENCE ──
    "rvi_enhanced": {
        "name": "Relative Vigor Index Enhanced (Lib3)",
        "category": "oscillator",
        "description": "RVI dengan divergence layer",
        "run": lambda df: df_to_dict(pd.DataFrame(relative_vigor_index_enhanced(df["open"].values, df["high"].values, df["low"].values, df["close"].values), index=df.index))
    },
    "chande_kroll": {
        "name": "Chande Kroll Stop (Lib3)",
        "category": "oscillator",
        "description": "Trailing stop + trend filter system",
        "run": lambda df: df_to_dict(pd.DataFrame(chande_kroll_stop(df["high"].values, df["low"].values, df["close"].values), index=df.index))
    },
    "dmi_quality": {
        "name": "DMI Crossover Quality (Lib3)",
        "category": "oscillator",
        "description": "Skor kualitas crossover +DI/-DI berdasarkan ADX",
        "run": lambda df: df_to_dict(pd.DataFrame(dmi_crossover_quality(df["high"].values, df["low"].values, df["close"].values), index=df.index))
    },
    "multi_divergence": {
        "name": "Multi-Indicator Divergence",
        "category": "oscillator",
        "description": "Divergensi antara 11 indikator vs price",
        "run": lambda df: df_to_dict(multi_indicator_divergence(df))
    },
    "dynamic_sr": {
        "name": "Dynamic Support/Resistance (Z-Score)",
        "category": "oscillator",
        "description": "S/R via DBSCAN clustering pada local extrema",
        "run": lambda df: df_to_dict(zscore_dynamic_support_resistance(df))
    },

    # ── 11. COMPOSITE SCORING (LIB2) ──
    "lib2_pipeline": {
        "name": "Deep OHLCV Pipeline (Full Frame)",
        "category": "scoring",
        "description": "Core indicators + patterns + statistics + regime + divergence + scoring",
        "run": lambda df: df_to_dict(build_deep_technical_frame(df).tail(1).reset_index(drop=True).T)
    },
    "lib2_signals": {
        "name": "Signal Events Scanner (Lib2)",
        "category": "scoring",
        "description": "Daftar semua long/short signal yang terdeteksi",
        "run": lambda df: df_to_dict(scan_signal_events(build_deep_technical_frame(df)))
    },

    # ── 12. MASTER SIGNAL ──
    "master_signal": {
        "name": "Master Signal Score (10 Subsystems)",
        "category": "scoring",
        "description": "Menggabungkan momentum, trend, volume, volatility, candlestick, entropy, dll",
        "run": lambda df: df_to_dict(master_signal_score(df["open"].values, df["high"].values, df["low"].values, df["close"].values, df["volume"].values))
    },
    "regime_signal": {
        "name": "Regime-Adaptive Signal",
        "category": "scoring",
        "description": "Signal berubah strategi: trend-following / mean-reversion / breakout",
        "run": lambda df: df_to_dict(regime_adaptive_signal(df))
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/api/init", methods=["POST"])
def api_init():
    """
    Inisialisasi sesi. Menerima data OHLCV + metadata, simpan ke memori.
    
    Body (JSON):
    {
        "entity_code": "AAPL",
        "start_date": "2023-01-01",     (opsional)
        "end_date": "2024-01-01",       (opsional)
        "ohlcv": [                       (opsional — jika tidak ada, pakai yfinance)
            {"date": "2023-01-01", "open": 130, "high": 132, "low": 129, "close": 131, "volume": 1000000},
            ...
        ]
    }
    """
    try:
        body = request.get_json(force=True)
        entity = body.get("entity_code", "AAPL")
        start = body.get("start_date")
        end = body.get("end_date")
        ohlcv_data = body.get("ohlcv")

        # Jika ada OHLCV manual, gunakan itu
        if ohlcv_data and len(ohlcv_data) > 0:
            df = pd.DataFrame(ohlcv_data)
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
            df.columns = [c.lower() for c in df.columns]
            required = ["open", "high", "low", "close", "volume"]
            for c in required:
                if c not in df.columns:
                    return jsonify({"status": "error", "error": f"Kolom '{c}' tidak ditemukan"}), 400
            df = df[required].astype(float).dropna()
        else:
            # Download dari YFinance
            import yfinance as yf
            period = body.get("period", "1y") # Ambil period dari body (1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, max)
            
            # Mapping jika frontend kirim format lain
            period_map = {
                "1M": "1mo", "3M": "3mo", "6M": "6mo",
                "1Y": "1y", "3Y": "2y", "5Y": "5y", "10Y": "10y"
            }
            if period in period_map:
                period = period_map[period]

            if start and end:
                period = None  # akan pakai start/end
            
            print(f"FETCHING DATA: {entity} | Period: {period}")
            raw = yf.download(entity, start=start, end=end, period=period, progress=False, auto_adjust=True)
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.columns = ["open", "high", "low", "close", "volume"]
            df = df.dropna().astype(float)

        if len(df) < 100:
            return jsonify({"status": "error", "error": f"Data terlalu pendek: {len(df)} baris. Minimal 100."}), 400

        # Validasi
        df = validate_ohlcv(df)

        # Buat session ID
        session_id = str(uuid.uuid4())[:8]
        SESSIONS[session_id] = {
            "entity_code": entity,
            "df": df,
            "results": {},
            "timestamps": {},
            "created_at": datetime.now().isoformat(),
            "files": []
        }

        return jsonify({
            "status": "success",
            "session_id": session_id,
            "entity_code": entity,
            "bars": len(df),
            "start": str(df.index[0].date()),
            "end": str(df.index[-1].date()),
            "available_functions": list(FUNCTION_REGISTRY.keys()),
            "available_functions_details": [
                {"id": k, "name": v["name"], "category": v.get("category", "misc"), "description": v["description"]}
                for k, v in FUNCTION_REGISTRY.items()
            ]
        })

    except Exception as e:
        return jsonify({"status": "error", "error": str(e), "traceback": traceback.format_exc()}), 500


@app.route("/api/status", methods=["GET"])
def api_status():
    """Cek status sesi & daftar fungsi yang sudah dijalankan."""
    sid = request.args.get("session_id")
    if not sid or sid not in SESSIONS:
        return jsonify({"status": "error", "error": "Sesi tidak ditemukan. Panggil /api/init terlebih dahulu."}), 404

    sess = SESSIONS[sid]
    categories = {}
    for fid, finfo in FUNCTION_REGISTRY.items():
        cat = finfo["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append({
            "id": fid,
            "name": finfo["name"],
            "description": finfo["description"],
            "computed": fid in sess["results"],
            "elapsed": sess["timestamps"].get(fid, None)
        })

    return jsonify({
        "status": "success",
        "session_id": sid,
        "entity_code": sess["entity_code"],
        "bars": len(sess["df"]),
        "total_functions": len(FUNCTION_REGISTRY),
        "computed_count": len(sess["results"]),
        "progress_pct": round(len(sess["results"]) / len(FUNCTION_REGISTRY) * 100, 1),
        "categories": categories
    })


@app.route("/api/data/ohlcv", methods=["GET"])
def api_ohlcv_data():
    """Mengambil data OHLCV mentah untuk tabel di frontend."""
    sid = request.args.get("session_id")
    if not sid or sid not in SESSIONS:
        return jsonify({"status": "error", "error": "Sesi tidak ditemukan"}), 404

    df = SESSIONS[sid]["df"]
    # Ambil 100 data terakhir saja untuk performa tabel
    tail_df = df.tail(100).copy()
    tail_df["date"] = tail_df.index.strftime("%Y-%m-%d %H:%M")
    
    return jsonify(recursive_clean({
        "status": "success",
        "data": tail_df.to_dict(orient="records")
    }))


@app.route("/api/run/<func_id>", methods=["GET"])
def api_run_function(func_id):
    """
    Menjalankan SATU fungsi analisa spesifik.
    Data OHLCV diambil dari sesi yang sudah di-init.
    Hasil disimpan ke sesi dan dikembalikan sebagai JSON.
    """
    sid = request.args.get("session_id")
    if not sid or sid not in SESSIONS:
        return jsonify({"status": "error", "error": "Sesi tidak ditemukan"}), 404

    if func_id not in FUNCTION_REGISTRY:
        return jsonify({"status": "error", "error": f"Fungsi '{func_id}' tidak terdaftar", "available": list(FUNCTION_REGISTRY.keys())}), 404

    sess = SESSIONS[sid]
    df = sess["df"]

    # Jalankan fungsi
    result = safe_call(FUNCTION_REGISTRY[func_id]["run"], df)

    # Simpan ke sesi
    sess["results"][func_id] = result
    sess["timestamps"][func_id] = result.get("elapsed_sec", 0)

    return jsonify(recursive_clean({
        "status": result["status"],
        "function_id": func_id,
        "function_name": FUNCTION_REGISTRY[func_id]["name"],
        "elapsed_sec": result.get("elapsed_sec", 0),
        "data": result.get("data"),
        "error": result.get("error"),
        "progress": round(len(sess["results"]) / len(FUNCTION_REGISTRY) * 100, 1)
    }))


@app.route("/api/dashboard/<dashboard_id>", methods=["POST"])
def api_dashboard(dashboard_id):
    """
    Generate SATU dashboard spesifik berdasarkan hasil yang sudah dikomputasi.
    
    Dashboard ID:
    - "1" : Price & Core Indicators
    - "2" : Momentum, Trend & Master Signals
    - "3" : Volume, Order Flow & Patterns
    - "4" : Complexity, Cycle, Risk & Summary Tables
    """
    sid = request.args.get("session_id") or request.json.get("session_id") if request.is_json else request.args.get("session_id")
    if not sid or sid not in SESSIONS:
        return jsonify({"status": "error", "error": "Sesi tidak ditemukan"}), 404

    sess = SESSIONS[sid]
    df = sess["df"]
    R = sess["results"]

    # Extract actual data from safe_call wrappers
    clean_R = {}
    for k, v in R.items():
        if isinstance(v, dict) and v.get("status") == "success":
            clean_R[k] = v.get("data")
        else:
            clean_R[k] = v

    # Reconstruct DataFrames dari dict results
    try:
        if "core" in clean_R and isinstance(clean_R["core"], list):
            clean_R["core"] = pd.DataFrame(clean_R["core"]).set_index("index") if "index" in clean_R["core"][0] else pd.DataFrame(clean_R["core"])
        # Reconstruct all list-of-dict results back to DataFrames
        for k in list(clean_R.keys()):
            if isinstance(clean_R[k], list) and len(clean_R[k]) > 0 and isinstance(clean_R[k][0], dict):
                try:
                    rdf = pd.DataFrame(clean_R[k])
                    if "index" in rdf.columns:
                        rdf = rdf.set_index("index")
                    clean_R[k] = rdf
                except:
                    pass
    except Exception as e:
        return jsonify({"status": "error", "error": f"Reconstruct error: {e}"}), 500

    # Import viz functions
    from asetpediadeepta.deep_analysis_viz import (
        build_dashboard_1, build_dashboard_2, build_dashboard_3, build_dashboard_4
    )

    ticker = sess["entity_code"]
    out_base = os.path.join(OUTPUT_DIR, f"{sid}_{ticker.replace('.','_').replace('-','_')}")
    dpi = int(request.args.get("dpi", 120))

    try:
        if dashboard_id == "1":
            path = build_dashboard_1(df, clean_R, ticker, out_base + ".png", dpi)
        elif dashboard_id == "2":
            path = build_dashboard_2(df, clean_R, ticker, out_base + ".png", dpi)
        elif dashboard_id == "3":
            path = build_dashboard_3(df, clean_R, ticker, out_base + ".png", dpi)
        elif dashboard_id == "4":
            path, _ = build_dashboard_4(df, clean_R, ticker, out_base + ".png", dpi)
        else:
            return jsonify({"status": "error", "error": f"Dashboard ID tidak valid. Pilih: 1, 2, 3, atau 4"}), 400

        sess["files"].append(path)
        return jsonify({
            "status": "success",
            "dashboard_id": dashboard_id,
            "file_path": path,
            "file_size_mb": round(os.path.getsize(path) / 1024 / 1024, 2)
        })

    except Exception as e:
        return jsonify({"status": "error", "error": str(e), "traceback": traceback.format_exc()}), 500


@app.route("/api/dashboard-all", methods=["POST"])
def api_dashboard_all():
    """Generate ke-4 dashboard sekaligus + file CSV."""
    sid = request.args.get("session_id") or (request.json.get("session_id") if request.is_json else None)
    if not sid or sid not in SESSIONS:
        return jsonify({"status": "error", "error": "Sesi tidak ditemukan"}), 404

    sess = SESSIONS[sid]
    df = sess["df"]
    R = sess["results"]

    # Clean results
    clean_R = {}
    for k, v in R.items():
        if isinstance(v, dict) and v.get("status") == "success":
            clean_R[k] = v.get("data")
        else:
            clean_R[k] = v

    try:
        for k in list(clean_R.keys()):
            if isinstance(clean_R[k], list) and len(clean_R[k]) > 0 and isinstance(clean_R[k][0], dict):
                try:
                    rdf = pd.DataFrame(clean_R[k])
                    if "index" in rdf.columns:
                        rdf = rdf.set_index("index")
                    clean_R[k] = rdf
                except:
                    pass
    except Exception as e:
        pass

    from asetpediadeepta.deep_analysis_viz import build_dashboard_1, build_dashboard_2, build_dashboard_3, build_dashboard_4
    ticker = sess["entity_code"]
    out_base = os.path.join(OUTPUT_DIR, f"{sid}_{ticker.replace('.','_').replace('-','_')}")
    dpi = int(request.args.get("dpi", 120))

    files = []
    try:
        for did in ["1", "2", "3", "4"]:
            if did == "1":
                p = build_dashboard_1(df, clean_R, ticker, out_base + ".png", dpi)
            elif did == "2":
                p = build_dashboard_2(df, clean_R, ticker, out_base + ".png", dpi)
            elif did == "3":
                p = build_dashboard_3(df, clean_R, ticker, out_base + ".png", dpi)
            elif did == "4":
                p, _ = build_dashboard_4(df, clean_R, ticker, out_base + ".png", dpi)
            files.append({"dashboard": did, "path": p, "size_mb": round(os.path.getsize(p)/1024/1024, 2)})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500

    # Generate CSV
    try:
        csv_path = out_base + "_summary.csv"
        # Collect last values from all results
        row = {"entity": ticker, "date": str(df.index[-1].date()), "close": float(df["close"].iloc[-1])}
        for k, v in clean_R.items():
            if isinstance(v, pd.DataFrame):
                for col in v.columns:
                    val = v[col].iloc[-1]
                    if isinstance(val, (int, float, np.floating)):
                        row[f"{k}_{col}"] = float(val)
            elif isinstance(v, (list, np.ndarray)) and len(v) > 0:
                row[f"{k}_last"] = float(v[-1]) if not np.isnan(v[-1]) else None
            elif isinstance(v, dict):
                for dk, dv in v.items():
                    if isinstance(dv, (list, np.ndarray)) and len(dv) > 0:
                        row[f"{k}_{dk}"] = float(dv[-1]) if not np.isnan(dv[-1]) else None
                    elif isinstance(dv, (int, float, np.floating)):
                        row[f"{k}_{dk}"] = float(dv)

        pd.DataFrame([row]).to_csv(csv_path, index=False)
        files.append({"dashboard": "csv", "path": csv_path, "size_mb": round(os.path.getsize(csv_path)/1024/1024, 2)})
    except Exception as e:
        pass

    sess["files"] = [f["path"] for f in files]
    return jsonify({"status": "success", "files": files})


@app.route("/api/summary", methods=["GET"])
def api_summary():
    """Ambil ringkasan teks hasil analisa."""
    sid = request.args.get("session_id")
    if not sid or sid not in SESSIONS:
        return jsonify({"status": "error", "error": "Sesi tidak ditemukan"}), 404

    sess = SESSIONS[sid]
    df = sess["df"]
    R = sess["results"]
    ticker = sess["entity_code"]

    lines = [f"=== {ticker} ANALYSIS SUMMARY ===",
             f"Period: {df.index[0].date()} → {df.index[-1].date()} ({len(df)} bars)",
             f"Close: {df['close'].iloc[-1]:.2f} | Return: {(df['close'].iloc[-1]/df['close'].iloc[0]-1)*100:.2f}%",
             f"Functions computed: {len(R)}/{len(FUNCTION_REGISTRY)}", ""]

    for fid, result in R.items():
        fname = FUNCTION_REGISTRY.get(fid, {}).get("name", fid)
        if isinstance(result, dict):
            if result.get("status") == "success":
                lines.append(f"  [✓] {fname} ({result.get('elapsed_sec',0):.2f}s)")
            else:
                lines.append(f"  [✗] {fname}: {result.get('error','?')[:80]}")
        else:
            lines.append(f"  [?] {fname}")

    return jsonify({"status": "success", "summary": "\n".join(lines)})


@app.route("/api/csv", methods=["GET"])
def api_csv():
    """Download file CSV hasil analisa."""
    sid = request.args.get("session_id")
    if not sid or sid not in SESSIONS:
        return jsonify({"status": "error", "error": "Sesi tidak ditemukan"}), 404

    csv_path = os.path.join(OUTPUT_DIR, f"{sid}_summary.csv")
    if not os.path.exists(csv_path):
        # Generate if not exists
        import requests as req
        req.post(f"{os.getenv('ANALYZER_API_URL', 'http://localhost:5000')}/api/dashboard-all?session_id={sid}")

    if os.path.exists(csv_path):
        return send_file(csv_path, as_attachment=True, mimetype="text/csv")
    return jsonify({"status": "error", "error": "CSV belum tersedia"}), 404


@app.route("/api/image/<filename>", methods=["GET"])
def api_image(filename):
    """Download file gambar dashboard."""
    filepath = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(filepath):
        return send_file(filepath, mimetype="image/png")
    return jsonify({"status": "error", "error": "File tidak ditemukan"}), 404


@app.route("/api/list-sessions", methods=["GET"])
def api_list_sessions():
    """Daftar semua sesi aktif."""
    result = []
    for sid, sess in SESSIONS.items():
        result.append({
            "session_id": sid,
            "entity": sess["entity_code"],
            "bars": len(sess["df"]),
            "computed": len(sess["results"]),
            "created": sess["created_at"]
        })
    return jsonify({"status": "success", "sessions": result})


@app.route("/api/cleanup/<session_id>", methods=["DELETE"])
def api_cleanup(session_id):
    """Hapus sesi dan file terkait."""
    if session_id in SESSIONS:
        del SESSIONS[session_id]
    # Hapus file
    # Clear old results if any
    for f in os.listdir(OUTPUT_DIR):
        if f.startswith(session_id):
            os.remove(os.path.join(OUTPUT_DIR, f))
    return jsonify({"status": "success", "message": f"Sesi {session_id} dibersihkan"})

# ═══════════════════════════════════════════════════════════════════
# ROUTES: ECHARTS JSON API (SEQUENTIAL/PARTIAL)
# ═══════════════════════════════════════════════════════════════════

@app.route("/api/charts/single/<func_id>", methods=["GET"])
def api_chart_single(func_id):
    """
    Generate SATU chart spesifik berdasarkan func_id.
    """
    sid = request.args.get("session_id")
    if not sid or sid not in SESSIONS:
        return jsonify({"status": "error", "error": "Sesi tidak ditemukan"}), 404

    sess = SESSIONS[sid]
    df = sess["df"]
    R_raw = sess["results"]

    # Re-map results to internal keys used by extract_all_charts
    # Viz library expects specific short keys like 'core', 'sr', 'vprof', etc.
    viz_mapping = {
        "core_indicators": "core",
        "dynamic_sr": "sr",
        "volume_profile": "vprof",
        "bollinger_squeeze": "bsi",
        "master_signal": "mss",
        "hurst_exponent": "regime1",
        "fractal_dimension": "fracdim",
        "price_entropy": "pent",
        "perm_entropy": "pentperm",
        "kolmogorov": "kolm",
        "market_inefficiency": "mii",
        "mutual_info": "mi",
        "head_shoulders": "hs",
        "double_top_bottom": "dbl",
        "wedge_patterns": "wedge",
        "elliott_wave": "elliott",
        "smc_concepts": "smc",
        "order_blocks": "order_blocks",
        "fair_value_gaps": "fair_value_gaps",
        "liquidity_sweeps": "liquidity_sweeps",
        "lib2_signals": "lib2_signals",
        "lib2_pipeline": "lib2",
        "volume_delta": "vdelta",
        "volume_divergence": "vdiv",
        "adaptive_macd": "amacd",
        "poly_momentum": "poly",
        "wavelet_decomp": "wavelet",
        "manifold_embedding": "manifold",
        "persistence_homology": "ph",
        "vwap_bands": "vwap1",
        "spectral_cycle": "spectral",
        "regime_signal": "regime_signal",
        "dominant_cycle": "dominant_cycle",
        "spectral_band": "spectral_band",
        "yang_zhang_vol": "yz_vol",
        "bollinger_squeeze": "bsi",
        "tail_risk": "tail_risk",
        "price_anomalies": "anomalies",
        "position_sizer": "sizer",
        "rvi_enhanced": "rvi",
        "chande_kroll": "chande",
        "dmi_quality": "dmi_q",
        "multi_divergence": "midiv",
        "inst_phase": "inst_phase",
    }
    
    R = {}
    for k, v in list(R_raw.items()):
        internal_key = viz_mapping.get(k, k)
        if isinstance(v, dict) and v.get("status") == "success":
            data = v.get("data")
            # Flatten nested safe_call results if necessary
            if isinstance(data, dict) and "data" in data and data.get("status") == "success":
                data = data["data"]

            if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
                try:
                    rdf = pd.DataFrame(data)
                    if "index" in rdf.columns:
                        rdf["index"] = pd.to_datetime(rdf["index"])
                        rdf = rdf.set_index("index")
                    R[internal_key] = rdf
                except: R[internal_key] = data
            else: R[internal_key] = data
        else: R[internal_key] = v

    from asetpediadeepta.deep_analysis_viz import extract_all_charts

    try:
        # Generate all available visualization objects from the results
        all_charts = extract_all_charts(df, R)
        
        # Mappings func_id to chart titles defined in deep_analysis_viz.py
        title_mapping = {
            "core_indicators": ["Price Action", "Volume + OBV", "MACD", "RSI Multi", "ADX + DI", "VWAP Bands"],
            "volume_profile": ["Volume Profile"],
            "bollinger_squeeze": ["Bollinger Squeeze"],
            "master_signal": ["Master Signal"],
            "hurst_exponent": ["Hurst + Fractal"],
            "fractal_dimension": ["Hurst + Fractal"],
            "head_shoulders": ["Elliott & Chart Patterns"],
            "double_top_bottom": ["Elliott & Chart Patterns"],
            "wedge_patterns": ["Elliott & Chart Patterns"],
            "elliott_wave": ["Elliott & Chart Patterns"],
            "smc_concepts": ["Elliott & Chart Patterns"],
            "order_blocks": ["Order Blocks Detection"],
            "fair_value_gaps": ["Fair Value Gaps Analysis"],
            "liquidity_sweeps": ["Liquidity Sweeps Analysis"],
            "smc_concepts": ["SMC Structural Analysis (BOS/CHoCH)"],
            "lib2_signals": ["Signal Events Scanner (Lib2)"],
            "lib2_pipeline": ["Composite Scores (Lib2)"],
            "regime_signal": ["Regime-Adaptive Signal Analysis"],
            "dominant_cycle": ["Dominant Cycle Analysis (Lib3)"],
            "spectral_band": ["Spectral Band Filter Analysis (Lib3)"],
            "inst_phase": ["Instantaneous Phase Hilbert Analysis (Lib3)"],
            "price_entropy": ["Complexity Metrics", "Price Entropy Score (Lib3)"],
            "perm_entropy": ["Complexity Metrics", "Permutation Entropy (Lib3)"],
            "kolmogorov": ["Kolmogorov Complexity (LZ77)"],
            "kolmogorov": ["Kolmogorov Complexity (LZ77)"],
            "market_inefficiency": ["Complexity Metrics", "Market Inefficiency Index (Lib3)"],
            "mutual_info": ["Complexity Metrics", "Mutual Information (Price ↔ Volume)"],
            "manifold_embedding": ["Price Manifold Embedding (Takens)"],
            "persistence_homology": ["Complexity Metrics", "Persistence Homology Approx"],
            # Raw extractors mapping
            "volume_delta": ["Volume Delta Imbalance"],
            "volume_divergence": ["Volume-Price Divergence"],
            "adaptive_macd": ["Adaptive MACD"],
            "poly_momentum": ["Polynomial Momentum"],
            "wavelet_decomp": ["Wavelet Decomposition"],
            "spectral_cycle": ["Spectral Cycle"],
            "yang_zhang_vol": ["Yang-Zhang Volatility (Lib3)"],
            "bollinger_squeeze": ["Bollinger Squeeze Intensity (Lib3)"],
            "tail_risk": ["Tail Risk (Cornish-Fisher Var)"],
            "price_anomalies": ["Price Anomalies (Isolation Forest)"],
            "position_sizer": ["Dynamic Position Sizer"],
            "rvi_enhanced": ["Relative Vigor Index Enhanced (Lib3)"],
            "chande_kroll": ["Chande Kroll Stop (Lib3)"],
            "dmi_quality": ["DMI Crossover Quality (Lib3)"],
            "multi_divergence": ["Multi-Indicator Divergence"],
            "dynamic_sr": ["Dynamic Support/Resistance (Z-Score)"],
        }
        
        target_titles = title_mapping.get(func_id, [])
        filtered = [c for c in all_charts if any(t in c.get("title", "") for t in target_titles)]
        
        # Backup: if not in mapping, try to match by func_id name
        if not filtered:
             name = FUNCTION_REGISTRY.get(func_id, {}).get("name", "")
             filtered = [c for c in all_charts if c.get("title") == name]

        return jsonify(recursive_clean({
            "status": "success",
            "function_id": func_id,
            "charts": filtered
        }))
    except Exception as e:
        return jsonify(recursive_clean({"status": "error", "error": str(e), "traceback": traceback.format_exc()})), 500


@app.route("/api/charts/summary-gauges", methods=["GET"])
def api_charts_gauges():
    """
    Generate data untuk Gauge Charts — menampilkan nilai TERAKHIR dari
    indikator-indikator utama.
    """
    sid = request.args.get("session_id")
    if not sid or sid not in SESSIONS:
        return jsonify({"status": "error", "error": "Sesi tidak ditemukan"}), 404

    # Import fmt_gauge dari viz library
    from asetpediadeepta.deep_analysis_viz import fmt_gauge

    sess = SESSIONS[sid]
    df = sess["df"]
    R_raw = sess["results"]
    
    # Extract data dari safe_call wrappers
    R = {}
    for k, v in R_raw.items():
        if isinstance(v, dict) and v.get("status") == "success":
            R[k] = v.get("data")
        else: R[k] = v

    def get_last(obj, col=None):
        if obj is None: return None
        try:
            # Jika DataFrame (hasil TA-Lib Core)
            if isinstance(obj, pd.DataFrame):
                if col and col in obj.columns:
                    v = obj[col].iloc[-1]
                else: 
                    v = obj.iloc[-1, 0] # Ambil kolom pertama jika tidak spesifik
                return float(v) if not pd.isna(v) else None
            
            # Jika Series
            if isinstance(obj, pd.Series):
                v = obj.iloc[-1]
                return float(v) if not pd.isna(v) else None
                
            # Jika Numpy Array (hasil Lib3)
            if isinstance(obj, (np.ndarray, list)) and len(obj) > 0:
                v = obj[-1]
                return float(v) if not np.isnan(v) else None
                
            # Jika Scalar
            if isinstance(obj, (int, float)):
                return float(obj)
        except:
            return None
        return None

    gauges = []
    last_close = float(df["close"].iloc[-1])
    ret_pct = (last_close / float(df["close"].iloc[0]) - 1) * 100

    # 1. RSI (14)
    core = R.get("core")
    rsi = get_last(core, "rsi_14")
    if rsi is not None:
        gauges.append(fmt_gauge("RSI (14)", rsi, 0, 100))

    # 2. ADX (Trend Strength)
    adx = get_last(core, "adx")
    if adx is not None:
        gauges.append(fmt_gauge("ADX Strength", adx, 0, 100))

    # 3. BB %B (Position relative to bands)
    bb_pb = get_last(core, "bbands_upper") # Kita hitung manual jika %B tidak ada
    if bb_pb is not None:
        upper = get_last(core, "bbands_upper")
        lower = get_last(core, "bbands_lower")
        if upper and lower and (upper - lower) != 0:
            pb_val = (last_close - lower) / (upper - lower)
            gauges.append(fmt_gauge("BB %B Position", pb_val, 0, 1))

    # 4. Hurst Exponent (Trendiness)
    regime1 = R.get("regime1")
    hurst = get_last(regime1, "hurst_exponent")
    if hurst is not None:
        gauges.append(fmt_gauge("Hurst Exponent", hurst, 0, 1))

    # 5. Master Signal Score
    mss = R.get("mss")
    mss_val = get_last(mss, "mss_total")
    if mss_val is not None:
        gauges.append(fmt_gauge("Master Signal", mss_val, -10, 10))

    # 6. Total Return (Gauge Utama)
    ret_gauge = fmt_gauge("Total Return %", ret_pct, -50, 50)

    return jsonify(recursive_clean({
        "status": "success",
        "session_id": sid,
        "entity_code": sess["entity_code"],
        "price": {
            "last": last_close,
            "change_pct": ret_pct
        },
        "gauges": [ret_gauge] + gauges
    }))


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import threading as _th
    import os
    _cleanup_t = _th.Thread(target=_session_cleanup_worker, daemon=True)
    _cleanup_t.start()
    app.run(host=os.getenv('API_HOST', '0.0.0.0'), port=5200, debug=True)