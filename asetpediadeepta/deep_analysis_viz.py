"""
deep_analysis_viz.py v2.0 — ECharts Data Formatter
Mengubah hasil analisa menjadi format JSON standar untuk ECharts JS.
Tidak lagi menghasilkan file gambar (matplotlib dihapus total).
"""

import numpy as np
import pandas as pd

# Konstanta warna ECharts Dark Theme
EC_COLORS = [
    "#58a6ff", "#3fb950", "#f85149", "#d29922", "#bc8cff", 
    "#39d2c0", "#f778ba", "#e3b341", "#8b949e", "#484f58"
]

def dates_to_str(idx):
    """Konversi DatetimeIndex ke list string YYYY-MM-DD."""
    if idx is None or len(idx) == 0: return []
    res = []
    for d in idx:
        if isinstance(d, str): res.append(d)
        elif hasattr(d, "strftime"): res.append(d.strftime("%Y-%m-%d"))
        else: res.append(str(d))
    return res

def clean_series(arr):
    """Bersihkan NaN/Inf menjadi null untuk JSON."""
    if arr is None: return []
    result = []
    for v in arr:
        if isinstance(v, (float, np.floating)):
            if np.isnan(v) or np.isinf(v): result.append(None)
            else: result.append(round(float(v), 17)) # Increased precision for institutional metrics
        else:
            result.append(v)
    return result

# ═══════════════════════════════════════════════════════════════════
# FORMAT STANDAR ECHARTS
# ═══════════════════════════════════════════════════════════════════

def fmt_line(title, dates, series_list, mark_lines=None, y_min=None, y_max=None):
    """Format standar untuk Line Chart."""
    return {
        "chartType": "line",
        "title": title,
        "xAxis": dates_to_str(dates),
        "series": [
            {"name": name, "data": clean_series(data)} 
            for name, data in series_list
        ],
        "options": {
            "yAxis": {"min": y_min, "max": y_max},
            **({"markLine": {"data": mark_lines}} if mark_lines else {})
        }
    }

def fmt_bar(title, dates, series_list, y_min=None, y_max=None):
    """Format standar untuk Bar Chart."""
    return {
        "chartType": "bar",
        "title": title,
        "xAxis": dates_to_str(dates),
        "series": [
            {"name": name, "data": clean_series(data)} 
            for name, data in series_list
        ],
        "options": {"yAxis": {"min": y_min, "max": y_max}}
    }

def fmt_scatter(title, dates, series_list):
    """Format standar untuk Scatter Chart."""
    return {
        "chartType": "scatter",
        "title": title,
        "xAxis": dates_to_str(dates),
        "series": [
            {"name": name, "data": clean_series(data), "symbolSize": 6} 
            for name, data in series_list
        ]
    }

def fmt_candlestick(title, dates, o, h, l, c, overlays=None):
    """
    Format khusus Candlestick.
    ECharts butuh data: [open, close, lowest, highest]
    """
    ohlc_data = []
    for i in range(len(c)):
        ohlc_data.append([
            round(float(o[i]), 4), 
            round(float(c[i]), 4), 
            round(float(l[i]), 4), 
            round(float(h[i]), 4)
        ])
    
    series = [{"name": "Price", "type": "candlestick", "data": ohlc_data}]
    
    if overlays:
        for name, data in overlays:
            series.append({"name": name, "type": "line", "data": clean_series(data), "lineStyle": {"width": 1.5}, "symbol": "none"})

    return {
        "chartType": "candlestick",
        "title": title,
        "xAxis": dates_to_str(dates),
        "series": series
    }

def fmt_heatmap(title, x_labels, y_labels, data_matrix):
    """Format untuk Heatmap (misal: Volume Profile)."""
    series_data = []
    for i in range(len(y_labels)):
        for j in range(len(x_labels)):
            val = data_matrix[i][j]
            if not np.isnan(val) and val > 0:
                series_data.append([j, i, round(float(val), 2)])
    
    return {
        "chartType": "heatmap",
        "title": title,
        "xAxis": x_labels,
        "yAxis": y_labels,
        "series": [{"name": "Value", "type": "heatmap", "data": series_data}]
    }

def fmt_gauge(title, value, min_val=0, max_val=100, opts=None):
    """Format untuk Gauge Chart (single value)."""
    return {
        "chartType": "gauge",
        "title": title,
        "xAxis": [],
        "series": [{"name": title, "type": "gauge", "data": [{"value": round(float(value), 2)}]}],
        "options": {"gauge": {"min": min_val, "max": max_val, **(opts or {})}}
    }

def fmt_score_board(title, labels, values):
    """Format untuk Horizontal Bar Chart (Scoring)."""
    return {
        "chartType": "horizontal_bar",
        "title": title,
        "yAxis": labels,
        "series": [{"name": "Score", "type": "bar", "data": [round(float(v), 4) for v in values]}]
    }

