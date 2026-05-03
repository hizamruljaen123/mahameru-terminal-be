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
    Consolidates generic data into tabs, while keeping 'card' components 
    (like Fundamental/Technical summaries) at the top level for prominence.
    """
    components: List[Dict[str, Any]] = []

    # 1. Main AI message at the top
    if message:
        components.append({
            "type": "markdown",
            "data": message,
        })
    # 2. Group tools for potential comparison
    from collections import defaultdict
    groups = defaultdict(list)
    remaining_results = []
    
    COMPARISON_TOOLS = {
        "get_technical_analysis": "Technical Analysis Comparison",
        "get_entity_analysis": "Fundamental Analysis Comparison",
        "get_corporate_intel": "Fundamental Analysis Comparison",
        "get_market_quote": "Market Price Comparison"
    }

    for result in tool_results:
        tool_name = result.get("tool", "unknown")
        if not result.get("success"):
            components.append({
                "type": "markdown",
                "data": f"⚠️ **{tool_name}**: {result.get('error', 'Unknown error')}",
            })
            continue
        
        if tool_name in COMPARISON_TOOLS:
            groups[COMPARISON_TOOLS[tool_name]].append(result)
        else:
            remaining_results.append(result)

    # 3. Process grouped comparisons
    for title, group_data in groups.items():
        if len(group_data) > 1:
            # Create a unified table
            comp_table = _transform_comparison_table(title, group_data)
            if comp_table:
                components.append(comp_table)
        else:
            # Only one result, treat as normal card
            remaining_results.append(group_data[0])

    # 4. Process remaining individual tool results
    tool_tabs = []
    for result in remaining_results:
        tool_name = result.get("tool", "unknown")
        data = result.get("data", {})
        transformer = _COMPONENT_TRANSFORMERS.get(tool_name, _transform_generic)
        
        try:
            comps = transformer(tool_name, data)
            
            # Humanize tool name
            label = tool_name.replace("get_", "").replace("run_", "").replace("_", " ").title()
            if label == "Ta": label = "Technical Analysis"
            
            for i, comp in enumerate(comps):
                # RULE: Cards go to top-level, everything else to tabs
                if comp.get("type") == "card" or comp.get("type") == "cards":
                    components.append(comp)
                elif comp.get("type") == "tabs":
                    for subtab in comp.get("tabs", []):
                        tool_tabs.append(subtab)
                else:
                    title = label if i == 0 else f"{label} ({i+1})"
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


def _transform_comparison_table(title: str, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge multiple analysis results into a single comparison table."""
    headers = ["Metric"]
    rows_map = {} # label -> [val1, val2, ...]
    
    for res in results:
        data = res.get("data", {})
        tool = res.get("tool", "")
        
        # Get symbol
        symbol = data.get("symbol", "N/A")
        if tool == "get_corporate_intel" and "info" in data:
            symbol = data["info"].get("symbol", symbol)
        
        headers.append(symbol)
        
        # Extract metrics based on tool type
        metrics = []
        if "technical" in title.lower():
            current = data.get("current", {})
            sig = data.get("signals", {}).get("verdict", "N/A")
            metrics = [
                ("Signal", sig),
                ("RSI (14)", current.get("rsi14", current.get("rsi", "N/A"))),
                ("MACD", current.get("macd", "N/A")),
                ("ADX", current.get("adx", "N/A")),
            ]
        elif "fundamental" in title.lower():
            # Handle both entity and corporate structure
            if "info" in data and "insider_transactions" in data:
                info = data.get("info", {})
                price = info.get("currentPrice", "N/A")
                mkt_cap = info.get("marketCap", "N/A")
                pe = info.get("trailingPE", "N/A")
                dy = info.get("dividendYield", 0)
                if isinstance(dy, (int, float)): dy = f"{dy*100:.2f}%"
            else:
                info = data.get("data", data)
                price = info.get("price", "N/A")
                mkt_cap = info.get("market_cap", "N/A")
                pe = info.get("trailing_pe", "N/A")
                dy = info.get("dividend_yield", 0)
                if isinstance(dy, (int, float)): dy = f"{dy*100:.2f}%"
            
            metrics = [
                ("Price", price),
                ("Market Cap", mkt_cap),
                ("P/E Ratio", pe),
                ("Div Yield", dy),
            ]
        elif "price" in title.lower():
            quote = data.get("quote", data.get("data", data))
            price = quote.get("regularMarketPrice", quote.get("price", "N/A"))
            change = quote.get("regularMarketChangePercent", quote.get("change_pct", "N/A"))
            metrics = [
                ("Last Price", price),
                ("Change (%)", f"{change:+.2f}%" if isinstance(change, (int, float)) else change),
            ]

        for label, val in metrics:
            if label not in rows_map:
                rows_map[label] = []
            # Align with previous results if some metric missing (though unlikely here)
            while len(rows_map[label]) < (len(headers) - 2):
                rows_map[label].append("N/A")
            
            # Format value
            if isinstance(val, float): val = round(val, 2)
            rows_map[label].append(str(val))

    # Convert rows_map to list
    final_rows = []
    for label, vals in rows_map.items():
        final_rows.append([label] + vals)

    return {
        "type": "table",
        "title": title,
        "headers": headers,
        "rows": final_rows
    }


