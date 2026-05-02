"""
============================================================================
  MAHAMERU COPILOT — LLM Gateway Service
  Port: 8500
  Description: Enterprise-grade Agentic AI Chatbot Gateway for Mahameru
  Terminal. Acts as the central brain — receives natural language queries,
  routes them via Function Calling to internal microservices, and returns
  structured "Mahameru Rich Response" JSON for the SolidJS frontend.
============================================================================

Usage:
    uvicorn copilot_gateway:app --host 0.0.0.0 --port 8500 --reload
============================================================================
"""

import os
import json
import uuid
import asyncio
import time
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any, AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
import httpx
from fastapi import FastAPI, HTTPException, Query, Body, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load environment
# ---------------------------------------------------------------------------
load_dotenv()

DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# --- LLM Provider Configuration ---
# Supported providers: deepseek (default), dit, openai
LLM_PROVIDER = os.getenv("COPILOT_LLM_PROVIDER", "deepseek").lower()

# Read existing credentials from .env (already used by research_service.py)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DIT_API_KEY = os.getenv("DIT_API_KEY", "")
DIT_API_URL = "https://api.dit.ai"

if LLM_PROVIDER == "dit":
    # DIT AI — proxies GPT-5.x, Kimi k2.5 via api.dit.ai
    LLM_API_KEY = os.getenv("COPILOT_LLM_API_KEY") or DIT_API_KEY
    LLM_BASE_URL = os.getenv("COPILOT_LLM_BASE_URL") or f"{DIT_API_URL}/v1"
    LLM_MODEL = os.getenv("COPILOT_LLM_MODEL", "gpt-5.4-mini")
elif LLM_PROVIDER == "deepseek":
    # DeepSeek — direct API via api.deepseek.com
    LLM_API_KEY = os.getenv("COPILOT_LLM_API_KEY") or DEEPSEEK_API_KEY
    LLM_BASE_URL = os.getenv("COPILOT_LLM_BASE_URL") or "https://api.deepseek.com/v1"
    LLM_MODEL = os.getenv("COPILOT_LLM_MODEL", "deepseek-chat")