def fmt_order_blocks(title, dates, o, h, l, c, ob_df):
    """
    Format khusus Order Blocks (SMC).
    Menampilkan Candlestick + Area untuk OB Zones.
    """
    base = fmt_candlestick(title, dates, o, h, l, c)
    base["chartType"] = "order_blocks"
    
    # Tambahkan data OB (Bearish/Bullish zones)
    ob_data = {
        "bearish": {
            "high": clean_series(ob_df["bearish_ob_high"].values) if "bearish_ob_high" in ob_df.columns else [],
            "low": clean_series(ob_df["bearish_ob_low"].values) if "bearish_ob_low" in ob_df.columns else []
        },
        "bullish": {
            "high": clean_series(ob_df["bullish_ob_high"].values) if "bullish_ob_high" in ob_df.columns else [],
            "low": clean_series(ob_df["bullish_ob_low"].values) if "bullish_ob_low" in ob_df.columns else []
        }
    }
    base["obZones"] = ob_data
    return base

def fmt_fair_value_gaps(title, dates, o, h, l, c, fvg_df):
    """
    Format khusus Fair Value Gaps (FVG).
    Menampilkan Candlestick + Area untuk FVG.
    """
    base = fmt_candlestick(title, dates, o, h, l, c)
    base["chartType"] = "fair_value_gaps"
    
    # Tambahkan data FVG
    fvg_data = {
        "top": clean_series(fvg_df["fvg_top"].values) if "fvg_top" in fvg_df.columns else [],
        "bottom": clean_series(fvg_df["fvg_bottom"].values) if "fvg_bottom" in fvg_df.columns else [],
        "type": clean_series(fvg_df["fvg_type"].values) if "fvg_type" in fvg_df.columns else []
    }
    base["fvgZones"] = fvg_data
    return base

def fmt_liquidity_sweeps(title, dates, o, h, l, c, sweep_df):
    """
    Format khusus Liquidity Sweeps.
    Candlestick + Markers.
    """
    base = fmt_candlestick(title, dates, o, h, l, c)
    base["chartType"] = "liquidity_sweeps"
    
    markers = []
    if "liquidity_sweep" in sweep_df.columns:
        valid = sweep_df[sweep_df["liquidity_sweep"] > 0]
        for idx, row in valid.iterrows():
            # Tentukan posisi marker (bisa di atas high atau bawah low)
            # Default ke high karena biasanya sweep mencari liquidity di atas
            price_pos = float(h[dates.get_loc(idx)]) if idx in dates else float(c[dates.get_loc(idx)])
            markers.append({
                "xAxis": idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx),
                "yAxis": round(price_pos, 4),
                "symbol": "circle",
                "itemStyle": {"color": "#bc8cff"}
            })
    base["markers"] = markers
    return base

def fmt_signal_markers(title, dates, o, h, l, c, signals_df):
    """
    Format khusus Signal Buy/Sell dari Lib2.
    Candlestick + Penanda Panah.
    """
    base = fmt_candlestick(title, dates, o, h, l, c)
    base["chartType"] = "signal_markers"
    
    markers = []
    if isinstance(signals_df, pd.DataFrame):
        for idx, row in signals_df.iterrows():
            if idx not in dates: continue
            d_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
            price_pos = float(c[dates.get_loc(idx)])
            
            # Logic sederhana: 1=Buy (Green), -1=Sell (Red)
            # Kolom bisa 'signal' atau 'buy_signal'/'sell_signal'
            sig_val = row.get("signal", 0)
            if sig_val > 0:
                markers.append({"xAxis": d_str, "yAxis": round(price_pos, 4), "symbol": "arrow", "color": "#3fb950", "label": "BUY"})
            elif sig_val < 0:
                markers.append({"xAxis": d_str, "yAxis": round(price_pos, 4), "symbol": "arrow", "symbolRotate": 180, "color": "#f85149", "label": "SELL"})
    
    base["markers"] = markers
    return base

def fmt_regime_indicators(title, dates, o, h, l, c, regime_df):
    """
    Format khusus Regime-Adaptive Signal.
    Candlestick + Multi-colored markers based on strength.
    """
    base = fmt_candlestick(title, dates, o, h, l, c)
    base["chartType"] = "regime_signal"
    
    markers = []
    if isinstance(regime_df, pd.DataFrame):
        for idx, row in regime_df.iterrows():
            if idx not in dates: continue
            d_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
            price_pos = float(c[dates.get_loc(idx)])
            
            # adaptive_signal = 1 could mean a "major" regime shift
            if row.get("adaptive_signal", 0) > 0:
                markers.append({"xAxis": d_str, "yAxis": round(price_pos, 4), "symbol": "diamond", "color": "#79c0ff", "label": "REGIME"})
            
            # signal_strength: positive=buy, negative=sell
            strength = row.get("signal_strength", 0)
            if strength > 0:
                markers.append({"xAxis": d_str, "yAxis": round(price_pos, 4), "symbol": "pin", "color": "#3fb950", "label": "B"})
            elif strength < 0:
                markers.append({"xAxis": d_str, "yAxis": round(price_pos, 4), "symbol": "pin", "color": "#f85149", "label": "S"})
                
    base["markers"] = markers
    return base

def fmt_inst_phase(title, dates, phase_df):
    """
    Format khusus untuk Instantaneous Phase (Hilbert Transform).
    Menampilkan multi-line untuk komponen InPhase, Quadrature, dll.
    """
    series_list = []
    # Dominant Cycle Period
    if "dcperiod" in phase_df.columns: series_list.append(("DC Period", phase_df["dcperiod"].values))
    # InPhase & Quadrature
    if "inphase" in phase_df.columns: series_list.append(("InPhase", phase_df["inphase"].values))
    if "quadrature" in phase_df.columns: series_list.append(("Quadrature", phase_df["quadrature"].values))
    # Instantaneous Phase Degree
    if "inst_phase_deg" in phase_df.columns: series_list.append(("Phase Deg", phase_df["inst_phase_deg"].values))
    
    return fmt_line(title, dates, series_list)

