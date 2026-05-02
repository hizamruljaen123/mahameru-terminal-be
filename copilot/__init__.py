"""
Mahameru Copilot — Modular LLM Gateway Package.

Provides a modular structure for the Mahameru Copilot LLM Gateway service.

Modules:
    config      — Environment configuration, constants, logging, port cleanup
    models      — Pydantic data models (ChatMessage, ChatRequest, etc.)
    tools       — 29 Function-calling TOOL_DEFINITIONS
    api_catalog — API_CATALOG (36 service groups), MICROSERVICE_ROUTES, MICROSERVICE_ROUTE_TEMPLATES
    slash_commands — SLASH_COMMANDS definitions (11 commands)
    helpers     — Internal helpers (_discover_services_handler, _call_api_handler,
                  _build_route, _call_microservice, _area_to_bbox)
    transformers — Component transformers (_build_rich_response, TA charts, sentiment,
                   vessel map, aircraft map, regime, market quote, generic)
    system_prompt — SYSTEM_PROMPT for the LLM agent
    llm         — LLM agent functions (_call_llm, _stream_llm, _execute_tool_plan, _llm_agent_loop)
"""

from copilot.config import (
    DEBUG, LLM_PROVIDER, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL,
    LLM_MAX_TOKENS, API_BASE, ENABLE_STREAMING, ENABLE_LLM,
    LOCAL_DEV, logger, clean_port,
)

from copilot.models import (
    ChatMessage, ChatRequest, ChatResponse,
    SlashCommandRequest, SlashCommandResponse,
)

from copilot.tools import TOOL_DEFINITIONS

from copilot.api_catalog import (
    API_CATALOG, MICROSERVICE_ROUTES, MICROSERVICE_ROUTE_TEMPLATES,
)

from copilot.slash_commands import SLASH_COMMANDS

from copilot.helpers import (
    _discover_services_handler, _call_api_handler,
    _build_route, _call_microservice,
    _AREA_BBOX_MAP, _area_to_bbox,
)

from copilot.transformers import (
    _build_rich_response, _is_echarts_compatible, _has_geojson,
    _extract_table_candidates,
    _transform_technical_analysis, _transform_market_quote,
    _transform_vessel_intel, _transform_aircraft,
    _transform_sentiment, _transform_regime, _transform_generic,
    _COMPONENT_TRANSFORMERS,
)

from copilot.system_prompt import SYSTEM_PROMPT

from copilot.llm import (
    _call_llm, _stream_llm, _execute_tool_plan, _llm_agent_loop,
)

__all__ = [
    # Config
    "DEBUG", "LLM_PROVIDER", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL",
    "LLM_MAX_TOKENS", "API_BASE", "ENABLE_STREAMING", "ENABLE_LLM",
    "LOCAL_DEV", "logger", "clean_port",
    # Models
    "ChatMessage", "ChatRequest", "ChatResponse",
    "SlashCommandRequest", "SlashCommandResponse",
    # Tools
    "TOOL_DEFINITIONS",
    # API Catalog
    "API_CATALOG", "MICROSERVICE_ROUTES", "MICROSERVICE_ROUTE_TEMPLATES",
    # Slash Commands
    "SLASH_COMMANDS",
    # Helpers
    "_discover_services_handler", "_call_api_handler",
    "_build_route", "_call_microservice",
    "_AREA_BBOX_MAP", "_area_to_bbox",
    # Transformers
    "_build_rich_response", "_is_echarts_compatible", "_has_geojson",
    "_extract_table_candidates",
    "_transform_technical_analysis", "_transform_market_quote",
    "_transform_vessel_intel", "_transform_aircraft",
    "_transform_sentiment", "_transform_regime", "_transform_generic",
    "_COMPONENT_TRANSFORMERS",
    # System Prompt
    "SYSTEM_PROMPT",
    # LLM
    "_call_llm", "_stream_llm", "_execute_tool_plan", "_llm_agent_loop",
]
