"""
SSE Generator — 7-stage research pipeline streaming via Server-Sent Events.

Generates real-time SSE events for the deep research pipeline:
  Stage 1 — Data Acquisition (real yfinance history)
  Stage 2 — Technical Analysis (RSI, MACD, SMA, support/resistance)
  Stage 3 — Fundamental Analysis (P/E, P/B, ROE, market cap, dividends)
  Stage 4 — News & Sentiment (real yfinance news articles)
  Stage 5 — Deep ML / Quantitative Analysis (composite scoring)
  Stage 6 — Cross-Validation (comparison across symbols)
  Stage 7 — Final Synthesis (comprehensive research report)
"""

import json
import uuid
import asyncio
import logging
import numpy as np
import yfinance as yf
from typing import AsyncGenerator

from copilot.deep_research.yfinance_fetcher import (
    fetch_yfinance_technical,
    fetch_yfinance_fundamental,
)

logger = logging.getLogger(__name__)


async def research_stream_generator(symbols: str, analysis_type: str) -> AsyncGenerator[str, None]:
    """Generate SSE events for the 7-stage research pipeline using REAL yfinance data.
    
    Args:
        symbols: Space or comma-separated stock symbols (e.g., "PTBA.JK BBRI.JK")
        analysis_type: Type of analysis (e.g., "full", "technical", "fundamental")
    
    Yields:
        SSE event strings: meta, stage_start, chunk, stage_complete, complete, done
    """
    # Parse symbols
    symbol_list = [s.strip().upper() for s in symbols.replace(",", " ").split() if s.strip()]
    if not symbol_list:
        symbol_list = ["BBRI.JK"]
    
    research_id = str(uuid.uuid4())[:8]
    
    # Fix symbols: if no exchange suffix and looks like IDX, add .JK
    fixed_symbols = []
    for s in symbol_list:
        if "." not in s and s.isupper() and len(s) <= 5:
            s = f"{s}.JK"
        fixed_symbols.append(s)
    symbol_list = fixed_symbols
    symbols_str = ", ".join(symbol_list)

    stages = [
        ("Stage 1/7", "📡 Data Acquisition", f"Fetching live market data for {symbols_str} via yfinance..."),
        ("Stage 2/7", "📊 Technical Analysis", f"Computing real technical indicators for {symbols_str}..."),
        ("Stage 3/7", "📈 Fundamental Analysis", f"Loading fundamental metrics for {symbols_str}..."),
        ("Stage 4/7", "📰 News & Sentiment", f"Processing news & sentiment for {symbols_str}..."),
        ("Stage 5/7", "🧠 Deep ML Analysis", f"Running quantitative models on {symbols_str}..."),
        ("Stage 6/7", "🔍 Cross-Validation", f"Cross-validating all findings for {symbols_str}..."),
        ("Stage 7/7", "📝 Final Synthesis", f"Generating comprehensive research report for {symbols_str}..."),
    ]

    total_stages = len(stages)
    
    # SSE header
    yield f"event: meta\ndata: {json.dumps({'research_id': research_id, 'symbols': symbols_str, 'analysis_type': analysis_type, 'total_stages': total_stages})}\n\n"

    accumulated_technical = {}
    accumulated_fundamental = {}

    for i, (stage_id, stage_name, stage_desc) in enumerate(stages):
        stage_num = i + 1
        progress_base = int((i / total_stages) * 100)
        
        # Stage start
        yield f"event: stage_start\ndata: {json.dumps({'stage': stage_id, 'name': stage_name, 'description': stage_desc, 'progress': progress_base})}\n\n"

        if stage_num == 1:
            # STAGE 1: Data Acquisition — fetch price data
            for sym in symbol_list:
                yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': f"📡 **{sym}**: Mengunduh data pasar real-time dari Yahoo Finance...\n\n", 'progress': progress_base + 2})}\n\n"
                await asyncio.sleep(0.2)
                
                ticker = yf.Ticker(sym)
                hist = ticker.history(period="6mo")
                
                if hist.empty:
                    yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': f"⚠️ `{sym}`: Tidak ada data historis ditemukan. Lewati...\n\n", 'progress': progress_base + 5})}\n\n"
                    continue
                
                info = ticker.info or {}
                company_name = info.get("longName") or info.get("shortName", sym)
                currency = info.get("currency", "USD")
                exchange = info.get("exchange", "Yahoo")
                
                yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': f"✅ **{company_name}** ({sym})\n- Exchange: {exchange}\n- Currency: {currency}\n- Data Points: {len(hist)} candles (6 months)\n- Period: {hist.index[0].strftime('%Y-%m-%d')} → {hist.index[-1].strftime('%Y-%m-%d')}\n\n", 'progress': progress_base + 10})}\n\n"
                await asyncio.sleep(0.1)
            
            yield f"event: stage_complete\ndata: {json.dumps({'stage': stage_id, 'name': stage_name, 'progress': int((stage_num / total_stages) * 100)})}\n\n"

        elif stage_num == 2:
            # STAGE 2: Real Technical Analysis via yfinance
            for sym in symbol_list:
                yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': f"📊 **Technical Analysis**: {sym}\n\n", 'progress': progress_base + 5})}\n\n"
                await asyncio.sleep(0.3)
                
                ta_data = fetch_yfinance_technical(sym)
                accumulated_technical[sym] = ta_data
                
                if ta_data.get("success"):
                    d = ta_data
                    yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': (
                        f"**{d.get('company_name', sym)}** — Teknikal\n\n"
                        f"| Indikator | Nilai |\n"
                        f"|---|---|\n"
                        f"| Harga Saat Ini | {d.get('current_price', 'N/A')} |\n"
                        f"| Perubahan (6mo) | {d.get('change_pct', 0):+.2f}% |\n"
                        f"| RSI (14) | {d.get('rsi_14', 'N/A')} |\n"
                        f"| MACD | {d.get('macd', 'N/A')} |\n"
                        f"| SMA 20 | {d.get('sma20', 'N/A')} |\n"
                        f"| SMA 50 | {d.get('sma50', 'N/A')} |\n"
                        f"| Support | {d.get('support', 'N/A')} |\n"
                        f"| Resistance | {d.get('resistance', 'N/A')} |\n"
                        f"| Volatilitas (20d) | {d.get('volatility_20d', 'N/A')}% |\n"
                        f"| Volume Rata-rata | {d.get('volume_avg', 'N/A'):,.0f} |\n\n"
                    ), 'progress': progress_base + 15})}\n\n"
                    
                    # RSI Signal interpretation
                    rsi_val = d.get('rsi_14')
                    if rsi_val is not None:
                        if rsi_val > 70:
                            signal = "🔴 **Overbought** — potensi koreksi"
                        elif rsi_val < 30:
                            signal = "🟢 **Oversold** — potensi rebound"
                        else:
                            signal = "⚪ **Netral**"
                        yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': f"➡️ RSI Signal: {signal} ({rsi_val})\n\n", 'progress': progress_base + 18})}\n\n"
                else:
                    yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': f"⚠️ Technical data unavailable for {sym}: {ta_data.get('error', 'Unknown')}\n\n", 'progress': progress_base + 10})}\n\n"
                    
                await asyncio.sleep(0.2)
            
            yield f"event: stage_complete\ndata: {json.dumps({'stage': stage_id, 'name': stage_name, 'progress': int((stage_num / total_stages) * 100)})}\n\n"

        elif stage_num == 3:
            # STAGE 3: Real Fundamental Analysis via yfinance
            for sym in symbol_list:
                yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': f"📈 **Fundamental Analysis**: {sym}\n\n", 'progress': progress_base + 5})}\n\n"
                await asyncio.sleep(0.3)
                
                fd = fetch_yfinance_fundamental(sym)
                accumulated_fundamental[sym] = fd
                
                if fd.get("success"):
                    def fmt(val, suffix=""):
                        if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
                            return "N/A"
                        if isinstance(val, float):
                            if abs(val) >= 1e12:
                                return f"{val/1e12:.2f}T{suffix}"
                            elif abs(val) >= 1e9:
                                return f"{val/1e9:.2f}B{suffix}"
                            elif abs(val) >= 1e6:
                                return f"{val/1e6:.2f}M{suffix}"
                            return f"{val:.2f}{suffix}"
                        return str(val)
                    
                    d = fd
                    yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': (
                        f"**{d.get('company_name', sym)}** — Fundamental\n\n"
                        f"| Metrik | Nilai |\n"
                        f"|---|---|\n"
                        f"| Sektor | {d.get('sector', 'N/A')} |\n"
                        f"| Industri | {d.get('industry', 'N/A')} |\n"
                        f"| Market Cap | {fmt(d.get('market_cap'))} |\n"
                        f"| P/E Ratio | {fmt(d.get('pe_ratio'), 'x')} |\n"
                        f"| Forward P/E | {fmt(d.get('forward_pe'), 'x')} |\n"
                        f"| P/B Ratio | {fmt(d.get('pb_ratio'), 'x')} |\n"
                        f"| EPS | {fmt(d.get('eps'))} |\n"
                        f"| Forward EPS | {fmt(d.get('forward_eps'))} |\n"
                        f"| Dividend Yield | {fmt(d.get('dividend_yield') * 100 if d.get('dividend_yield') else None, '%')} |\n"
                        f"| Beta | {fmt(d.get('beta'))} |\n"
                        f"| ROE | {fmt(d.get('return_on_equity') * 100 if d.get('return_on_equity') else None, '%')} |\n"
                        f"| Profit Margin | {fmt(d.get('profit_margins') * 100 if d.get('profit_margins') else None, '%')} |\n"
                        f"| Revenue Growth | {fmt(d.get('revenue_growth') * 100 if d.get('revenue_growth') else None, '%')} |\n"
                        f"| Debt/Equity | {fmt(d.get('debt_to_equity'))} |\n"
                        f"| Analyst Target | {fmt(d.get('analyst_target'))} |\n"
                        f"| Rekomendasi | {d.get('recommendation', 'N/A')} |\n"
                        f"| 52W High | {fmt(d.get('52_week_high'))} |\n"
                        f"| 52W Low | {fmt(d.get('52_week_low'))} |\n\n"
                    ), 'progress': progress_base + 15})}\n\n"
                    
                    # Recommendation interpretation
                    rec = d.get('recommendation')
                    if rec:
                        rec_map = {
                            "buy": "🟢 **BUY**",
                            "strong_buy": "🟢 **STRONG BUY**",
                            "outperform": "🟡 **Outperform**",
                            "hold": "⚪ **HOLD**",
                            "underperform": "🟠 **Underperform**",
                            "sell": "🔴 **SELL**",
                            "strong_sell": "🔴 **STRONG SELL**",
                        }
                        rec_label = rec_map.get(rec, rec)
                        yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': f"➡️ Analyst Consensus: **{rec_label}** ({d.get('number_of_analysts', '?')} analysts)\n\n", 'progress': progress_base + 18})}\n\n"
                else:
                    yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': f"⚠️ Fundamental data unavailable for {sym}: {fd.get('error', 'Unknown')}\n\n", 'progress': progress_base + 10})}\n\n"
                    
                await asyncio.sleep(0.2)
            
            yield f"event: stage_complete\ndata: {json.dumps({'stage': stage_id, 'name': stage_name, 'progress': int((stage_num / total_stages) * 100)})}\n\n"

        elif stage_num == 4:
            # STAGE 4: News & Sentiment (fetch real news via yfinance)
            for sym in symbol_list:
                try:
                    ticker = yf.Ticker(sym)
                    news_items = ticker.news or []
                    
                    yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': f"📰 **News & Sentiment**: {sym}\n\n{len(news_items)} news articles found.\n\n", 'progress': progress_base + 10})}\n\n"
                    
                    for idx, item in enumerate(news_items[:5]):
                        title = item.get("title", "No title")
                        publisher = item.get("publisher", "Unknown")
                        link = item.get("link", "#")
                        yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': f"{idx+1}. **{title}** — *{publisher}*\n   [Read more]({link})\n\n", 'progress': progress_base + 10 + (idx * 3)})}\n\n"
                        await asyncio.sleep(0.1)
                    
                    if not news_items:
                        yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': f"ℹ️ No recent news for {sym}\n\n", 'progress': progress_base + 10})}\n\n"
                except Exception as e:
                    yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': f"⚠️ News unavailable for {sym}: {str(e)[:100]}\n\n", 'progress': progress_base + 10})}\n\n"
                    
                await asyncio.sleep(0.1)
            
            yield f"event: stage_complete\ndata: {json.dumps({'stage': stage_id, 'name': stage_name, 'progress': int((stage_num / total_stages) * 100)})}\n\n"

        elif stage_num == 5:
            # STAGE 5: Deep ML Analysis — statistical analysis on real data
            for sym in symbol_list:
                ta = accumulated_technical.get(sym, {})
                fd = accumulated_fundamental.get(sym, {})
                
                yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': f"🧠 **Quantitative Analysis**: {sym}\n\n", 'progress': progress_base + 5})}\n\n"
                await asyncio.sleep(0.2)
                
                if ta.get("success") and fd.get("success"):
                    rsi_val = ta.get('rsi_14')
                    volatility = ta.get('volatility_20d')
                    pe = fd.get('pe_ratio')
                    pb = fd.get('pb_ratio')
                    roe = fd.get('return_on_equity')
                    beta = fd.get('beta')
                    rec = fd.get('recommendation')
                    
                    # Generate composite scores
                    tech_score = 0
                    if rsi_val is not None:
                        if 30 <= rsi_val <= 70:
                            tech_score += 2  # Neutral zone
                        elif rsi_val < 30:
                            tech_score += 4  # Oversold (buy opportunity)
                        else:
                            tech_score += 1  # Overbought
                    
                    fund_score = 0
                    if pe is not None and pe > 0 and pe < 30:
                        fund_score += 2
                    if roe is not None and roe > 0.1:
                        fund_score += 2
                    if pb is not None and pb < 3:
                        fund_score += 1
                    
                    total_score = tech_score + fund_score
                    rating = "🟢 **Strong Buy**" if total_score >= 7 else "🟡 **Hold/Watch**" if total_score >= 4 else "🔴 **Caution**"
                    
                    yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': (
                        f"**Composite Analysis**\n\n"
                        f"| Factor | Score |\n"
                        f"|---|---|\n"
                        f"| Teknikal (RSI, trend) | {tech_score}/4 |\n"
                        f"| Fundamental (PE, ROE, PB) | {fund_score}/4 |\n"
                        f"| **Total Skor** | **{total_score}/8** |\n"
                        f"| **Rating** | **{rating}** |\n\n"
                        f"**Risk Metrics:**\n"
                        f"- Beta: {beta or 'N/A'} (Market Sensitivity)\n"
                        f"- Volatility (20d): {volatility or 'N/A'}%\n"
                        f"- Recommendation: {rec or 'N/A'}\n\n"
                    ), 'progress': progress_base + 20})}\n\n"
                else:
                    yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': f"⚠️ Insufficient data for quantitative analysis on {sym}\n\n", 'progress': progress_base + 10})}\n\n"
                    
                await asyncio.sleep(0.2)
            
            yield f"event: stage_complete\ndata: {json.dumps({'stage': stage_id, 'name': stage_name, 'progress': int((stage_num / total_stages) * 100)})}\n\n"

        elif stage_num == 6:
            # STAGE 6: Cross-Validation — compare across symbols
            all_symbols_data = []
            for sym in symbol_list:
                ta = accumulated_technical.get(sym, {})
                fd = accumulated_fundamental.get(sym, {})
                if ta.get("success") or fd.get("success"):
                    all_symbols_data.append({
                        "symbol": sym,
                        "company": ta.get("company_name", sym),
                        "price": ta.get("current_price"),
                        "change_pct": ta.get("change_pct"),
                        "rsi": ta.get("rsi_14"),
                        "pe": fd.get("pe_ratio"),
                        "pb": fd.get("pb_ratio"),
                        "market_cap": fd.get("market_cap"),
                        "roe": fd.get("return_on_equity"),
                        "rec": fd.get("recommendation"),
                    })
            
            if len(all_symbols_data) > 0:
                yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': f"🔍 **Cross-Validation Report**\n\n", 'progress': progress_base + 5})}\n\n"
                await asyncio.sleep(0.2)
                
                # Build comparison table
                table = "| Simbol | Harga | Change(6mo) | RSI | P/E | P/B | ROE |\n|---|---|---|---|---|---|---|\n"
                for d in all_symbols_data:
                    change_str = f"{d.get('change_pct', 0):+.2f}%" if d.get('change_pct') else "N/A"
                    rsi_str = f"{d.get('rsi', 'N/A')}"
                    pe_str = f"{d.get('pe', 'N/A'):.1f}" if d.get('pe') else "N/A"
                    pb_str = f"{d.get('pb', 'N/A'):.2f}" if d.get('pb') else "N/A"
                    roe_str = f"{d.get('roe', 0)*100:.1f}%" if d.get('roe') else "N/A"
                    table += f"| {d['symbol']} | {d.get('price', 'N/A')} | {change_str} | {rsi_str} | {pe_str} | {pb_str} | {roe_str} |\n"
                
                yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': table + '\n\n', 'progress': progress_base + 20})}\n\n"
            else:
                yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': f"🔍 Cross-validation: No comparable data available.\n\n", 'progress': progress_base + 10})}\n\n"
            
            await asyncio.sleep(0.2)
            yield f"event: stage_complete\ndata: {json.dumps({'stage': stage_id, 'name': stage_name, 'progress': int((stage_num / total_stages) * 100)})}\n\n"

        elif stage_num == 7:
            # STAGE 7: Final Synthesis Report
            yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': f"📝 **Final Research Report**\n\n", 'progress': progress_base + 5})}\n\n"
            await asyncio.sleep(0.3)
            
            report_sections = []
            for sym in symbol_list:
                ta = accumulated_technical.get(sym, {})
                fd = accumulated_fundamental.get(sym, {})
                
                section = f"### {sym}"
                name = ta.get("company_name") or fd.get("company_name", sym)
                section += f" — {name}\n\n"
                
                if ta.get("success"):
                    rsi = ta.get('rsi_14')
                    if rsi is not None:
                        if rsi > 70:
                            section += f"- **Teknikal**: Jenuh beli (RSI {rsi}). Waspada koreksi.\n"
                        elif rsi < 30:
                            section += f"- **Teknikal**: Jenuh jual (RSI {rsi}). Potensi rebound.\n"
                        else:
                            section += f"- **Teknikal**: Netral (RSI {rsi}). Tidak ada sinyal ekstrem.\n"
                    section += f"- Support: {ta.get('support', 'N/A')} | Resistance: {ta.get('resistance', 'N/A')}\n"
                    section += f"- Perubahan 6 bulan: {ta.get('change_pct', 0):+.2f}%\n"
                
                if fd.get("success"):
                    section += f"- **Fundamental**: "
                    pe = fd.get('pe_ratio')
                    roe = fd.get('return_on_equity')
                    if pe and pe > 0:
                        section += f"P/E {pe:.1f}x | "
                    if roe:
                        section += f"ROE {roe*100:.1f}% | "
                    rec = fd.get('recommendation')
                    if rec:
                        section += f"Rekomendasi: {rec}"
                    section += "\n"
                    section += f"- Target Analyst: {fd.get('analyst_target', 'N/A')}\n"
                
                section += "\n---\n\n"
                report_sections.append(section)
            
            final_report = f"""
## 📊 Deep Research Report

**Research ID**: `{research_id}`
**Symbols**: {symbols_str}
**Analysis Type**: {analysis_type}
**Source**: Yahoo Finance (yfinance) — Real Market Data

{"".join(report_sections)}

### ⚠️ Disclaimer
> Analisis ini dibuat berdasarkan data real dari Yahoo Finance.
> Bukan merupakan rekomendasi beli/jual. Lakukan due diligence sendiri.
"""
            yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': final_report, 'progress': progress_base + 50})}\n\n"
            await asyncio.sleep(0.3)
            
            yield f"event: stage_complete\ndata: {json.dumps({'stage': stage_id, 'name': stage_name, 'progress': 100})}\n\n"

    # Final complete event
    final_payload = {
        'research_id': research_id,
        'symbols': symbols_str,
        'report': f"Deep Research completed for {symbols_str}. Analysis ID: {research_id}",
        'progress': 100
    }
    yield f"event: complete\ndata: {json.dumps(final_payload)}\n\n"
    yield "event: done\ndata: {}\n\n"