def fmt_smc_concepts(title, dates, o, h, l, c, smc_df):
    """
    Format khusus SMC (BOS/CHoCH).
    Candlestick + Label Markers.
    """
    base = fmt_candlestick(title, dates, o, h, l, c)
    base["chartType"] = "smc_concepts"
    
    # Pre-calculate main dates as strings for lookup
    date_map = { (d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]): i for i, d in enumerate(dates) }
    
    markers = []
    if isinstance(smc_df, pd.DataFrame):
        for idx, row in smc_df.iterrows():
            d_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
            if d_str not in date_map: continue
            
            i = date_map[d_str]
            price_pos = float(c[i])
            
            if row.get("break_of_structure", 0) > 0:
                markers.append({
                    "xAxis": dates_to_str(dates)[i], "yAxis": round(price_pos, 4),
                    "label": "BOS", "color": "#58a6ff"
                })
            if row.get("change_of_character", 0) > 0:
                markers.append({
                    "xAxis": dates_to_str(dates)[i], "yAxis": round(price_pos, 4),
                    "label": "CHoCH", "color": "#d29922"
                })
    base["markers"] = markers
    return base


# ═══════════════════════════════════════════════════════════════════
# EXTRACTOR: MENGUBAH DATAFRAME HASIL ANALISA KE JSON
# ═══════════════════════════════════════════════════════════════════

def extract_candlestick_master(df, core, sr):
    """Chart 1: Candlestick + EMA + BBands + S/R."""
    overlays = []
    if core is not None:
        overlays.append(("EMA 9", core["ema_9"].values))
        overlays.append(("EMA 50", core["ema_50"].values))
        overlays.append(("EMA 200", core["ema_200"].values))
        overlays.append(("BB Upper", core["bbands_upper"].values))
        overlays.append(("BB Lower", core["bbands_lower"].values))
    
    mark_lines = []
    if sr is not None:
        sv = sr["dynamic_support"].dropna()
        rv = sr["dynamic_resistance"].dropna()
        if len(sv): mark_lines.append({"yAxis": round(float(sv.iloc[-1]), 2), "lineStyle": {"color": "#3fb950"}, "label": {"formatter": f"Support: {sv.iloc[-1]:.2f}"}})
        if len(rv): mark_lines.append({"yAxis": round(float(rv.iloc[-1]), 2), "lineStyle": {"color": "#f85149"}, "label": {"formatter": f"Resist: {rv.iloc[-1]:.2f}"}})
    
    return fmt_candlestick(
        f"Price Action", df.index, 
        df["open"].values, df["high"].values, df["low"].values, df["close"].values, 
        overlays=overlays
    ) | {"options": {"markLine": {"data": mark_lines}}}

def extract_volume_obv(df, core):
    """Chart 2: Volume + OBV."""
    # Menghitung warna volume (hijau jika close >= open, merah jika sebaliknya)
    # Ini bisa digunakan di itemStyle jika ingin volume bar berwarna dinamis
    vol_colors = ["#3fb950" if df["close"].iat[i] >= df["open"].iat[i] else "#f85149" for i in range(len(df))]
    
    return {
        "chartType": "mixed_bar_line",
        "title": "Volume + OBV",
        "xAxis": dates_to_str(df.index),
        "series": [
            {
                "name": "Volume", 
                "type": "bar", 
                "data": clean_series(df["volume"].values), 
                "itemStyle": {"color": "#58a6ff", "opacity": 0.5}
            },
            {
                "name": "OBV", 
                "type": "line", 
                "data": clean_series(core["obv"].values) if core is not None else [], 
                "yAxisIndex": 1,
                "lineStyle": {"width": 2}
            }
        ],
        "options": {
            "yAxis": [
                {"type": "value", "name": "Volume"}, 
                {"type": "value", "name": "OBV", "position": "right", "splitLine": {"show": False}}
            ]
        }
    }


def extract_macd(core):
    """Chart 3: MACD."""
    if core is None: return {"chartType": "line", "title": "MACD", "xAxis": [], "series": []}
    hist_data = [{"value": round(float(v), 4), "itemStyle": {"color": "#3fb950" if v >= 0 else "#f85149"}} for v in core["macd_hist"].values]
    return {
        "chartType": "mixed_bar_line",
        "title": "MACD (12, 26, 9)",
        "xAxis": dates_to_str(core.index),
        "series": [
            {"name": "MACD", "type": "line", "data": clean_series(core["macd"].values)},
            {"name": "Signal", "type": "line", "data": clean_series(core["macd_signal"].values), "lineStyle": {"type": "dashed"}},
            {"name": "Histogram", "type": "bar", "data": hist_data, "yAxisIndex": 1}
        ],
        "options": {"yAxis": [{"type": "value"}, {"type": "value", "position": "right"}]}
    }

