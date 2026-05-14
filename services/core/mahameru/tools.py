"""
Mahameru Tool Registry - Tool-Based Context Retrieval

This module implements the OpenCode pattern of treating microservices
as "tools" that agents can call with proper permission control.

Based on OpenCode's Tool System architecture.
"""

import logging
from typing import Dict, List, Any, Optional, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class PermissionLevel(Enum):
    """Permission levels for tool access."""
    ALLOW = "allow"      # Execute without confirmation
    ASK = "ask"          # Require user confirmation
    DENY = "deny"        # Tool not available


class ToolDefinition:
    """
    Represents a single tool that can be called by agents.
    
    Each tool has:
    - name: Unique identifier
    - description: What the tool does (for LLM selection)
    - parameters: JSON schema for tool arguments
    - permission: Permission level required
    - handler: Async function to execute the tool
    - category: Tool category (market_data, intelligence, analysis, etc.)
    """
    
    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        permission: PermissionLevel = PermissionLevel.ALLOW,
        category: str = "general",
        examples: Optional[List[str]] = None,
        handler: Optional[Callable] = None,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.permission = permission
        self.category = category
        self.examples = examples or []
        self.handler = handler
    
    def to_openai_format(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "permission": self.permission.value,
            "category": self.category,
            "examples": self.examples,
        }


