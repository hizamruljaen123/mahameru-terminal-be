"""
Descriptive Statistics Module
Metrics: Mean Return, Std Dev, Skewness, Kurtosis (Excess), Variance Ratio
Charts: Return histogram with normal overlay, rolling skewness, rolling kurtosis, cumulative returns
"""
import numpy as np
from scipy import stats


def compute_descriptive(prices, returns, dates):
    n = len(returns)
    metrics = []
    chart_data = {}

    mu = np.mean(returns)
    sigma = np.std(returns, ddof=1)
    annual_factor = np.sqrt(252)

    # 1. Mean Daily Return
    ann_return = (1 + mu) ** 252 - 1
    metrics.append({
        "id": "mean_return",
        "name": "Mean Daily Return",
        "statistic": round(float(mu), 8),
        "formatted": f"{mu * 100:+.4f}%",
        "annualized": f"{ann_return * 100:+.2f}%",
        "interpretation": f"Average daily log-return: {mu * 100:.4f}% (annualized: {ann_return * 100:.2f}%)"
    })

    # 2. Standard Deviation
    ann_vol = sigma * annual_factor
    metrics.append({
        "id": "std_return",
        "name": "Standard Deviation (Daily)",
        "statistic": round(float(sigma), 8),
        "formatted": f"{sigma * 100:.4f}%",
        "annualized": f"{ann_vol * 100:.2f}%",
        "interpretation": f"Daily volatility: {sigma * 100:.2f}% (annualized: {ann_vol * 100:.2f}%)"
    })

    # 3. Skewness
    sk = stats.skew(returns)
    sk_sig = abs(sk) > 0.5
    sk_verdict = "Positively Skewed" if sk > 0.5 else ("Negatively Skewed" if sk < -0.5 else "Symmetric")
    metrics.append({
        "id": "skewness",
        "name": "Skewness",
        "statistic": round(float(sk), 6),
        "is_significant": sk_sig,
        "verdict": sk_verdict,
        "interpretation": "Right-tailed — positive returns dominate in magnitude" if sk > 0.5 else ("Left-tailed — negative returns tend to be larger" if sk < -0.5 else "Roughly symmetric return distribution")
    })

    # 4. Kurtosis (Excess)
    ku = stats.kurtosis(returns)
    ku_sig = ku > 1.0
    ku_verdict = "Leptokurtic (Fat Tails)" if ku > 1.0 else ("Platykurtic (Thin Tails)" if ku < -1.0 else "Mesokurtic (Normal)")
    metrics.append({
        "id": "kurtosis_excess",
        "name": "Kurtosis (Excess)",
        "statistic": round(float(ku), 6),
        "is_significant": ku_sig,
        "verdict": ku_verdict,
        "interpretation": "Excess kurtosis > 0 → fat tails; extreme events more frequent than normal predicts" if ku > 1.0 else ("Excess kurtosis < 0 → thinner tails than normal" if ku < -1.0 else "Tails consistent with normal distribution")
    })

    # 5. Variance Ratio (Lo-MacKinlay style, simplified)
    # VR(k) = Var(r_t + ... + r_{t-k+1}) / (k * Var(r_t))
    k_periods = [2, 5, 10, 20]
    vr_results = []
    for k in k_periods:
        if k < n:
            multi_period = np.array([np.sum(returns[i:i + k]) for i in range(n - k + 1)])
            var_k = np.var(multi_period, ddof=1)
            var_1 = np.var(returns, ddof=1)
            vr = (var_k / (k * var_1)) if var_1 > 0 else None
            if vr is not None:
                vr_results.append({
                    "k": k,
                    "variance_ratio": round(float(vr), 6),
                    "deviation_pct": round(float(abs(vr - 1) * 100), 2),
                    "interpretation": f"VR({k})={'≈1.0 — random walk' if abs(vr-1)<0.1 else ('>1 — trending/persistent' if vr>1 else '<1 — mean-reverting')}"
                })

    # Main VR (k=10 by default)
    default_vr = vr_results[2] if len(vr_results) > 2 else (vr_results[-1] if vr_results else None)
    if default_vr:
        vr_val = default_vr["variance_ratio"]
        vr_sig = abs(vr_val - 1) > 0.15
        metrics.append({
            "id": "variance_ratio",
            "name": "Variance Ratio (k=10)",
            "statistic": vr_val,
            "is_significant": vr_sig,
            "verdict": "Trending/Persistent" if vr_val > 1.1 else ("Mean-Reverting" if vr_val < 0.9 else "Near Random Walk"),
            "interpretation": f"VR(10)={' > 1.0 — prices trending (momentum behavior)' if vr_val>1.1 else (' < 1.0 — mean-reversion tendency' if vr_val<0.9 else ' ≈ 1.0 — consistent with random walk hypothesis')}"
        })
        chart_data["variance_ratio_profile"] = {
            "type": "bar_line",
            "title": "Variance Ratio Profile",
            "x_label": "Period (k)",
            "y_label": "Variance Ratio",
            "bars": [{"x": f"k={r['k']}", "y": r["variance_ratio"]} for r in vr_results],
            "reference_line": 1.0
        }

    # --- Chart Data: Rolling Skewness ---
    window = min(60, max(30, n // 3))
    rolling_skew = []
    rolling_kurt = []
    rolling_vol = []
    rolling_dates = []

    for i in range(window, n):
        w_ret = returns[i - window:i]
        rolling_skew.append(round(float(stats.skew(w_ret)), 4))
        rolling_kurt.append(round(float(stats.kurtosis(w_ret)), 4))
        rolling_vol.append(round(float(np.std(w_ret, ddof=1) * np.sqrt(252) * 100), 4))
        rolling_dates.append(dates[i] if dates else str(i))

    chart_data["rolling_skewness"] = {
        "type": "line",
        "title": f"Rolling Skewness (window={window})",
        "x_label": "Date",
        "y_label": "Skewness",
        "series": [{"name": "Skewness", "data": [
            {"x": d, "y": v} for d, v in zip(rolling_dates, rolling_skew)
        ]}],
        "mark_lines": [{"value": 0, "label": "Symmetric", "style": "dashed"}]
    }

    chart_data["rolling_kurtosis"] = {
        "type": "line",
        "title": f"Rolling Excess Kurtosis (window={window})",
        "x_label": "Date",
        "y_label": "Excess Kurtosis",
        "series": [{"name": "Kurtosis", "data": [
            {"x": d, "y": v} for d, v in zip(rolling_dates, rolling_kurt)
        ]}],
        "mark_lines": [{"value": 0, "label": "Normal", "style": "dashed"}]
    }

    chart_data["rolling_volatility"] = {
        "type": "line",
        "title": f"Rolling Annualized Volatility (window={window})",
        "x_label": "Date",
        "y_label": "Volatility (%)",
        "series": [{"name": "Volatility", "data": [
            {"x": d, "y": v} for d, v in zip(rolling_dates, rolling_vol)
        ]}]
    }

    # --- Cumulative Returns ---
    cum_ret = np.cumprod(1 + returns)
    chart_data["cumulative_returns"] = {
        "type": "line",
        "title": "Cumulative Returns",
        "x_label": "Date",
        "y_label": "Cumulative Return (x base)",
        "series": [{
            "name": "Cumulative Return",
            "data": [{"x": dates[i] if dates else str(i), "y": round(float(cum_ret[i]), 6)} for i in range(n)]
        }]
    }

    fat_tails = ku_sig

    return {
        "stats": metrics,
        "charts": chart_data,
        "fat_tails": fat_tails,
        "summary": f"Mean: {mu*100:+.4f}%/day | Vol: {sigma*100:.2f}%/day | Skew: {sk:+.3f} | Kurt(excess): {ku:+.3f} {'(FAT TAILS)' if fat_tails else ''}"
    }
