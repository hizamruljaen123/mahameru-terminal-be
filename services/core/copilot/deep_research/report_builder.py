"""
Report Builder — Unified markdown report generator for stock research.

Consolidates the previously duplicated report-building logic from:
  - _handle_slash_command() in copilot_gateway.py
  - _echo_chat() in copilot_gateway.py

Both callers now use build_markdown_report() instead of duplicating code.
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)


def _fmt(val, suffix=""):
    """Format a value with appropriate suffix (B, M, T) for display."""
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


def build_markdown_report(tech: dict, fund: dict, symbol: str) -> tuple:
    """Build a comprehensive markdown research report from technical & fundamental data.
    
    Args:
        tech: Result dict from fetch_yfinance_technical()
        fund: Result dict from fetch_yfinance_fundamental()
        symbol: The stock symbol (e.g., "PTBA.JK", "TSLA")
    
    Returns:
        Tuple of (markdown_string, metadata_dict)
        - markdown_string: Formatted markdown with technical, fundamental, and signal sections
        - metadata_dict: Dict with symbol, source info for component rendering
    """
    md_parts = [f"## 📊 Deep Research: {symbol}\n"]
    
    # ── Technical Analysis Section ──
    if tech.get("success"):
        t = tech
        company = t.get("company_name", symbol)
        md_parts.append(f"### 📈 Technical Analysis\n")
        md_parts.append(f"**{company}** ({symbol})\n\n")
        md_parts.append(f"| Metric | Value |\n|--------|-------|\n")
        if t.get("current_price"):
            md_parts.append(f"| Current Price | **{t['current_price']:,.2f}** |\n")
        if t.get("change_pct") is not None:
            emoji = "🟢" if t["change_pct"] >= 0 else "🔴"
            md_parts.append(f"| 6-Month Change | {emoji} {t['change_pct']:+.2f}% |\n")
        if t.get("rsi_14") is not None:
            rsi = t["rsi_14"]
            signal = "Oversold 📗" if rsi < 30 else "Overbought 📕" if rsi > 70 else "Neutral 📘"
            md_parts.append(f"| RSI(14) | {rsi:.1f} ({signal}) |\n")
        if t.get("macd") is not None:
            md_parts.append(f"| MACD | {t['macd']:.2f} (Signal: {t.get('macd_signal', 0):.2f}) |\n")
        if t.get("sma20") is not None:
            md_parts.append(f"| SMA 20 | {t['sma20']:,.2f} |\n")
        if t.get("sma50") is not None:
            md_parts.append(f"| SMA 50 | {t['sma50']:,.2f} |\n")
        if t.get("support"):
            md_parts.append(f"| Support | {t['support']:,.2f} |\n")
        if t.get("resistance"):
            md_parts.append(f"| Resistance | {t['resistance']:,.2f} |\n")
        if t.get("volatility_20d") is not None:
            md_parts.append(f"| 20-Day Volatility | {t['volatility_20d']:.1f}% |\n")
        if t.get("volume_avg"):
            md_parts.append(f"| Avg Volume (20d) | {t['volume_avg']:,.0f} |\n")
    else:
        md_parts.append(f"⚠️ Technical data unavailable: {tech.get('error', 'Unknown error')}\n")
    
    # ── Fundamental Analysis Section ──
    if fund.get("success"):
        f = fund
        md_parts.append(f"\n### 💰 Fundamental Analysis\n")
        md_parts.append(f"| Metric | Value |\n|--------|-------|\n")
        if f.get("market_cap"):
            md_parts.append(f"| Market Cap | {_fmt(f['market_cap'])} |\n")
        if f.get("pe_ratio"):
            md_parts.append(f"| P/E Ratio | {f['pe_ratio']:.2f} |\n")
        if f.get("forward_pe"):
            md_parts.append(f"| Forward P/E | {f['forward_pe']:.2f} |\n")
        if f.get("pb_ratio"):
            md_parts.append(f"| P/B Ratio | {f['pb_ratio']:.2f} |\n")
        if f.get("dividend_yield"):
            md_parts.append(f"| Dividend Yield | {f['dividend_yield']*100:.2f}% |\n")
        if f.get("return_on_equity"):
            md_parts.append(f"| ROE | {f['return_on_equity']*100:.1f}% |\n")
        if f.get("return_on_assets"):
            md_parts.append(f"| ROA | {f['return_on_assets']*100:.1f}% |\n")
        if f.get("profit_margins"):
            md_parts.append(f"| Profit Margin | {f['profit_margins']*100:.1f}% |\n")
        if f.get("revenue"):
            md_parts.append(f"| Revenue | {_fmt(f['revenue'])} |\n")
        if f.get("debt_to_equity"):
            md_parts.append(f"| Debt/Equity | {f['debt_to_equity']:.2f} |\n")
        if f.get("beta"):
            md_parts.append(f"| Beta (β) | {f['beta']:.2f} |\n")
        if f.get("analyst_target"):
            md_parts.append(f"| Analyst Target | {f['analyst_target']:,.2f} |\n")
        if f.get("recommendation"):
            rec = f["recommendation"]
            rec_emoji = "🟢" if rec in ("buy", "strong_buy") else "🟡" if rec in ("hold", "neutral") else "🔴"
            md_parts.append(f"| Recommendation | {rec_emoji} {rec.upper()} |\n")
        if f.get("sector"):
            md_parts.append(f"| Sector | {f['sector']} |\n")
        if f.get("industry"):
            md_parts.append(f"| Industry | {f['industry']} |\n")
        if f.get("exchange"):
            md_parts.append(f"| Exchange | {f['exchange']} |\n")
        if f.get("currency"):
            md_parts.append(f"| Currency | {f['currency']} |\n")
    else:
        md_parts.append(f"\n⚠️ Fundamental data unavailable: {fund.get('error', 'Unknown error')}\n")
    
    # ── Signal Summary ──
    if tech.get("success") and fund.get("success"):
        signals = []
        rsi = tech.get("rsi_14")
        if rsi is not None:
            if rsi < 30:
                signals.append("Oversold — potential bounce 📗")
            elif rsi > 70:
                signals.append("Overbought — caution 📕")
            else:
                signals.append("Neutral momentum 📘")
        
        rec = fund.get("recommendation")
        if rec:
            signals.append(f"Analyst consensus: {rec.upper()}")
        
        md_parts.append(f"\n### 🔍 Signal Summary\n")
        for s in signals:
            md_parts.append(f"- {s}\n")
        md_parts.append(f"\n> Data sourced from **Yahoo Finance (yfinance)** — real-time market data\n")
    
    markdown = "".join(md_parts)
    
    # Build metadata for component rendering
    metadata = {
        "symbol": symbol,
        "source": "yfinance",
    }
    if tech.get("success"):
        metadata["technical"] = {k: v for k, v in tech.items() if k != "success"}
    if fund.get("success"):
        metadata["fundamental"] = {k: v for k, v in fund.items() if k != "success"}
    
    return markdown, metadata