class ToolRegistry:
    """
    Registry of all available tools with permission management.
    
    This implements the Tool-Based Retrieval pattern where:
    1. All Mahameru microservices are wrapped as "tools"
    2. Each tool has a permission level
    3. Agents can only access tools they have permission for
    4. Tools are filtered based on agent's permission ruleset
    
    Based on OpenCode's ToolRegistry + Permission System.
    """
    
    # Default tool definitions for Mahameru services
    DEFAULT_TOOLS = {
        # === MARKET DATA TOOLS === #
        "get_market_quote": {
            "name": "get_market_quote",
            "description": "Get real-time market quote for a stock, crypto, or forex symbol. Returns current price, change, volume, and day range.",
            "category": "market_data",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Symbol to query (e.g., BBRI.JK, BTC-USD, USDIDR)"
                    }
                },
                "required": ["symbol"]
            },
            "examples": [
                "/quote BBRI.JK",
                "What's the price of BTC-USD?"
            ]
        },
        
        "get_technical_analysis": {
            "name": "get_technical_analysis",
            "description": "Get technical analysis indicators (RSI, MACD, Bollinger Bands, Moving Averages, Support/Resistance). Includes regime-adaptive signal generation.",
            "category": "market_data",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Stock/Crypto symbol"},
                    "timeframe": {
                        "type": "string", 
                        "enum": ["1d", "1w", "1mo"],
                        "description": "Timeframe for analysis"
                    }
                },
                "required": ["symbol"]
            },
            "examples": [
                "/ta BBRI.JK",
                "Show technicals for ETH-USD"
            ]
        },
        
        "get_market_history": {
            "name": "get_market_history",
            "description": "Get historical price data with OHLCV candles for a symbol across multiple timeframes.",
            "category": "market_data",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "period": {"type": "string", "enum": ["1d", "5d", "1mo", "3mo", "6mo", "1y", "5y"]},
                    "interval": {"type": "string", "enum": ["1m", "5m", "15m", "1h", "1d", "1wk"]}
                },
                "required": ["symbol"]
            },
            "examples": [
                "Show me 6 months of ASII.JK data"
            ]
        },
        
        "get_watchlist": {
            "name": "get_watchlist",
            "description": "Get current prices and changes for the standard watchlist (indices, blue chips, crypto, forex).",
            "category": "market_data",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["all", "indices", "stocks", "crypto", "forex", "commodities"],
                        "description": "Filter by category"
                    }
                }
            },
            "examples": [
                "Show my watchlist",
                "What's moving in the market?"
            ]
        },
        
        # === CRYPTO TOOLS === #
        "get_crypto_analysis": {
            "name": "get_crypto_analysis",
            "description": "Get comprehensive crypto analysis including price, market cap, volume, and sector performance.",
            "category": "crypto",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Crypto symbol (e.g., BTC, ETH)"},
                    "timeframe": {"type": "string", "enum": ["1h", "1d", "1w"]}
                },
                "required": ["symbol"]
            },
            "examples": [
                "/crypto BTC",
                "Analyze Ethereum's performance"
            ]
        },
        
        "get_crypto_onchain": {
            "name": "get_crypto_onchain",
            "description": "Get on-chain metrics: exchange flows, whale transactions, NVT ratio, DeFi TVL.",
            "category": "crypto",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific metrics to fetch"
                    }
                },
                "required": ["symbol"]
            },
            "examples": [
                "Show whale activity for BTC",
                "What's the NVT ratio for ETH?"
            ]
        },
        
        "get_crypto_derivatives": {
            "name": "get_crypto_derivatives",
            "description": "Get derivatives data: funding rates, open interest, liquidation zones, perp prices.",
            "category": "crypto",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"}
                },
                "required": ["symbol"]
            }
        },
        
        # === NEWS & SENTIMENT TOOLS === #
        "get_news_feed": {
            "name": "get_news_feed",
            "description": "Get latest news from 80+ RSS sources. Filter by category (Indonesia, Business, Geopolitics, Energy, etc.) and keyword search.",
            "category": "intelligence",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword"},
                    "category": {"type": "string", "description": "News category"},
                    "max_results": {"type": "integer", "default": 10}
                }
            },
            "examples": [
                "/news Indonesia",
                "Latest news about Tesla"
            ]
        },
        
        "get_sentiment_analysis": {
            "name": "get_sentiment_analysis",
            "description": "Get BERT-based sentiment analysis for a topic or ticker. Returns aggregated sentiment score (-1 to 1), confidence, and breakdown by source.",
            "category": "intelligence",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "days": {"type": "integer", "default": 7},
                    "language": {"type": "string", "enum": ["auto", "en", "id"]}
                },
                "required": ["query"]
            },
            "examples": [
                "/sentiment BBRI.JK",
                "What's the sentiment on oil?"
            ]
        },
        
        # === TECHNICAL & QUANT TOOLS === #
        "get_deep_ta": {
            "name": "get_deep_ta",
            "description": "Get advanced technical analysis with 50+ indicators: Volume analysis, Momentum entropy, Pattern recognition, Smart money concepts, Volatility risk, Composite scoring.",
            "category": "analysis",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": ["volume", "momentum", "trend", "pattern", "volatility", "composite"],
                        "description": "Analysis category"
                    }
                },
                "required": ["symbol"]
            },
            "examples": [
                "Run deep TA on BBCA.JK"
            ]
        },
        
        "get_market_regime": {
            "name": "get_market_regime",
            "description": "Get HMM-based market regime detection: Bull, Bear, Sideways, or Volatile regime classification with transition probabilities.",
            "category": "analysis",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "asset_class": {
                        "type": "string",
                        "enum": ["all", "equity", "crypto", "forex", "commodity"],
                        "description": "Asset class to analyze"
                    }
                }
            },
            "examples": [
                "/regime",
                "What's the current market regime?"
            ]
        },
        
        "run_deep_research": {
            "name": "run_deep_research",
            "description": "Execute 7-stage deep research pipeline for a ticker: Business Model → Technical Analysis → Fundamental → Comparative Scorecard → News Sentiment → Leadership → Final Report. Streams results via SSE.",
            "category": "analysis",
            "permission": PermissionLevel.ASK,
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "analysis_type": {
                        "type": "string",
                        "enum": ["full", "fundamental", "technical", "comparative"],
                        "default": "full"
                    }
                },
                "required": ["symbol"]
            },
            "examples": [
                "/research BBRI.JK",
                "Deep research on PTBA.JK"
            ]
        },
        
        # === VESSEL & MARITIME TOOLS === #
        "get_vessel_radar": {
            "name": "get_vessel_radar",
            "description": "Get real-time AIS vessel tracking for a port, strait, or geographic area. Returns vessel list with MMSI, name, type, flag, speed, heading, and coordinates.",
            "category": "intelligence",
            "permission": PermissionLevel.ASK,
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "Port name, strait, or area (e.g., Singapore, Malacca, Jakarta)"},
                    "vessel_type": {"type": "string", "description": "Filter by vessel type"},
                    "limit": {"type": "integer", "default": 50}
                },
                "required": ["location"]
            },
            "examples": [
                "/vessel Singapore",
                "Show tankers in Strait of Malacca"
            ]
        },
        
        "get_vessel_intelligence": {
            "name": "get_vessel_intelligence",
            "description": "Get advanced vessel intelligence: dark vessel detection, route deviation alerts, floating storage estimation, inventory model for oil tankers.",
            "category": "intelligence",
            "permission": PermissionLevel.DENY,
            "parameters": {
                "type": "object",
                "properties": {
                    "bbox": {
                        "type": "object",
                        "description": "Bounding box {min_lat, max_lat, min_lon, max_lon}"
                    },
                    "alert_type": {"type": "string", "enum": ["dark_vessel", "route_deviation", "speed_anomaly"]}
                }
            },
            "examples": [
                "Detect dark vessels in South China Sea"
            ]
        },
        
        # === MACRO & ECONOMICS TOOLS === #
        "get_macro_economics": {
            "name": "get_macro_economics",
            "description": "Get macroeconomic indicators from FRED: Interest rates, CPI, PPI, PCE, GDP, NFP, PMI, Consumer confidence. Supports multiple countries.",
            "category": "macro",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "country": {"type": "string", "enum": ["US", "EU", "ID", "CN", "JP", "GB"]},
                    "indicator": {"type": "string"},
                    "period": {"type": "string"}
                }
            },
            "examples": [
                "/macro",
                "What's US CPI inflation?"
            ]
        },
        
        "get_bond_yield_curve": {
            "name": "get_bond_yield_curve",
            "description": "Get global bond yield data: US Treasuries, Eurozone, Japan, UK, Australia, Indonesia. Includes yield curve construction (2Y-10Y spread) and inversion detection.",
            "category": "macro",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "country": {"type": "string"},
                    "tenor": {"type": "string", "enum": ["2Y", "5Y", "10Y", "30Y"]}
                }
            },
            "examples": [
                "Show US yield curve",
                "Is the yield curve inverted?"
            ]
        },
        
        "get_volatility_data": {
            "name": "get_volatility_data",
            "description": "Get VIX index, term structure, volatility regime, volatility surface data, implied vs historical volatility comparison.",
            "category": "macro",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "index": {"type": "string", "enum": ["VIX", "VVIX", "OVX"]}
                }
            },
            "examples": [
                "What's VIX telling us?",
                "Show volatility regime"
            ]
        },
        
        "get_capital_flow": {
            "name": "get_capital_flow",
            "description": "Get capital flow data: sector rotation, ETF flows, safe haven flows, risk-on/risk-off regime, cross-asset correlation shifts.",
            "category": "macro",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "flow_type": {"type": "string", "enum": ["sector", "etf", "safe_haven"]}
                }
            },
            "examples": [
                "Show sector rotation",
                "Where is capital flowing?"
            ]
        },
        
        # === FOREX & COMMODITIES === #
        "get_forex_rates": {
            "name": "get_forex_rates",
            "description": "Get forex rates for 48 currency pairs. Focus on Indonesia pairs (USDIDR, EURIDR, etc.) plus major pairs (EURUSD, GBPUSD, USDJPY).",
            "category": "market_data",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "pair": {"type": "string", "description": "Currency pair (e.g., USDIDR, EURUSD)"},
                    " timeframe": {"type": "string", "enum": ["realtime", "1h", "1d"]}
                }
            },
            "examples": [
                "/forex USDIDR",
                "Show EURUSD rate"
            ]
        },
        
        "get_commodity_prices": {
            "name": "get_commodity_prices",
            "description": "Get commodity prices: Crude oil (WTI, Brent), Natural Gas, Gold, Silver, Copper, Agricultural (Wheat, Corn, Soybeans, Coffee).",
            "category": "market_data",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "commodity": {"type": "string"},
                    "timeframe": {"type": "string"}
                }
            },
            "examples": [
                "What's gold price?",
                "Show crude oil prices"
            ]
        },
        
        # === CORPORATE INTELLIGENCE === #
        "get_corporate_intel": {
            "name": "get_corporate_intel",
            "description": "Get corporate intelligence: insider trading, analyst ratings, earnings calendar, dividend calendar, price targets.",
            "category": "intelligence",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "data_type": {
                        "type": "string",
                        "enum": ["insider", "analyst", "earnings", "dividends", "all"]
                    }
                },
                "required": ["symbol"]
            },
            "examples": [
                "Show insider trading for BBRI",
                "When is BBCA earnings?"
            ]
        },
        
        # === GEOSPATIAL & STRATEGIC ASSETS === #
        "get_strategic_assets": {
            "name": "get_strategic_assets",
            "description": "Query strategic assets database: Global mines (24K+), power plants (34K+), oil refineries, ports, airports, datacenters, government facilities.",
            "category": "intelligence",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "asset_type": {
                        "type": "string",
                        "enum": ["mines", "power_plants", "refineries", "ports", "airports", "datacenters", "government"]
                    },
                    "country": {"type": "string"},
                    "filters": {"type": "object"}
                },
                "required": ["asset_type"]
            },
            "examples": [
                "Show oil refineries in Singapore",
                "List power plants in Indonesia"
            ]
        },
        
        "get_disaster_data": {
            "name": "get_disaster_data",
            "description": "Get disaster and crisis monitoring: earthquakes (USGS, BMKG), weather events (GDACS, NASA EONET), fire hotspots (NASA FIRMS). Includes market risk panel.",
            "category": "intelligence",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {"type": "string"},
                    "event_type": {"type": "string", "enum": ["earthquake", "weather", "fire", "all"]},
                    "severity": {"type": "string", "enum": ["low", "medium", "high", "all"]}
                }
            },
            "examples": [
                "Show recent earthquakes in Indonesia",
                "Any disasters near Singapore?"
            ]
        },
        
        "get_conflict_index": {
            "name": "get_conflict_index",
            "description": "Get conflict and military intelligence: global conflicts (53+), military strength (GFP), government facilities, military news aggregation.",
            "category": "intelligence",
            "permission": PermissionLevel.ASK,
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {"type": "string"},
                    "data_type": {"type": "string", "enum": ["conflicts", "military", "facilities"]}
                }
            },
            "examples": [
                "Show active conflicts in Middle East",
                "Military strength comparison China vs US"
            ]
        },
        
        # === ESG & SUPPLY CHAIN === #
        "get_esg_data": {
            "name": "get_esg_data",
            "description": "Get ESG scores and ratings, environmental risk assessment, social responsibility metrics, governance quality indicators, controversy monitoring.",
            "category": "analysis",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "metric": {"type": "string", "enum": ["environmental", "social", "governance", "overall"]}
                },
                "required": ["symbol"]
            },
            "examples": [
                "Show ESG scores for BBCA.JK"
            ]
        },
        
        "get_supply_chain_intel": {
            "name": "get_supply_chain_intel",
            "description": "Get supply chain intelligence: Supply Chain Pressure Index, global trade flows, shipping costs, port congestion, supplier concentration risk.",
            "category": "macro",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "region": {"type": "string"},
                    "indicator": {"type": "string"}
                }
            },
            "examples": [
                "Show supply chain pressure index",
                "Port congestion in Shanghai?"
            ]
        },
        
        # === ENTITY ANALYSIS === #
        "get_entity_analysis": {
            "name": "get_entity_analysis",
            "description": "Get entity correlation analysis: Visual entity graph, drag-and-drop relationship mapping, project file management (.ecp), entity news panel.",
            "category": "analysis",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_name": {"type": "string"},
                    "correlation_type": {"type": "string"}
                },
                "required": ["entity_name"]
            }
        },
        
        # === DISCOVERY & UTILITY === #
        "discover_services": {
            "name": "discover_services",
            "description": "Discover available Mahameru services and their capabilities. Returns list of all services with descriptions.",
            "category": "utility",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Filter by category"}
                }
            },
            "examples": [
                "What services are available?",
                "Show all market data services"
            ]
        },
        
        "call_api": {
            "name": "call_api",
            "description": "Make a dynamic API call to any Mahameru microservice endpoint. Use for custom queries not covered by specific tools.",
            "category": "utility",
            "permission": PermissionLevel.ASK,
            "parameters": {
                "type": "object",
                "properties": {
                    "endpoint": {"type": "string", "description": "API endpoint path"},
                    "method": {"type": "string", "enum": ["GET", "POST"]},
                    "params": {"type": "object"}
                },
                "required": ["endpoint"]
            },
            "examples": [
                "Call custom endpoint /api/v1/custom"
            ]
        },
        
        "use_skill": {
            "name": "use_skill",
            "description": "Load a pre-packaged instruction set (skill) for a specific workflow (e.g., hedging-strategy, earnings-analysis). Returns the skill instructions to guide your next steps.",
            "category": "orchestration",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {"type": "string", "description": "Name of the skill to load"}
                },
                "required": ["skill_name"]
            }
        },
        
        # === ORCHESTRATION TOOLS === #
        "dispatch_subagent": {
            "name": "dispatch_subagent",
            "description": "Dispatch a specialized subagent to perform a complex task. Use this to parallelize work or delegate to specialized agents.",
            "category": "orchestration",
            "permission": PermissionLevel.ALLOW,
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "ID of the subagent (e.g., explore-agent, analyst-agent, research-agent)"
                    },
                    "task": {
                        "type": "string",
                        "description": "The specific task instructions for the subagent."
                    }
                },
                "required": ["agent_id", "task"]
            },
            "examples": [
                "Dispatch explore-agent to find data"
            ]
        },
    }
    
    def __init__(self):
        self.tools: Dict[str, ToolDefinition] = {}
        self._register_default_tools()
        self._load_dynamic_tools()
    
    def _register_default_tools(self):
        """Register all default Mahameru tools."""
        for tool_id, tool_config in self.DEFAULT_TOOLS.items():
            self.register_tool(
                name=tool_config["name"],
                description=tool_config["description"],
                parameters=tool_config["parameters"],
                permission=tool_config["permission"],
                category=tool_config["category"],
                examples=tool_config.get("examples", [])
            )
        
        logger.info(f"[ToolRegistry] Registered {len(self.tools)} tools")
        
    def _load_dynamic_tools(self):
        import os
        import importlib.util
        import sys
        
        tools_dir = os.path.join(os.getcwd(), ".mahameru", "tools")
        if not os.path.exists(tools_dir):
            return
            
        for filename in os.listdir(tools_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                filepath = os.path.join(tools_dir, filename)
                module_name = f"mahameru_dynamic_tool_{filename[:-3]}"
                
                try:
                    spec = importlib.util.spec_from_file_location(module_name, filepath)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[module_name] = module
                        spec.loader.exec_module(module)
                        
                        # Look for a register_tools function or TOOL_DEFINITIONS list
                        if hasattr(module, "TOOL_DEFINITIONS"):
                            for tool_config in module.TOOL_DEFINITIONS:
                                self.register_tool(
                                    name=tool_config["name"],
                                    description=tool_config["description"],
                                    parameters=tool_config["parameters"],
                                    permission=tool_config.get("permission", PermissionLevel.ALLOW),
                                    category=tool_config.get("category", "custom"),
                                    examples=tool_config.get("examples", [])
                                )
                        logger.info(f"[ToolRegistry] Loaded custom tools from {filename}")
                except Exception as e:
                    logger.error(f"[ToolRegistry] Failed to load tool from {filename}: {e}")
    
    def register_tool(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        permission: PermissionLevel = PermissionLevel.ALLOW,
        category: str = "general",
        examples: Optional[List[str]] = None,
        handler: Optional[Callable] = None,
    ):
        """Register a new tool or update existing."""
        tool = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            permission=permission,
            category=category,
            examples=examples,
            handler=handler,
        )
        self.tools[name] = tool
        logger.debug(f"[ToolRegistry] Registered tool: {name}")
    
    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get a tool by name."""
        return self.tools.get(name)
    
    def get_tools_by_category(self, category: str) -> List[ToolDefinition]:
        """Get all tools in a category."""
        return [t for t in self.tools.values() if t.category == category]
    
    def get_all_tools(self) -> List[ToolDefinition]:
        """Get all registered tools."""
        return list(self.tools.values())
    
    def get_tools_for_agent(
        self,
        agent_permissions: Dict[str, str]
    ) -> List[ToolDefinition]:
        """
        Filter tools based on agent's permission ruleset.
        
        Args:
            agent_permissions: Dict mapping tool categories/actions to permission levels
            
        Returns:
            List of tools the agent is allowed to access
        """
        allowed_tools = []
        
        for tool in self.tools.values():
            # Check tool-specific permission if defined in agent ruleset
            tool_permission = agent_permissions.get(tool.name)
            
            if tool_permission is None:
                # Check category-level permission
                tool_permission = agent_permissions.get(tool.category)
            
            if tool_permission is None:
                # Default: if not specified, allow
                tool_permission = PermissionLevel.ALLOW
            
            # Convert string to PermissionLevel if needed
            if isinstance(tool_permission, str):
                try:
                    tool_permission = PermissionLevel(tool_permission)
                except ValueError:
                    tool_permission = PermissionLevel.ASK
            
            if tool_permission == PermissionLevel.ALLOW:
                allowed_tools.append(tool)
            elif tool_permission == PermissionLevel.ASK:
                # Include but mark as requiring confirmation
                allowed_tools.append(tool)
            # DENY = don't include
        
        return allowed_tools
    
    def check_tool_permission(
        self,
        tool_name: str,
        agent_permissions: Dict[str, str]
    ) -> PermissionLevel:
        """
        Check if an agent has permission to use a specific tool.
        
        Returns:
            PermissionLevel indicating what to do
        """
        tool = self.get_tool(tool_name)
        if not tool:
            return PermissionLevel.DENY
        
        # Check tool-specific rule
        tool_permission = agent_permissions.get(tool_name)
        
        if tool_permission is None:
            # Check category rule
            tool_permission = agent_permissions.get(tool.category)
        
        if tool_permission is None:
            # Default: use tool's own permission level
            return tool.permission
        
        if isinstance(tool_permission, str):
            try:
                return PermissionLevel(tool_permission)
            except ValueError:
                return PermissionLevel.ASK
        
        return tool_permission
    
    def to_function_definitions(self) -> List[Dict[str, Any]]:
        """Convert all tools to OpenAI function calling format."""
        return [tool.to_openai_format() for tool in self.tools.values()]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert registry to dictionary."""
        return {
            "total_tools": len(self.tools),
            "categories": list(set(t.category for t in self.tools.values())),
            "tools": [t.to_dict() for t in self.tools.values()],
        }


# Global instance
tool_registry = ToolRegistry()