# ---------------------------------------------------------------------------
# Technical Analysis transformer (Now returns a Card for analysis)
# ---------------------------------------------------------------------------


def _transform_technical_analysis(tool: str, data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Transform TA data. 
    If tool is 'get_technical_analysis', returns a summary CARD.
    If tool is 'get_market_history', returns an ECharts OHLCV chart.
    """
    symbol = data.get("symbol", "N/A")

    # CASE A: If it's just market history, show the chart
    if tool == "get_market_history":
        ohlcv = data.get("ohlcv", data.get("history", []))
        if not ohlcv:
            return [{"type": "markdown", "data": f"No history found for {symbol}"}]
        
        # Reuse logic for building chart (omitted here for brevity, assuming existing logic)
        # For now, let's use a simplified version or the one above if we can refactor.
        # But wait, I'll just keep the original logic for history.
        return _transform_history_chart(symbol, data)

    # CASE B: If it's the analysis tool, return a CARD as requested
    signals = data.get("signals", {})
    verdict = signals.get("verdict", "NEUTRAL")
    current = data.get("current", {})
    
    rsi = current.get("rsi14", current.get("rsi", "N/A"))
    macd = current.get("macd", "N/A")
    adx = current.get("adx", "N/A")
    
    fields = [
        {"label": "Signal", "value": verdict},
        {"label": "RSI (14)", "value": str(round(rsi, 2)) if isinstance(rsi, (int, float)) else rsi},
        {"label": "MACD", "value": str(round(macd, 4)) if isinstance(macd, (int, float)) else macd},
        {"label": "ADX", "value": str(round(adx, 2)) if isinstance(adx, (int, float)) else adx},
    ]
    
    sr = data.get("support_resistance", {})
    if sr:
        supports = sr.get("supports", [])
        if supports: fields.append({"label": "Support", "value": str(round(supports[0], 2))})
        resistances = sr.get("resistances", [])
        if resistances: fields.append({"label": "Resistance", "value": str(round(resistances[0], 2))})

    return [{
        "type": "card",
        "title": f"Technical Analysis: {symbol}",
        "subtitle": "Core Signals & Indicators",
        "fields": fields,
        "color": "#22d3ee"
    }]


def _transform_history_chart(symbol: str, data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Transform OHLCV data into an ECharts candlestick chart."""
    ohlcv = data.get("ohlcv", data.get("history", []))
    if not isinstance(ohlcv, list) or len(ohlcv) == 0:
        return [{"type": "markdown", "data": f"No historical data for {symbol}"}]

    dates = []
    ohlc_data = []
    volume_data = []
    
    # Take last 200 candles for a clean view
    for row in ohlcv[-200:]:
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

    option = {
        "title": {"text": f"{symbol} Price Action", "left": "center", "textStyle": {"color": "#e0e0e0", "fontSize": 14}},
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "cross"}},
        "grid": [
            {"left": "10%", "right": "10%", "top": "15%", "height": "50%"},
            {"left": "10%", "right": "10%", "top": "70%", "height": "15%"}
        ],
        "xAxis": [
            {"type": "category", "data": dates, "gridIndex": 0, "axisLabel": {"color": "#888", "fontSize": 10, "rotate": 30}},
            {"type": "category", "data": dates, "gridIndex": 1, "axisLabel": {"show": False}}
        ],
        "yAxis": [
            {"type": "value", "scale": True, "gridIndex": 0, "axisLabel": {"color": "#888", "fontSize": 10}},
            {"type": "value", "gridIndex": 1, "axisLabel": {"show": False}, "splitLine": {"show": False}}
        ],
        "series": [
            {
                "name": "Price",
                "type": "candlestick",
                "data": ohlc_data,
                "itemStyle": {"color": "#26a69a", "color0": "#ef5350", "borderColor": "#26a69a", "borderColor0": "#ef5350"},
                "xAxisIndex": 0, "yAxisIndex": 0,
            },
            {
                "name": "Volume",
                "type": "bar",
                "data": volume_data,
                "xAxisIndex": 1, "yAxisIndex": 1,
                "itemStyle": {"color": "rgba(255, 255, 255, 0.15)"}
            }
        ],
        "dataZoom": [{"type": "inside", "xAxisIndex": [0, 1], "start": 50, "end": 100}]
    }

    return [{
        "type": "chart",
        "engine": "echarts",
        "options": option
    }]