def extract_rsi_multi(core):
    """Chart 4: RSI Multi-Period."""
    if core is None: return {"chartType": "line", "title": "RSI", "xAxis": [], "series": []}
    return fmt_line("RSI Multi-Period (6, 14, 21)", core.index, [
        ("RSI 6", core["rsi_6"].values),
        ("RSI 14", core["rsi_14"].values),
        ("RSI 21", core["rsi_21"].values)
    ], mark_lines=[
        {"yAxis": 70, "lineStyle": {"color": "#f85149", "type": "dashed"}},
        {"yAxis": 30, "lineStyle": {"color": "#3fb950", "type": "dashed"}}
    ], y_min=0, y_max=100)

def extract_adx_di(core):
    """Chart 5: ADX + DI."""
    if core is None: return {"chartType": "line", "title": "ADX", "xAxis": [], "series": []}
    return fmt_line("ADX + DI — Trend Strength", core.index, [
        ("ADX", core["adx"].values),
        ("+DI", core["plus_di"].values),
        ("-DI", core["minus_di"].values)
    ], mark_lines=[{"yAxis": 25, "lineStyle": {"color": "#d29922", "type": "dotted"}}])

def extract_bollinger_squeeze(bsi, core):
    """Chart 6: Bollinger Squeeze Intensity."""
    if bsi is None: return {"chartType": "line", "title": "Bollinger Squeeze", "xAxis": [], "series": []}
    series_list = [("Squeeze Intensity", bsi)]
    if core is not None:
        bb_w = (core["bbands_upper"] - core["bbands_lower"]) / core["bbands_middle"]
        series_list.append(("BB Width", bb_w.values))
    return fmt_line("Bollinger Squeeze Intensity + BB Width", core.index, series_list)

def extract_spectral_momentum(sms):
    """Chart 7: Spectral Momentum."""
    if sms is None: return {"chartType": "line", "title": "Spectral Momentum", "xAxis": [], "series": []}
    # sms adalah numpy array, kita butuh index dari global context. Kita return data mentah saja.
    return {
        "chartType": "raw_array",
        "title": "Spectral Momentum Score",
        "data": clean_series(sms)
    }

def extract_master_signal(mss):
    """Chart 8: Master Signal Score."""
    if mss is None: return {"chartType": "line", "title": "Master Signal", "xAxis": [], "series": []}
    signal_colors = []
    for val in mss["mss_total"].values:
        signal_colors.append({"value": round(float(val), 2), "itemStyle": {"color": "#3fb950" if val > 2 else "#f85149" if val < -2 else "#58a6ff"}})
    
    return {
        "chartType": "mixed_bar_line",
        "title": "Master Signal Score (10 Subsystems)",
        "xAxis": dates_to_str(mss.index),
        "series": [
            {"name": "MSS Total", "type": "bar", "data": signal_colors},
        ],
        "options": {"markLine": {"data": [
            {"yAxis": 5, "lineStyle": {"color": "#3fb950", "type": "dashed"}, "label": {"formatter": "Strong Buy"}},
            {"yAxis": -5, "lineStyle": {"color": "#f85149", "type": "dashed"}, "label": {"formatter": "Strong Sell"}}
        ]}}
    }

def extract_hurst_fractal(regime1, fracdim):
    """Chart 9: Hurst + Fractal Dimension."""
    if regime1 is None: return {"chartType": "line", "title": "Hurst/Fractal", "xAxis": [], "series": []}
    series_list = [("Hurst Exponent", regime1["hurst_exponent"].values)]
    if fracdim is not None: series_list.append(("Fractal Dimension", fracdim.values))
    return fmt_line("Hurst Exponent + Fractal Dimension", regime1.index, series_list, 
                    mark_lines=[{"yAxis": 0.5, "lineStyle": {"color": "#d29922", "type": "dashed"}, "label": {"formatter": "Random Walk"}}])

def extract_volume_profile(vprof, df):
    """Chart 10: Volume Profile (Horizontal Bar)."""
    if vprof is None: return {"chartType": "heatmap", "title": "Vol Profile", "xAxis": [], "series": []}
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    nb = 50; pn = np.min(l[-200:]); px = np.max(h[-200:])
    edges = np.linspace(pn, px, nb+1); centers = [(edges[i]+edges[i+1])/2 for i in range(nb)]
    prof = np.zeros(nb)
    for i in range(max(0, len(df)-200), len(df)):
        tp = (h[i]+l[i]+c[i])/3; bi = np.clip(int((tp-pn)/(px-pn+1e-10)*nb), 0, nb-1); prof[bi] += df["volume"].iloc[i]
    
    y_labels = [f"{c:.2f}" for c in centers]
    x_labels = ["Volume"]
    
    return fmt_heatmap("Volume Profile", x_labels, y_labels, [prof.tolist()])

def extract_complexity(df, pentperm, pent, kolm, mii, mi):
    """Chart 11: Kompleksitas & Entropy."""
    return {
        "chartType": "raw_multi_array",
        "title": "Complexity & Information Theory Metrics",
        "xAxis": dates_to_str(df.index),
        "series": {
            "permutation_entropy": clean_series(pentperm),
            "price_entropy": clean_series(pent),
            "kolmogorov": clean_series(kolm.values if kolm is not None else (kolm if kolm is not None else [])),
            "market_inefficiency": clean_series(mii),
            "mutual_info": clean_series(mi.iloc[:, 0].values if hasattr(mi, 'iloc') else [])
        }
    }

