"""
============================================================================
  API CATALOG — Complete registry of all available microservice endpoints
  Enables the call_api tool to dynamically access any service
============================================================================
"""

from typing import Dict, Any
from copilot.config import API_BASE, LOCAL_DEV


# ===========================================================================
# SERVICE DISCOVERY LOGIC
# ===========================================================================

SERVICE_PORTS: Dict[str, int] = {
    "market": 8088,
    "ta": 5007,
    "deep-ta": 5200,
    "crypto": 8085,
    "forex": 8086,
    "bonds": 8145,
    "volatility": 8155,
    "options": 8165,
    "vessel": 8100,  # vessel_intelligence_service.py
    "sky": 5002,
    "infra": 8097,
    "sentiment": 5008,
    "regime": 8195,
    "corporate": 8185,
    "entity": 5005,
    "research": 5202,
    "news": 5101,
    "commodity": 8087,
    "capital-flow": 8175,
    "macro": 8205,
    "supply-chain": 8210,
    "disaster": 8095,
    "conflict": 8140,
    "geo": 8091,
}

def get_service_base(service_name: str, path: str = "") -> str:
    """Return the base URL for a service based on the environment."""
    # In Local Dev, we use port-based routing
    if LOCAL_DEV:
        port = SERVICE_PORTS.get(service_name)
        if port:
            return f"http://127.0.0.1:{port}{path}"
    
    # In Production, we use path-based routing via the gateway
    # Using {base} allows runtime injection in helpers._build_route
    return "{base}/" + service_name + path

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
            "sentiment_search": {"path": "/api/sentiment/search",           "method": "GET", "params": {"q": "str", "days": "int"}, "desc": "Search sentiment (gateway alias)"},
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
            "entity_summary":   {"path": "/api/entity/summary",             "method": "GET", "params": {"symbol": "str", "analysis_type": "full|fundamental|valuation"}, "desc": "Entity summary"},
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
    "get_market_quote":          get_service_base("market", "/api/market/quote"),
    "get_market_history":        get_service_base("market", "/api/market/history"),
    "get_technical_analysis":    get_service_base("ta", "/api/ta/analyze"),
    "get_watchlist":             get_service_base("market", "/api/market/watchlist"),
    "get_crypto_analysis":       get_service_base("crypto", "/api/crypto/analyze"),
    "get_crypto_onchain":        get_service_base("crypto", "/api/crypto/onchain"),
    "get_forex_rates":           get_service_base("forex", "/api/forex/rates"),
    "get_bond_yield_curve":      get_service_base("bonds", "/api/bonds/yield-curve"),
    "get_volatility_data":       get_service_base("volatility", "/api/volatility/summary"),
    "get_options_data":          get_service_base("options", "/api/options/summary"),

    # Geospatial & OSINT
    "get_vessel_intelligence":   get_service_base("vessel", "/api/vessels/search"),
    "get_vessel_radar":          get_service_base("vessel", "/intelligence/radar"),
    "get_aircraft_tracking":     get_service_base("sky", "/api/sky/aircraft"),
    "get_strategic_assets":      get_service_base("infra", "/api/infrastructure/search"),
    "get_disaster_data":         get_service_base("disaster", "/api/disaster/recent"),
    "get_conflict_index":        get_service_base("conflict", "/api/conflict/index"),

    # Deep Analysis & AI
    "run_deep_research":         get_service_base("research", "/api/analyze/report"),
    "get_sentiment_analysis":    get_service_base("sentiment", "/api/sentiment/search"),
    "get_market_regime":         get_service_base("regime", "/api/regime/current"),
    "get_corporate_intel":       get_service_base("corporate", "/api/corporate/summary"),
    "get_entity_analysis":       get_service_base("entity", "/api/entity/summary"),

    # Macro & Cross-Asset
    "get_macro_economics":       get_service_base("macro", "/api/macro/indicators"),
    "get_capital_flow":          get_service_base("capital-flow", "/api/capital-flow/summary"),
    "get_commodity_prices":      get_service_base("commodity", "/api/commodity/prices"),
    "get_esg_data":              get_service_base("market", "/api/market/esg/summary"),
    "get_supply_chain_intel":    get_service_base("supply-chain", "/api/supply-chain/summary"),
    "get_price_intelligence":    get_service_base("macro", "/api/price-intel/predict"),
    "get_news_feed":             get_service_base("news", "/api/news/search"),
}

