"""
Autocorrelation Tests Module
Tests: Ljung-Box (multiple lags), Durbin-Watson
Charts: ACF (Autocorrelation Function), PACF (Partial Autocorrelation Function)
"""
import numpy as np
from statsmodels.tsa.stattools import acf, pacf
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.stats.stattools import durbin_watson


def compute_autocorrelation(prices, returns, dates):
    n = len(returns)
    tests = []
    chart_data = {}

    # 1. Ljung-Box (test lags 1, 5, 10, 20)
    max_lag = min(20, n // 5)
    test_lags = [l for l in [1, 5, 10, 20] if l <= max_lag]

    lb_results = []
    try:
        for lag in test_lags:
            lb = acorr_ljungbox(returns, lags=[lag], return_df=True)
            stat_val = float(lb["lb_stat"].values[0])
            p_val = float(lb["lb_pvalue"].values[0])
            sig = p_val < 0.05
            lb_results.append({
                "id": f"ljung_box_{lag}",
                "name": f"Ljung-Box (lag={lag})",
                "statistic": round(stat_val, 6),
                "p_value": round(p_val, 6),
                "lags_tested": lag,
                "is_significant": sig,
                "verdict": "Autocorrelation Detected" if sig else "No Autocorrelation",
                "interpretation": f"Significant autocorrelation at lag {lag} — serial dependence present" if sig else f"No significant autocorrelation at lag {lag}"
            })
        tests.extend(lb_results)
    except Exception as e:
        tests.append({
            "id": "ljung_box",
            "name": "Ljung-Box",
            "error": str(e),
            "verdict": "COMPUTATION_FAILED"
        })

    # 2. Durbin-Watson
    try:
        dw_stat = durbin_watson(returns)
        if dw_stat < 1.5:
            dw_verdict = "Positive Autocorrelation"
            dw_interp = f"DW={dw_stat:.3f} < 1.5 — significant positive first-order autocorrelation"
        elif dw_stat > 2.5:
            dw_verdict = "Negative Autocorrelation"
            dw_interp = f"DW={dw_stat:.3f} > 2.5 — significant negative first-order autocorrelation"
        else:
            dw_verdict = "No 1st-Order Autocorrelation"
            dw_interp = f"DW≈{dw_stat:.3f} ≈ 2.0 — no first-order serial correlation in returns"

        tests.append({
            "id": "durbin_watson",
            "name": "Durbin-Watson",
            "statistic": round(float(dw_stat), 6),
            "p_value": None,
            "is_significant": dw_stat < 1.5 or dw_stat > 2.5,
            "verdict": dw_verdict,
            "interpretation": dw_interp
        })
    except Exception as e:
        tests.append({
            "id": "durbin_watson",
            "name": "Durbin-Watson",
            "error": str(e),
            "verdict": "COMPUTATION_FAILED"
        })

    # --- Chart Data: ACF ---
    acf_lags = min(40, n // 4)
    try:
        acf_values = acf(returns, nlags=acf_lags)
        # Confidence intervals: ±1.96 / sqrt(n)
        ci = 1.96 / np.sqrt(n)
        chart_data["acf"] = {
            "type": "bar",
            "title": "Autocorrelation Function (ACF)",
            "x_label": "Lag",
            "y_label": "Autocorrelation",
            "bars": [
                {"x": i, "y": round(float(v), 6)}
                for i, v in enumerate(acf_values)
            ],
            "confidence_band": round(float(ci), 6),
            "n_lags": acf_lags
        }
    except:
        chart_data["acf"] = {"error": "ACF computation failed"}

    # --- Chart Data: PACF ---
    try:
        pacf_values = pacf(returns, nlags=min(acf_lags, n // 2 - 1))
        chart_data["pacf"] = {
            "type": "bar",
            "title": "Partial Autocorrelation Function (PACF)",
            "x_label": "Lag",
            "y_label": "Partial Autocorrelation",
            "bars": [
                {"x": i, "y": round(float(v), 6)}
                for i, v in enumerate(pacf_values)
            ],
            "confidence_band": round(float(ci), 6),
            "n_lags": len(pacf_values) - 1
        }
    except:
        chart_data["pacf"] = {"error": "PACF computation failed"}

    # --- Lag correlation line chart ---
    lag_corr = []
    for i in range(1, min(21, n)):
        if i < n:
            corr = np.corrcoef(returns[:-i], returns[i:])[0, 1] if len(returns) > i + 1 else None
            lag_corr.append({"x": i, "y": round(float(corr), 6) if corr is not None and not np.isnan(corr) else None})

    chart_data["lag_correlation"] = {
        "type": "bar_line",
        "title": "Lag Autocorrelation Structure",
        "x_label": "Lag",
        "y_label": "Correlation",
        "bars": lag_corr,
        "confidence_band": round(float(ci), 6)
    }

    any_sig = any(t.get("is_significant") for t in tests)
    return {
        "stats": tests,
        "charts": chart_data,
        "summary": "AUTOCORRELATION DETECTED — Serial dependence present in returns" if any_sig else "NO AUTOCORRELATION — Returns appear independently distributed"
    }