# ---------------------------------------------------------------------------
# Entity / Fundamental Analysis transformer
# ---------------------------------------------------------------------------


def _transform_entity_analysis(tool: str, data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Transform fundamental data into a summary CARD."""
    # Handle differences between get_entity_analysis and get_corporate_intel structures
    if "info" in data and "insider_transactions" in data:
        # Structure from get_corporate_intel
        info = data.get("info", {})
        symbol = info.get("symbol", "N/A")
        name = info.get("shortName", info.get("longName", "N/A"))
        price = info.get("currentPrice", info.get("previousClose"))
        # yfinance info doesn't always have change_pct directly
        change_pct = 0.0
        if "currentPrice" in info and "previousClose" in info and info["previousClose"]:
            change_pct = ((info["currentPrice"] - info["previousClose"]) / info["previousClose"]) * 100
        mkt_cap = info.get("marketCap")
        pe = info.get("trailingPE")
        dy = info.get("dividendYield", 0)
    else:
        # Structure from get_entity_analysis
        info = data.get("data", data)
        symbol = info.get("symbol", "N/A")
        name = info.get("name", "N/A")
        price = info.get("price")
        change_pct = info.get("change_pct", 0.0)
        mkt_cap = info.get("market_cap")
        pe = info.get("trailing_pe")
        dy = info.get("dividend_yield")
    
    # Format large numbers
    def format_mkt_cap(val):
        if not val: return "N/A"
        if val >= 1e12: return f"{val/1e12:.2f}T"
        if val >= 1e9: return f"{val/1e9:.2f}B"
        return f"{val/1e6:.2f}M"

    fields = [
        {"label": "Price", "value": f"{price} ({change_pct:+.2f}%)" if price else "N/A"},
        {"label": "Market Cap", "value": format_mkt_cap(mkt_cap)},
        {"label": "P/E Ratio", "value": f"{pe:.2f}" if pe else "N/A"},
        {"label": "Div Yield", "value": f"{dy*100:.2f}%" if dy else "0.00%"},
        {"label": "Sector", "value": info.get("sector", "N/A")},
        {"label": "Industry", "value": info.get("industry", "N/A")},
    ]

    return [{
        "type": "card",
        "title": f"Fundamental: {name} ({symbol})",
        "subtitle": "Company Profile & Key Metrics",
        "fields": fields,
        "color": "#f59e0b"
    }]


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

    # Use a Card instead of Markdown for consistency
    fields = [
        {"label": "Last Price", "value": f"{price}"},
        {"label": "Change", "value": f"{change:+.4f} ({change_pct:+.2f}%)"},
        {"label": "Day Range", "value": f"{quote.get('dayLow')} - {quote.get('dayHigh')}"},
        {"label": "Volume", "value": f"{quote.get('regularMarketVolume', quote.get('volume', 0)):,}"},
    ]

    components.append({
        "type": "card",
        "title": f"Market Quote: {symbol}",
        "subtitle": name,
        "fields": fields,
        "color": "#10b981" if change >= 0 else "#ef4444"
    })

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
    "get_market_history": _transform_technical_analysis,  # Now handles chart logic
    "get_market_quote": _transform_market_quote,
    "get_vessel_intelligence": _transform_vessel_intel,
    "get_aircraft_tracking": _transform_aircraft,
    "get_sentiment_analysis": _transform_sentiment,
    "get_market_regime": _transform_regime,
    "get_entity_analysis": _transform_entity_analysis,
    "get_corporate_intel": _transform_entity_analysis,  # Fundamental focus
}
