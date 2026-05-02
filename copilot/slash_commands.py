"""
Slash command definitions for Mahameru Copilot.
Maps slash commands to tool names with usage info.
"""

from typing import Dict, Any

SLASH_COMMANDS: Dict[str, Dict[str, Any]] = {
    "/ta": {
        "description": "Instant Technical Analysis Chart",
        "usage": "/ta [SYMBOL]",
        "example": "/ta BBRI.JK",
        "tool": "get_technical_analysis",
    },
    "/quote": {
        "description": "Instant Price Card",
        "usage": "/quote [SYMBOL]",
        "example": "/quote AAPL",
        "tool": "get_market_quote",
    },
    "/vessel": {
        "description": "Instant Vessel Map for an area",
        "usage": "/vessel [AREA]",
        "example": "/vessel Singapore",
        "tool": "get_vessel_intelligence",
    },
    "/news": {
        "description": "Instant News Feed",
        "usage": "/news [TOPIC]",
        "example": "/news BBRI",
        "tool": "get_news_feed",
    },
    "/research": {
        "description": "Trigger 7-Stage Deep Research Pipeline",
        "usage": "/research [SYMBOL]",
        "example": "/research BBRI.JK",
        "tool": "run_deep_research",
    },
    "/macro": {
        "description": "Macro Dashboard Snapshot",
        "usage": "/macro",
        "example": "/macro",
        "tool": "get_macro_economics",
    },
    "/crypto": {
        "description": "Crypto Analysis Dashboard",
        "usage": "/crypto [SYMBOL]",
        "example": "/crypto BTC",
        "tool": "get_crypto_analysis",
    },
    "/forex": {
        "description": "Forex Rates & Analysis",
        "usage": "/forex [PAIR]",
        "example": "/forex USDIDR",
        "tool": "get_forex_rates",
    },
    "/sentiment": {
        "description": "Market Sentiment Analysis",
        "usage": "/sentiment [TOPIC]",
        "example": "/sentiment banking",
        "tool": "get_sentiment_analysis",
    },
    "/regime": {
        "description": "Current Market Regime",
        "usage": "/regime",
        "example": "/regime",
        "tool": "get_market_regime",
    },
    "/help": {
        "description": "Show all available slash commands",
        "usage": "/help",
        "example": "/help",
        "tool": None,
    },
}
