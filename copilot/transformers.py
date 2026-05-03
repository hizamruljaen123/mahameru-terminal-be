"""
Component transformers for Mahameru Copilot.
Each transformer converts raw microservice data into Rich Response components
(charts, tables, maps, markdown, cards) for the SolidJS frontend.
"""

import json
import logging
from typing import Dict, Any, List, Optional, Callable

from copilot.config import logger

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _is_echarts_compatible(data: Dict[str, Any]) -> bool:
    """Check if the data looks like it could be rendered as an ECharts config."""
    return any(k in data for k in ["xAxis", "yAxis", "series", "option", "options", "echarts"])


def _has_geojson(data: Dict[str, Any]) -> bool:
    """Check if data contains GeoJSON features."""
    if "geojson" in data:
        return True
    if "type" in data and data["type"] == "FeatureCollection":
        return True
    if "features" in data and isinstance(data["features"], list):
        return True
    if "coordinates" in data or "geometry" in data:
        return True
    return False


def _extract_table_candidates(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract tabular data from a response."""
    # Try common table patterns
    for key in ["data", "results", "items", "rows", "records", "values", "table"]:
        val = data.get(key, data.get(f"{key}s"))
        if isinstance(val, list) and len(val) > 0:
            if isinstance(val[0], dict):
                headers = list(val[0].keys())
                rows = [[str(row.get(h, "")) for h in headers] for row in val]
                return {"headers": headers, "rows": rows}
            elif isinstance(val[0], list):
                return {"headers": [f"Col{i+1}" for i in range(len(val[0]))], "rows": val}
    return None


# ---------------------------------------------------------------------------
# _build_rich_response — orchestrator that routes tool results to transformers
# ---------------------------------------------------------------------------


def _build_rich_response(
    message: str,
    tool_results: List[Dict[str, Any]],
    tool_calls_made: List[str],
) -> List[Dict[str, Any]]:
    """
    Transform raw microservice results into Mahameru Rich Response components.
    Consolidates non-text components (charts, tables, maps) into dynamic tabs
    to keep the interface clean.
    """
    components: List[Dict[str, Any]] = []

    # 1. Main AI message at the top
    if message:
        components.append({
            "type": "markdown",
            "data": message,
        })

    # 2. Collect tool results into tabs
    tool_tabs = []
    
    for result in tool_results:
        tool_name = result.get("tool", "unknown")
        if not result.get("success"):
            # Errors can stay as markdown for visibility or go in a tab
            # Let's put errors in the main flow so user knows it failed
            components.append({
                "type": "markdown",
                "data": f"⚠️ **{tool_name}**: {result.get('error', 'Unknown error')}",
            })
            continue

        data = result.get("data", {})
        transformer = _COMPONENT_TRANSFORMERS.get(tool_name, _transform_generic)
        
        try:
            comps = transformer(tool_name, data)
            
            # Humanize tool name for tab title
            label = tool_name.replace("get_", "").replace("run_", "").replace("_", " ").title()
            if label == "Ta": label = "Technical Analysis"
            
            for i, comp in enumerate(comps):
                # If a tool returns multiple components (e.g. Chart + Table), 
                # we can either put them in separate tabs or find a way to group them.
                # Rich Response doesn't support nested components well yet, so separate tabs:
                title = label if i == 0 else f"{label} ({i+1})"
                
                # Check if it's already a tabs component (don't nest tabs)
                if comp.get("type") == "tabs":
                    for subtab in comp.get("tabs", []):
                        tool_tabs.append(subtab)
                else:
                    tool_tabs.append({
                        "title": title,
                        **comp
                    })
        except Exception as e:
            logger.error(f"Transformer error for {tool_name}: {e}")
            tool_tabs.append({
                "title": f"Raw {label}",
                "type": "markdown",
                "data": f"```json\n{json.dumps(data, indent=2, default=str)[:1000]}\n```",
            })

    # 3. Append consolidated tabs at the bottom
    if tool_tabs:
        components.append({
            "type": "tabs",
            "tabs": tool_tabs
        })

    return components


# ---------------------------------------------------------------------------
# Technical Analysis transformer (5 categorized tabbed chart panels)
# ---------------------------------------------------------------------------


def _transform_technical_analysis(tool: str, data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Transform TA data into categorized tabbed ECharts charts.

    Produces tabbed chart panels organized by indicator category:
      - Tab 'Price & MA'        — OHLC + Volume + SMA/EMA overlays
      - Tab 'Bollinger & VWAP'  — OHLC + Volume + BB/U/M/L + VWAP + SAR
      - Tab 'RSI'               — Standalone RSI with overbought/oversold
      - Tab 'MACD'              — MACD line + signal + histogram
      - Tab 'Stochastic'        — %K/%D with overbought/oversold
    """
    components = []
    ohlc_data = None
    dates = None
    volume_data = None

    # ── Parse OHLCV data (handles 2 formats) ──────────────────────────────────
    ohlcv = data.get("ohlcv", data.get("history", []))
    if isinstance(ohlcv, list) and len(ohlcv) > 0:
        # Format A: list of dicts {date, open, high, low, close, volume}
        dates = []
        ohlc_data = []
        volume_data = []
        for row in ohlcv[:300]:
            if isinstance(row, dict):
                dates.append(row.get("date", row.get("Date", "")))
                ohlc_data.append([
                    row.get("open", row.get("Open", 0)),
                    row.get("close", row.get("Close", 0)),
                    row.get("low", row.get("Low", 0)),
                    row.get("high", row.get("High", 0)),
                ])
                vol = row.get("volume", row.get("Volume", 0))
                volume_data.append(float(vol) if vol else 0)
            elif isinstance(row, (list, tuple)) and len(row) >= 5:
                dates.append(str(row[0]))
                ohlc_data.append([float(row[1]), float(row[4]), float(row[3]), float(row[2])])
                volume_data.append(float(row[5]) if len(row) >= 6 else 0)

    elif isinstance(ohlcv, dict) and "open" in ohlcv:
        # Format B: dict {open: [...], high: [...], low: [...], close: [...], volume: [...]}
        dates = data.get("dates", [])
        opens = ohlcv.get("open", [])
        closes = ohlcv.get("close", [])
        lows = ohlcv.get("low", [])
        highs = ohlcv.get("high", [])
        volumes = ohlcv.get("volume", [])
        n = min(len(dates), len(opens), len(closes), len(lows), len(highs), 300)
        if n > 0:
            dates = dates[:n]
            ohlc_data = []
            volume_data = []
            for i in range(n):
                ohlc_data.append([
                    opens[i] if opens[i] is not None else 0,
                    closes[i] if closes[i] is not None else 0,
                    lows[i] if lows[i] is not None else 0,
                    highs[i] if highs[i] is not None else 0,
                ])
                volume_data.append(float(volumes[i]) if i < len(volumes) and volumes[i] else 0)

    if not (dates and ohlc_data and volume_data is not None):
        components.append({
            "type": "markdown",
            "data": f"```json\n{json.dumps(data, indent=2, default=str)[:2000]}\n```",
        })
        return components

    indicators = data.get("indicators", data.get("indicator", {}))
    symbol = data.get("symbol", "Price Chart")
    n_dates = len(dates)

    tabs = []

    # ── Helper: dual-grid OHLCV chart with extra overlay series ──────────────
    def _ohlcv_chart(title: str, extra_series: list = None) -> Dict:
        legend_data = ["OHLC", "Volume"]
        series_list = [
            {
                "name": "OHLC",
                "type": "candlestick",
                "data": ohlc_data,
                "itemStyle": {
                    "color": "#26a69a", "color0": "#ef5350",
                    "borderColor": "#26a69a", "borderColor0": "#ef5350",
                },
                "xAxisIndex": 0, "yAxisIndex": 0,
            },
            {
                "name": "Volume",
                "type": "bar",
                "data": volume_data,
                "itemStyle": {"color": "#666"},
                "xAxisIndex": 1, "yAxisIndex": 1,
            },
        ]
        if extra_series:
            for s in extra_series:
                series_list.append(s)
                if s.get("name"):
                    legend_data.append(s["name"])

        return {
            "title": {"text": f"{symbol} — {title}", "left": "center", "textStyle": {"color": "#e0e0e0", "fontSize": 13}},
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "cross"}},
            "legend": {"data": legend_data, "textStyle": {"color": "#aaa", "fontSize": 10}, "top": 30},
            "xAxis": [
                {"type": "category", "data": dates, "gridIndex": 0, "axisLabel": {"color": "#888", "rotate": 30, "fontSize": 9}},
                {"type": "category", "data": dates, "gridIndex": 1, "axisLabel": {"show": False}},
            ],
            "yAxis": [
                {"type": "value", "scale": True, "gridIndex": 0, "axisLabel": {"color": "#888", "fontSize": 9}},
                {"type": "value", "scale": True, "gridIndex": 1, "axisLabel": {"show": False}, "splitLine": {"show": False}},
            ],
            "grid": [
                {"left": "6%", "right": "6%", "top": "15%", "height": "52%"},
                {"left": "6%", "right": "6%", "top": "72%", "height": "18%"},
            ],
            "series": series_list,
            "darkMode": True,
            "backgroundColor": "transparent",
        }

    # ── Helper: single-axis line/bar chart (for RSI, MACD, Stoch) ────────────
    def _single_chart(title: str, y_name: str, series_list: list,
                      y_min: float = None, y_max: float = None,
                      mark_lines: list = None) -> Dict:
        """Build a standalone chart. mark_lines: [{value, label, color}]"""
        sers = []
        legend = []
        for i, s in enumerate(series_list):
            stype = s.get("type", "line")
            entry = {
                "name": s.get("name", ""),
                "type": stype,
                "data": s["data"],
                "symbol": "none",
            }
            if stype == "line":
                entry["lineStyle"] = {"width": 1.5, "color": s.get("color", "#22d3ee")}
            if s.get("area"):
                entry["areaStyle"] = s["area"]
            if s.get("itemStyle"):
                entry["itemStyle"] = s["itemStyle"]

            # Attach mark lines to first series
            if i == 0 and mark_lines:
                entry["markLine"] = {
                    "silent": True,
                    "data": [
                        {
                            "yAxis": ml["value"],
                            "label": {"formatter": ml.get("label", str(ml["value"])),
                                      "color": ml.get("color", "#888"), "fontSize": 9},
                            "lineStyle": {"color": ml.get("color", "#666"), "type": "dashed", "width": 1},
                        }
                        for ml in mark_lines
                    ],
                }
            sers.append(entry)
            if s.get("name"):
                legend.append(s["name"])

        opts = {
            "title": {"text": f"{symbol} — {title}", "left": "center", "textStyle": {"color": "#e0e0e0", "fontSize": 13}},
            "tooltip": {"trigger": "axis"},
            "legend": {"data": legend, "textStyle": {"color": "#aaa", "fontSize": 10}, "top": 30},
            "xAxis": {"type": "category", "data": dates, "axisLabel": {"color": "#888", "rotate": 30, "fontSize": 9}},
            "yAxis": {
                "type": "value", "scale": True,
                "name": y_name,
                "nameTextStyle": {"color": "#888", "fontSize": 9},
                "axisLabel": {"color": "#888", "fontSize": 9},
            },
            "grid": {"left": "6%", "right": "6%", "top": "15%", "bottom": "15%"},
            "series": sers,
            "darkMode": True,
            "backgroundColor": "transparent",
        }
        if y_min is not None:
            opts["yAxis"]["min"] = y_min
        if y_max is not None:
            opts["yAxis"]["max"] = y_max
        return opts

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1: Price & Moving Averages
    # ══════════════════════════════════════════════════════════════════════════
    ma_series = []
    if isinstance(indicators, dict):
        sma_data = indicators.get("sma", {})
        sma_colors = {"sma10": "#42a5f5", "sma20": "#1e88e5", "sma50": "#1565c0",
                      "sma100": "#0d47a1", "sma200": "#0a3d6b"}
        for key, values in sma_data.items():
            if isinstance(values, list) and len(values) >= n_dates:
                ma_series.append({
                    "name": key.upper(), "type": "line", "data": values[:n_dates],
                    "xAxisIndex": 0, "yAxisIndex": 0,
                    "lineStyle": {"width": 1, "color": sma_colors.get(key, "#78909c")},
                    "symbol": "none", "z": 2,
                })

        ema_data = indicators.get("ema", {})
        ema_colors = {"ema9": "#ce93d8", "ema12": "#ab47bc", "ema21": "#8e24aa",
                      "ema26": "#6a1b9a", "ema50": "#4a148c", "ema200": "#7b1fa2"}
        for key, values in ema_data.items():
            if isinstance(values, list) and len(values) >= n_dates:
                ma_series.append({
                    "name": key.upper(), "type": "line", "data": values[:n_dates],
                    "xAxisIndex": 0, "yAxisIndex": 0,
                    "lineStyle": {"width": 1, "color": ema_colors.get(key, "#9575cd")},
                    "symbol": "none", "z": 2,
                })

    if ma_series:
        tabs.append({
            "title": "Price & MA",
            "type": "chart",
            "engine": "echarts",
            "options": _ohlcv_chart("Price & Moving Averages", ma_series),
        })

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2: Bollinger Bands & VWAP
    # ══════════════════════════════════════════════════════════════════════════
    bbvwap_series = []
    if isinstance(indicators, dict):
        bb_data = indicators.get("bb", {})
        upper = bb_data.get("upper", [])
        middle = bb_data.get("middle", [])
        lower = bb_data.get("lower", [])
        if isinstance(upper, list) and isinstance(middle, list) and isinstance(lower, list):
            if len(upper) >= n_dates and len(middle) >= n_dates and len(lower) >= n_dates:
                bbvwap_series.extend([
                    {"name": "BB Upper", "type": "line", "data": upper[:n_dates],
                     "xAxisIndex": 0, "yAxisIndex": 0,
                     "lineStyle": {"width": 0.5, "color": "#ef6c00", "type": "dashed"},
                     "symbol": "none", "z": 1},
                    {"name": "BB Middle", "type": "line", "data": middle[:n_dates],
                     "xAxisIndex": 0, "yAxisIndex": 0,
                     "lineStyle": {"width": 1, "color": "#ef6c00", "type": "solid"},
                     "symbol": "none", "z": 1},
                    {"name": "BB Lower", "type": "line", "data": lower[:n_dates],
                     "xAxisIndex": 0, "yAxisIndex": 0,
                     "lineStyle": {"width": 0.5, "color": "#ef6c00", "type": "dashed"},
                     "symbol": "none", "z": 1},
                ])

        vwap_data = indicators.get("vwap", [])
        if isinstance(vwap_data, list) and len(vwap_data) >= n_dates:
            bbvwap_series.append({
                "name": "VWAP", "type": "line", "data": vwap_data[:n_dates],
                "xAxisIndex": 0, "yAxisIndex": 0,
                "lineStyle": {"width": 1, "color": "#ffb74d", "type": "dotted"},
                "symbol": "none", "z": 2,
            })

        sar_data = indicators.get("sar", [])
        if isinstance(sar_data, list) and len(sar_data) >= n_dates:
            bbvwap_series.append({
                "name": "SAR", "type": "scatter", "data": sar_data[:n_dates],
                "xAxisIndex": 0, "yAxisIndex": 0,
                "symbol": "diamond", "symbolSize": 4,
                "itemStyle": {"color": "#fdd835"}, "z": 5,
            })

    if bbvwap_series:
        tabs.append({
            "title": "Bollinger & VWAP",
            "type": "chart",
            "engine": "echarts",
            "options": _ohlcv_chart("Bollinger Bands, VWAP & SAR", bbvwap_series),
        })

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3: RSI
    # ══════════════════════════════════════════════════════════════════════════
    if isinstance(indicators, dict):
        rsi_data = indicators.get("rsi", {})
        rsi_values = rsi_data.get("rsi14", [])
        if isinstance(rsi_values, list) and len(rsi_values) >= n_dates:
            tabs.append({
                "title": "RSI",
                "type": "chart",
                "engine": "echarts",
                "options": _single_chart(
                    "RSI (14)",
                    "RSI",
                    [{"name": "RSI", "data": rsi_values[:n_dates], "color": "#ab47bc",
                      "area": {"color": "rgba(171,71,188,0.1)"}}],
                    y_min=0, y_max=100,
                    mark_lines=[
                        {"value": 70, "label": "Overbought 70", "color": "#ef5350"},
                        {"value": 30, "label": "Oversold 30", "color": "#26a69a"},
                    ],
                ),
            })

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 4: MACD
    # ══════════════════════════════════════════════════════════════════════════
    if isinstance(indicators, dict):
        macd_data = indicators.get("macd", {})
        macd_line = macd_data.get("macd", [])
        macd_signal = macd_data.get("signal", [])
        macd_hist = macd_data.get("histogram", [])
        macd_series = []
        if isinstance(macd_line, list) and len(macd_line) >= n_dates:
            macd_series.append({"name": "MACD", "data": macd_line[:n_dates], "color": "#22d3ee"})
        if isinstance(macd_signal, list) and len(macd_signal) >= n_dates:
            macd_series.append({"name": "Signal", "data": macd_signal[:n_dates], "color": "#f97316"})
        if isinstance(macd_hist, list) and len(macd_hist) >= n_dates:
            hist_data = macd_hist[:n_dates]
            macd_series.append({
                "name": "Histogram", "type": "bar", "data": hist_data,
                "itemStyle": {
                    "color": {"type": "piecewise", "pieces": [
                        {"gt": 0, "color": "#26a69a"},
                        {"lte": 0, "color": "#ef5350"},
                    ]},
                },
            })
        if macd_series:
            tabs.append({
                "title": "MACD",
                "type": "chart",
                "engine": "echarts",
                "options": _single_chart("MACD (12,26,9)", "MACD", macd_series,
                                          mark_lines=[{"value": 0, "label": "Zero", "color": "#666"}]),
            })

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 5: Stochastic
    # ══════════════════════════════════════════════════════════════════════════
    if isinstance(indicators, dict):
        stoch_data = indicators.get("stoch", {})
        stoch_k = stoch_data.get("k", [])
        stoch_d = stoch_data.get("d", [])
        stoch_series = []
        if isinstance(stoch_k, list) and len(stoch_k) >= n_dates:
            stoch_series.append({"name": "%K", "data": stoch_k[:n_dates], "color": "#22d3ee"})
        if isinstance(stoch_d, list) and len(stoch_d) >= n_dates:
            stoch_series.append({"name": "%D", "data": stoch_d[:n_dates], "color": "#f97316"})
        if stoch_series:
            tabs.append({
                "title": "Stochastic",
                "type": "chart",
                "engine": "echarts",
                "options": _single_chart("Stochastic Oscillator", "Stochastic", stoch_series,
                                          y_min=0, y_max=100,
                                          mark_lines=[
                                              {"value": 80, "label": "Overbought 80", "color": "#ef5350"},
                                              {"value": 20, "label": "Oversold 20", "color": "#26a69a"},
                                          ]),
            })

    # ── Build final component ──────────────────────────────────────────────────
    if tabs:
        components.append({"type": "tabs", "tabs": tabs})
    else:
        # No indicator data — basic OHLCV chart only
        components.append({
            "type": "chart",
            "engine": "echarts",
            "options": _ohlcv_chart("Price Chart"),
        })

    # ── Current values & signals summary table ─────────────────────────────────
    current = data.get("current", {})
    signals_data = data.get("signals", {})
    table_rows = []

    if isinstance(current, dict):
        for key, val in current.items():
            if not isinstance(val, (list, dict)):
                table_rows.append([key.upper(), str(val)[:50], ""])

    if isinstance(signals_data, dict):
        verdict = signals_data.get("verdict", "")
        if verdict:
            table_rows.insert(0, ["SIGNAL", "", verdict])
        inner_signals = signals_data.get("signals", {})
        if isinstance(inner_signals, dict):
            for key, val in inner_signals.items():
                table_rows.append([key, str(val), ""])

    if table_rows:
        components.append({
            "type": "table",
            "headers": ["Indicator", "Value", "Signal"],
            "rows": table_rows,
            "title": f"{symbol} — Current Values & Signals",
        })

    # ── Support / Resistance markdown ─────────────────────────────────────────
    sr = data.get("support_resistance", {})
    if sr and isinstance(sr, dict):
        supports = sr.get("supports", [])
        resistances = sr.get("resistances", [])
        parts = []
        if supports:
            parts.append("**Support Levels:** " + ", ".join(str(round(s, 2)) for s in supports if s is not None))
        if resistances:
            parts.append("**Resistance Levels:** " + ", ".join(str(round(r, 2)) for r in resistances if r is not None))
        if parts:
            components.append({"type": "markdown", "data": "  \n".join(parts)})

    # ── Fibonacci levels markdown ─────────────────────────────────────────────
    fib = data.get("fibonacci", {})
    if fib and isinstance(fib, dict):
        levels = fib.get("levels", {})
        if levels:
            fib_text = "**Fibonacci Retracement Levels:**  \n"
            fib_text += " | ".join(f"{k}: {round(v, 2)}" for k, v in sorted(levels.items()))
            components.append({"type": "markdown", "data": fib_text})

    return components


