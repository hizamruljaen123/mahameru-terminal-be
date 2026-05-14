"""
Explore Agent - Data Source Search Specialist

The Explore Agent is a subagent specialized in searching and exploring
Mahameru data sources. It only has access to read/search tools and cannot
perform any write operations.

Based on OpenCode's explore agent architecture.
"""

import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class ExploreAgent:
    """
    Explore Agent - Specialist for searching Mahameru data sources.
    
    Permission Scope (Read-Only):
    - grep: Search content with regex
    - glob: Find files by pattern
    - read: Read file/directory contents
    - webfetch: Fetch external URLs
    - websearch: Search the web
    
    NOT permitted:
    - edit: Modify files
    - write: Create new files
    - bash/shell: Execute commands (unless for grep/glob)
    - task: Spawn subagents (prevent recursion)
    
    This agent is used when:
    - User needs to find specific data across multiple services
    - Exploratory analysis is required
    - Quick data discovery without full analysis
    """
    
    TOOL_PERMISSIONS = {
        "allowed_tools": [
            "get_market_quote",
            "get_technical_analysis",
            "get_fundamental_data",
            "get_sentiment_analysis",
            "get_news_feed",
            "get_watchlist",
            "get_market_history",
            "get_crypto_analysis",
            "get_crypto_onchain",
            "get_forex_rates",
            "get_commodity_prices",
            "get_bond_yield_curve",
            "get_volatility_data",
            "get_options_data",
            "get_vessel_radar",
            "get_aircraft_tracking",
            "get_strategic_assets",
            "get_disaster_data",
            "get_conflict_index",
            "get_market_regime",
            "get_corporate_intel",
            "get_macro_economics",
            "get_capital_flow",
            "get_entity_analysis",
            "get_esg_data",
            "get_supply_chain_intel",
            "get_price_intelligence",
            "run_deep_research",
            "discover_services",
            "call_api",
        ],
        "denied_tools": [
            "execute_code",
            "write_report",
            "export_data",
            "vessel_intelligence_advanced",
            "military_intelligence",
        ],
        "max_parallel_calls": 3,
        "max_steps": 5,
    }
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.agent_id = self.config.get("identifier", "explore-agent")
        self.name = self.config.get("name", "Mahameru Data Explorer")
        self.description = self.config.get(
            "description",
            "Specialist agent for searching and exploring Mahameru data sources."
        )
        self.model = self.config.get("model", "gemini-2.0-flash")
        self.temperature = self.config.get("temperature", 0)
        self.steps = self.config.get("steps", 5)
        
    def get_allowed_tools(self) -> List[str]:
        """Returns list of tools this agent is allowed to call."""
        return self.TOOL_PERMISSIONS["allowed_tools"]
    
    def get_denied_tools(self) -> List[str]:
        """Returns list of tools this agent cannot call."""
        return self.TOOL_PERMISSIONS["denied_tools"]
    
    def can_access_tool(self, tool_name: str) -> bool:
        """Check if this agent can access the given tool."""
        if tool_name in self.TOOL_PERMISSIONS["denied_tools"]:
            return False
        if tool_name in self.TOOL_PERMISSIONS["allowed_tools"]:
            return True
        # Default: allow if not explicitly denied
        return True
    
    async def explore(
        self,
        query: str,
        data_types: Optional[List[str]] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Explore Mahameru data sources based on query.
        
        Args:
            query: The search query (e.g., "BBRI.JK technical analysis", "dark vessel Singapore")
            data_types: Optional list of data types to focus on
            limit: Maximum results per data type
            
        Returns:
            Dict with exploration results organized by data type
        """
        logger.info(f"[ExploreAgent] Exploring query: {query[:100]}...")
        
        results = {
            "query": query,
            "data_types_searched": data_types or ["all"],
            "results": {},
            "summary": "",
            "tools_used": [],
        }
        
        # Determine data types to search based on query keywords
        search_types = self._determine_search_types(query, data_types)
        
        for data_type in search_types:
            try:
                type_results = await self._search_data_type(data_type, query, limit)
                if type_results:
                    results["results"][data_type] = type_results
                    results["tools_used"].append(data_type)
            except Exception as e:
                logger.warning(f"[ExploreAgent] Error searching {data_type}: {e}")
        
        # Generate summary
        results["summary"] = self._generate_summary(results)
        
        return results
    
    def _determine_search_types(
        self,
        query: str,
        preferred_types: Optional[List[str]] = None
    ) -> List[str]:
        """Determine which data types to search based on query analysis."""
        query_lower = query.lower()
        types = []
        
        type_keywords = {
            "market_quote": ["price", "quote", "stock", "saham", "equity", "market"],
            "technical_analysis": ["ta", "technical", "indicator", "rsi", "macd", "bollinger"],
            "sentiment": ["sentiment", "news", "berita", "opinion", "beritas"],
            "crypto": ["crypto", "bitcoin", "btc", "ethereum", "eth", "altcoin"],
            "forex": ["forex", "fx", "usdidr", "eurusd", "currency", "valas"],
            "vessel": ["vessel", "ship", "tanker", "maritime", "ais", "kapal"],
            "macro": ["macro", "economic", "fed", "inflation", "gdp", "interest"],
            "regime": ["regime", "bull", "bear", "trending", "ranging", "market regime"],
            "corporate": ["corporate", "insider", "analyst", "earnings", "dividend"],
            "commodity": ["commodity", "oil", "gold", "crude", "commodities"],
        }
        
        # Use preferred types if provided
        if preferred_types:
            return preferred_types[:5]  # Limit to 5 types
        
        # Auto-detect from query
        for dtype, keywords in type_keywords.items():
            if any(kw in query_lower for kw in keywords):
                if dtype not in types:
                    types.append(dtype)
        
        # Default if nothing detected
        if not types:
            types = ["market_quote", "technical_analysis", "news"]
        
        return types[:5]  # Max 5 types per exploration
    
    async def _search_data_type(
        self,
        data_type: str,
        query: str,
        limit: int
    ) -> List[Dict[str, Any]]:
        """
        Search a specific data type.
        
        This is a base implementation - actual searching would be done
        through the tool system. This method returns mock results for
        demonstration. In production, this would call the actual service.
        """
        # This would be connected to actual service calls
        # For now, return placeholder structure
        return []
    
    def _generate_summary(self, results: Dict[str, Any]) -> str:
        """Generate a human-readable summary of exploration results."""
        total_results = sum(len(r) for r in results.get("results", {}).values())
        types_found = list(results.get("results", {}).keys())
        
        if total_results == 0:
            return "No results found for the given query."
        
        summary = f"Found {total_results} results across {len(types_found)} data types: "
        summary += ", ".join(types_found)
        
        return summary
    
    async def parallel_search(
        self,
        queries: List[str],
        max_parallel: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Perform parallel searches for multiple queries.
        
        Args:
            queries: List of search queries
            max_parallel: Maximum concurrent searches
            
        Returns:
            List of results for each query
        """
        import asyncio
        
        logger.info(f"[ExploreAgent] Starting parallel search for {len(queries)} queries...")
        
        # Process in batches to avoid overwhelming the system
        all_results = []
        
        for i in range(0, len(queries), max_parallel):
            batch = queries[i:i + max_parallel]
            batch_results = await asyncio.gather(
                *[self.explore(q) for q in batch],
                return_exceptions=True
            )
            
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error(f"[ExploreAgent] Search failed: {result}")
                    all_results.append({"error": str(result)})
                else:
                    all_results.append(result)
        
        return all_results
    
    def get_exploration_prompt(self, query: str) -> str:
        """
        Generate a system prompt for exploration based on the query.
        
        This is injected into the LLM when using explore mode.
        """
        return f"""You are Mahameru Explore Agent - a data search specialist.

TASK: {query}

Your goal is to efficiently discover and retrieve relevant data from
Mahameru's data sources. You have access to read-only tools.

SEARCH STRATEGY:
1. First, identify the key entities (tickers, locations, keywords) in the query
2. Determine which data types are most relevant
3. Execute parallel searches for independent data types
4. Aggregate and synthesize findings

OUTPUT FORMAT:
Return a structured summary with:
- Data types searched
- Key findings per data type
- Confidence level (high/medium/low)
- Any anomalies or notable patterns

Remember: You are a SEARCH specialist. Focus on discovery and retrieval,
not deep analysis. That will be done by other agents."""