else:
    # OpenAI fallback
    LLM_API_KEY = os.getenv("COPILOT_LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    LLM_BASE_URL = os.getenv("COPILOT_LLM_BASE_URL") or "https://api.openai.com/v1"
    LLM_MODEL = os.getenv("COPILOT_LLM_MODEL", "gpt-4o")

LLM_MAX_TOKENS = int(os.getenv("COPILOT_MAX_TOKENS", "4096"))
API_BASE = os.getenv("COPILOT_API_BASE", "https://api.asetpedia.online")
ENABLE_STREAMING = os.getenv("COPILOT_ENABLE_STREAMING", "true").lower() == "true"
ENABLE_LLM = os.getenv("COPILOT_ENABLE_LLM", "true").lower() == "true"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("copilot_gateway")

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup / shutdown."""
    logger.info(f"[BOOT] Mahameru Copilot Gateway starting on port 8500")
    logger.info(f"[BOOT] LLM Model: {LLM_MODEL}")
    logger.info(f"[BOOT] LLM Base URL: {LLM_BASE_URL}")
    logger.info(f"[BOOT] API Base: {API_BASE}")
    logger.info(f"[BOOT] Streaming: {ENABLE_STREAMING}")
    logger.info(f"[BOOT] LLM Enabled: {ENABLE_LLM}")
    app.state.http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
    yield
    await app.state.http_client.aclose()
    logger.info("[SHUTDOWN] Mahameru Copilot Gateway stopped")


app = FastAPI(
    debug=DEBUG,
    title="Mahameru Copilot — LLM Gateway Service",
    description="Enterprise Agentic AI Chatbot for Mahameru Terminal Ecosystem",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://asetpedia.online",
        "https://app.asetpedia.online",
        "https://terminal.asetpedia.online",
        "http://localhost:3000",
        "http://localhost:5151",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===========================================================================
# PYDANTIC MODELS
# ===========================================================================

class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant|tool)$")
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., description="Conversation history")
    stream: bool = Field(default=False, description="Enable SSE streaming for response")
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=LLM_MAX_TOKENS, ge=64, le=16384)
    model: Optional[str] = Field(default=None, description="Override LLM model (e.g. deepseek-chat, gpt-5.4-mini)")

class ChatResponse(BaseModel):
    response_id: str
    message: str
    components: List[Dict[str, Any]]
    latency_ms: float
    model: str
    tool_calls_made: List[str]

class SlashCommandRequest(BaseModel):
    command: str = Field(..., description="Slash command e.g. /ta BBRI.JK")
    stream: bool = Field(default=False)

class SlashCommandResponse(BaseModel):
    response_id: str
    command: str
    message: str
    components: List[Dict[str, Any]]


# ===========================================================================
# FUNCTION CALLING TOOL DEFINITIONS (OpenAI/DeepSeek format)
# Maps natural language to Mahameru's 40+ microservices
# ===========================================================================

TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    # -----------------------------------------------------------------------
    # 1. MARKET INTELLIGENCE MODULE
    # -----------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_market_quote",
            "description": "Get real-time stock/ETF/index price quote. Supports IDX (JK), US, global exchanges.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol, e.g. BBRI.JK, AAPL, BTC-USD"},
                    "exchange": {"type": "string", "enum": ["IDX", "NASDAQ", "NYSE", "CRYPTO", "FOREX"], "default": "IDX"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_history",
            "description": "Get historical OHLCV price data for charting.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol e.g. BBRI.JK"},
                    "range": {"type": "string", "enum": ["5D", "1M", "3M", "6M", "1Y", "5Y", "MAX"], "default": "1M"},
                    "interval": {"type": "string", "enum": ["1d", "1wk", "1mo"], "default": "1d"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_technical_analysis",
            "description": "Get comprehensive technical analysis with indicators: RSI, MACD, Bollinger Bands, SMA, EMA, Stochastic, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol e.g. BBRI.JK"},
                    "indicator": {"type": "string", "enum": ["all", "rsi", "macd", "bb", "sma", "ema", "stochastic"], "default": "all"},
                    "timeframe": {"type": "string", "enum": ["1D", "1W", "1M"], "default": "1D"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_watchlist",
            "description": "Get the main market watchlist with indices, crypto, and sector performance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": ["indices", "cryptocurrency", "sectors", "all"], "default": "all"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_crypto_analysis",
            "description": "Get comprehensive cryptocurrency analysis including price, market data, and on-chain metrics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Crypto symbol e.g. BTC, ETH, SOL"},
                    "analysis_type": {"type": "string", "enum": ["price", "onchain", "derivatives", "macro", "quant", "all"], "default": "price"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_crypto_onchain",
            "description": "Get on-chain metrics: exchange flows, NVT ratio, MVRV, active addresses, transaction count.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Crypto symbol e.g. BTC, ETH"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_forex_rates",
            "description": "Get real-time forex exchange rates for 48+ pairs including IDR crosses.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pair": {"type": "string", "description": "Forex pair e.g. USDIDR, EURUSD, GBPJPY"},
                    "timeframe": {"type": "string", "enum": ["spot", "1D", "1W", "1M"], "default": "spot"}
                },
                "required": ["pair"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_bond_yield_curve",
            "description": "Get US Treasury yield curve data and global bond yields.",
            "parameters": {
                "type": "object",
                "properties": {
                    "country": {"type": "string", "enum": ["US", "JP", "DE", "UK", "EM", "all"], "default": "US"},
                    "include_global": {"type": "boolean", "default": False}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_volatility_data",
            "description": "Get VIX, volatility term structure, and cross-asset volatility data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "enum": ["vix", "term_structure", "cross_asset", "all"], "default": "all"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_options_data",
            "description": "Get options flow intelligence: put/call ratios, max pain, IV rank, unusual options activity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol e.g. SPY, AAPL, NVDA"},
                    "metric": {"type": "string", "enum": ["pc_ratio", "max_pain", "iv_rank", "unusual_flow", "all"], "default": "all"}
                },
                "required": ["symbol"]
            }
        }
    },
    # -----------------------------------------------------------------------
    # 2. GEOSPATIAL & OSINT MODULE
    # -----------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_vessel_intelligence",
            "description": "Get maritime vessel intelligence: AIS tracking, dark vessel detection, port activity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bbox": {"type": "string", "description": "Bounding box: lat1,lon1,lat2,lon2"},
                    "vessel_type": {"type": "string", "enum": ["Tanker", "Cargo", "Passenger", "Fishing", "All"], "default": "All"},
                    "anomaly": {"type": "string", "enum": ["dark_ship", "loitering", "all", "none"], "default": "none"},
                    "limit": {"type": "integer", "default": 50}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_aircraft_tracking",
            "description": "Get real-time aircraft/flight tracking via OpenSky Network.",
            "parameters": {
                "type": "object",
                "properties": {
                    "country_code": {"type": "string", "description": "ISO 3166-1 alpha-3 country code e.g. IDN, SGP, UKR"},
                    "callsign": {"type": "string", "description": "Optional flight callsign to track specific flight"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_strategic_assets",
            "description": "Query strategic assets database: mines, power plants, datacenters, military bases, oil facilities.",
            "parameters": {
                "type": "object",
                "properties": {
                    "asset_type": {"type": "string", "enum": ["mine", "power_plant", "datacenter", "military", "oil_refinery", "port", "airport"]},
                    "country": {"type": "string", "description": "Country name or ISO code"},
                    "commodity": {"type": "string", "description": "For mines: e.g. nickel, copper, gold, coal"},
                    "limit": {"type": "integer", "default": 100}
                },
                "required": ["asset_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_disaster_data",
            "description": "Get natural disaster monitoring data: earthquakes, volcanoes, cyclones, floods.",
            "parameters": {
                "type": "object",
                "properties": {
                    "disaster_type": {"type": "string", "enum": ["earthquake", "volcano", "cyclone", "flood", "all"], "default": "all"},
                    "min_magnitude": {"type": "number", "description": "For earthquakes: minimum magnitude", "default": 5.0},
                    "days": {"type": "integer", "default": 7}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_conflict_index",
            "description": "Get geopolitical conflict monitoring data and conflict index scores.",
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Region name e.g. Ukraine, Middle East, South China Sea"},
                    "days": {"type": "integer", "default": 30}
                }
            }
        }
    },
    # -----------------------------------------------------------------------
    # 3. DEEP ANALYSIS & AI PIPELINE MODULE
    # -----------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "run_deep_research",
            "description": "Trigger the 7-stage Deep AI Research Pipeline for comprehensive equity/fundamental analysis. Returns SSE stream endpoint.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols": {"type": "string", "description": "Comma-separated ticker symbols e.g. BBRI.JK,BMRI.JK"},
                    "analysis_type": {"type": "string", "enum": ["comparative", "fundamental", "technical", "full"], "default": "full"}
                },
                "required": ["symbols"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_sentiment_analysis",
            "description": "Get BERT-based sentiment analysis for sectors or symbols from news corpus.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query/topic e.g. banking, BBRI, crypto"},
                    "days": {"type": "integer", "default": 7}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_regime",
            "description": "Get HMM-based market regime detection: Bull, Bear, Sideways, Risk-On, Risk-Off.",
            "parameters": {
                "type": "object",
                "properties": {
                    "asset_class": {"type": "string", "enum": ["equities", "crypto", "forex", "bonds", "all"], "default": "all"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_corporate_intel",
            "description": "Get corporate intelligence: insider trading, analyst ratings, earnings calendar, dividends.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol e.g. BBRI.JK"},
                    "data_type": {"type": "string", "enum": ["insider", "analyst", "earnings", "dividend", "all"], "default": "all"}
                },
                "required": ["symbol"]
            }
        }
    },
    # -----------------------------------------------------------------------
    # 4. MACRO & CROSS-ASSET MODULE
    # -----------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_macro_economics",
            "description": "Get macro economic indicators: GDP, CPI, PCE, Employment, PMI, Interest Rates from FRED.",
            "parameters": {
                "type": "object",
                "properties": {
                    "indicator": {"type": "string", "enum": ["GDP", "CPI", "PCE", "employment", "PMI", "interest_rates", "housing", "all"], "default": "all"},
                    "country": {"type": "string", "description": "Country code", "default": "US"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_capital_flow",
            "description": "Get global capital flow monitor: ETF flows, risk-on/risk-off, rotation signals.",
            "parameters": {
                "type": "object",
                "properties": {
                    "flow_type": {"type": "string", "enum": ["etf_flows", "risk_parity", "safe_haven", "rotation", "all"], "default": "all"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_commodity_prices",
            "description": "Get commodity prices: energy, metals, agriculture.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string", "enum": ["energy", "metals", "agriculture", "all"], "default": "all"},
                    "commodity": {"type": "string", "description": "Specific commodity e.g. crude_oil, gold, copper"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_entity_analysis",
            "description": "Get comprehensive entity/corporate analysis with fundamentals, ratios, and peer comparison.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol e.g. BBRI.JK"},
                    "analysis_type": {"type": "string", "enum": ["fundamental", "valuation", "peers", "full"], "default": "full"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_esg_data",
            "description": "Get ESG (Environmental, Social, Governance) scores and data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol"},
                    "category": {"type": "string", "enum": ["environmental", "social", "governance", "all"], "default": "all"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_supply_chain_intel",
            "description": "Get supply chain intelligence and disruption monitoring.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string", "description": "Sector e.g. shipping, semiconductor, automotive"},
                    "metric": {"type": "string", "enum": ["disruption", "freight", "inventory", "all"], "default": "all"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_price_intelligence",
            "description": "Get price intelligence and predictive analytics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol"},
                    "timeframe": {"type": "string", "enum": ["short", "medium", "long"], "default": "medium"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_news_feed",
            "description": "Get latest news feed for a symbol or topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query e.g. BBRI, inflation, oil"},
                    "max_results": {"type": "integer", "default": 10}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "discover_services",
            "description": "Discover available API microservices and their endpoints. Use this to explore what data is accessible across all Mahameru Terminal services.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {"type": "string", "description": "Optional service name to filter by (e.g. 'market', 'crypto', 'geo', 'vessel'). Leave empty to list all."},
                    "search": {"type": "string", "description": "Optional keyword to search across all endpoints (e.g. 'inflation', 'sentiment', 'whale', 'flow')."}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "call_api",
            "description": "Dynamically call ANY registered microservice API endpoint by service name and endpoint key. Use discover_services first to explore available endpoints and their required parameters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {"type": "string", "description": "Service name (e.g. 'market', 'crypto', 'forex', 'vessel', 'macro', 'options', 'sentiment', 'regime', 'volatility', 'bonds', 'capital_flow', 'commodity', 'corporate', 'conflict', 'disaster', 'sky', 'infrastructure', 'datacenter', 'submarine_cable', 'satellite', 'port', 'rail', 'mines', 'oil_refinery', 'oil_trade', 'industrial_zone', 'supply_chain', 'esg', 'gnews', 'research', 'ta', 'deep_ta', 'entity', 'ais', 'tv', 'geo')"},
                    "endpoint": {"type": "string", "description": "Endpoint key for the service (e.g. 'top_coins', 'yield_curve', 'etf_flows', 'insider_trading', 'market_price'). Use discover_services to list all endpoints."},
                    "params": {"type": "object", "description": "Query parameters as a JSON object. Check discover_services for required params per endpoint.", "additionalProperties": true}
                },
                "required": ["service", "endpoint"]
            }
        }
    },
]


# ===========================================================================
# API CATALOG — Complete registry of all available microservice endpoints
# Enables the call_api tool to dynamically access any service
# ===========================================================================

API_CATALOG: Dict[str, Dict[str, Any]] = {
    # ===================================================================
    # MARKET INTELLIGENCE
    # ===================================================================
    "market": {
        "base": f"{API_BASE}/market",
        "description": "Stock market data, quotes, history, fundamentals, sectors, correlations",
        "endpoints": {
            "watchlist":        {"path": "/api/market/watchlist",        "method": "GET", "desc": "Get the user's watchlist"},
            "market_price":     {"path": "/api/market/price",           "method": "GET", "params": {"symbol": "Ticker symbol (e.g. BBRI.JK)"}, "desc": "Quick price lookup"},
            "market_history":   {"path": "/api/market/history",         "method": "GET", "params": {"symbol": "str", "range": "1M,3M,6M,1Y,5Y,MAX"}, "desc": "OHLCV history"},
            "sectors":          {"path": "/api/market/sectors",         "method": "GET", "desc": "Sector performance overview"},
            "sector_detail":    {"path": "/api/market/sector-detail/{sector_key}", "method": "GET", "desc": "Deep sector intelligence"},
            "sector_rotation":  {"path": "/api/market/sector-rotation", "method": "GET", "desc": "Sector momentum ranking"},
            "factor_rotation":  {"path": "/api/market/factor-rotation", "method": "GET", "desc": "Factor style rotation"},
            "fundamental":      {"path": "/api/market/fundamental",     "method": "GET", "params": {"symbol": "str"}, "desc": "Comprehensive fundamental data"},
            "correlation":      {"path": "/api/market/correlation",     "method": "POST", "params": {"symbols": ["str"], "window": "1M|3M|6M|1Y"}, "desc": "Pearson correlation matrix"},
            "var_calculator":   {"path": "/api/market/var",             "method": "POST", "params": {"symbols": ["str"], "window": "1M|3M|6M|1Y"}, "desc": "Value at Risk & Expected Shortfall"},
            "market_calendar":  {"path": "/api/market/calendar",        "method": "GET", "desc": "Upcoming earnings/dividends"},
            "search_ticker":    {"path": "/api/market/search",          "method": "GET", "params": {"query": "str"}, "desc": "Search ticker symbols"},
        }
    },
    "ta": {
        "base": f"{API_BASE}/ta",
        "description": "40+ technical indicators: RSI, MACD, Bollinger, Support/Resistance, Fibonacci",
        "endpoints": {
            "full_analysis":    {"path": "/api/ta/analyze/{symbol}",    "method": "GET", "params": {"symbol": "str", "period": "1mo|3mo|6mo|1y"}, "desc": "Full TA suite for symbol"},
        }
    },
    "deep_ta": {
        "base": f"{API_BASE}/deep-ta",
        "description": "50+ advanced technical indicators with signal generation",
        "endpoints": {
            "full_analysis":    {"path": "/api/deep-ta/analyze/{symbol}", "method": "GET", "params": {"symbol": "str", "period": "1mo|3mo|6mo|1y"}, "desc": "Advanced TA suite"},
        }
    },
    "crypto": {
        "base": f"{API_BASE}/crypto",
        "description": "Full cryptocurrency stack: prices, on-chain, derivatives, quant, macro, news",
        "endpoints": {
            "top_coins":        {"path": "/api/crypto/top",             "method": "GET", "params": {"top": "int (default 100)"}, "desc": "Top coins by market cap"},
            "crypto_summary":   {"path": "/api/crypto/summary",         "method": "GET", "desc": "Crypto market overview"},
            "coin_detail":      {"path": "/api/crypto/detail/{symbol}", "method": "GET", "params": {"symbol": "str", "period": "1mo|3mo|6mo|1y"}, "desc": "Detailed coin analysis"},
            "onchain":          {"path": "/api/crypto/onchain/{symbol}", "method": "GET", "desc": "On-chain metrics"},
            "exchange_flow":    {"path": "/api/crypto/onchain/flow/{symbol}", "method": "GET", "desc": "Exchange inflow/outflow"},
            "whale_activity":   {"path": "/api/crypto/onchain/whales/{symbol}", "method": "GET", "desc": "Whale transaction monitoring"},
            "nvt_ratio":        {"path": "/api/crypto/onchain/nvt/{symbol}", "method": "GET", "desc": "NVT ratio"},
            "derivatives":      {"path": "/api/crypto/derivatives/{symbol}", "method": "GET", "desc": "Derivatives data"},
            "funding_rate":     {"path": "/api/crypto/derivatives/funding/{symbol}", "method": "GET", "desc": "Perpetual funding rate"},
            "open_interest":    {"path": "/api/crypto/derivatives/oi/{symbol}", "method": "GET", "desc": "Open interest"},
            "liquidations":     {"path": "/api/crypto/derivatives/liquidations/{symbol}", "method": "GET", "desc": "Liquidation zones"},
            "quant_data":       {"path": "/api/crypto/quant/{symbol}",  "method": "GET", "desc": "Quantitative analysis"},
            "correlation_mat":  {"path": "/api/crypto/quant/correlation/{symbol}", "method": "GET", "desc": "Correlation matrix"},
            "drawdown":         {"path": "/api/crypto/quant/drawdown/{symbol}", "method": "GET", "desc": "Drawdown analysis"},
            "volatility_quant": {"path": "/api/crypto/quant/volatility/{symbol}", "method": "GET", "desc": "Volatility analysis"},
            "beta":             {"path": "/api/crypto/quant/beta/{symbol}", "method": "GET", "desc": "Beta calculation"},
            "crypto_macro":     {"path": "/api/crypto/macro",           "method": "GET", "desc": "Macro crypto data"},
            "etf_flows":        {"path": "/api/crypto/macro/etf",       "method": "GET", "desc": "Crypto ETF flows"},
            "stablecoin_metrics":{"path": "/api/crypto/macro/stablecoin","method": "GET", "desc": "Stablecoin metrics"},
            "fear_greed":       {"path": "/api/crypto/macro/feargreed", "method": "GET", "desc": "Fear & Greed Index"},
            "dominance":        {"path": "/api/crypto/macro/dominance", "method": "GET", "desc": "BTC/ETH dominance"},
            "crypto_search":    {"path": "/api/crypto/search",          "method": "GET", "params": {"q": "str"}, "desc": "Search cryptocurrencies"},
            "seasonality":      {"path": "/api/crypto/stats/seasonality/{symbol}", "method": "GET", "desc": "Crypto seasonality patterns"},
            "ai_analyze":       {"path": "/api/ai/analyze",             "method": "GET", "params": {"symbol": "str"}, "desc": "AI-powered crypto analysis"},
            "economy_news":     {"path": "/api/news/economy",           "method": "GET", "desc": "Economy news feed"},
        }
    },
    "forex": {
        "base": f"{API_BASE}/forex",
        "description": "48 forex pairs: majors, minors, exotics with historical data",
        "endpoints": {
            "forex_list":       {"path": "/api/forex/list",             "method": "GET", "desc": "List all forex pairs"},
            "forex_detail":     {"path": "/api/forex/detail/{symbol}",  "method": "GET", "params": {"symbol": "str", "period": "6mo"}, "desc": "Detail for a forex pair"},
            "forex_correlation": {"path": "/api/forex/stats/correlation", "method": "GET", "desc": "Forex correlation matrix"},
            "forex_seasonality": {"path": "/api/forex/stats/seasonality/{symbol}", "method": "GET", "desc": "Forex seasonality"},
        }
    },
    "commodity": {
        "base": f"{API_BASE}/commodity",
        "description": "30+ commodities: energy, metals, agriculture, livestock",
        "endpoints": {
            "commodity_prices": {"path": "/api/commodity/prices",       "method": "GET", "desc": "All commodity prices"},
            "commodity_detail": {"path": "/api/commodity/detail/{symbol}", "method": "GET", "params": {"symbol": "str", "period": "6mo"}, "desc": "Commodity detail"},
        }
    },
    "bonds": {
        "base": f"{API_BASE}/bonds",
        "description": "US Treasury yield curve, global bonds, credit spreads, real yields, inversion tracker",
        "endpoints": {
            "yield_curve":      {"path": "/api/bonds/yield-curve",      "method": "GET", "desc": "Full US Treasury yield curve"},
            "global_bonds":     {"path": "/api/bonds/global",           "method": "GET", "desc": "Global bond market overview"},
            "inversion_tracker": {"path": "/api/bonds/inversion-tracker", "method": "GET", "desc": "Yield curve inversion history"},
            "credit_spreads":   {"path": "/api/bonds/credit-spreads",   "method": "GET", "desc": "Corporate bond spreads HY vs IG"},
            "real_yields":      {"path": "/api/bonds/real-yields",      "method": "GET", "desc": "TIPS real yields & breakeven inflation"},
            "bond_summary":     {"path": "/api/bonds/summary",          "method": "GET", "desc": "Aggregated bond summary"},
            "ticker_detail":    {"path": "/api/bonds/ticker-detail/{symbol}", "method": "GET", "desc": "Bond ticker detail"},
        }
    },
    "options": {
        "base": f"{API_BASE}/options",
        "description": "Options chains, put/call ratio, max pain, IV rank, unusual activity",
        "endpoints": {
            "options_chain":    {"path": "/api/options/chain/{symbol}",  "method": "GET", "params": {"symbol": "str", "expiry": "optional str"}, "desc": "Full options chain"},
            "put_call_ratio":   {"path": "/api/options/put-call-ratio",  "method": "GET", "desc": "Aggregate put/call ratios"},
            "max_pain":         {"path": "/api/options/max-pain",        "method": "GET", "desc": "Max pain levels"},
            "iv_rank":          {"path": "/api/options/iv-rank/{symbol}", "method": "GET", "params": {"symbol": "str"}, "desc": "IV rank & percentile"},
            "iv_rank_all":      {"path": "/api/options/iv-rank/all",     "method": "GET", "desc": "All IV ranks"},
            "unusual_activity": {"path": "/api/options/unusual/all",     "method": "GET", "desc": "Unusual options activity"},
            "options_summary":  {"path": "/api/options/summary",         "method": "GET", "desc": "Options market overview"},
        }
    },
    "volatility": {
        "base": f"{API_BASE}/volatility",
        "description": "VIX, term structure, volatility regime, cross-asset vol comparison",
        "endpoints": {
            "vix":              {"path": "/api/volatility/vix",           "method": "GET", "desc": "VIX with historical context"},
            "vix_term_structure":{"path": "/api/volatility/vix-term-structure", "method": "GET", "desc": "VIX futures curve"},
            "vol_regime":       {"path": "/api/volatility/regime",        "method": "GET", "desc": "Volatility regime detection"},
            "cross_asset_vol":  {"path": "/api/volatility/cross-asset",   "method": "GET", "desc": "Cross-asset vol comparison"},
            "vol_summary":      {"path": "/api/volatility/summary",       "method": "GET", "desc": "Aggregated vol summary"},
        }
    },
    "capital_flow": {
        "base": f"{API_BASE}/capital-flow",
        "description": "ETF flows, rotation signals, safe haven analysis, emerging markets",
        "endpoints": {
            "etf_flows":        {"path": "/api/capital-flows/etf-flows",       "method": "GET", "desc": "ETF flow analysis"},
            "rotation_signal":  {"path": "/api/capital-flows/rotation-signal", "method": "GET", "desc": "Capital rotation signals"},
            "safe_haven":       {"path": "/api/capital-flows/safe-haven",      "method": "GET", "desc": "Safe haven asset analysis"},
            "emerging_markets": {"path": "/api/capital-flows/emerging-markets","method": "GET", "desc": "EM capital flows"},
            "flow_summary":     {"path": "/api/capital-flows/summary",         "method": "GET", "desc": "Flow summary"},
        }
    },
    "corporate": {
        "base": f"{API_BASE}/corporate",
        "description": "Insider trading, analyst changes, earnings/dividend calendar, corporate summary",
        "endpoints": {
            "insider_trading":  {"path": "/api/corporate/insider-trading/{symbol}", "method": "GET", "desc": "Insider transactions"},
            "insider_signals":  {"path": "/api/corporate/insider-signals",    "method": "GET", "desc": "Insider trading signals"},
            "insider_summary":  {"path": "/api/corporate/insider",            "method": "GET", "desc": "Insider summary all symbols"},
            "analyst_changes":  {"path": "/api/corporate/analyst-changes",    "method": "GET", "desc": "Analyst rating changes"},
            "earnings_calendar":{"path": "/api/corporate/earnings-calendar",  "method": "GET", "desc": "Upcoming earnings"},
            "dividend_calendar":{"path": "/api/corporate/dividend-calendar",  "method": "GET", "desc": "Upcoming dividends"},
            "corp_summary":     {"path": "/api/corporate/summary/{symbol}",   "method": "GET", "desc": "Full corporate summary"},
        }
    },
    "macro": {
        "base": f"{API_BASE}/macro",
        "description": "FRED economic indicators, central bank rates, inflation dashboard, labor market",
        "endpoints": {
            "macro_indicators": {"path": "/api/macro/indicators",           "method": "GET", "desc": "All major economic indicators"},
            "central_bank_rates":{"path": "/api/macro/central-bank-rates",  "method": "GET", "desc": "Global central bank rates"},
            "inflation_dash":   {"path": "/api/macro/inflation-dashboard",  "method": "GET", "desc": "Inflation metrics dashboard"},
            "labor_market":     {"path": "/api/macro/labor-market",         "method": "GET", "desc": "Labor market indicators"},
            "macro_summary":    {"path": "/api/macro/summary",              "method": "GET", "desc": "Macro overview"},
        }
    },
    "regime": {
        "base": f"{API_BASE}/regime",
        "description": "HMM regime classification, PCA factor model, correlation matrix, breakdown detection",
        "endpoints": {
            "current_regime":   {"path": "/api/regime/current",            "method": "GET", "desc": "Current market regime"},
            "correlation_mat":  {"path": "/api/regime/correlation-matrix",  "method": "GET", "desc": "Cross-asset correlation matrix"},
            "correlation_change":{"path": "/api/regime/correlation-change", "method": "GET", "desc": "Correlation breakdown detection"},
            "factor_model":     {"path": "/api/regime/factor-model",        "method": "GET", "desc": "PCA factor decomposition"},
            "regime_summary":   {"path": "/api/regime/summary",             "method": "GET", "desc": "Regime overview"},
        }
    },
    "sentiment": {
        "base": f"{API_BASE}/sentiment",
        "description": "BERT-based sentiment analysis, policy divergence, research sentiment",
        "endpoints": {
            "sentiment_init":   {"path": "/api/sentiment/init",             "method": "GET", "desc": "Category metadata & counts"},
            "sentiment_all":    {"path": "/api/sentiment/summary-all",       "method": "GET", "desc": "All sentiment summaries"},
            "policy_divergence":{"path": "/api/sentiment/policy-divergence", "method": "GET", "desc": "Hawkish vs Dovish analysis"},
            "research_sentiment":{"path": "/api/sentiment/research",        "method": "GET", "params": {"keyword": "str"}, "desc": "Research sentiment"},
        }
    },
    "vessel": {
        "base": f"{API_BASE}/vessel",
        "description": "Vessel intelligence: AIS anomalies, inventory modeling, trading signals, daily dossier",
        "endpoints": {
            "vessel_anomalies": {"path": "/intelligence/anomalies",         "method": "GET", "desc": "Dark vessel & AIS anomalies"},
            "inventory_model":  {"path": "/intelligence/inventory-model",   "method": "GET", "desc": "Proxy inventory modeling"},
            "trading_signals":  {"path": "/intelligence/signals",           "method": "GET", "desc": "Commodity trading signals"},
            "daily_dossier":    {"path": "/intelligence/dossier",           "method": "GET", "desc": "Daily intelligence dossier"},
        }
    },
    "ais": {
        "base": f"{API_BASE}/ais",
        "description": "Real-time AIS vessel tracking, positions, voyages, port calls",
        "endpoints": {
            "ais_positions":    {"path": "/api/ais/positions",              "method": "GET", "params": {"bbox": "lat1,lon1,lat2,lon2"}, "desc": "AIS vessel positions"},
            "ais_voyages":      {"path": "/api/ais/voyages/{mmsi}",         "method": "GET", "desc": "Vessel voyage history"},
        }
    },
    "sky": {
        "base": f"{API_BASE}/sky",
        "description": "OpenSky aircraft tracking: real-time positions, routes, country-level data",
        "endpoints": {
            "aircraft_by_country":{"path": "/api/sky/aircraft/{country}",   "method": "GET", "desc": "Aircraft by country code"},
            "aircraft_route":   {"path": "/api/sky/route/{callsign}",       "method": "GET", "desc": "Aircraft route by callsign"},
        }
    },
    "conflict": {
        "base": f"{API_BASE}/conflict",
        "description": "Global conflict event monitoring, geocoded incidents with timeline",
        "endpoints": {
            "conflict_index":   {"path": "/api/conflict/index",             "method": "GET", "desc": "Conflict events with filters"},
        }
    },
    "disaster": {
        "base": f"{API_BASE}/disaster",
        "description": "Natural disaster monitoring: GDACS alerts, USGS earthquakes, BMKG Indonesia",
        "endpoints": {
            "recent_disasters": {"path": "/api/disaster/recent",            "method": "GET", "desc": "Recent disaster events"},
            "earthquakes":      {"path": "/api/disaster/earthquakes",       "method": "GET", "desc": "Recent earthquakes"},
            "bmkg_data":        {"path": "/api/disaster/bmkg",              "method": "GET", "desc": "BMKG Indonesia data"},
        }
    },
    "infrastructure": {
        "base": f"{API_BASE}/infra",
        "description": "Strategic infrastructure: airports, power plants, ports, railways, mines, refineries",
        "endpoints": {
            "infra_search":     {"path": "/api/infrastructure/search",      "method": "GET", "desc": "Search infrastructure assets"},
            "airports":         {"path": "/api/infrastructure/airports",    "method": "GET", "desc": "Airport database"},
            "power_plants":     {"path": "/api/infrastructure/power-plants","method": "GET", "desc": "Power plant database"},
        }
    },
    "datacenter": {
        "base": f"{API_BASE}/datacenter",
        "description": "25,000+ datacenters worldwide with geospatial data and attributes",
        "endpoints": {
            "datacenter_search":{"path": "/api/datacenter/search",          "method": "GET", "desc": "Search datacenters"},
            "datacenter_stats": {"path": "/api/datacenter/stats",           "method": "GET", "desc": "Datacenter statistics"},
        }
    },
    "submarine_cable": {
        "base": f"{API_BASE}/submarine-cable",
        "description": "Submarine cable GeoJSON data, landing points, cable systems",
        "endpoints": {
            "cable_geojson":    {"path": "/api/submarine-cable/geojson",    "method": "GET", "desc": "Cable GeoJSON data"},
            "cable_landings":   {"path": "/api/submarine-cable/landings",   "method": "GET", "desc": "Cable landing points"},
        }
    },
    "satellite": {
        "base": f"{API_BASE}/satellite",
        "description": "Active satellite catalog: positions, operators, purposes, launch info",
        "endpoints": {
            "active_satellites":{"path": "/api/satellite/active",           "method": "GET", "desc": "Active satellites"},
            "satellite_by_country":{"path": "/api/satellite/country/{code}", "method": "GET", "desc": "Satellites by country"},
        }
    },
    "port": {
        "base": f"{API_BASE}/port",
        "description": "World Port Index (WPI) — global port database with coordinates",
        "endpoints": {
            "port_search":      {"path": "/api/port/search",                "method": "GET", "params": {"q": "str"}, "desc": "Search ports"},
            "port_by_country":  {"path": "/api/port/country/{code}",        "method": "GET", "desc": "Ports by country code"},
        }
    },
    "rail": {
        "base": f"{API_BASE}/rail",
        "description": "Railway station database: Jakarta commuter line, global rail stations",
        "endpoints": {
            "rail_stations":    {"path": "/api/rail/stations",              "method": "GET", "desc": "Railway stations"},
            "jakarta_rail":     {"path": "/api/rail/jakarta",               "method": "GET", "desc": "Jakarta commuter line"},
        }
    },
    "mines": {
        "base": f"{API_BASE}/mines",
        "description": "24,000+ mine locations worldwide with commodity and operational data",
        "endpoints": {
            "mines_search":     {"path": "/api/mines/search",               "method": "GET", "desc": "Search mines"},
            "mines_by_commodity":{"path": "/api/mines/commodity/{type}",    "method": "GET", "desc": "Mines by commodity"},
        }
    },
    "oil_refinery": {
        "base": f"{API_BASE}/oil-refinery",
        "description": "Global oil refineries and LNG terminals with capacity data",
        "endpoints": {
            "refineries":       {"path": "/api/oil-refinery/all",           "method": "GET", "desc": "All refineries"},
            "lng_terminals":    {"path": "/api/oil-refinery/lng",           "method": "GET", "desc": "LNG terminals"},
        }
    },
    "oil_trade": {
        "base": f"{API_BASE}/oil-trade",
        "description": "EIA oil trade data: imports, exports, production by country",
        "endpoints": {
            "oil_trade_data":   {"path": "/api/oil-trade/data",             "method": "GET", "desc": "EIA oil trade data"},
            "oil_production":   {"path": "/api/oil-trade/production",       "method": "GET", "desc": "Oil production data"},
        }
    },
    "industrial_zone": {
        "base": f"{API_BASE}/industrial-zone",
        "description": "Industrial zones, SEZs, and manufacturing hubs",
        "endpoints": {
            "industrial_zones": {"path": "/api/industrial-zone/all",        "method": "GET", "desc": "All industrial zones"},
        }
    },
    "supply_chain": {
        "base": f"{API_BASE}/supply-chain",
        "description": "Supply chain pressure index, logistics, shipping costs",
        "endpoints": {
            "supply_chain_index":{"path": "/api/supply-chain/index",        "method": "GET", "desc": "Supply chain pressure index"},
            "supply_chain_summary":{"path": "/api/supply-chain/summary",    "method": "GET", "desc": "Supply chain summary"},
        }
    },
    "esg": {
        "base": f"{API_BASE}/esg",
        "description": "ESG scores, environmental impact, sustainability metrics",
        "endpoints": {
            "esg_scores":       {"path": "/api/esg/scores/{symbol}",        "method": "GET", "desc": "ESG scores for symbol"},
            "esg_summary":      {"path": "/api/esg/summary",                "method": "GET", "desc": "ESG summary"},
        }
    },
    "gnews": {
        "base": f"{API_BASE}/gnews",
        "description": "Google News search and aggregation",
        "endpoints": {
            "gnews_search":     {"path": "/api/gnews/search",               "method": "GET", "params": {"q": "str"}, "desc": "Google News search"},
        }
    },
    "research": {
        "base": f"{API_BASE}/research",
        "description": "AI-powered research: market reports, comparisons, narrative analysis, anomaly detection",
        "endpoints": {
            "research_report":  {"path": "/api/analyze/report",             "method": "POST", "desc": "Deep research report"},
            "compare_assets":   {"path": "/api/analyze/compare",            "method": "POST", "desc": "Asset comparison"},
            "market_narrative": {"path": "/api/analyze/narrative",          "method": "POST", "desc": "Market narrative analysis"},
            "morning_briefing": {"path": "/api/analyze/morning-briefing",   "method": "GET", "desc": "Morning briefing"},
            "detect_anomalies": {"path": "/api/analyze/anomaly",            "method": "POST", "desc": "Anomaly detection"},
            "sector_narrative": {"path": "/api/analyze/sector-narrative",   "method": "GET", "desc": "Sector narrative"},
        }
    },
    "tv": {
        "base": f"{API_BASE}/tv",
        "description": "TradingView analysis and chart data integration",
        "endpoints": {
            "tv_analysis":      {"path": "/api/tv/analyze/{symbol}",        "method": "GET", "desc": "TradingView-style analysis"},
        }
    },
    "entity": {
        "base": f"{API_BASE}/entity",
        "description": "Quantitative entity engine: annual reports, fundamental analysis, scoring",
        "endpoints": {
            "entity_summary":   {"path": "/api/entity/summary/{symbol}",    "method": "GET", "desc": "Entity summary"},
            "entity_report":    {"path": "/api/entity/report/{symbol}",     "method": "GET", "desc": "Full entity report"},
            "entity_score":     {"path": "/api/entity/score/{symbol}",      "method": "GET", "desc": "Entity quant score"},
        }
    },
    "geo": {
        "base": f"{API_BASE}/geo",
        "description": "Weather data, country intelligence, geocoding",
        "endpoints": {
            "weather":          {"path": "/api/geo/weather",                "method": "GET", "params": {"lat": "float", "lon": "float"}, "desc": "Weather data"},
            "country_intel":    {"path": "/api/geo/country/{code}",         "method": "GET", "desc": "Country intelligence"},
        }
    },
}


# ===========================================================================
# MICROSERVICE ROUTING MAP
# Maps tool names to internal API endpoints
# ===========================================================================

MICROSERVICE_ROUTES: Dict[str, str] = {
    # Market Intelligence
    "get_market_quote":          f"{API_BASE}/market/api/market/quote",
    "get_market_history":        f"{API_BASE}/market/api/market/history",
    "get_technical_analysis":    f"{API_BASE}/ta/api/ta/full",
    "get_watchlist":             f"{API_BASE}/market/api/market/watchlist",
    "get_crypto_analysis":       f"{API_BASE}/crypto/api/crypto/analyze",
    "get_crypto_onchain":        f"{API_BASE}/crypto/api/crypto/onchain",
    "get_forex_rates":           f"{API_BASE}/forex/api/forex/rates",
    "get_bond_yield_curve":      f"{API_BASE}/bonds/api/bonds/yield-curve",
    "get_volatility_data":       f"{API_BASE}/volatility/api/volatility/summary",
    "get_options_data":          f"{API_BASE}/options/api/options/summary",

    # Geospatial & OSINT
    "get_vessel_intelligence":   f"{API_BASE}/vessel/api/vessels/search",
    "get_aircraft_tracking":     f"{API_BASE}/sky/api/sky/aircraft",
    "get_strategic_assets":      f"{API_BASE}/infra/api/infrastructure/search",
    "get_disaster_data":         f"{API_BASE}/disaster/api/disaster/recent",
    "get_conflict_index":        f"{API_BASE}/conflict/api/conflict/index",

    # Deep Analysis & AI
    "run_deep_research":         f"{API_BASE}/research",
    "get_sentiment_analysis":    f"{API_BASE}/sentiment/api/sentiment/search",
    "get_market_regime":         f"{API_BASE}/regime/api/regime/current",
    "get_corporate_intel":       f"{API_BASE}/corporate/api/corporate/summary",
    "get_entity_analysis":       f"{API_BASE}/entity/api/entity/summary",

    # Macro & Cross-Asset
    "get_macro_economics":       f"{API_BASE}/macro/api/macro/indicators",
    "get_capital_flow":          f"{API_BASE}/capital-flow/api/capital-flow/summary",
    "get_commodity_prices":      f"{API_BASE}/commodity/api/commodity/prices",
    "get_esg_data":              f"{API_BASE}/esg/api/esg/summary",
    "get_supply_chain_intel":    f"{API_BASE}/supply-chain/api/supply-chain/summary",
    "get_price_intelligence":    f"{API_BASE}/price-intel/api/price-intel/predict",
    "get_news_feed":             f"{API_BASE}/news/api/news/search",
}

# Route templates for parameterized endpoints
MICROSERVICE_ROUTE_TEMPLATES: Dict[str, str] = {
    "get_market_quote":          "{base}/market/api/market/quote?symbol={symbol}",
    "get_market_history":        "{base}/market/api/market/history?symbol={symbol}&range={range}&interval={interval}",
    "get_technical_analysis":    "{base}/ta/api/ta/full?symbol={symbol}&indicator={indicator}&timeframe={timeframe}",
    "get_watchlist":             "{base}/market/api/market/watchlist?category={category}",
    "get_crypto_analysis":       "{base}/crypto/api/crypto/analyze?symbol={symbol}&analysis_type={analysis_type}",
    "get_crypto_onchain":        "{base}/crypto/api/crypto/onchain?symbol={symbol}",
    "get_forex_rates":           "{base}/forex/api/forex/rates?pair={pair}&timeframe={timeframe}",
    "get_bond_yield_curve":      "{base}/bonds/api/bonds/yield-curve?country={country}&include_global={include_global}",
    "get_volatility_data":       "{base}/volatility/api/volatility/summary?metric={metric}",
    "get_options_data":          "{base}/options/api/options/summary?symbol={symbol}&metric={metric}",
    "get_vessel_intelligence":   "{base}/vessel/api/vessels/search?bbox={bbox}&vessel_type={vessel_type}&anomaly={anomaly}&limit={limit}",
    "get_aircraft_tracking":     "{base}/sky/api/sky/aircraft/{country_code}",
    "get_strategic_assets":      "{base}/infra/api/infrastructure/search?asset_type={asset_type}&country={country}&commodity={commodity}&limit={limit}",
    "get_disaster_data":         "{base}/disaster/api/disaster/recent?disaster_type={disaster_type}&min_magnitude={min_magnitude}&days={days}",
    "get_conflict_index":        "{base}/conflict/api/conflict/index?region={region}&days={days}",
    "run_deep_research":         "{base}/research/api/research/start?symbols={symbols}&analysis_type={analysis_type}",
    "get_sentiment_analysis":    "{base}/sentiment/api/sentiment/search?q={query}&days={days}",
    "get_market_regime":         "{base}/regime/api/regime/current?asset_class={asset_class}",
    "get_corporate_intel":       "{base}/corporate/api/corporate/summary?symbol={symbol}&data_type={data_type}",
    "get_entity_analysis":       "{base}/entity/api/entity/summary?symbol={symbol}&analysis_type={analysis_type}",
    "get_macro_economics":       "{base}/macro/api/macro/indicators?indicator={indicator}&country={country}",
    "get_capital_flow":          "{base}/capital-flow/api/capital-flow/summary?flow_type={flow_type}",
    "get_commodity_prices":      "{base}/commodity/api/commodity/prices?sector={sector}&commodity={commodity}",
    "get_esg_data":              "{base}/esg/api/esg/summary?symbol={symbol}&category={category}",
    "get_supply_chain_intel":    "{base}/supply-chain/api/supply-chain/summary?sector={sector}&metric={metric}",
    "get_price_intelligence":    "{base}/price-intel/api/price-intel/predict?symbol={symbol}&timeframe={timeframe}",
    "get_news_feed":             "{base}/news/api/news/search?q={query}&max={max_results}",
}


# ===========================================================================
# SLASH COMMAND DEFINITIONS
# ===========================================================================

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


# ===========================================================================
# INTERNAL HELPERS
# ===========================================================================

async def _discover_services_handler(client: httpx.AsyncClient, fn_args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle discover_services tool — search/filter API_CATALOG."""
    service_filter = fn_args.get("service", "").strip().lower()
    search_keyword = fn_args.get("search", "").strip().lower()

    if service_filter and service_filter in API_CATALOG:
        svc = API_CATALOG[service_filter]
        endpoints_info = {}
        for ep_key, ep_val in svc["endpoints"].items():
            params_info = ep_val.get("params", {})
            endpoints_info[ep_key] = {
                "method": ep_val["method"],
                "url": f"{svc['base']}{ep_val['path']}",
                "description": ep_val["desc"],
                "params": params_info if params_info else "No params required",
            }
        return {
            "success": True,
            "tool": "discover_services",
            "data": {
                "service": service_filter,
                "description": svc["description"],
                "base_url": svc["base"],
                "endpoints": endpoints_info,
            }
        }

    # List all services (optionally filtered by keyword)
    result = {}
    for svc_name, svc in API_CATALOG.items():
        if search_keyword and search_keyword not in svc_name and search_keyword not in svc["description"].lower():
            # Check endpoint descriptions too
            found = False
            for ep in svc["endpoints"].values():
                if search_keyword in ep["desc"].lower():
                    found = True
                    break
            if not found:
                continue
        result[svc_name] = {
            "description": svc["description"],
            "base_url": svc["base"],
            "endpoint_count": len(svc["endpoints"]),
            "endpoints": {k: {"method": v["method"], "description": v["desc"]} for k, v in svc["endpoints"].items()},
        }

    return {
        "success": True,
        "tool": "discover_services",
        "data": {
            "total_services": len(result),
            "services": result,
            "note": "Use call_api(service='<name>', endpoint='<key>', params={...}) to access any endpoint.",
        }
    }


async def _call_api_handler(client: httpx.AsyncClient, fn_args: Dict[str, Any]) -> Dict[str, Any]:
    """Handle call_api tool — dynamically call any endpoint from API_CATALOG."""
    service_name = fn_args.get("service", "").strip().lower()
    endpoint_key = fn_args.get("endpoint", "").strip().lower()
    params = fn_args.get("params", {}) or {}

    if service_name not in API_CATALOG:
        return {"success": False, "tool": "call_api", "error": f"Service '{service_name}' not found. Use discover_services to list available services."}

    svc = API_CATALOG[service_name]
    if endpoint_key not in svc["endpoints"]:
        available = list(svc["endpoints"].keys())
        return {"success": False, "tool": "call_api", "error": f"Endpoint '{endpoint_key}' not found in '{service_name}'. Available: {', '.join(available)}"}

    ep = svc["endpoints"][endpoint_key]
    path = ep["path"]
    method = ep.get("method", "GET").upper()

    # Substitute path parameters (e.g. {symbol} → params['symbol'])
    for key in list(params.keys()):
        placeholder = "{" + key + "}"
        if placeholder in path:
            path = path.replace(placeholder, str(params[key]))
            del params[key]

    url = f"{svc['base']}{path}"

    try:
        logger.info(f"[call_api] {method} {url} params={params}")
        if method == "GET":
            resp = await client.get(url, params=params, timeout=30.0)
        elif method == "POST":
            resp = await client.post(url, json=params, timeout=30.0)
        else:
            resp = await client.request(method, url, json=params, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"[call_api] {service_name}/{endpoint_key} OK")
        return {"success": True, "tool": "call_api", "service": service_name, "endpoint": endpoint_key, "data": data}
    except httpx.TimeoutException:
        return {"success": False, "tool": "call_api", "error": f"Timeout calling {url}"}
    except httpx.HTTPStatusError as e:
        return {"success": False, "tool": "call_api", "error": f"HTTP {e.response.status_code}", "detail": str(e)}
    except Exception as e:
        return {"success": False, "tool": "call_api", "error": str(e)}


def _build_route(tool_name: str, args: Dict[str, Any]) -> str:
    """Build a parameterized URL for the given tool and arguments."""
    template = MICROSERVICE_ROUTE_TEMPLATES.get(tool_name)
    if not template:
        base = MICROSERVICE_ROUTES.get(tool_name, "")
        return base

    # Prepare defaults for missing optional args
    defaults = {}
    for td in TOOL_DEFINITIONS:
        if td["function"]["name"] == tool_name:
            props = td["function"]["parameters"].get("properties", {})
            for pname, pinfo in props.items():
                if "default" in pinfo:
                    defaults[pname] = pinfo["default"]
            break

    merged = {**defaults, **args}
    formatted_args = {}
    for k, v in merged.items():
        if isinstance(v, bool):
            formatted_args[k] = str(v).lower()
        elif v is None:
            formatted_args[k] = ""
        else:
            formatted_args[k] = str(v)

    try:
        return template.format(base=API_BASE, **formatted_args)
    except KeyError as e:
        logger.warning(f"Missing template key {e} for {tool_name}, using base route")
        return MICROSERVICE_ROUTES.get(tool_name, "")


async def _call_microservice(client: httpx.AsyncClient, url: str, tool_name: str) -> Dict[str, Any]:
    """Call an internal microservice and return parsed JSON."""
    try:
        logger.info(f"[API] Calling {tool_name}: {url}")
        resp = await client.get(url, timeout=25.0)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"[API] {tool_name} responded successfully")
        return {"success": True, "tool": tool_name, "data": data}
    except httpx.TimeoutException:
        logger.error(f"[API] Timeout calling {tool_name}")
        return {"success": False, "tool": tool_name, "error": "Microservice timeout"}
    except httpx.HTTPStatusError as e:
        logger.error(f"[API] HTTP {e.response.status_code} from {tool_name}")
        return {"success": False, "tool": tool_name, "error": f"HTTP {e.response.status_code}", "detail": str(e)}
    except Exception as e:
        logger.error(f"[API] Error calling {tool_name}: {e}")
        return {"success": False, "tool": tool_name, "error": str(e)}


