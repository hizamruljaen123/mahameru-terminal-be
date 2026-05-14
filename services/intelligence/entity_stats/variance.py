"""
Variance & Homoscedasticity Tests Module
Tests: Levene (median-based, robust), Bartlett (mean-based, sensitive to normality)
Charts: Rolling variance of returns, first-half vs second-half comparison
"""
import numpy as np
from scipy import stats


def compute_variance(prices, returns, dates):
    n = len(returns)
    tests = []
    chart_data = {}

    mid = n // 2
    returns_1 = returns[:mid]
    returns_2 = returns[mid:]
    var_1 = np.var(returns_1, ddof=1)
    var_2 = np.var(returns_2, ddof=1)

    # 1. Levene Test (robust, median-based)
    try:
        lev_stat, lev_p = stats.levene(returns_1, returns_2, center='median')
        lev_sig = lev_p < 0.05
        tests.append({
            "id": "levene",
            "name": "Levene Test (Half-Split)",
            "statistic": round(float(lev_stat), 6),
            "p_value": round(float(lev_p), 6),
            "group_1_variance": round(float(var_1), 8),
            "group_2_variance": round(float(var_2), 8),
            "variance_ratio": round(float(var_2 / var_1), 6) if var_1 > 0 else None,
            "is_significant": lev_sig,
            "verdict": "Unequal Variance (Heteroscedastic)" if lev_sig else "Equal Variance (Homoscedastic)",
            "interpretation": f"Significant variance difference between halves — volatility regime change detected (Levene p={lev_p:.4f})" if lev_sig else f"No significant variance difference — variance is stable across the sample period"
        })
    except Exception as e:
        tests.append({"id": "levene", "name": "Levene Test (Half-Split)", "error": str(e), "verdict": "COMPUTATION_FAILED"})

    # 2. Bartlett Test (mean-based, more sensitive to normality)
    try:
        bar_stat, bar_p = stats.bartlett(returns_1, returns_2)
        bar_sig = bar_p < 0.05
        tests.append({
            "id": "bartlett",
            "name": "Bartlett Test (Half-Split)",
            "statistic": round(float(bar_stat), 6),
            "p_value": round(float(bar_p), 6),
            "is_significant": bar_sig,
            "verdict": "Unequal Variance (Heteroscedastic)" if bar_sig else "Equal Variance (Homoscedastic)",
            "interpretation": f"Bartlett detects significant variance difference (p={bar_p:.4f})" if bar_sig else f"Bartlett confirms homoscedasticity — variance is stable (p={bar_p:.4f})"
        })
    except Exception as e:
        tests.append({"id": "bartlett", "name": "Bartlett Test (Half-Split)", "error": str(e), "verdict": "COMPUTATION_FAILED"})

    # --- Chart Data: Rolling Variance ---
    window = min(60, max(30, n // 3))
    rolling_var = []
    rolling_std = []
    rolling_dates = []

    for i in range(window, n):
        w_ret = returns[i - window:i]
        w_var = np.var(w_ret, ddof=1)
        rolling_var.append(round(float(w_var), 8))
        rolling_std.append(round(float(np.sqrt(w_var) * 100), 4))
        rolling_dates.append(dates[i] if dates else str(i))

    chart_data["rolling_variance"] = {
        "type": "line",
        "title": f"Rolling Variance of Returns (window={window})",
        "x_label": "Date",
        "y_label": "Variance",
        "series": [{"name": "Variance", "data": [
            {"x": d, "y": v} for d, v in zip(rolling_dates, rolling_var)
        ]}]
    }

    chart_data["rolling_std"] = {
        "type": "line",
        "title": f"Rolling Standard Deviation % (window={window})",
        "x_label": "Date",
        "y_label": "Std Dev (%)",
        "series": [{"name": "Std Dev %", "data": [
            {"x": d, "y": v} for d, v in zip(rolling_dates, rolling_std)
        ]}]
    }

    # --- Box plot data for two halves ---
    chart_data["variance_boxplot"] = {
        "type": "box",
        "title": "Variance Distribution: First Half vs Second Half",
        "series": [
            {"name": f"First Half (n={mid})", "variance": round(float(var_1), 8), "std_pct": round(float(np.sqrt(var_1) * 100), 4)},
            {"name": f"Second Half (n={n-mid})", "variance": round(float(var_2), 8), "std_pct": round(float(np.sqrt(var_2) * 100), 4)}
        ]
    }

    any_sig = any(t.get("is_significant") for t in tests)
    regime_stable = not any_sig

    return {
        "stats": tests,
        "charts": chart_data,
        "regime_stability": "STABLE" if regime_stable else "REGIME_SHIFT_DETECTED",
        "summary": "Homoscedastic — Variance is stable across periods" if regime_stable else "Heteroscedastic — Variance differs significantly between halves, suggesting regime change"
    }