def extract_kolmogorov(df, kolm_df):
    """Chart 22: Kolmogorov Complexity (LZ77)."""
    if kolm_df is None: return None
    
    # Reconstruct index if needed
    if isinstance(kolm_df, list):
        kolm_df = pd.DataFrame(kolm_df)
        if "index" in kolm_df.columns:
            kolm_df = kolm_df.set_index("index")
    
    # Align with main df index to prevent length mismatch
    kolm_df = kolm_df.reindex(df.index)
    
    series_list = []
    if "kolmogorov_complexity" in kolm_df.columns:
        series_list.append(("Complexity", kolm_df["kolmogorov_complexity"].values))
        
    if not series_list: return None
    # Use localized scale to see extremely small variations (e.g. 0.999 vs 0.998)
    return fmt_line("Kolmogorov Complexity (LZ77)", df.index, series_list, y_min=0.97, y_max=1.0)

def extract_mutual_info(df, mi_df):
    """Chart 23: Mutual Information (Price-Volume Interaction)."""
    if mi_df is None: return None
    
    # Reconstruct index if needed
    if isinstance(mi_df, list):
        mi_df = pd.DataFrame(mi_df)
        if "index" in mi_df.columns:
            mi_df = mi_df.set_index("index")
            
    # Align with main df index
    mi_df = mi_df.reindex(df.index)
    
    series_list = []
    if "mi_price_volume" in mi_df.columns:
        series_list.append(("Mutual Info", mi_df["mi_price_volume"].values))
        
    if not series_list: return None
    return fmt_line("Mutual Information (Price ↔ Volume)", df.index, series_list)

def extract_order_blocks(df, ob_df):
    """Chart 12: Order Blocks (SMC)."""
    if ob_df is None: return None
    return fmt_order_blocks(
        "Order Blocks Detection", df.index,
        df["open"].values, df["high"].values, df["low"].values, df["close"].values,
        ob_df
    )

def extract_fair_value_gaps(df, fvg_df):
    """Chart 13: Fair Value Gaps (SMC)."""
    if fvg_df is None: return None
    return fmt_fair_value_gaps(
        "Fair Value Gaps Analysis", df.index,
        df["open"].values, df["high"].values, df["low"].values, df["close"].values,
        fvg_df
    )

def extract_liquidity_sweeps(df, sweep_df):
    """Chart 14: Liquidity Sweeps (SMC)."""
    if sweep_df is None: return None
    return fmt_liquidity_sweeps(
        "Liquidity Sweeps Analysis", df.index,
        df["open"].values, df["high"].values, df["low"].values, df["close"].values,
        sweep_df
    )

def extract_smc_concepts(df, smc_df):
    """Chart 15: SMC Structural Analysis."""
    if smc_df is None: return None
    return fmt_smc_concepts(
        "SMC Structural Analysis (BOS/CHoCH)", df.index,
        df["open"].values, df["high"].values, df["low"].values, df["close"].values,
        smc_df
    )

def extract_lib2_signals(df, sig_df):
    """Chart 17: Signal Event Markers."""
    # Selalu return candlestick walaupun data signals kosong agar tidak "hitam"
    return fmt_signal_markers(
        "Signal Events Scanner (Lib2)", df.index,
        df["open"].values, df["high"].values, df["low"].values, df["close"].values,
        sig_df
    )

def extract_regime_signals(df, regime_df):
    """Chart 18: Regime-Adaptive Signals."""
    return fmt_regime_indicators(
        "Regime-Adaptive Signal Analysis", df.index,
        df["open"].values, df["high"].values, df["low"].values, df["close"].values,
        regime_df
    )

def extract_inst_phase(df, phase_df):
    """Chart 21: Instantaneous Phase Hilbert Analysis."""
    if phase_df is None: return None
    
    # Reconstruct index if needed
    if isinstance(phase_df, list):
        phase_df = pd.DataFrame(phase_df)
        if "index" in phase_df.columns:
            phase_df = phase_df.set_index("index")
    
    # Align with main df index
    phase_df = phase_df.reindex(df.index)
        
    return fmt_inst_phase("Instantaneous Phase Hilbert Analysis (Lib3)", df.index, phase_df)

def extract_manifold(df, manifold_df):
    """Chart 24: Manifold Embedding (Topology)."""
    if manifold_df is None: return None
    if isinstance(manifold_df, list):
        manifold_df = pd.DataFrame(manifold_df)
        if "index" in manifold_df.columns:
            manifold_df = manifold_df.set_index("index")
    manifold_df = manifold_df.reindex(df.index)
    
    series_list = []
    if "nn_distance" in manifold_df.columns:
        series_list.append(("NN Distance", manifold_df["nn_distance"].values))
    if "recurrence_rate" in manifold_df.columns:
        series_list.append(("Recurrence Rate", manifold_df["recurrence_rate"].values))
    
    if not series_list: return None
    
    # Dual Y-axis: Distance (left), Rate (right)
    chart = fmt_line("Price Manifold Embedding (Takens)", df.index, series_list)
    chart["chartType"] = "topology"
    if len(chart["series"]) > 1:
        chart["series"][1]["yAxisIndex"] = 1
    
    chart["options"] = {
        "yAxis": [
            {"name": "Dist", "type": "value", "position": "left", "scale": True},
            {"name": "Rate", "type": "value", "position": "right", "min": 0, "max": 1, "splitLine": {"show": False}}
        ]
    }
    return chart