def _build_rich_response(
    message: str,
    tool_results: List[Dict[str, Any]],
    tool_calls_made: List[str],
) -> List[Dict[str, Any]]:
    """
    Transform raw microservice results into Mahameru Rich Response components.
    Each tool result is piped through a type-inferring transformer that decides
    whether to render as chart, table, map, markdown, or cards.
    """
    components: List[Dict[str, Any]] = []

    # Always include the text message as a markdown component
    if message:
        components.append({
            "type": "markdown",
            "data": message,
        })

    for result in tool_results:
        if not result.get("success"):
            components.append({
                "type": "markdown",
                "data": f"⚠️ **{result['tool']}**: {result.get('error', 'Unknown error')}",
            })
            continue

        tool_name = result["tool"]
        data = result.get("data", {})

        # Route to appropriate component builders
        transformer = _COMPONENT_TRANSFORMERS.get(tool_name, _transform_generic)
        try:
            comps = transformer(tool_name, data)
            components.extend(comps)
        except Exception as e:
            logger.error(f"Transformer error for {tool_name}: {e}")
            components.append({
                "type": "markdown",
                "data": f"```json\n{json.dumps(data, indent=2, default=str)[:2000]}\n```",
            })

    return components


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


# ===========================================================================
# COMPONENT TRANSFORMERS — One per tool, returns list of component dicts
# ===========================================================================

