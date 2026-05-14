"""
Distribution Tests Module
Tests: Kolmogorov-Smirnov (vs Normal), Mann-Whitney U (half-split)
Charts: ECDF (Empirical CDF vs Theoretical Normal CDF), Kernel Density Estimate
"""
import numpy as np
from scipy import stats


def compute_distribution(prices, returns, dates):
    n = len(returns)
    tests = []
    chart_data = {}

    # 1. Kolmogorov-Smirnov (vs Normal)
    mu, sigma = np.mean(returns), np.std(returns, ddof=1)
    try:
        ks_stat, ks_p = stats.kstest(returns, 'norm', args=(mu, sigma))
        ks_sig = ks_p < 0.05
        tests.append({
            "id": "ks_normal",
            "name": "Kolmogorov-Smirnov (vs Normal)",
            "statistic": round(float(ks_stat), 6),
            "p_value": round(float(ks_p), 6),
            "is_significant": ks_sig,
            "verdict": "Not Normal" if ks_sig else "Normal",
            "interpretation": f"Empirical CDF differs significantly from theoretical normal (D={ks_stat:.4f}, p<0.05)" if ks_sig else f"No significant difference from normal distribution (D={ks_stat:.4f}, p≥0.05)"
        })
    except Exception as e:
        tests.append({"id": "ks_normal", "name": "Kolmogorov-Smirnov (vs Normal)", "error": str(e), "verdict": "COMPUTATION_FAILED"})

    # 2. Mann-Whitney U (first half vs second half) — structural stability proxy
    try:
        mid = n // 2
        mw_stat, mw_p = stats.mannwhitneyu(returns[:mid], returns[mid:], alternative='two-sided')
        mw_sig = mw_p < 0.05
        tests.append({
            "id": "mann_whitney",
            "name": "Mann-Whitney U (Half-Split)",
            "statistic": round(float(mw_stat), 6),
            "p_value": round(float(mw_p), 6),
            "is_significant": mw_sig,
            "verdict": "Different Distribution" if mw_sig else "Same Distribution",
            "interpretation": "First and second halves come from different distributions — possible structural shift" if mw_sig else "First and second halves likely from same distribution — no structural shift detected"
        })
    except Exception as e:
        tests.append({"id": "mann_whitney", "name": "Mann-Whitney U (Half-Split)", "error": str(e), "verdict": "COMPUTATION_FAILED"})

    # --- Chart Data: ECDF vs Theoretical CDF ---
    sorted_returns = np.sort(returns)
    ecdf_y = np.arange(1, n + 1) / n
    x_grid = np.linspace(sorted_returns[0], sorted_returns[-1], 200)
    theoretical_cdf = stats.norm.cdf(x_grid, loc=mu, scale=sigma)

    chart_data["ecdf"] = {
        "type": "multi_line",
        "title": "Empirical CDF vs Theoretical Normal CDF",
        "x_label": "Daily Log Return",
        "y_label": "Cumulative Probability",
        "series": [
            {
                "name": "Empirical CDF",
                "data": [{"x": round(float(sr), 6), "y": round(float(ey), 6)} for sr, ey in zip(sorted_returns, ecdf_y)]
            },
            {
                "name": "Normal CDF",
                "data": [{"x": round(float(xv), 6), "y": round(float(yv), 6)} for xv, yv in zip(x_grid, theoretical_cdf)]
            }
        ]
    }

    # --- Chart Data: KDE (Kernel Density Estimate) ---
    try:
        kde = stats.gaussian_kde(returns)
        x_kde = np.linspace(sorted_returns[0], sorted_returns[-1], 200)
        y_kde = kde(x_kde)
        y_normal = stats.norm.pdf(x_kde, loc=mu, scale=sigma)

        chart_data["kde"] = {
            "type": "multi_line",
            "title": "Kernel Density Estimate vs Normal",
            "x_label": "Daily Log Return",
            "y_label": "Density",
            "series": [
                {
                    "name": "KDE (Empirical)",
                    "data": [{"x": round(float(xv), 6), "y": round(float(yv), 6)} for xv, yv in zip(x_kde, y_kde)]
                },
                {
                    "name": "Normal PDF",
                    "data": [{"x": round(float(xv), 6), "y": round(float(yv), 6)} for xv, yv in zip(x_kde, y_normal)]
                }
            ]
        }
    except:
        chart_data["kde"] = {"error": "KDE computation failed"}

    # --- Chart Data: Half-Split Distribution Comparison (Box Plot Data) ---
    mid = n // 2
    chart_data["half_split_box"] = {
        "type": "box",
        "title": "Distribution: First Half vs Second Half",
        "series": [
            {
                "name": "First Half",
                "data": [round(float(v), 6) for v in returns[:mid].tolist()]
            },
            {
                "name": "Second Half",
                "data": [round(float(v), 6) for v in returns[mid:].tolist()]
            }
        ]
    }

    any_sig = any(t.get("is_significant") for t in tests)
    return {
        "stats": tests,
        "charts": chart_data,
        "summary": "DISTRIBUTION DEVIATES FROM NORMAL" if any_sig else "DISTRIBUTION CONSISTENT WITH NORMAL"
    }
