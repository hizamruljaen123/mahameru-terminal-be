"""
Normality Tests Module
Tests: Shapiro-Wilk, Jarque-Bera, D'Agostino K², Anderson-Darling
Charts: Q-Q Plot data (theoretical vs sample quantiles), histogram bins for distribution overlay
"""
import numpy as np
from scipy import stats


def compute_normality(prices, returns, dates):
    n = len(returns)
    tests = []
    chart_data = {}

    # Helper
    def build(name, fid, stat_val, p_val, is_sig, verdict, interpretation):
        return {
            "id": fid,
            "name": name,
            "statistic": round(float(stat_val), 6) if stat_val is not None else None,
            "p_value": round(float(p_val), 6) if p_val is not None else None,
            "is_significant": is_sig,
            "verdict": verdict,
            "interpretation": interpretation,
        }

    # 1. Shapiro-Wilk (best for n < 5000)
    if n >= 3 and n <= 5000:
        sw_stat, sw_p = stats.shapiro(returns)
        sig = sw_p < 0.05
        tests.append(build(
            "Shapiro-Wilk", "shapiro_wilk", sw_stat, sw_p, sig,
            "Non-Normal" if sig else "Normal",
            "Returns deviate significantly from normal distribution at α=5%" if sig else "No evidence to reject normality at α=5%"
        ))

    # 2. Jarque-Bera
    jb_stat, jb_p = stats.jarque_bera(returns)
    sig = jb_p < 0.05
    tests.append(build(
        "Jarque-Bera", "jarque_bera", jb_stat, jb_p, sig,
        "Non-Normal" if sig else "Normal",
        "Strong evidence of non-normal returns (combined skewness + kurtosis)" if sig else "Skewness and kurtosis consistent with normal distribution"
    ))

    # 3. D'Agostino K²
    dk_stat, dk_p = stats.normaltest(returns)
    sig = dk_p < 0.05
    tests.append(build(
        "D'Agostino K²", "dagostino_k2", dk_stat, dk_p, sig,
        "Non-Normal" if sig else "Normal",
        "Omnibus test combining skewness and kurtosis — deviation from normality" if sig else "No significant departure from normality detected"
    ))

    # 4. Anderson-Darling
    ad_result = stats.anderson(returns, dist='norm')
    ad_stat = ad_result.statistic
    crit_5 = ad_result.critical_values[2]  # 5% level
    sig = ad_stat > crit_5
    sig_level_idx = None
    for i, cv in enumerate(ad_result.critical_values):
        if ad_stat > cv:
            sig_level_idx = i
    sig_pct = [15.0, 10.0, 5.0, 2.5, 1.0][sig_level_idx] if sig_level_idx is not None else None

    tests.append({
        "id": "anderson_darling",
        "name": "Anderson-Darling",
        "statistic": round(float(ad_stat), 6),
        "critical_1pct": round(float(ad_result.critical_values[4]), 6),
        "critical_5pct": round(float(crit_5), 6),
        "critical_10pct": round(float(ad_result.critical_values[1]), 6),
        "p_value": None,
        "significance_level": f"{sig_pct}%" if sig_pct else "None",
        "is_significant": sig,
        "verdict": f"Non-Normal ({sig_pct}%)" if sig else "Normal (5%)",
        "interpretation": f"AD statistic exceeds {sig_pct}% critical value → reject normality" if sig else "No evidence against normality at 5% level"
    })

    # --- Chart Data: Q-Q Plot ---
    sorted_returns = np.sort(returns)
    theoretical_quantiles = stats.norm.ppf(
        (np.arange(1, n + 1) - 0.5) / n,
        loc=np.mean(returns),
        scale=np.std(returns, ddof=1)
    )
    chart_data["qq_plot"] = {
        "type": "scatter",
        "title": "Q-Q Plot (Returns vs Normal)",
        "x_label": "Theoretical Normal Quantiles",
        "y_label": "Sample Quantiles",
        "points": [
            {"x": round(float(tq), 6), "y": round(float(sr), 6)}
            for tq, sr in zip(theoretical_quantiles, sorted_returns)
        ]
    }

    # --- Chart Data: Histogram + Normal Overlay ---
    hist, bin_edges = np.histogram(returns, bins='auto', density=True)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    x_fit = np.linspace(min(returns), max(returns), 200)
    y_fit = stats.norm.pdf(x_fit, loc=np.mean(returns), scale=np.std(returns, ddof=1))

    chart_data["histogram"] = {
        "type": "bar_line",
        "title": "Return Distribution vs Normal Curve",
        "x_label": "Daily Log Return",
        "y_label": "Density",
        "bars": [
            {"x": round(float(bc), 6), "y": round(float(h), 6)}
            for bc, h in zip(bin_centers, hist)
        ],
        "line": [
            {"x": round(float(xv), 6), "y": round(float(yv), 6)}
            for xv, yv in zip(x_fit, y_fit)
        ]
    }

    normality_rejected = any(t.get("is_significant") for t in tests)

    return {
        "stats": tests,
        "charts": chart_data,
        "summary": "NORMALITY REJECTED — Non-normal distribution detected" if normality_rejected else "NORMALITY ACCEPTED — Returns follow normal distribution"
    }