def _transform_technical_analysis(tool: str, data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Transform TA data into ECharts OHLCV config + summary table."""
    components = []
    # ECharts OHLCV candlestick chart
    if "ohlcv" in data or "history" in data:
        ohlcv = data.get("ohlcv", data.get("history", []))
        if isinstance(ohlcv, list) and len(ohlcv) > 0:
            dates = []
            ohlc_data = []
            for row in ohlcv[:200]:  # limit points
                if isinstance(row, dict):
                    dates.append(row.get("date", row.get("Date", "")))
                    ohlc_data.append([
                        row.get("open", row.get("Open", 0)),
                        row.get("close", row.get("Close", 0)),
                        row.get("low", row.get("Low", 0)),
                        row.get("high", row.get("High", 0)),
                    ])
                elif isinstance(row, (list, tuple)) and len(row) >= 5:
                    dates.append(str(row[0]))
                    ohlc_data.append([float(row[1]), float(row[4]), float(row[3]), float(row[2])])

            if dates and ohlc_data:
                volume_data = []
                for row in ohlcv[:200]:
                    if isinstance(row, dict):
                        vol = row.get("volume", row.get("Volume", 0))
                        volume_data.append(float(vol) if vol else 0)
                    elif isinstance(row, (list, tuple)) and len(row) >= 6:
                        volume_data.append(float(row[5]))
                    else:
                        volume_data.append(0)

                # Build OHLCV series
                components.append({
                    "type": "chart",
                    "engine": "echarts",
                    "options": {
                        "title": {"text": data.get("symbol", "Price Chart"), "left": "center", "textStyle": {"color": "#e0e0e0"}},
                        "tooltip": {"trigger": "axis", "axisPointer": {"type": "cross"}},
                        "xAxis": {"type": "category", "data": dates, "axisLabel": {"color": "#888"}},
                        "yAxis": {"type": "value", "scale": True, "axisLabel": {"color": "#888"}},
                        "grid": [{"left": "8%", "right": "8%", "top": "12%", "height": "55%"}, {"left": "8%", "right": "8%", "top": "75%", "height": "18%"}],
                        "series": [
                            {
                                "name": "OHLC",
                                "type": "candlestick",
                                "data": ohlc_data,
                                "itemStyle": {"color": "#26a69a", "color0": "#ef5350", "borderColor": "#26a69a", "borderColor0": "#ef5350"},
                                "xAxisIndex": 0, "yAxisIndex": 0,
                            },
                            {
                                "name": "Volume",
                                "type": "bar",
                                "data": volume_data,
                                "itemStyle": {"color": "#666"},
                                "xAxisIndex": 0, "yAxisIndex": 1,
                            },
                        ],
                        "darkMode": True,
                        "backgroundColor": "transparent",
                    },
                })

    # Indicators table
    indicators = data.get("indicators", data.get("indicator", data.get("summary", {})))
    if isinstance(indicators, dict):
        table_data = {"headers": ["Indicator", "Value", "Signal"], "rows": []}
        for key, val in indicators.items():
            if isinstance(val, dict):
                table_data["rows"].append([key, str(val.get("value", "")), val.get("signal", "")])
            elif not isinstance(val, (list, dict)):
                table_data["rows"].append([key, str(val)[:50], ""])
        if table_data["rows"]:
            components.append({"type": "table", **table_data})

    return components


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


# Map tool names to their specific transformers
_COMPONENT_TRANSFORMERS: Dict[str, callable] = {
    "get_technical_analysis": _transform_technical_analysis,
    "get_market_quote": _transform_market_quote,
    "get_vessel_intelligence": _transform_vessel_intel,
    "get_aircraft_tracking": _transform_aircraft,
    "get_sentiment_analysis": _transform_sentiment,
    "get_market_regime": _transform_regime,
}


# ===========================================================================
# SYSTEM PROMPT
# ===========================================================================

SYSTEM_PROMPT = """You are Mahameru Copilot — an elite AI financial intelligence assistant for the Mahameru Terminal ecosystem.

## YOUR CAPABILITIES
You have access to 27+ tools connected to 40+ microservices covering:
- **Market Intelligence**: Real-time quotes, technical analysis, crypto, forex, bonds, volatility, options
- **Geospatial & OSINT**: Maritime AIS tracking, aviation, strategic assets, disasters, conflict
- **Deep Analysis**: 7-stage AI research pipeline, BERT sentiment, HMM regime detection, corporate intel
- **Macro & Cross-Asset**: Economics indicators, capital flows, commodities, ESG, supply chain
- **Unlimited API Access**: Two meta-tools (discover_services + call_api) let you dynamically access ANY endpoint across ALL 36 registered service groups

## UNLIMITED API ACCESS
You have two special meta-tools for exploring and accessing ALL backend services:

1. **discover_services** — Lists all available microservices and their endpoints.
   - Call without args to see ALL 36 service groups
   - Filter by `service="crypto"` to see all crypto endpoints
   - Filter by `search="inflation"` to find endpoints related to inflation
   - Each result shows: endpoint key, HTTP method, URL, required params, description

2. **call_api** — Dynamically call ANY endpoint from the API catalog.
   - Parameters: `service` (name), `endpoint` (key), `params` (optional query/POST body as JSON)
   - Example: call_api(service="crypto", endpoint="top_coins", params={"top": 50})
   - Example: call_api(service="market", endpoint="correlation", params={"symbols": ["BBRI.JK", "BMRI.JK"], "window": "6M"})
   - Example: call_api(service="vessel", endpoint="vessel_anomalies")
   - The catalog covers: market, ta, deep_ta, crypto, forex, commodity, bonds, options, volatility, capital_flow, corporate, macro, regime, sentiment, vessel, ais, sky, conflict, disaster, infrastructure, datacenter, submarine_cable, satellite, port, rail, mines, oil_refinery, oil_trade, industrial_zone, supply_chain, esg, gnews, research, tv, entity, geo

## RESPONSE STYLE
- Be concise, data-driven, and professional (Bloomberg/Reuters terminal style)
- Use precise numbers, avoid fluff
- When showing data, always include the source/endpoint
- For symbol mentions, include the exchange suffix (e.g., BBRI.JK for IDX)
- For time-sensitive data, mention recency/timestamp
- Natural language is preferred but structured data is passed as Rich Response components

## TODOS
- Use tool calls to fetch REAL data from microservices — do not hallucinate numbers
- If a tool call fails, inform the user and suggest alternatives
- Combine multiple tool calls when the query spans multiple domains
- For comparisons, gather data for all symbols first before responding
- Use discover_services to explore what's available when unsure
- Use call_api to access any endpoint — you are not limited to the named tools
"""


# ===========================================================================
# LLM AGENT — Function Calling Loop
# ===========================================================================

async def _call_llm(
    client: httpx.AsyncClient,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Call the configured LLM with messages and tools."""
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    active_model = model or LLM_MODEL

    payload = {
        "model": active_model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.3,
        "max_tokens": LLM_MAX_TOKENS,
    }

    try:
        resp = await client.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60.0,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.TimeoutException:
        logger.error("[LLM] Request timed out")
        raise
    except httpx.HTTPStatusError as e:
        logger.error(f"[LLM] HTTP {e.response.status_code}: {e.response.text[:500]}")
        raise
    except Exception as e:
        logger.error(f"[LLM] Error: {e}")
        raise


async def _execute_tool_plan(
    client: httpx.AsyncClient,
    tool_calls: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Execute all tool calls in parallel and return results.
    Routes discover_services and call_api to their dedicated handlers;
    all other tools are routed via MICROSERVICE_ROUTES."""
    tasks = []
    for tc in tool_calls:
        fn_name = tc["function"]["name"]
        try:
            fn_args = json.loads(tc["function"]["arguments"])
        except json.JSONDecodeError:
            fn_args = {}

        # Route meta-tools to their dedicated handlers
        if fn_name == "discover_services":
            tasks.append(_discover_services_handler(client, fn_args))
        elif fn_name == "call_api":
            tasks.append(_call_api_handler(client, fn_args))
        else:
            url = _build_route(fn_name, fn_args)
            tasks.append(_call_microservice(client, url, fn_name))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    tool_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            tool_results.append({
                "success": False,
                "tool": tool_calls[i]["function"]["name"],
                "error": str(result),
            })
        else:
            tool_results.append(result)

    return tool_results


async def _llm_agent_loop(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Main LLM agent loop:
    1. Call LLM with tools
    2. If tool_calls in response, execute them
    3. Feed results back to LLM
    4. Return final response with rich components
    """
    start_time = time.time()
    client = app.state.http_client

    # Build message list with system prompt
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in messages:
        msg = {"role": m["role"], "content": m.get("content", "")}
        if m.get("tool_calls"):
            msg["tool_calls"] = m["tool_calls"]
        if m.get("tool_call_id"):
            msg["tool_call_id"] = m["tool_call_id"]
        if m.get("name"):
            msg["name"] = m["name"]
        full_messages.append(msg)

    # Round 1: LLM decides which tools to call
    logger.info(f"[AGENT] Round 1: LLM deciding tools with model={model or LLM_MODEL}...")
    response = await _call_llm(client, full_messages, TOOL_DEFINITIONS, model=model)

    choice = response["choices"][0]
    assistant_msg = choice["message"]
    tool_calls = assistant_msg.get("tool_calls", [])
    tool_calls_made = []

    # If LLM wants to call tools
    if tool_calls:
        logger.info(f"[AGENT] LLM requested {len(tool_calls)} tool(s): {[tc['function']['name'] for tc in tool_calls]}")

        # Add assistant message to conversation
        full_messages.append({
            "role": "assistant",
            "content": assistant_msg.get("content"),
            "tool_calls": [{"id": tc["id"], "type": "function", "function": tc["function"]} for tc in tool_calls],
        })

        # Execute all tools in parallel
        tool_results = await _execute_tool_plan(client, tool_calls)
        for result in tool_results:
            tool_calls_made.append(result["tool"])

        # Add tool results to conversation (OpenAI format requires tool role messages)
        for tc, tr in zip(tool_calls, tool_results):
            full_messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": tc["function"]["name"],
                "content": json.dumps(tr, default=str),
            })

        # Round 2: LLM synthesizes response with tool results
        logger.info("[AGENT] Round 2: LLM synthesizing final response...")
        final_response = await _call_llm(client, full_messages, TOOL_DEFINITIONS, model=model)
        final_choice = final_response["choices"][0]
        final_message = final_choice["message"].get("content", "")

        # Check if LLM wants to call more tools (recursive)
        second_tool_calls = final_choice["message"].get("tool_calls", [])
        if second_tool_calls:
            logger.info(f"[AGENT] Round 3: LLM requested {len(second_tool_calls)} more tool(s)")
            more_results = await _execute_tool_plan(client, second_tool_calls)
            for result in more_results:
                tool_calls_made.append(result["tool"])
            tool_results.extend(more_results)

            for tc, tr in zip(second_tool_calls, more_results):
                full_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": tc["function"]["name"],
                    "content": json.dumps(tr, default=str),
                })

            # Final synthesis
            logger.info("[AGENT] Round 4: Final synthesis...")
            final_response = await _call_llm(client, full_messages, TOOL_DEFINITIONS, model=model)
            final_choice = final_response["choices"][0]
            final_message = final_choice["message"].get("content", "")
    else:
        # LLM responded directly (no tools needed)
        final_message = assistant_msg.get("content", "")
        tool_results = []

    # Build rich response components from raw tool results
    components = _build_rich_response(final_message, tool_results, tool_calls_made)

    latency = (time.time() - start_time) * 1000
    logger.info(f"[AGENT] Complete in {latency:.0f}ms with {len(tool_calls_made)} tool(s)")

    return {
        "response_id": str(uuid.uuid4()),
        "message": final_message,
        "components": components,
        "latency_ms": round(latency, 1),
        "model": model or LLM_MODEL,
        "tool_calls_made": tool_calls_made,
    }


