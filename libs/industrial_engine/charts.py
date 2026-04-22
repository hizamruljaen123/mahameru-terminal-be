"""
modules/charts.py
==================
Plotly visualizations for the Industrial Activity Monitor.
All charts use a dark industrial theme consistent with the Streamlit UI.
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots


# ── Shared theme config
DARK_THEME = dict(
    paper_bgcolor="#0d1117",
    plot_bgcolor="#0d1117",
    font=dict(family="IBM Plex Mono, monospace", color="#c9d1d9", size=11),
    xaxis=dict(
        gridcolor="#21262d",
        linecolor="#30363d",
        tickcolor="#30363d",
        showgrid=True,
    ),
    yaxis=dict(
        gridcolor="#21262d",
        linecolor="#30363d",
        tickcolor="#30363d",
        showgrid=True,
    ),
    legend=dict(
        bgcolor="#161b22",
        bordercolor="#30363d",
        borderwidth=1,
        font=dict(size=10),
    ),
)


def plot_timeseries(
    df: pd.DataFrame,
    thresh_high: float = 0.70,
    thresh_normal: float = 0.40,
) -> go.Figure:
    """
    Multi-panel time-series showing:
    - Panel 1: Business Activity Score with threshold bands
    - Panel 2: NO2 and NTL normalized signals
    """
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("Business Activity Score", "Component Signals (Normalized)"),
        row_heights=[0.6, 0.4],
    )

    dates = df.index

    # ── Panel 1: Activity Score
    score = df["activity_score"] if "activity_score" in df.columns else pd.Series(0.5, index=dates)

    # Threshold fill bands
    fig.add_hrect(y0=thresh_high, y1=1.05, row=1, col=1,
                  fillcolor="rgba(63, 185, 80, 0.08)", line_width=0,
                  annotation_text="PEAK", annotation_position="top right",
                  annotation_font_color="#3fb950", annotation_font_size=9)

    fig.add_hrect(y0=thresh_normal, y1=thresh_high, row=1, col=1,
                  fillcolor="rgba(88, 166, 255, 0.06)", line_width=0,
                  annotation_text="NORMAL", annotation_position="top right",
                  annotation_font_color="#58a6ff", annotation_font_size=9)

    fig.add_hrect(y0=0, y1=thresh_normal, row=1, col=1,
                  fillcolor="rgba(248, 81, 73, 0.06)", line_width=0,
                  annotation_text="LOW", annotation_position="top right",
                  annotation_font_color="#f85149", annotation_font_size=9)

    # Score line — colored by zone
    fig.add_trace(go.Scatter(
        x=dates, y=score,
        mode="lines+markers",
        name="Activity Score",
        line=dict(color="#58a6ff", width=2.5),
        marker=dict(size=5, color=score, colorscale=[
            [0.0, "#f85149"], [0.4, "#d29922"], [0.7, "#3fb950"], [1.0, "#3fb950"]
        ], showscale=False),
        fill="tozeroy",
        fillcolor="rgba(88, 166, 255, 0.07)",
        hovertemplate="<b>%{x|%b %Y}</b><br>Score: %{y:.3f}<extra></extra>",
    ), row=1, col=1)

    # Threshold lines
    for thresh, color, label in [
        (thresh_high, "#3fb950", f"High ({thresh_high})"),
        (thresh_normal, "#f85149", f"Low ({thresh_normal})"),
    ]:
        fig.add_hline(y=thresh, line_dash="dot", line_color=color, line_width=1,
                      row=1, col=1)

    # Rolling 3-month average
    if len(score) >= 3:
        rolling = score.rolling(3).mean()
        fig.add_trace(go.Scatter(
            x=dates, y=rolling,
            mode="lines",
            name="3M Rolling Avg",
            line=dict(color="#d29922", width=1.5, dash="dash"),
            hovertemplate="<b>%{x|%b %Y}</b><br>3M Avg: %{y:.3f}<extra></extra>",
        ), row=1, col=1)

    # ── Panel 2: NO2 + NTL normalized
    if "no2_norm" in df.columns:
        fig.add_trace(go.Scatter(
            x=dates, y=df["no2_norm"],
            mode="lines",
            name="NO₂ (norm)",
            line=dict(color="#ffa657", width=1.5),
            hovertemplate="<b>%{x|%b %Y}</b><br>NO₂ norm: %{y:.3f}<extra></extra>",
        ), row=2, col=1)

    if "ntl_norm" in df.columns:
        fig.add_trace(go.Scatter(
            x=dates, y=df["ntl_norm"],
            mode="lines",
            name="NTL (norm)",
            line=dict(color="#bc8cff", width=1.5),
            hovertemplate="<b>%{x|%b %Y}</b><br>NTL norm: %{y:.3f}<extra></extra>",
        ), row=2, col=1)

    fig.update_layout(
        **DARK_THEME,
        height=380,
        margin=dict(l=40, r=20, t=30, b=30),
        showlegend=True,
    )
    fig.update_yaxes(range=[0, 1.05], row=1, col=1, tickformat=".2f")
    fig.update_yaxes(range=[0, 1.05], row=2, col=1, tickformat=".2f")

    return fig


def plot_score_gauge(
    score: float,
    thresh_high: float = 0.70,
    thresh_normal: float = 0.40,
) -> go.Figure:
    """
    Gauge chart showing current Business Activity Score.
    """
    if score >= thresh_high:
        bar_color = "#3fb950"
        status_text = "PEAK PRODUCTION"
    elif score >= thresh_normal:
        bar_color = "#58a6ff"
        status_text = "NORMAL OPERATION"
    else:
        bar_color = "#f85149"
        status_text = "ECONOMIC SLOWDOWN"

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=score,
        number=dict(
            font=dict(size=36, color="#f0f6fc", family="IBM Plex Mono, monospace"),
            valueformat=".3f",
        ),
        title=dict(
            text=f"<b style='color:{bar_color}'>{status_text}</b>",
            font=dict(size=11, color=bar_color),
        ),
        gauge=dict(
            axis=dict(
                range=[0, 1],
                tickwidth=1,
                tickcolor="#30363d",
                tickvals=[0, thresh_normal, thresh_high, 1.0],
                ticktext=["0", f"{thresh_normal}", f"{thresh_high}", "1"],
                tickfont=dict(size=9, color="#8b949e"),
            ),
            bar=dict(color=bar_color, thickness=0.3),
            bgcolor="#161b22",
            borderwidth=0,
            steps=[
                dict(range=[0, thresh_normal], color="#4d1a1a"),
                dict(range=[thresh_normal, thresh_high], color="#1a2d4d"),
                dict(range=[thresh_high, 1.0], color="#1a4d2e"),
            ],
            threshold=dict(
                line=dict(color="#f0f6fc", width=2),
                thickness=0.75,
                value=score,
            ),
        ),
    ))

    fig.update_layout(
        **DARK_THEME,
        height=220,
        margin=dict(l=20, r=20, t=30, b=10),
    )
    return fig


def plot_trend_bar(df: pd.DataFrame) -> go.Figure:
    """
    Monthly bar chart of activity score with color-coded bars.
    Shows last 12 months max.
    """
    if "activity_score" not in df.columns:
        return go.Figure()

    tail = df["activity_score"].tail(12)
    colors = ["#3fb950" if v >= 0.7 else "#58a6ff" if v >= 0.4 else "#f85149"
              for v in tail.values]

    fig = go.Figure(go.Bar(
        x=tail.index.strftime("%b %y"),
        y=tail.values,
        marker_color=colors,
        marker_line_width=0,
        hovertemplate="<b>%{x}</b><br>Score: %{y:.3f}<extra></extra>",
    ))

    fig.update_layout(
        **DARK_THEME,
        height=180,
        margin=dict(l=40, r=20, t=30, b=30),
        yaxis_range=[0, 1.05],
        yaxis_tickformat=".2f",
        bargap=0.15,
        showlegend=False,
    )
    return fig
