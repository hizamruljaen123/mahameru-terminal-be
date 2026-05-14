"""
Mahameru Copilot — Deep Research Module.

Modular package for automated stock research using yfinance.
Provides ticker detection, real data fetching, markdown report building,
and SSE streaming for the 7-stage research pipeline.

Modules:
    ticker_detector   — Regex-based stock symbol detection from natural language
    yfinance_fetcher  — Real technical & fundamental data from Yahoo Finance
    report_builder    — Unified markdown report generator (eliminates duplication)
    sse_generator     — 7-stage SSE research pipeline generator
"""

from copilot.deep_research.yfinance_fetcher import (
    fetch_yfinance_technical,
    fetch_yfinance_fundamental,
)

from copilot.deep_research.report_builder import build_markdown_report

from copilot.deep_research.sse_generator import research_stream_generator

__all__ = [
    "fetch_yfinance_technical",
    "fetch_yfinance_fundamental",
    "build_markdown_report",
    "research_stream_generator",
]