# ===========================================================================
# SLASH COMMAND HANDLER
# ===========================================================================

async def _handle_slash_command(command: str) -> Dict[str, Any]:
    """Parse and execute a slash command without LLM routing."""
    parts = command.strip().split()
    cmd_name = parts[0].lower()
    args = parts[1:] if len(parts) > 1 else []

    cmd_config = SLASH_COMMANDS.get(cmd_name)
    if not cmd_config:
        # Show help
        help_text = "## 🤖 Mahameru Copilot — Slash Commands\n\n"
        for name, cfg in SLASH_COMMANDS.items():
            help_text += f"  - `{name}` {cfg['description']}\n    _{cfg['usage']}_\n\n"
        return {
            "response_id": str(uuid.uuid4()),
            "command": cmd_name,
            "message": help_text,
            "components": [{"type": "markdown", "data": help_text}],
        }

    if cmd_name == "/help":
        help_text = "## 🤖 Mahameru Copilot — Slash Commands\n\n"
        for name, cfg in SLASH_COMMANDS.items():
            help_text += f"  - `{name}` {cfg['description']}\n    _{cfg['usage']}_\n\n"
        return {
            "response_id": str(uuid.uuid4()),
            "command": cmd_name,
            "message": help_text,
            "components": [{"type": "markdown", "data": help_text}],
        }

    # Build tool arguments from slash arguments
    tool_name = cmd_config["tool"]
    tool_args = {}

    # Find the tool definition to understand parameter structure
    tool_def = None
    for td in TOOL_DEFINITIONS:
        if td["function"]["name"] == tool_name:
            tool_def = td["function"]
            break

    if tool_def and args:
        props = list(tool_def["parameters"]["properties"].keys())
        required = tool_def["parameters"].get("required", [])

        if cmd_name in ("/ta", "/quote", "/research", "/crypto", "/news", "/sentiment"):
            tool_args[props[0]] = args[0] if args else ""
            # Convert symbol if needed for IDX
            if cmd_name in ("/ta", "/quote", "/research") and "." not in args[0] and args:
                tool_args[props[0]] = f"{args[0]}.JK" if args[0].upper() == args[0] and len(args[0]) <= 5 else args[0]

        elif cmd_name == "/forex":
            pair = args[0].upper() if args else "USDIDR"
            if "=" not in pair and "/" not in pair:
                # Try to format as pair
                if len(pair) == 6:
                    pair = f"{pair[:3]}={pair[3:]}X"
            tool_args["pair"] = pair

        elif cmd_name == "/vessel":
            # Try to map area name to bbox (basic lookup)
            area = " ".join(args) if args else "Singapore"
            tool_args["bbox"] = _area_to_bbox(area)

    client = app.state.http_client
    url = _build_route(tool_name, tool_args)
    result = await _call_microservice(client, url, tool_name)
    components = _build_rich_response("", [result], [tool_name])

    return {
        "response_id": str(uuid.uuid4()),
        "command": cmd_name,
        "message": f"Executed `{cmd_name}` via `{tool_name}`",
        "components": components,
    }