# ---------------------------------------------------------------------------
# Market Quote transformer
# ---------------------------------------------------------------------------


def _transform_market_quote(tool: str, data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Transform quote data into a price card + mini sparkline."""
    components = []
    quote = data.get("quote", data.get("data", data))
    symbol = quote.get("symbol", quote.get("ticker", data.get("symbol", "N/A")))
    price = quote.get("regularMarketPrice", quote.get("price", quote.get("last", "N/A")))
    change = quote.get("regularMarketChange", quote.get("change", 0))
    change_pct = quote.get("regularMarketChangePercent", quote.get("changePercent", quote.get("changesPercentage", 0)))
    name = quote.get("shortName", quote.get("name", quote.get("longName", symbol)))

    # Price card as markdown for quick view
    arrow = "🟢" if (isinstance(change, (int, float)) and change >= 0) else "🔴"
    card = f"## {name} ({symbol})\n\n{arrow} **{price}** | {change:+.4f} ({change_pct:+.2f}%)"
    components.append({"type": "markdown", "data": card})

    # Add key stats table if available
    stats = {}
    for k in ["dayLow", "dayHigh", "fiftyTwoWeekLow", "fiftyTwoWeekHigh", "volume", "marketCap", "peRatio", "dividendYield"]:
        if k in quote and quote[k] is not None:
            stats[k] = quote[k]

    if stats:
        table_data = {
            "headers": ["Metric", "Value"],
            "rows": [[k, str(v)[:30]] for k, v in stats.items()],
        }
        components.append({"type": "table", **table_data})

    return components


# ---------------------------------------------------------------------------
# Vessel Intelligence transformer (Leaflet map + anomaly table)
# ---------------------------------------------------------------------------


def _transform_vessel_intel(tool: str, data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Transform vessel data into Leaflet map + anomaly table."""
    components = []
    vessels = data.get("vessels", data.get("data", data.get("results", [])))
    if isinstance(vessels, dict):
        vessels = [vessels]

    if isinstance(vessels, list) and len(vessels) > 0:
        features = []
        table_rows = []
        for v in vessels:
            lat = v.get("lat", v.get("latitude"))
            lon = v.get("lon", v.get("longitude", v.get("lng")))
            if lat and lon:
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
                    "properties": {
                        "name": v.get("name", v.get("shipName", "Unknown")),
                        "type": v.get("type", v.get("vesselType", "Unknown")),
                        "speed": v.get("speed", v.get("sog", "N/A")),
                        "course": v.get("course", v.get("cog", "N/A")),
                        "destination": v.get("destination", ""),
                        "anomaly": v.get("anomaly", v.get("flag", "normal")),
                    },
                })
                table_rows.append([
                    v.get("name", v.get("shipName", "Unknown")),
                    v.get("type", v.get("vesselType", "N/A")),
                    f"{lat}, {lon}",
                    str(v.get("speed", v.get("sog", "N/A"))),
                    v.get("anomaly", v.get("flag", "normal")),
                ])

        if features:
            components.append({
                "type": "map",
                "engine": "leaflet",
                "geojson": {"type": "FeatureCollection", "features": features},
                "center": [features[0]["geometry"]["coordinates"][1], features[0]["geometry"]["coordinates"][0]],
                "zoom": 6,
            })

        if table_rows:
            components.append({
                "type": "table",
                "headers": ["Vessel", "Type", "Position", "Speed", "Status"],
                "rows": table_rows[:20],
            })

    return components