MICROSERVICE_ROUTE_TEMPLATES: Dict[str, str] = {
    "get_market_quote":          get_service_base("market", "/api/market/price?symbol={symbol}"),
    "get_market_history":        get_service_base("market", "/api/market/history?symbol={symbol}&range={range}&interval={interval}"),
    "get_technical_analysis":    get_service_base("ta", "/api/ta/analyze/{symbol}?period={period}&include={include}"),
    "get_watchlist":             get_service_base("market", "/api/market/watchlist?category={category}"),
    "get_crypto_analysis":       get_service_base("crypto", "/api/crypto/analyze?symbol={symbol}&analysis_type={analysis_type}"),
    "get_crypto_onchain":        get_service_base("crypto", "/api/crypto/onchain?symbol={symbol}"),
    "get_forex_rates":           get_service_base("forex", "/api/forex/rates?pair={pair}&timeframe={timeframe}"),
    "get_bond_yield_curve":      get_service_base("bonds", "/api/bonds/yield-curve?country={country}&include_global={include_global}"),
    "get_volatility_data":       get_service_base("volatility", "/api/volatility/summary?metric={metric}"),
    "get_options_data":          get_service_base("options", "/api/options/summary?symbol={symbol}&metric={metric}"),
    "get_vessel_intelligence":   get_service_base("vessel", "/api/vessels/search?bbox={bbox}&vessel_type={vessel_type}&anomaly={anomaly}&limit={limit}"),
    "get_aircraft_tracking":     get_service_base("sky", "/api/sky/aircraft/{country_code}"),
    "get_strategic_assets":      get_service_base("infra", "/api/infrastructure/search?asset_type={asset_type}&country={country}&commodity={commodity}&limit={limit}"),
    "get_disaster_data":         get_service_base("disaster", "/api/disaster/recent?disaster_type={disaster_type}&min_magnitude={min_magnitude}&days={days}"),
    "get_conflict_index":        get_service_base("conflict", "/api/conflict/index?region={region}&days={days}"),
    "run_deep_research":         get_service_base("research", "/api/research/start?symbols={symbols}&analysis_type={analysis_type}"),
    "get_sentiment_analysis":    get_service_base("sentiment", "/api/sentiment/search?q={query}&days={days}"),
    "get_market_regime":         get_service_base("regime", "/api/regime/current?asset_class={asset_class}"),
    "get_corporate_intel":       get_service_base("corporate", "/api/corporate/summary/{symbol}?data_type={data_type}"),
    "get_entity_analysis":       get_service_base("entity", "/api/entity/summary?symbol={symbol}&analysis_type={analysis_type}"),
    "get_macro_economics":       get_service_base("macro", "/api/macro/indicators?indicator={indicator}&country={country}"),
    "get_capital_flow":          get_service_base("capital-flow", "/api/capital-flow/summary?flow_type={flow_type}"),
    "get_commodity_prices":      get_service_base("commodity", "/api/commodity/prices?sector={sector}&commodity={commodity}"),
    "get_esg_data":              get_service_base("market", "/api/market/esg/summary?symbol={symbol}&category={category}"),
    "get_supply_chain_intel":    get_service_base("supply-chain", "/api/supply-chain/summary?sector={sector}&metric={metric}"),
    "get_price_intelligence":    get_service_base("macro", "/api/price-intel/predict?symbol={symbol}&timeframe={timeframe}"),
    "get_news_feed":             get_service_base("news", "/api/news/search?q={query}&max={max_results}"),
    "get_vessel_radar":          get_service_base("vessel", "/intelligence/radar?location={location}"),
}