def extract_tail_risk(df, risk_df):
    """Chart 25: Tail Risk (Cornish-Fisher VaR)."""
    if risk_df is None: return None
    if isinstance(risk_df, list):
        risk_df = pd.DataFrame(risk_df)
        if "index" in risk_df.columns:
            risk_df["index"] = pd.to_datetime(risk_df["index"])
            risk_df = risk_df.set_index("index")
    
    # Force alignment with main price index to avoid empty data due to date formatting
    risk_df = risk_df.reindex(df.index)
    
    series_list = []
    if "cornish_fisher_var_95" in risk_df.columns:
        series_list.append(("VaR 95%", risk_df["cornish_fisher_var_95"].values))
    if "cornish_fisher_var_99" in risk_df.columns:
        series_list.append(("VaR 99%", risk_df["cornish_fisher_var_99"].values))
        
    if not series_list: return None
    
    chart = fmt_line("Tail Risk (Cornish-Fisher Var)", df.index, series_list)
    chart["chartType"] = "risk" # Use the new specialized "Blood Red" risk renderer
    return chart

def extract_anomalies(df, anomaly_df):
    """Chart 26: Price Anomalies (Isolation Forest) with Stats."""
    if anomaly_df is None: return None
    if isinstance(anomaly_df, list):
        anomaly_df = pd.DataFrame(anomaly_df)
        if "index" in anomaly_df.columns:
            anomaly_df["index"] = pd.to_datetime(anomaly_df["index"])
            anomaly_df = anomaly_df.set_index("index")
    anomaly_df = anomaly_df.reindex(df.index)
    
    score = anomaly_df["anomaly_score"].values
    is_anomaly = anomaly_df["is_anomaly"].values.astype(bool)
    
    chart = fmt_line("Price Anomalies (Isolation Forest)", df.index, [("Anomaly Score", score)])
    
    # Calculate markers
    markers = []
    for i, is_a in enumerate(is_anomaly):
        if is_a and i < len(df.index):
            idx_val = df.index[i]
            markers.append({
                "xAxis": idx_val.strftime('%Y-%m-%d %H:%M:%S') if hasattr(idx_val, 'strftime') else str(idx_val),
                "value": float(score[i])
            })
    
    # Calculate stats for the Pie chart overlay
    total = len(is_anomaly[~np.isnan(score)])
    if total > 0:
        count_true = int(np.sum(is_anomaly[is_anomaly == True]))
        pct_true = (count_true / total) * 100
        stats = [
            {"name": "Normal", "value": total - count_true},
            {"name": "Anomaly", "value": count_true}
        ]
    else:
        stats = []
        pct_true = 0

    chart["chartType"] = "anomaly"
    chart["markers"] = markers
    chart["stats"] = stats
    chart["anomaly_percentage"] = pct_true
    return chart

def extract_position_sizer(df, sizer_df):
    """Chart 27: Dynamic Position Sizer."""
    if sizer_df is None: return None
    if isinstance(sizer_df, list):
        sizer_df = pd.DataFrame(sizer_df)
        if "index" in sizer_df.columns:
            sizer_df["index"] = pd.to_datetime(sizer_df["index"])
            sizer_df = sizer_df.set_index("index")
    sizer_df = sizer_df.reindex(df.index)
    
    series_list = []
    if "position_size_pct" in sizer_df.columns:
        series_list.append(("Pos Size %", sizer_df["position_size_pct"].values))
    if "atr_zscore" in sizer_df.columns:
        series_list.append(("ATR Z-Score", sizer_df["atr_zscore"].values))
        
    if not series_list: return None
    
    chart = fmt_line("Dynamic Position Sizer", df.index, series_list)
    chart["chartType"] = "mixed"
    if len(chart["series"]) > 1:
        chart["series"][0]["yAxisIndex"] = 1 # Size % on right
        chart["series"][1]["yAxisIndex"] = 0 # Z-Score on left
    
    chart["options"] = {
        "yAxis": [
            {"name": "Z-Score", "type": "value", "position": "left"},
            {"name": "Size %", "type": "value", "position": "right", "min": 0, "max": 1, "splitLine": {"show": False}}
        ]
    }
    return chart

def extract_elliott_patterns(df, hs, dbl, wedge, ew, smc):
    """Chart 12: Chart Patterns Scatter."""
    if ew is None: return {"chartType": "scatter", "title": "Patterns", "xAxis": [], "series": []}
    
    c = df["close"].values; dates = df.index
    base_line = [("Price", c)]
    
    # Elliott wave labels
    ew_markers = []
    if ew is not None:
        for i in range(len(c)):
            pos = ew["elliott_wave_position"].iloc[i]
            if pos in [1,2,3,4,5]:
                ew_markers.append({"value": [dates_to_str(dates)[i], round(float(c[i]), 2)], "symbol": str(pos)})
    
    return {
        "chartType": "line_with_markers",
        "title": "Elliott Wave & Chart Patterns",
        "xAxis": dates_to_str(dates),
        "series": [{"name": "Price", "data": clean_series(c)}],
        "markers": ew_markers
    }

