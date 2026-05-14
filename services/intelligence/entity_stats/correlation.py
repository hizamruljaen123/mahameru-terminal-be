"""
Correlation Module
Computes correlation matrix of the entity's price returns with:
- Its own lagged returns (autocorrelation matrix)
- OHLCV components (Open, High, Low, Close, Volume cross-correlations)
Returns data suited for correlation heatmap (ECharts) and Mermaid.js diagram
"""
import numpy as np
import pandas as pd
from scipy import stats


def compute_correlation(prices, returns, dates, df=None):
    """
    df: optional pandas DataFrame with OHLCV columns
    Returns correlation matrix suitable for heatmap rendering and Mermaid diagram generation
    """
    n = len(returns)
    result = {"matrix": {}, "mermaid_diagram": "", "heatmap_data": {}, "cross_correlations": []}

    # If OHLCV data is provided, build feature matrix
    features = {"Close_Return": returns}
    feature_labels = ["Close_Return"]

    if df is not None and isinstance(df, pd.DataFrame):
        if 'Open' in df.columns and 'Close' in df.columns:
            try:
                open_rets = np.diff(np.log(df['Open'].values))
                if len(open_rets) == n:
                    features["Open_Return"] = open_rets
                    feature_labels.append("Open_Return")
            except:
                pass
        if 'High' in df.columns:
            try:
                high_rets = np.diff(np.log(df['High'].values))
                if len(high_rets) == n:
                    features["High_Return"] = high_rets
                    feature_labels.append("High_Return")
            except:
                pass
        if 'Low' in df.columns:
            try:
                low_rets = np.diff(np.log(df['Low'].values))
                if len(low_rets) == n:
                    features["Low_Return"] = low_rets
                    feature_labels.append("Low_Return")
            except:
                pass
        if 'Volume' in df.columns and 'Close' in df.columns:
            try:
                vol_change = np.diff(df['Volume'].values) / (df['Volume'].values[:-1] + 1)
                if len(vol_change) == n:
                    features["Volume_Change"] = vol_change
                    feature_labels.append("Volume_Change")
            except:
                pass
        if 'High' in df.columns and 'Low' in df.columns:
            try:
                hl_spread = (df['High'].values[1:] - df['Low'].values[1:]) / df['Close'].values[1:]
                if len(hl_spread) == n:
                    features["HL_Spread"] = hl_spread
                    feature_labels.append("HL_Spread")
            except:
                pass

    # Build inter-feature correlation matrix
    m = len(feature_labels)
    corr_matrix = np.zeros((m, m))
    for i, fi in enumerate(feature_labels):
        for j, fj in enumerate(feature_labels):
            if i == j:
                corr_matrix[i][j] = 1.0
            else:
                valid = ~(np.isnan(features[fi]) | np.isnan(features[fj]))
                if valid.sum() > 10:
                    cc = np.corrcoef(features[fi][valid], features[fj][valid])[0, 1]
                    corr_matrix[i][j] = round(float(cc), 6) if not np.isnan(cc) else 0.0
                else:
                    corr_matrix[i][j] = 0.0

    # Heatmap data (for ECharts)
    heatmap_points = []
    for i, fi in enumerate(feature_labels):
        for j, fj in enumerate(feature_labels):
            heatmap_points.append({
                "x": i, "y": j,
                "x_label": fi, "y_label": fj,
                "value": round(float(corr_matrix[i][j]), 4)
            })

    result["heatmap_data"] = {
        "labels": feature_labels,
        "points": heatmap_points
    }

    # Correlation pairs (for bar chart and Mermaid)
    cross_corr = []
    for i in range(m):
        for j in range(i + 1, m):
            val = corr_matrix[i][j]
            cross_corr.append({
                "pair": f"{feature_labels[i]} ↔ {feature_labels[j]}",
                "source": feature_labels[i],
                "target": feature_labels[j],
                "correlation": round(float(val), 4),
                "strength": "Strong Positive" if val > 0.7 else (
                    "Moderate Positive" if val > 0.3 else (
                        "Weak Positive" if val > 0 else (
                            "Strong Negative" if val < -0.7 else (
                                "Moderate Negative" if val < -0.3 else "Weak Negative"
                            )
                        )
                    )
                ),
                "abs_correlation": round(float(abs(val)), 4)
            })

    # Sort by absolute correlation strength
    cross_corr.sort(key=lambda x: x["abs_correlation"], reverse=True)
    result["cross_correlations"] = cross_corr

    # --- Mermaid.js Diagram ---
    mermaid_lines = ["flowchart TD", "    subgraph Correlation_Matrix"]
    for item in cross_corr[:10]:  # Top 10
        source_id = item['source'].replace(' ', '_')
        target_id = item['target'].replace(' ', '_')
        source_label = item['source'].replace('_', ' ')
        target_label = item['target'].replace('_', ' ')
        
        label = f"{item['correlation']:+.3f}"
        
        # Using [ ] for rectangular nodes and proper link labels
        mermaid_lines.append(f'    {source_id}["{source_label}"] -->|"{label}"| {target_id}["{target_label}"]')
    mermaid_lines.append("    end")

    result["mermaid_diagram"] = "\n".join(mermaid_lines)
    result["matrix"] = {
        "labels": feature_labels,
        "values": corr_matrix.tolist()
    }

    return result