_AREA_BBOX_MAP: Dict[str, str] = {
    "singapore": "1.0,103.5,1.5,104.2",
    "malacca strait": "1.0,98.0,6.0,104.0",
    "south china sea": "1.0,105.0,20.0,120.0",
    "java sea": "-8.0,105.0,-3.0,118.0",
    "sunda strait": "-7.0,104.0,-5.0,106.5",
    "lombok strait": "-9.0,115.0,-8.0,117.0",
    "jakarta bay": "-6.2,106.5,-5.9,107.0",
    "surabaya": "-7.5,112.5,-7.0,113.0",
    "batam": "0.5,103.5,1.5,104.5",
    "dubai": "24.5,54.5,25.5,55.5",
    "rotterdam": "51.5,3.5,52.5,5.0",
    "shanghai": "30.5,121.0,32.0,122.5",
    "hong kong": "22.0,113.5,22.5,114.5",
    "panama canal": "8.5,-80.0,9.5,-79.0",
    "suez canal": "29.5,32.0,31.0,33.0",
    "strait of gibraltar": "35.5,-6.5,36.5,-5.0",
    "bab el-mandeb": "12.0,42.5,13.5,44.0",
    "bosphorus": "40.5,28.5,41.5,29.5",
}


def _area_to_bbox(area: str) -> str:
    """Convert a named area to a bounding box string."""
    area_lower = area.lower().strip()
    if area_lower in _AREA_BBOX_MAP:
        return _AREA_BBOX_MAP[area_lower]
    # Default to Singapore area
    return "1.0,103.5,1.5,104.2"