def extract_composite_lib2(lib2):
    """Chart 16: Deep OHLCV Scoreboard."""
    if lib2 is None: return None
    
    # Deteksi jika ini adalah format transposed summary (list of dict dengan key 'index')
    if isinstance(lib2, list) and len(lib2) > 0 and "index" in lib2[0]:
        data_map = { row["index"]: next((v for k, v in row.items() if k != "index"), 0) for row in lib2 }
        target_scores = [
            "momentum_score", "trend_score", "mean_reversion_score", 
            "volume_score", "volatility_score", "pattern_score",
            "composite_long_score", "composite_short_score"
        ]
        labels = [s.replace("_score", "").upper() for s in target_scores if s in data_map]
        values = [data_map[s] for s in target_scores if s in data_map]
        
        if not labels: return None
        return fmt_score_board("Composite Scores (Lib2)", labels, values)
        
    # Format DataFrame (Full Series)
    if isinstance(lib2, pd.DataFrame):
        scores = ["momentum_score","trend_score","mean_reversion_score","volume_score","volatility_score","pattern_score"]
        series_list = [(s.replace("_score",""), lib2[s].values) for s in scores if s in lib2.columns]
        return fmt_line("Composite Sub-Scores (Lib2)", lib2.index, series_list)
    
    return None


def extract_dominant_cycle(df, cyc_df):
    """Chart 19: Dominant Cycle Analysis."""
    if cyc_df is None: return None
    
    # Reconstruct index if needed
    if isinstance(cyc_df, list):
        cyc_df = pd.DataFrame(cyc_df)
        if "index" in cyc_df.columns:
            cyc_df = cyc_df.set_index("index")
    
    # Align
    cyc_df = cyc_df.reindex(df.index)
    
    series_list = []
    if "dom_period" in cyc_df.columns: series_list.append(("Period", cyc_df["dom_period"].round(2).values))
    if "dom_power" in cyc_df.columns: series_list.append(("Power", cyc_df["dom_power"].round(2).values))
    if "phase_deg" in cyc_df.columns: series_list.append(("Phase", cyc_df["phase_deg"].round(2).values))
    
    if not series_list: return None
    return fmt_line("Dominant Cycle Analysis (Lib3)", df.index, series_list)

def extract_spectral_band(df, band_df):
    """Chart 20: Spectral Band Filter Analysis."""
    if band_df is None: return None
    
    # Reconstruct index if needed
    if isinstance(band_df, list):
        band_df = pd.DataFrame(band_df)
        if "index" in band_df.columns:
            band_df = band_df.set_index("index")
    
    # Align
    band_df = band_df.reindex(df.index)
    
    series_list = []
    if "filtered_price" in band_df.columns: series_list.append(("Filtered Price", band_df["filtered_price"].values))
    if "trend_component" in band_df.columns: series_list.append(("Trend", band_df["trend_component"].values))
    if "noise_component" in band_df.columns: series_list.append(("Noise", band_df["noise_component"].values))
    
    if not series_list: return None
    return fmt_line("Spectral Band Filter Analysis (Lib3)", df.index, series_list)

# ═══════════════════════════════════════════════════════════════════
# MASTER EXTRACTOR: MEMANGGIL SEMUA BERDASARKAN DATA YANG ADA
# ═══════════════════════════════════════════════════════════════════