# ---------------------------------------------------------------------------
# Aircraft Tracking transformer (Leaflet map)
# ---------------------------------------------------------------------------


def _transform_aircraft(tool: str, data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Transform aircraft tracking data into Leaflet map."""
    components = []
    states = data.get("states", [])
    if isinstance(states, list) and len(states) > 0:
        features = []
        for s in states[:100]:
            lat, lng = s.get("lat"), s.get("lng")
            if lat and lng:
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [float(lng), float(lat)]},
                    "properties": {
                        "callsign": s.get("callsign", "N/A"),
                        "origin": s.get("origin_country", "Unknown"),
                        "altitude": s.get("alt", "N/A"),
                        "speed": s.get("spd", "N/A"),
                        "track": s.get("track", "N/A"),
                    },
                })
        if features:
            components.append({
                "type": "map",
                "engine": "leaflet",
                "geojson": {"type": "FeatureCollection", "features": features},
                "center": [features[0]["geometry"]["coordinates"][1], features[0]["geometry"]["coordinates"][0]],
                "zoom": 5,
            })
    return components


# ---------------------------------------------------------------------------
# Sentiment Analysis transformer (ECharts donut + keyword table)
# ---------------------------------------------------------------------------


def _transform_sentiment(tool: str, data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Transform sentiment data into ECharts donut + keyword table."""
    components = []

    # Donut chart for sentiment distribution
    sentiment = data.get("sentiment", data.get("summary", data.get("distribution", data)))
    if isinstance(sentiment, dict):
        positive = float(sentiment.get("positive", sentiment.get("Positive", 0)))
        negative = float(sentiment.get("negative", sentiment.get("Negative", 0)))
        neutral = float(sentiment.get("neutral", sentiment.get("Neutral", 0)))

        if positive or negative or neutral:
            components.append({
                "type": "chart",
                "engine": "echarts",
                "options": {
                    "title": {"text": "Sentiment Distribution", "left": "center", "textStyle": {"color": "#e0e0e0"}},
                    "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
                    "series": [{
                        "type": "pie",
                        "radius": ["45%", "70%"],
                        "center": ["50%", "55%"],
                        "data": [
                            {"value": round(positive, 2), "name": "Positive", "itemStyle": {"color": "#26a69a"}},
                            {"value": round(negative, 2), "name": "Negative", "itemStyle": {"color": "#ef5350"}},
                            {"value": round(neutral, 2), "name": "Neutral", "itemStyle": {"color": "#ffa726"}},
                        ],
                        "label": {"color": "#e0e0e0"},
                    }],
                    "darkMode": True,
                    "backgroundColor": "transparent",
                },
            })

    # Excerpts table
    excerpts = data.get("excerpts", data.get("articles", data.get("results", [])))
    if isinstance(excerpts, list) and len(excerpts) > 0:
        rows = []
        for art in excerpts[:10]:
            title = art.get("title", art.get("headline", "N/A"))
            sentiment_label = art.get("sentiment", art.get("label", "N/A"))
            url = art.get("url", art.get("link", ""))
            rows.append([title[:80], sentiment_label, url[:60] if url else ""])
        if rows:
            components.append({
                "type": "table",
                "headers": ["Article", "Sentiment", "Source"],
                "rows": rows,
            })

    return components


# ---------------------------------------------------------------------------
# Regime Detection transformer
# ---------------------------------------------------------------------------


def _transform_regime(tool: str, data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Transform regime detection data."""
    components = []
    regime = data.get("regime", data.get("current_regime", data.get("state", {})))
    if isinstance(regime, dict):
        state = regime.get("state", regime.get("regime", "Unknown"))
        confidence = regime.get("confidence", regime.get("probability", 0))
        components.append({
            "type": "markdown",
            "data": f"## 📊 Current Market Regime: **{state}**\n\nConfidence: **{float(confidence)*100:.1f}%**" if isinstance(confidence, (int, float)) else f"## 📊 Current Market Regime: **{state}**",
        })

    # Table of asset correlations
    correlations = data.get("correlations", data.get("correlation_matrix", {}))
    if isinstance(correlations, dict) and len(correlations) > 0:
        rows = []
        for k, v in correlations.items():
            rows.append([k, str(round(float(v), 3) if isinstance(v, (int, float)) else v)])
        if rows:
            components.append({
                "type": "table",
                "headers": ["Asset", "Correlation"],
                "rows": rows,
            })

    return components


# ---------------------------------------------------------------------------
# Generic transformer — auto-discovers renderable components
# ---------------------------------------------------------------------------


def _transform_generic(tool: str, data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generic transformer — introspects data and auto-discovers renderable components."""
    components = []

    # Check for GeoJSON
    if _has_geojson(data):
        geojson_data = data.get("geojson", data)
        components.append({
            "type": "map",
            "engine": "leaflet",
            "geojson": geojson_data,
            "center": data.get("center", [0, 0]),
            "zoom": data.get("zoom", 5),
        })
        return components

    # Check for ECharts-compatible data
    echarts_data = data.get("echarts", data.get("option", data.get("options", data.get("chart_config", {}))))
    if isinstance(echarts_data, dict) and ("series" in echarts_data or "xAxis" in echarts_data):
        components.append({
            "type": "chart",
            "engine": "echarts",
            "options": {**echarts_data, "darkMode": True, "backgroundColor": "transparent"},
        })
        return components

    # Check for tabular data
    table = _extract_table_candidates(data)
    if table:
        components.append({"type": "table", **table})

    # Fallback: raw JSON dump as markdown code block
    if not components:
        # Render as structured markdown
        md_parts = []
        for k, v in data.items():
            if isinstance(v, (str, int, float, bool)) and not isinstance(v, bool):
                md_parts.append(f"**{k}**: {v}")
            elif isinstance(v, dict):
                inner = ", ".join(f"{ik}: {iv}" for ik, iv in v.items() if not isinstance(iv, (list, dict)))
                md_parts.append(f"**{k}**: {inner}")
        if md_parts:
            components.append({"type": "markdown", "data": "\n\n".join(md_parts)})
        else:
            components.append({
                "type": "markdown",
                "data": f"```json\n{json.dumps(data, indent=2, default=str)[:3000]}\n```",
            })

    return components


# ---------------------------------------------------------------------------
# Component Transformer Registry
# ---------------------------------------------------------------------------

_COMPONENT_TRANSFORMERS: Dict[str, Callable] = {
    "get_technical_analysis": _transform_technical_analysis,
    "get_market_history": _transform_technical_analysis,  # OHLCV data → ECharts candlestick chart
    "get_market_quote": _transform_market_quote,
    "get_vessel_intelligence": _transform_vessel_intel,
    "get_aircraft_tracking": _transform_aircraft,
    "get_sentiment_analysis": _transform_sentiment,
    "get_market_regime": _transform_regime,
}