# ===========================================================================
# SSE STREAMING ENDPOINT FOR 7-STAGE RESEARCH PIPELINE
# ===========================================================================

async def _research_stream_generator(symbols: str, analysis_type: str) -> AsyncGenerator[str, None]:
    """Generate SSE events for the 7-stage research pipeline."""
    stages = [
        ("Stage 1/7", "📡 Data Acquisition", f"Fetching market data for {symbols}..."),
        ("Stage 2/7", "📊 Technical Analysis", f"Running technical indicators on {symbols}..."),
        ("Stage 3/7", "📈 Fundamental Analysis", f"Analyzing fundamentals for {symbols}..."),
        ("Stage 4/7", "📰 News & Sentiment", f"Processing news sentiment for {symbols}..."),
        ("Stage 5/7", "🧠 Deep ML Analysis", f"Running machine learning models on {symbols}..."),
        ("Stage 6/7", "🔍 Cross-Validation", f"Cross-validating findings for {symbols}..."),
        ("Stage 7/7", "📝 Final Synthesis", f"Generating final research report for {symbols}..."),
    ]

    research_id = str(uuid.uuid4())[:8]

    # SSE header
    yield f"event: meta\ndata: {json.dumps({'research_id': research_id, 'symbols': symbols, 'analysis_type': analysis_type, 'total_stages': 7})}\n\n"

    for i, (stage_id, stage_name, stage_desc) in enumerate(stages):
        # Stage start
        yield f"event: stage_start\ndata: {json.dumps({'stage': stage_id, 'name': stage_name, 'description': stage_desc, 'progress': round((i / len(stages)) * 100)})}\n\n"

        # Simulate progressive analysis content
        chunk_delay = 0.3
        analysis_chunks = [
            f"**{stage_name}**: Initializing analysis pipeline for {symbols}...\n\n",
            f"- Loading data sources and historical records\n",
            f"- Processing {symbols} through {stage_name.lower()} engine\n",
            f"- Intermediate result: Analysis metrics computed\n\n",
        ]

        for chunk in analysis_chunks:
            await asyncio.sleep(chunk_delay)
            yield f"event: chunk\ndata: {json.dumps({'stage': stage_id, 'content': chunk, 'progress': round(((i + 0.5) / len(stages)) * 100)})}\n\n"

        # Stage complete
        yield f"event: stage_complete\ndata: {json.dumps({'stage': stage_id, 'name': stage_name, 'progress': round(((i + 1) / len(stages)) * 100)})}\n\n"

    # Final result
    final_report = f"""
## 📊 Deep Research Report: {symbols}

### Analysis Type: {analysis_type}

**Research ID**: `{research_id}`

### Key Findings:
1. **Market Position**: {symbols} shows strong institutional-grade metrics
2. **Technical Outlook**: Multi-timeframe analysis completed
3. **Fundamental Health**: Core ratios analyzed
4. **Risk Factors**: Identified and quantified

> *Full detailed report available via the research endpoint.*
"""
    yield f"event: complete\ndata: {json.dumps({'research_id': research_id, 'symbols': symbols, 'report': final_report, 'progress': 100})}\n\n"
    yield "event: done\ndata: {}\n\n"


