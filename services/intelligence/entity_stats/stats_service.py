"""
Entity Stats Blueprint — Multi-Method Statistical Testing Engine
Provides comprehensive statistical analysis with chart data for every test category.
Mounted at /api/entity/stats/ in entity_service.py
"""
import numpy as np
from flask import Blueprint, jsonify, request
from flask_cors import CORS
from datetime import datetime
import yfinance as yf

from .normality import compute_normality
from .stationarity import compute_stationarity
from .autocorrelation import compute_autocorrelation
from .distribution import compute_distribution
from .descriptive import compute_descriptive
from .variance import compute_variance
from .correlation import compute_correlation

stats_bp = Blueprint('entity_stats', __name__)
CORS(stats_bp)

def clean_data(obj):
    """Recursively convert numpy types to standard python types for JSON serialization."""
    if isinstance(obj, (float, int, np.floating, np.integer)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, dict):
        return {k: clean_data(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, np.ndarray)):
        return [clean_data(x) for x in obj]
    return obj

# Simple in-memory cache
_cache = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


def _get_cached(key):
    entry = _cache.get(key)
    if entry and (datetime.utcnow() - entry['ts']).total_seconds() < CACHE_TTL_SECONDS:
        return entry['data']
    return None


def _set_cached(key, data):
    _cache[key] = {'data': data, 'ts': datetime.utcnow()}


def _normalize_symbol(symbol):
    """Normalize Indonesian tickers for Yahoo Finance"""
    symbol = symbol.upper().strip()
    if symbol.endswith('.JK'):
        return symbol
    if not '.' in symbol:
        candidates = [
            f"{symbol}.JK", f"{symbol}.SI", f"{symbol}.SA",
            f"{symbol}.NS", f"{symbol}.T", f"{symbol}.HK",
        ]
        for c in candidates:
            try:
                t = yf.Ticker(c)
                info = t.info
                if info and info.get('symbol'):
                    return c
            except:
                continue
        return f"{symbol}.JK"
    return symbol