def extract_all_charts(df, R):
    """
    Menerima df (OHLCV) dan R (dict hasil analisa).
    Mengembalikan list of chart objects untuk ECharts.
    """
    charts = []
    
    gv = lambda k: R.get(k)
    df_idx = df.index
    df_o, df_h, df_l, df_c, df_v = df["open"].values, df["high"].values, df["low"].values, df["close"].values, df["volume"].values
    
    core = gv("core")
    
    def has_real_data(res):
        if not res: return False
        if res.get("chartType") in ["candlestick", "order_blocks", "fair_value_gaps", "smc_concepts", "anomaly"]: 
            return True
        pts = []
        for s in res.get("series", []): pts.extend(s.get("data", []))
        pts.extend(res.get("data", []))
        return sum(1 for v in pts if v is not None) >= 5

    def add_chart(category, func):
        try:
            res = func()
            if res and has_real_data(res):
                res["category"] = category
                charts.append(res)
        except Exception as e:
            pass # Silent fail for partial data

    # 1. Candlestick Master
    add_chart("core", lambda: extract_candlestick_master(df, core, gv("sr")))
    
    # 2. Volume + OBV
    add_chart("core", lambda: extract_volume_obv(df, core))
    
    # 3. MACD
    add_chart("core", lambda: extract_macd(core))
    
    # 4. RSI Multi
    add_chart("core", lambda: extract_rsi_multi(core))
    
    # 5. ADX + DI
    add_chart("core", lambda: extract_adx_di(core))
    
    # 6. Bollinger Squeeze
    add_chart("risk", lambda: extract_bollinger_squeeze(gv("bsi"), core))
    
    # 7. Master Signal
    add_chart("scoring", lambda: extract_master_signal(gv("mss")))
    
    # 8. Hurst + Fractal
    add_chart("complexity", lambda: extract_hurst_fractal(gv("regime1"), gv("fracdim")))
    
    # 9. Volume Profile
    add_chart("smart_money", lambda: extract_volume_profile(gv("vprof"), df))
    
    # 10. Complexity Metrics
    add_chart("complexity", lambda: extract_complexity(df, gv("pentperm"), gv("pent"), gv("kolm"), gv("mii"), gv("mi")))
    
    # 11. Patterns
    add_chart("smart_money", lambda: extract_elliott_patterns(df, gv("hs"), gv("dbl"), gv("wedge"), gv("elliott"), gv("smc")))
    
    # 12. Order Blocks
    add_chart("smart_money", lambda: extract_order_blocks(df, gv("order_blocks")))

    # 13. Fair Value Gaps
    add_chart("smart_money", lambda: extract_fair_value_gaps(df, gv("fair_value_gaps")))
    
    # 14. Liquidity Sweeps
    add_chart("smart_money", lambda: extract_liquidity_sweeps(df, gv("liquidity_sweeps")))

    # 15. SMC Concepts (BOS/CHoCH)
    add_chart("smart_money", lambda: extract_smc_concepts(df, gv("smc")))

    # 16. Lib2 Signals (Entry/Exit)
    add_chart("scoring", lambda: extract_lib2_signals(df, gv("lib2_signals")))
    
    # 17. Lib2 Scores
    add_chart("scoring", lambda: extract_composite_lib2(gv("lib2")))
    
    # 18. Regime Signals
    add_chart("scoring", lambda: extract_regime_signals(df, gv("regime_signal")))
    
    # 19. Dominant Cycle
    add_chart("spectral", lambda: extract_dominant_cycle(df, gv("dominant_cycle")))
    
    # 20. Spectral Band Filter
    add_chart("spectral", lambda: extract_spectral_band(df, gv("spectral_band")))
    
    # 21. Instantaneous Phase
    add_chart("spectral", lambda: extract_inst_phase(df, gv("inst_phase")))
    
    # 22. Kolmogorov Complexity
    add_chart("complexity", lambda: extract_kolmogorov(df, gv("kolm")))

    # 23. Mutual Information
    add_chart("complexity", lambda: extract_mutual_info(df, gv("mi")))

    # 24. Manifold Embedding
    add_chart("complexity", lambda: extract_manifold(df, gv("manifold")))

    # 25. Tail Risk
    add_chart("risk", lambda: extract_tail_risk(df, gv("tail_risk")))
    
    # 26. Price Anomalies
    add_chart("risk", lambda: extract_anomalies(df, gv("anomalies")))
    
    # 27. Position Sizer
    add_chart("risk", lambda: extract_position_sizer(df, gv("sizer")))




    # 13-20: Ambil data mentah dari fungsi lain yang tersedia (Line/Bar generik)
    raw_extractors = {
        "Volume Delta Imbalance": ("vdelta", ["cumulative_delta", "imbalance_ratio"], "smart_money"),
        "Volume-Price Divergence": ("vdiv", ["divergence_correlation"], "oscillator"),
        "Adaptive MACD": ("amacd", ["adaptive_macd_hist_norm"], "oscillator"),
        "Polynomial Momentum": ("poly", ["poly_momentum", "poly_curvature"], "scoring"),
        "Wavelet Decomposition": ("wavelet", ["wavelet_trend", "wavelet_cycle"], "spectral"),
        "VWAP Bands": ("vwap1", ["vwap", "vwap_upper", "vwap_lower"], "core"),
        "Spectral Cycle": ("spectral", ["cycle_signal"], "spectral"),
        "Price Entropy Score (Lib3)": ("pent", None, "complexity"),
        "Permutation Entropy (Lib3)": ("pentperm", None, "complexity"),
        "Market Inefficiency Index (Lib3)": ("mii", None, "complexity"),
        "Kinetic Price Energy (Lib3)": ("kpe", None, "complexity"),
        "Persistence Homology Approx": ("ph", None, "complexity"),
        "Yang-Zhang Volatility (Lib3)": ("yz_vol", None, "risk"),
        "Bollinger Squeeze Intensity (Lib3)": ("bsi", None, "risk"),
        "Relative Vigor Index Enhanced (Lib3)": ("rvi", ["rvi", "signal"], "oscillator"),
        "Chande Kroll Stop (Lib3)": ("chande", ["stop_long", "stop_short"], "oscillator"),
        "DMI Crossover Quality (Lib3)": ("dmi_q", ["adx", "quality"], "oscillator"),
        "Multi-Indicator Divergence": ("midiv", ["indicator_agreement", "divergence_count"], "oscillator"),
        "Dynamic Support/Resistance (Z-Score)": ("sr", ["dynamic_support", "dynamic_resistance"], "patterns"),
    }
    
    for title, (key, cols, cat) in raw_extractors.items():
        data_obj = gv(key)
        if data_obj is None: continue
        
        chart = None
        if isinstance(data_obj, dict) and "data" in data_obj:
            raw = data_obj["data"]
            if isinstance(raw, list):
                chart = {"chartType": "raw_array", "title": title, "data": raw}
        elif isinstance(data_obj, pd.DataFrame):
            series_list = [(col, data_obj[col].values) for col in (cols or data_obj.columns) if col in data_obj.columns]
            if series_list:
                chart = fmt_line(title, data_obj.index, series_list)
        elif isinstance(data_obj, (np.ndarray, list)):
            if len(data_obj) == len(df.index):
                chart = fmt_line(title, df.index, [(title, data_obj)])
            else:
                chart = {"chartType": "raw_array", "title": title, "data": clean_series(data_obj)}
        
        if chart and has_real_data(chart):
            chart["category"] = cat
            charts.append(chart)

    return charts