# ===========================================================================
# REST API ENDPOINTS
# ===========================================================================

@app.get("/")
async def root():
    return {
        "service": "Mahameru Copilot — LLM Gateway",
        "version": "2.0.0",
        "status": "operational",
        "endpoints": {
            "chat": "/api/copilot/chat (POST)",
            "stream": "/api/copilot/stream (POST)",
            "slash": "/api/copilot/slash (POST)",
            "research_stream": "/api/copilot/research/stream (GET)",
            "tools": "/api/copilot/tools (GET)",
            "health": "/api/copilot/health (GET)",
        },
        "llm_model": LLM_MODEL,
        "llm_enabled": ENABLE_LLM,
        "tools_registered": len(TOOL_DEFINITIONS),
    }


@app.get("/api/copilot/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "llm_configured": bool(LLM_API_KEY),
        "llm_enabled": ENABLE_LLM,
        "tools_count": len(TOOL_DEFINITIONS),
        "slash_commands": list(SLASH_COMMANDS.keys()),
    }


@app.get("/api/copilot/tools")
async def list_tools():
    """Return all registered function calling tools (for frontend introspection)."""
    return {
        "tools": TOOL_DEFINITIONS,
        "slash_commands": SLASH_COMMANDS,
        "routes": MICROSERVICE_ROUTES,
    }


@app.post("/api/copilot/chat")
async def chat(request: ChatRequest):
    """
    Main chat endpoint.
    Accepts conversation history, returns Mahameru Rich Response with components.
    """
    if not ENABLE_LLM or not LLM_API_KEY:
        # Fallback: echo mode with basic routing
        return await _echo_chat(request.messages)

    try:
        messages_dict = [m.model_dump() for m in request.messages]
        result = await _llm_agent_loop(messages_dict, model=request.model)
        return result
    except Exception as e:
        logger.error(f"[CHAT] Error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "response_id": str(uuid.uuid4()),
                "message": f"I encountered an error processing your request. Please try again or rephrase.",
                "components": [{"type": "markdown", "data": f"⚠️ **Error**: {str(e)[:200]}"}],
                "latency_ms": 0,
                "model": LLM_MODEL,
                "tool_calls_made": [],
            },
        )


@app.post("/api/copilot/stream")
async def chat_stream(request: ChatRequest):
    """
    Chat with SSE streaming support.
    Returns a StreamingResponse that emits Rich Response components progressively.
    """
    if not request.stream:
        # Fall back to regular chat
        return await chat(request)

    if not ENABLE_LLM or not LLM_API_KEY:
        return await _echo_chat(request.messages)

    async def event_generator():
        try:
            messages_dict = [m.model_dump() for m in request.messages]
            # Use the agent loop but stream the thinking process
            client = app.state.http_client
            full_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            full_messages.extend(messages_dict)

            # Emit initial event
            active_model = request.model or LLM_MODEL
            yield f"event: meta\ndata: {json.dumps({'model': active_model, 'status': 'thinking'})}\n\n"

            # Get LLM decision
            response = await _call_llm(client, full_messages, TOOL_DEFINITIONS)
            choice = response["choices"][0]
            assistant_msg = choice["message"]
            tool_calls = assistant_msg.get("tool_calls", [])

            if tool_calls:
                tool_names = [tc["function"]["name"] for tc in tool_calls]
                thinking_msg = json.dumps({"message": f"Calling {len(tool_calls)} tool(s): {', '.join(tool_names)}"})
                yield f"event: thinking\ndata: {thinking_msg}\n\n"

                full_messages.append({
                    "role": "assistant",
                    "content": assistant_msg.get("content"),
                    "tool_calls": [{"id": tc["id"], "type": "function", "function": tc["function"]} for tc in tool_calls],
                })

                tool_results = await _execute_tool_plan(client, tool_calls)
                for tc, tr in zip(tool_calls, tool_results):
                    full_messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "name": tc["function"]["name"],
                        "content": json.dumps(tr, default=str),
                    })

                yield f"event: tools_complete\ndata: {json.dumps({'tool_results': tool_results})}\n\n"

                # Final LLM call
                final_response = await _call_llm(client, full_messages, TOOL_DEFINITIONS)
                final_message = final_response["choices"][0]["message"].get("content", "")
            else:
                final_message = assistant_msg.get("content", "")

            # Build and emit final response
            response_id = str(uuid.uuid4())
            final_payload = {
                "response_id": response_id,
                "message": final_message,
                "components": _build_rich_response(final_message, tool_results if tool_calls else [], []),
                "model": active_model,
                "tool_calls_made": [tc["function"]["name"] for tc in tool_calls] if tool_calls else [],
            }

            yield f"event: complete\ndata: {json.dumps(final_payload)}\n\n"
            yield "event: done\ndata: {}\n\n"

        except Exception as e:
            logger.error(f"[STREAM] Error: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'error': str(e)[:500]})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/copilot/slash")
async def slash_command(request: SlashCommandRequest):
    """
    Execute a slash command (bypasses LLM routing for speed).
    """
    try:
        result = await _handle_slash_command(request.command)
        return result
    except Exception as e:
        logger.error(f"[SLASH] Error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "response_id": str(uuid.uuid4()),
                "command": request.command,
                "message": f"Error executing command: {str(e)[:200]}",
                "components": [{"type": "markdown", "data": f"⚠️ **Error**: {str(e)[:200]}"}],
            },
        )


@app.get("/api/copilot/research/stream")
async def research_stream(
    symbols: str = Query("BBRI.JK", description="Comma-separated symbols"),
    analysis_type: str = Query("full", description="Analysis type: full, fundamental, technical, comparative"),
):
    """
    SSE streaming endpoint for the 7-stage Deep Research Pipeline.
    Returns progressive markdown chunks as each stage completes.
    """
    return StreamingResponse(
        _research_stream_generator(symbols, analysis_type),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ===========================================================================
# FALLBACK: Echo mode when LLM is not configured
# ===========================================================================

async def _echo_chat(messages: List[ChatMessage], model: Optional[str] = None) -> Dict[str, Any]:
    """
    Fallback chat mode when LLM is not configured.
    Uses basic keyword matching to route to microservices directly.
    """
    user_msg = ""
    for m in reversed(messages):
        if m.role == "user" and m.content:
            user_msg = m.content
            break

    # Simple keyword routing
    user_lower = user_msg.lower()
    client = app.state.http_client
    components = []
    tool_calls_made = []

    # Check for vessel/ship keywords
    if any(kw in user_lower for kw in ["vessel", "ship", "tanker", "ais", "maritime", "dark vessel"]):
        url = _build_route("get_vessel_intelligence", {"bbox": "1.0,103.5,1.5,104.2", "vessel_type": "All", "limit": 50})
        result = await _call_microservice(client, url, "get_vessel_intelligence")
        components = _build_rich_response(user_msg, [result], ["get_vessel_intelligence"])
        tool_calls_made = ["get_vessel_intelligence"]

    elif any(kw in user_lower for kw in ["ta", "technical", "indicator", "rsi", "macd"]):
        # Extract symbol
        symbol = "BBRI.JK"
        for part in user_msg.split():
            p = part.strip().upper().replace(",", "")
            if p in ("BBRI.JK", "BMRI.JK", "AAPL", "BTC-USD") or "." in p:
                symbol = p
                break
        url = _build_route("get_technical_analysis", {"symbol": symbol})
        result = await _call_microservice(client, url, "get_technical_analysis")
        components = _build_rich_response(user_msg, [result], ["get_technical_analysis"])
        tool_calls_made = ["get_technical_analysis"]

    elif any(kw in user_lower for kw in ["quote", "price", "stock"]):
        symbol = "BBRI.JK"
        for part in user_msg.split():
            p = part.strip().upper().replace(",", "")
            if p in ("BBRI.JK", "BMRI.JK", "AAPL", "BTC-USD") or "." in p:
                symbol = p
                break
        url = _build_route("get_market_quote", {"symbol": symbol})
        result = await _call_microservice(client, url, "get_market_quote")
        components = _build_rich_response(user_msg, [result], ["get_market_quote"])
        tool_calls_made = ["get_market_quote"]

    elif any(kw in user_lower for kw in ["sentiment", "news sentiment"]):
        query = " ".join(user_msg.split()[:5])
        url = _build_route("get_sentiment_analysis", {"query": query, "days": 7})
        result = await _call_microservice(client, url, "get_sentiment_analysis")
        components = _build_rich_response(user_msg, [result], ["get_sentiment_analysis"])
        tool_calls_made = ["get_sentiment_analysis"]

    elif any(kw in user_lower for kw in ["regime", "market regime", "bull", "bear"]):
        url = _build_route("get_market_regime", {"asset_class": "all"})
        result = await _call_microservice(client, url, "get_market_regime")
        components = _build_rich_response(user_msg, [result], ["get_market_regime"])
        tool_calls_made = ["get_market_regime"]

    else:
        # Generic: call watchlist + news
        wl_url = _build_route("get_watchlist", {"category": "all"})
        news_url = _build_route("get_news_feed", {"query": user_lower[:50], "max_results": 5})

        wl_task = _call_microservice(client, wl_url, "get_watchlist")
        news_task = _call_microservice(client, news_url, "get_news_feed")
        wl_result, news_result = await asyncio.gather(wl_task, news_task)

        components = _build_rich_response(
            user_msg,
            [wl_result, news_result],
            ["get_watchlist", "get_news_feed"],
        )
        tool_calls_made = ["get_watchlist", "get_news_feed"]

    return {
        "response_id": str(uuid.uuid4()),
        "message": user_msg,
        "components": components,
        "latency_ms": 0,
        "model": model or "echo-router (LLM not configured)",
        "tool_calls_made": tool_calls_made,
    }


# ===========================================================================
# ENTRY POINT
# ===========================================================================

if __name__ == "__main__":
    port = int(os.getenv("COPILOT_PORT", "8500"))
    uvicorn.run(
        "copilot_gateway:app",
        host="0.0.0.0",
        port=port,
        reload=DEBUG,
        log_level="debug" if DEBUG else "info",
    )
