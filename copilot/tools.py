"""
============================================================================
  Function Calling Tool Definitions (OpenAI/DeepSeek format)
  Maps natural language to Mahameru's 40+ microservices
============================================================================
"""

from typing import List, Dict, Any


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
            "description": "Get comprehensive technical analysis with indicators: RSI, MACD, Bollinger Bands, SMA, EMA, Stochastic, ADX, ATR, Volume, SAR, and more.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol e.g. BBRI.JK"},
                    "include": {"type": "string", "enum": ["all", "rsi", "macd", "bb", "sma", "ema", "stochastic", "adx", "atr", "volume", "sar"], "default": "all", "description": "Indicators to include (comma-separated or 'all')"},
                    "period": {"type": "string", "enum": ["1mo", "3mo", "6mo", "1y", "2y", "5y"], "default": "6mo", "description": "Analysis period"}
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
                    "commodity": {"type": "string", "description": "Specific commodity e.g. crude_oil, gold, copper", "default": ""}
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
                    "params": {"type": "object", "description": "Query parameters as a JSON object. Check discover_services for required params per endpoint.", "additionalProperties": True}
                },
                "required": ["service", "endpoint"]
            }
        }
    },
]
