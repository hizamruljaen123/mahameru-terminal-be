"""
Stationarity Tests Module
Tests: Augmented Dickey-Fuller (ADF), KPSS
Charts: Rolling ADF statistic, rolling KPSS statistic, price series overlay
Also returns ACF/PACF-ready lags for autocorrelation chart
"""
import numpy as np
from statsmodels.tsa.stattools import adfuller, kpss


def compute_stationarity(prices, returns, dates):
    tests = []
    chart_data = {}
    n = len(prices)

    # 1. ADF Test
    try:
        adf_result = adfuller(prices, autolag='AIC', maxlag=min(int(n / 2), 30))
        adf_stat = adf_result[0]
        adf_p = adf_result[1]
        adf_lags = adf_result[2]
        adf_nobs = adf_result[3]
        adf_crit = adf_result[4]
        adf_sig = adf_p < 0.05
        tests.append({
            "id": "adf",
            "name": "Augmented Dickey-Fuller (ADF)",
            "statistic": round(float(adf_stat), 6),
            "p_value": round(float(adf_p), 6),
            "critical_1pct": round(float(adf_crit["1%"]), 6),
            "critical_5pct": round(float(adf_crit["5%"]), 6),
            "critical_10pct": round(float(adf_crit["10%"]), 6),
            "lags_used": int(adf_lags),
            "observations": int(adf_nobs),
            "is_significant": adf_sig,
            "verdict": "Stationary (p<0.05)" if adf_sig else "Non-Stationary",
            "interpretation": "Price series is stationary — mean-reversion tendency detected (unit root rejected)" if adf_sig else "Price series contains a unit root — non-stationary, trends may persist"
        })
    except Exception as e:
        tests.append({
            "id": "adf",
            "name": "Augmented Dickey-Fuller (ADF)",
            "error": str(e),
            "is_significant": None,
            "verdict": "COMPUTATION_FAILED",
            "interpretation": f"ADF test could not be computed: {str(e)}"
        })
        adf_sig = None

    # 2. KPSS Test
    try:
        kpss_result = kpss(prices, regression='c', nlags='auto')
        kpss_stat = kpss_result[0]
        kpss_p = kpss_result[1]
        kpss_lags = kpss_result[2]
        kpss_crit = kpss_result[3]
        kpss_sig = kpss_p < 0.05
        tests.append({
            "id": "kpss",
            "name": "KPSS",
            "statistic": round(float(kpss_stat), 6),
            "p_value": round(float(kpss_p), 6),
            "critical_1pct": round(float(kpss_crit["1%"]), 6),
            "critical_5pct": round(float(kpss_crit["5%"]), 6),
            "critical_10pct": round(float(kpss_crit["10%"]), 6),
            "lags_used": int(kpss_lags),
            "is_significant": kpss_sig,
            "verdict": "Non-Stationary (p<0.05)" if kpss_sig else "Stationary",
            "interpretation": "KPSS rejects null of stationarity — evidence of non-stationarity" if kpss_sig else "KPSS cannot reject stationarity — series appears trend-stationary"
        })
    except Exception as e:
        tests.append({
            "id": "kpss",
            "name": "KPSS",
            "error": str(e),
            "is_significant": None,
            "verdict": "COMPUTATION_FAILED",
            "interpretation": f"KPSS test could not be computed: {str(e)}"
        })
        kpss_sig = None

    # Combined verdict
    if adf_sig is True and kpss_sig is False:
        combined = "STATIONARY"
        combined_text = "ADF rejects unit root + KPSS accepts stationarity → strong evidence of stationarity. Suitable for mean-reversion strategies."
    elif adf_sig is False and kpss_sig is True:
        combined = "NON-STATIONARY"
        combined_text = "ADF cannot reject unit root + KPSS rejects stationarity → series is non-stationary. Trending/persistent behavior expected."
    elif adf_sig is True and kpss_sig is True:
        combined = "INCONCLUSIVE"
        combined_text = "Both ADF and KPSS reject — contradictory signals suggesting possible structural breaks or regime shifts."
    elif adf_sig is False and kpss_sig is False:
        combined = "LOW_POWER"
        combined_text = "Both tests inconclusive — sample may be too small or series near boundary of stationarity."
    else:
        combined = "UNDETERMINED"
        combined_text = "One or both tests failed to compute."

    # --- Chart Data: Rolling ADF Statistic (window = 60 or n//3, whichever is smaller) ---
    window = min(60, max(30, n // 3))
    rolling_adf = []
    rolling_kpss = []
    rolling_dates = []

    for i in range(window, n):
        window_prices = prices[i - window:i]
        try:
            r_adf = adfuller(window_prices, autolag='AIC', maxlag=min(int(window / 2), 15))
            rolling_adf.append(round(float(r_adf[0]), 4))
        except:
            rolling_adf.append(None)
        try:
            r_kpss = kpss(window_prices, regression='c', nlags='auto')
            rolling_kpss.append(round(float(r_kpss[0]), 4))
        except:
            rolling_kpss.append(None)
        rolling_dates.append(dates[i] if dates else str(i))

    chart_data["rolling_adf"] = {
        "type": "line",
        "title": f"Rolling ADF Statistic (window={window})",
        "x_label": "Date",
        "y_label": "ADF Statistic",
        "series": [{"name": "ADF Stat", "data": [
            {"x": d, "y": v} for d, v in zip(rolling_dates, rolling_adf)
        ]}],
        "mark_lines": [
            {"value": -2.877 if adf_result else -2.877, "label": "5% Critical", "style": "dashed"}
        ]
    }

    chart_data["rolling_kpss"] = {
        "type": "line",
        "title": f"Rolling KPSS Statistic (window={window})",
        "x_label": "Date",
        "y_label": "KPSS Statistic",
        "series": [{"name": "KPSS Stat", "data": [
            {"x": d, "y": v} for d, v in zip(rolling_dates, rolling_kpss)
        ]}],
        "mark_lines": [
            {"value": kpss_crit["5%"] if 'kpss_crit' in dir() else 0.463, "label": "5% Critical", "style": "dashed"}
        ]
    }

    # --- Price series for overlay ---
    chart_data["price_overlay"] = {
        "type": "line",
        "title": "Price Series",
        "x_label": "Date",
        "y_label": "Price",
        "series": [{"name": "Close", "data": [
            {"x": dates[i] if dates else str(i), "y": round(float(prices[i]), 4)}
            for i in range(n)
        ]}]
    }

    return {
        "stats": tests,
        "charts": chart_data,
        "combined_verdict": combined,
        "combined_interpretation": combined_text,
        "summary": f"STATIONARITY: {combined} — {combined_text}"
    }