@stats_bp.route('/api/entity/stats/<symbol>')
def get_statistical_tests(symbol):
    """
    Comprehensive multi-method statistical testing.
    Returns 15+ tests across 6 categories with chart data for visualization.
    
    Query params:
        period: Yahoo Finance period (default: 6mo)
        categories: comma-separated filter (default: all)
            e.g. normality,stationarity,autocorrelation,distribution,descriptive,variance,correlation
    """
    period = request.args.get('period', '6mo')
    categories_filter = request.args.get('categories', '').strip()

    cache_key = f"stats_{symbol}_{period}"
    cached = _get_cached(cache_key)
    if cached:
        return jsonify(cached)

    try:
        normalized = _normalize_symbol(symbol)
        ticker = yf.Ticker(normalized)
        df = ticker.history(period=period)
    except Exception as e:
        return jsonify({"error": f"Failed to fetch data for {symbol}: {str(e)}"}), 502

    if df is None or df.empty or 'Close' not in df.columns:
        return jsonify({"error": f"No data available for {symbol} (period={period})"}), 404

    df.index = df.index.tz_localize(None)
    prices = df['Close'].values
    returns = np.diff(np.log(prices[prices > 0]))
    dates = [d.strftime('%Y-%m-%d') for d in df.index]

    if len(returns) < 10:
        return jsonify({"error": f"Insufficient data points ({len(returns)}). Need at least 10."}), 400

    n = len(returns)

    # Determine which categories to compute
    all_cats = {'normality', 'stationarity', 'autocorrelation', 'distribution', 'descriptive', 'variance', 'correlation'}
    if categories_filter:
        requested = set(c.strip() for c in categories_filter.split(',') if c.strip())
        cats_to_run = requested & all_cats
    else:
        cats_to_run = all_cats

    result = {
        "symbol": symbol,
        "period": period,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "data_points": n,
        "categories": {}
    }

    # --- NORMALITY ---
    if 'normality' in cats_to_run:
        norm = compute_normality(prices, returns, dates)
        result["categories"]["normality"] = {
            "label": "NORMALITY TESTS",
            "description": "Tests whether returns follow a Gaussian (normal) distribution",
            "icon": "📊",
            "tests": norm["stats"],
            "charts": norm["charts"],
            "summary": norm["summary"]
        }

    # --- STATIONARITY ---
    if 'stationarity' in cats_to_run:
        stat_result = compute_stationarity(prices, returns, dates)
        result["categories"]["stationarity"] = {
            "label": "STATIONARITY TESTS",
            "description": "Tests for unit roots and trend-stationarity in price series",
            "icon": "📈",
            "tests": stat_result["stats"],
            "charts": stat_result["charts"],
            "combined_verdict": stat_result.get("combined_verdict"),
            "combined_interpretation": stat_result.get("combined_interpretation"),
            "summary": stat_result["summary"]
        }

    # --- AUTOCORRELATION ---
    if 'autocorrelation' in cats_to_run:
        autocorr = compute_autocorrelation(prices, returns, dates)
        result["categories"]["autocorrelation"] = {
            "label": "AUTOCORRELATION TESTS",
            "description": "Tests for serial dependence and lag structure in returns",
            "icon": "🔄",
            "tests": autocorr["stats"],
            "charts": autocorr["charts"],
            "summary": autocorr["summary"]
        }

    # --- DISTRIBUTION ---
    if 'distribution' in cats_to_run:
        dist = compute_distribution(prices, returns, dates)
        result["categories"]["distribution"] = {
            "label": "DISTRIBUTION TESTS",
            "description": "Goodness-of-fit and distribution comparison across sample halves",
            "icon": "🎯",
            "tests": dist["stats"],
            "charts": dist["charts"],
            "summary": dist["summary"]
        }

    # --- DESCRIPTIVE ---
    if 'descriptive' in cats_to_run:
        desc = compute_descriptive(prices, returns, dates)
        result["categories"]["descriptive"] = {
            "label": "DESCRIPTIVE STATISTICS",
            "description": "Summary moments, shape characteristics, and variance ratio profile",
            "icon": "📋",
            "tests": desc["stats"],
            "charts": desc["charts"],
            "fat_tails": desc.get("fat_tails", False),
            "summary": desc["summary"]
        }

    # --- VARIANCE ---
    if 'variance' in cats_to_run:
        var_result = compute_variance(prices, returns, dates)
        result["categories"]["variance"] = {
            "label": "VARIANCE & HOMOSCEDASTICITY",
            "description": "Tests for equal variance across time — regime stability detection",
            "icon": "📉",
            "tests": var_result["stats"],
            "charts": var_result["charts"],
            "regime_stability": var_result.get("regime_stability"),
            "summary": var_result["summary"]
        }

    # --- CORRELATION ---
    if 'correlation' in cats_to_run:
        corr = compute_correlation(prices, returns, dates, df=df)
        result["categories"]["correlation"] = {
            "label": "FEATURE CORRELATION MATRIX",
            "description": "Cross-correlation of OHLCV components and derived features",
            "icon": "🔗",
            "tests": corr.get("cross_correlations", []),
            "charts": {
                "heatmap": corr.get("heatmap_data", {}),
                "correlation_bars": {
                    "type": "bar",
                    "title": "Feature Cross-Correlations",
                    "x_label": "Feature Pair",
                    "y_label": "Correlation",
                    "bars": [
                        {"x": c["pair"], "y": c["correlation"]}
                        for c in corr.get("cross_correlations", [])
                    ]
                }
            },
            "mermaid_diagram": corr.get("mermaid_diagram", ""),
            "summary": f"Top correlation: {corr.get('cross_correlations', [{}])[0].get('pair', 'N/A')} (r={corr.get('cross_correlations', [{}])[0].get('correlation', 0):+.4f})" if corr.get("cross_correlations") else "No cross-correlations computed"
        }

    # --- Build Aggregate Summary ---
    total_tests = sum(
        len(cat.get("tests", []))
        for cat in result["categories"].values()
    )
    significant_tests = sum(
        1 for cat in result["categories"].values()
        for t in cat.get("tests", [])
        if t.get("is_significant")
    )

    normality_rejected = result["categories"].get("normality", {}).get("tests", [{}])
    normality_rejected = any(t.get("is_significant") for t in normality_rejected)

    stationarity_verdict = result["categories"].get("stationarity", {}).get("combined_verdict", "UNKNOWN")

    autocorr_present = result["categories"].get("autocorrelation", {}).get("tests", [{}])
    autocorr_present = any(t.get("is_significant") for t in autocorr_present)

    fat_tails = result["categories"].get("descriptive", {}).get("fat_tails", False)

    regime_stable = result["categories"].get("variance", {}).get("regime_stability", "UNKNOWN")

    # Generate overall verdict
    parts = []
    if normality_rejected:
        parts.append("Non-normal distribution")
    else:
        parts.append("Normal-like distribution")
    if fat_tails:
        parts.append("fat tails detected")
    if autocorr_present:
        parts.append("significant autocorrelation present")
    if regime_stable == "REGIME_SHIFT_DETECTED":
        parts.append("variance regime change detected")
    parts.append(f"stationarity: {stationarity_verdict.lower()}")

    result["summary"] = {
        "total_tests": total_tests,
        "significant_tests": significant_tests,
        "normality_rejected": normality_rejected,
        "stationarity": stationarity_verdict,
        "autocorrelation_present": autocorr_present,
        "fat_tails": fat_tails,
        "regime_stability": regime_stable,
        "overall_verdict": ", ".join(parts)
    }

    cleaned_result = clean_data(result)
    _set_cached(cache_key, cleaned_result)
    return jsonify(cleaned_result)


@stats_bp.route('/api/entity/stats/<symbol>/categories')
def get_available_categories(symbol):
    """Returns list of available statistical categories"""
    return jsonify({
        "symbol": symbol,
        "categories": [
            {"id": "normality", "label": "Normality Tests", "tests": 4, "icon": "📊"},
            {"id": "stationarity", "label": "Stationarity Tests", "tests": 2, "icon": "📈"},
            {"id": "autocorrelation", "label": "Autocorrelation Tests", "tests": 3, "icon": "🔄"},
            {"id": "distribution", "label": "Distribution Tests", "tests": 2, "icon": "🎯"},
            {"id": "descriptive", "label": "Descriptive Statistics", "tests": 5, "icon": "📋"},
            {"id": "variance", "label": "Variance & Homoscedasticity", "tests": 2, "icon": "📉"},
            {"id": "correlation", "label": "Feature Correlation Matrix", "tests": "dynamic", "icon": "🔗"},
        ]
    })
