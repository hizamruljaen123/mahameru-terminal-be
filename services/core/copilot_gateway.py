import os
import json
import uuid
import asyncio
import time
import logging
import subprocess
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

# ---------------------------------------------------------------------------
# Import from modular copilot package
# ---------------------------------------------------------------------------
from copilot.config import (
    DEBUG, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_MAX_TOKENS,
    API_BASE, ENABLE_STREAMING, ENABLE_LLM, LOCAL_DEV, COPILOT_ROOT_PATH, SSL_VERIFY, logger, clean_port,
)
from copilot.models.schemas import (
    ChatMessage, ChatRequest, ChatResponse, SlashCommandRequest, SlashCommandResponse,
    SessionInfo, HistoryUpdate, CodeExecutionRequest, CodeExecutionResponse
)
from copilot.api_catalog import API_CATALOG, MICROSERVICE_ROUTES, MICROSERVICE_ROUTE_TEMPLATES
from copilot.slash_commands import SLASH_COMMANDS
from copilot.helpers import _build_route, _call_microservice, _area_to_bbox, _extract_vessel_location
from copilot.transformers import _build_rich_response
from copilot.system_prompt import SYSTEM_PROMPT, CHAT_SYSTEM_PROMPT
from copilot.llm import (
    _call_llm, _stream_llm, _execute_tool_plan, _llm_agent_loop,
    _deduplicate_tool_calls, _trim_tool_result, _llm_plan_tools
)
# Mahameru Modular System
from mahameru.agents.registry import agent_registry
from mahameru.permissions import permission_service
from mahameru.history_service import history_service
from mahameru.orchestrator import CopilotOrchestrator
from mahameru.instructions import InstructionInjectionMiddleware
from mahameru.tools import ToolRegistry
from services.code_interpreter.service import CodeInterpreterService

# Deep Research (for /research slash command)
from copilot.deep_research import fetch_yfinance_technical, fetch_yfinance_fundamental, build_markdown_report

# Mahameru Agents
from mahameru.agents.plan_agent import PlanAgent
from mahameru.agents.explore_agent import ExploreAgent
from mahameru.agents.compaction_agent import CompactionAgent

# Global Instances
instruction_middleware = InstructionInjectionMiddleware()
mahameru_tool_registry = ToolRegistry()

# Use Mahameru ToolRegistry as single source of truth for LLM tool definitions
# (replaces legacy copilot.tools.TOOL_DEFINITIONS)
TOOL_DEFINITIONS = mahameru_tool_registry.to_function_definitions()

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

async def _generate_chat_title(message: str, model: str) -> str:
    """Generate a short, 3-5 word title for the chat using AI."""
    prompt = [
        {"role": "system", "content": "Generate a professional and concise title (3-5 words, max 5 words) for this chat session based on the user's message. Use Title Case (capitalize first letter of each word). Do NOT use all caps. Respond ONLY with the title text. No quotes, no prefix."},
        {"role": "user", "content": message}
    ]
    try:
        async with httpx.AsyncClient(verify=SSL_VERIFY) as client:
            response = await _call_llm(client, prompt, None, model)
            title = response["choices"][0]["message"]["content"]
            return title.strip().strip('"').strip("'")
    except Exception as e:
        logger.warning(f"Failed to generate title: {e}")
        return message[:40] + "..." if len(message) > 40 else message


async def _resolve_ticker_with_llm(text: str, model: str) -> str:
    """Extract stock ticker from natural language using a lightweight LLM call."""
    if not text or not ENABLE_LLM:
        return ""
    
    # Fast path: if it's already a single word ticker like BBRI.JK
    words = text.strip().split()
    if len(words) == 1:
        s = words[0].upper()
        if "." in s or (len(s) >= 3 and len(s) <= 6):
            if "." not in s and len(s) <= 5: s = f"{s}.JK"
            return s

    prompt = [
        {"role": "system", "content": "Extract the single primary stock ticker from the user prompt. For Indonesian stocks (BEI), ensure it has .JK suffix. If it's crypto, add -USD. If no ticker found, respond with 'NONE'. Respond ONLY with the ticker string."},
        {"role": "user", "content": text}
    ]
    try:
        async with httpx.AsyncClient(verify=SSL_VERIFY) as client:
            response = await _call_llm(client, prompt, None, model)
            res = response["choices"][0]["message"]["content"].strip().upper()
            return "" if "NONE" in res else res
    except Exception as e:
        logger.warning(f"Failed to resolve ticker with LLM: {e}")
        return words[0].upper() if words else ""

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup / shutdown."""
    logger.info(f"[BOOT] Mahameru Copilot Gateway starting on port 8500")
    logger.info(f"[BOOT] Root Path: {COPILOT_ROOT_PATH}")
    logger.info(f"[BOOT] LLM Model: {LLM_MODEL}")
    logger.info(f"[BOOT] LLM Base URL: {LLM_BASE_URL}")
    logger.info(f"[BOOT] API Base: {API_BASE}")
    logger.info(f"[BOOT] Streaming: {ENABLE_STREAMING}")
    logger.info(f"[BOOT] LLM Enabled: {ENABLE_LLM}")
    app.state.http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True, verify=SSL_VERIFY)
    
    # Initialize Unified History Service
    await history_service.initialize()
    
    # Initialize Orchestrator
    app.state.orchestrator = CopilotOrchestrator(TOOL_DEFINITIONS)
    
    yield
    await app.state.http_client.aclose()
    logger.info("[SHUTDOWN] Mahameru Copilot Gateway stopped")


app = FastAPI(
    debug=DEBUG,
    title="Mahameru Copilot — LLM Gateway Service",
    description="Enterprise Agentic AI Chatbot for Mahameru Terminal Ecosystem",
    version="2.0.0",
    lifespan=lifespan,
    root_path=COPILOT_ROOT_PATH,
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
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# PERMISSION MIDDLEWARE
# ---------------------------------------------------------------------------

@app.middleware("http")
async def permission_middleware(request: Request, call_next):
    # Always allow preflight requests
    if request.method == "OPTIONS":
        return await call_next(request)

    # Skip permission check for public endpoints or if no auth provided
    auth_header = request.headers.get("Authorization")
    tier = "GUEST" # Default tier
    
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        # TODO: Implement proper JWT verification for production.
        # For now, accept tier name as token OR env-configured admin token.
        _admin_token = os.getenv("MAHAMERU_ADMIN_TOKEN")
        if token.upper() in ["USER", "INSTITUTIONAL"]:
            tier = token.upper()
        elif _admin_token and token == _admin_token:
            tier = "INSTITUTIONAL"

    # Load ruleset for this tier
    ruleset = permission_service.get_ruleset_for_tier(tier)
    
    # We'll use request.state to pass the tier and ruleset
    request.state.user_tier = tier
    request.state.permissions = ruleset
    
    response = await call_next(request)
    return response


# ===========================================================================
# SLASH COMMAND HANDLER
# ===========================================================================

async def _handle_slash_command(command: str) -> Dict[str, Any]:
    """Parse and execute a slash command without LLM routing.
    
    For `/research`, uses yfinance directly (bypasses Flask research service).
    For other commands, routes through the microservice layer.
    """
    parts = command.strip().split()
    cmd_name = parts[0].lower()
    args = " ".join(parts[1:]) if len(parts) > 1 else ""

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

    # ── SPECIAL HANDLING FOR /research: USE YFINANCE DIRECTLY ──────────
    if cmd_name == "/research":
        # Ask LLM to resolve the ticker if args are complex
        symbol = await _resolve_ticker_with_llm(args, LLM_MODEL)
        
        if not symbol:
            symbol = "BBRI.JK"

        # Fetch real data from yfinance (modular fetchers)
        tech = fetch_yfinance_technical(symbol)
        fund = fetch_yfinance_fundamental(symbol)

        # Build comprehensive markdown report (unified builder)
        markdown, metadata = build_markdown_report(tech, fund, symbol)

        return {
            "response_id": str(uuid.uuid4()),
            "command": cmd_name,
            "message": markdown,
            "components": [
                {
                    "type": "markdown",
                    "data": markdown,
                    "metadata": metadata,
                }
            ],
        }

    # ── OTHER SLASH COMMANDS: route through microservice ───────────────
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

        if cmd_name in ("/ta", "/quote", "/crypto", "/news", "/sentiment"):
            # Use LLM to resolve the ticker from natural language args
            symbol = await _resolve_ticker_with_llm(args, LLM_MODEL)
            tool_args[props[0]] = symbol

        elif cmd_name == "/forex":
            pair = args.upper().split()[0] if args else "USDIDR"
            if "=" not in pair and "/" not in pair:
                if len(pair) == 6:
                    pair = f"{pair[:3]}={pair[3:]}X"
            tool_args["pair"] = pair

        elif cmd_name == "/vessel":
            client = app.state.http_client
            location = await _extract_vessel_location(client, args) if args else "Singapore"
            tool_args["location"] = location

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


# Deep Research Pipeline is now handled by copilot.deep_research modular package.


# ===========================================================================
# REST API ENDPOINTS
# ===========================================================================

@app.get("/")
async def root():
    return {
        "service": "Mahameru Copilot — LLM Gateway",
        "version": "2.0.0",
        "status": "operational",
        "base_url": "https://api.asetpedia.online/copilot",
        "endpoints": {
            "chat": "/api/copilot/chat",
            "stream": "/api/copilot/stream",
            "slash": "/api/copilot/slash",
            "research_stream": "/api/copilot/research/stream",
            "tools": "/api/copilot/tools",
            "health": "/api/copilot/health",
        },
        "llm_model": LLM_MODEL,
        "llm_enabled": ENABLE_LLM,
        "tools_registered": len(TOOL_DEFINITIONS),
        "environment": "production" if not LOCAL_DEV else "development"
    }


@app.get("/api/copilot/agents")
async def list_agents():
    """List all available AI agents in the Mahameru Registry."""
    return {
        "agents": agent_registry.list_agents()
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
async def list_tools(http_request: Request):
    """Return tool catalog (Mahameru ToolRegistry) for frontend introspection."""
    permissions = getattr(http_request.state, "permissions", permission_service.get_ruleset_for_tier("GUEST"))

    # Filter tools for this tier
    allowed = mahameru_tool_registry.get_tools_for_agent(permissions)
    allowed_defs = [t.to_openai_format() for t in allowed]

    user_tier = getattr(http_request.state, "user_tier", "GUEST")
    result = {
        "tools": allowed_defs,
        "tools_count": len(allowed_defs),
        "slash_commands": SLASH_COMMANDS,
        "routes": MICROSERVICE_ROUTES,
        "tier": user_tier,
    }
    # Only expose full unfiltered tool list to INSTITUTIONAL tier
    if user_tier == "INSTITUTIONAL":
        result["tools_all"] = TOOL_DEFINITIONS
    return result




@app.post("/api/copilot/chat", response_model=ChatResponse)
async def chat(http_request: Request, request: ChatRequest):
    """Main chat endpoint."""
    try:
        permissions = getattr(http_request.state, "permissions", permission_service.get_ruleset_for_tier("GUEST"))
        return await app.state.orchestrator.handle_chat(request, app.state.http_client, permissions)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 402:
            return {
                "response_id": str(uuid.uuid4()),
                "message": "⚠️ **API Balance Exhausted**: The selected model provider requires a top-up. Please notify the administrator or switch to another model.",
                "components": [{"type": "markdown", "data": "### 💳 Insufficient Balance\nYour API key has run out of credits. Please refill your balance at the provider's dashboard."}],
                "latency_ms": 0,
                "model": request.model or LLM_MODEL,
                "tool_calls_made": [],
            }
        raise
    except Exception as e:
        logger.error(f"[CHAT] Error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "response_id": str(uuid.uuid4()),
                "message": f"I encountered an error processing your request. Please try again or rephrase.",
                "components": [{"type": "markdown", "data": f"⚠️ **Error**: {str(e)[:200]}"}],
                "latency_ms": 0,
                "model": request.model or LLM_MODEL,
                "tool_calls_made": [],
            },
        )


@app.post("/api/copilot/stream")
async def chat_stream(http_request: Request, request: ChatRequest):
    """
    Chat with SSE streaming support.
    Returns a StreamingResponse that emits Rich Response components progressively.
    Emits real-time step progress events and LLM reasoning when available.
    """
    if not request.stream:
        return await chat(request)

    if not ENABLE_LLM or not LLM_API_KEY:
        return await _echo_chat(request.messages)

    permissions = getattr(http_request.state, "permissions", permission_service.get_ruleset_for_tier("GUEST"))
    return StreamingResponse(
        app.state.orchestrator.generate_chat_stream(request, app.state.http_client, permissions),
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
        
        # Save to history if session_id provided (Async)
        if request.session_id:
            await history_service.add_message(request.session_id, "user", request.command)
            await history_service.add_message(request.session_id, "assistant", result.get("message", ""), metadata={"agent_id": "slash"})
            
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


# ─── CODE INTERPRETER ENDPOINT ───────────────────────────────────────────

# Rate limiting for code execution (in-memory, per-session)
_code_exec_timestamps: Dict[str, float] = {}
_CODE_EXEC_RATE_LIMIT_SECONDS = 10  # min seconds between executions per session
_CODE_EXEC_MAX_TIMEOUT = 120

@app.post("/api/copilot/code/execute", response_model=CodeExecutionResponse)
async def execute_code(http_request: Request, request: CodeExecutionRequest):
    """
    Execute code in a sandboxed environment.
    Supports Python and JavaScript. Shell/bash/cmd execution is restricted.
    Requires at least USER tier authentication.
    """
    # Code execution permission check (User requested to allow all)
    user_tier = getattr(http_request.state, "user_tier", "GUEST")
    # if user_tier == "GUEST":
    #     raise HTTPException(status_code=403, detail="Code execution requires authentication (USER tier or above).")

    # Block shell/bash/cmd execution for security
    if request.language.lower() in ("bash", "shell", "cmd", "sh", "zsh", "powershell"):
        raise HTTPException(status_code=400, detail="Shell execution is not permitted. Use 'python' or 'javascript' instead.")

    # Cap timeout
    safe_timeout = min(request.timeout, _CODE_EXEC_MAX_TIMEOUT)

    # Rate limit per session (use client IP as fallback)
    client_id = getattr(http_request.state, "user_tier", "GUEST") + "_" + (http_request.client.host if http_request.client else "unknown")
    now = time.time()
    last_exec = _code_exec_timestamps.get(client_id, 0)
    if now - last_exec < _CODE_EXEC_RATE_LIMIT_SECONDS:
        raise HTTPException(status_code=429, detail=f"Rate limited. Please wait {_CODE_EXEC_RATE_LIMIT_SECONDS - int(now - last_exec)}s before executing again.")
    _code_exec_timestamps[client_id] = now

    logger.info(f"[CODE] Executing {request.language} code (tier={user_tier}, timeout={safe_timeout}s)...")
    result = await CodeInterpreterService.run_code(request.language, request.code, safe_timeout)
    return result



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

    # Echo mode no longer uses research auto-routing.

    # Check for vessel/ship keywords — use get_vessel_radar for visual radar
    if any(kw in user_lower for kw in ["vessel", "ship", "tanker", "ais", "maritime", "dark vessel"]):
        # Try to extract a location name from the message
        # Common port/strait names to look for
        known_locations = [
            "singapore", "malacca", "selat malaka", "dubai", "rotterdam", "shanghai",
            "shenzhen", "ningbo", "busan", "guangzhou", "qingdao", "hong kong",
            "jakarta", "tanjung priok", "surabaya", "belawan", "makassar",
            "panjang", "batam", "dumai", "palembang", "semarang",
        ]
        location = "singapore"  # default
        for loc in known_locations:
            if loc in user_lower:
                location = loc
                break
        # If no known location found, try last meaningful word
        if location == "singapore" and "singapore" not in user_lower:
            words = user_msg.split()
            # Take the last 1-3 words that aren't vessel/ship keywords
            for i in range(len(words) - 1, -1, -1):
                w = words[i].strip().lower().rstrip(".,!?")
                if w not in ("vessel", "ship", "tanker", "ais", "maritime", "the", "di", "wilayah", "radar", "tampilkan", "lihat", "cek", "cari", "saya", "kamu", "dan", "untuk", "yang", "ada", "di"):
                    location = w
                    break
        url = _build_route("get_vessel_radar", {"location": location})
        result = await _call_microservice(client, url, "get_vessel_radar")
        components = _build_rich_response(user_msg, [result], ["get_vessel_radar"])
        tool_calls_made = ["get_vessel_radar"]

    elif any(kw in user_lower for kw in ["ta", "technical", "indicator", "rsi", "macd"]):
        # Try simple extraction from message
        symbol = ""
        for word in user_msg.split():
            w = word.strip().upper().replace(",", "").replace(";", "")
            if "." in w or (w.isupper() and 3 <= len(w) <= 6):
                symbol = w
                break
        
        if symbol:
            if "." not in symbol and len(symbol) <= 5:
                symbol = f"{symbol}.JK"
            url = _build_route("get_technical_analysis", {"symbol": symbol})
            result = await _call_microservice(client, url, "get_technical_analysis")
            components = _build_rich_response(user_msg, [result], ["get_technical_analysis"])
            tool_calls_made = ["get_technical_analysis"]
        else:
            components = [{"type": "markdown", "data": "⚠️ **Echo Mode**: Maaf, saya tidak dapat mendeteksi simbol saham dalam pesan Anda untuk analisis teknikal. Silakan gunakan format `/ta [SYMBOL]` atau berikan nama ticker (contoh: BBRI)."}]

    elif any(kw in user_lower for kw in ["quote", "price", "stock"]):
        symbol = ""
        for word in user_msg.split():
            w = word.strip().upper().replace(",", "").replace(";", "")
            if "." in w or (w.isupper() and 3 <= len(w) <= 6):
                symbol = w
                break

        if symbol:
            if "." not in symbol and len(symbol) <= 5:
                symbol = f"{symbol}.JK"
            url = _build_route("get_market_quote", {"symbol": symbol})
            result = await _call_microservice(client, url, "get_market_quote")
            components = _build_rich_response(user_msg, [result], ["get_market_quote"])
            tool_calls_made = ["get_market_quote"]
        else:
            components = [{"type": "markdown", "data": "⚠️ **Echo Mode**: Simbol saham tidak terdeteksi. Silakan gunakan format `/quote [SYMBOL]`."}]

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



# ---------------------------------------------------------------------------
# History Management
# ---------------------------------------------------------------------------

@app.get("/api/copilot/history")
async def get_history(http_request: Request, user_id: str = "user"):
    """Fetch all chat sessions for a user."""
    sessions = await history_service.get_all_sessions(user_id)
    return sessions

@app.get("/api/copilot/history/{session_id}")
async def get_session_history(session_id: str):
    """Fetch all messages for a specific session."""
    messages = await history_service.get_messages(session_id)
    if not messages:
        # Fallback for UI if session exists but no messages
        session = await history_service.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return []
    return messages
    
@app.get("/api/copilot/history/session/{session_id}")
async def get_session_details(session_id: str):
    """Fetch metadata for a specific session."""
    session = await history_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session

@app.delete("/api/copilot/history/{session_id}")
async def delete_session(session_id: str):
    """Delete a chat session."""
    await history_service.delete_session(session_id)
    return {"status": "ok"}

@app.post("/api/copilot/history/rename")
async def rename_session_post(update: HistoryUpdate):
    """Rename a session title (Newer POST variant)."""
    await history_service.rename_session(update.session_id, update.new_title)
    return {"status": "ok"}

@app.put("/api/copilot/history/{session_id}")
async def rename_session_put(session_id: str, request: Dict[str, str]):
    """Rename a session (Legacy PUT variant for frontend compatibility)."""
    title = request.get("title", request.get("new_title", "Untitled Chat"))
    await history_service.rename_session(session_id, title)
    return {"status": "ok", "success": True}

# ---------------------------------------------------------------------------
# Code Execution
# ---------------------------------------------------------------------------

_code_exec_timestamps: Dict[str, float] = {}
_CODE_EXEC_RATE_LIMIT_SECONDS = 10

@app.post("/api/copilot/code/execute", response_model=CodeExecutionResponse)
async def execute_code(http_request: Request, request: CodeExecutionRequest):
    """
    Execute arbitrary code in a sandboxed environment.
    """
    # Code execution permission check (User requested to allow all)
    user_tier = getattr(http_request.state, "user_tier", "GUEST")
    
    # Block shell execution for security
    if request.language.lower() in ("bash", "shell", "cmd", "sh", "zsh", "powershell"):
        raise HTTPException(status_code=403, detail="Shell execution is not allowed.")

    # Rate limit (Disabled by user request)
    # client_id = f"{user_tier}_{http_request.client.host if http_request.client else 'unknown'}"
    # now = time.time()
    # if now - _code_exec_timestamps.get(client_id, 0) < _CODE_EXEC_RATE_LIMIT_SECONDS:
    #     raise HTTPException(status_code=429, detail="Rate limited.")
    # _code_exec_timestamps[client_id] = now

    interpreter = CodeInterpreterService()
    try:
        result = await asyncio.wait_for(
            interpreter.execute_code(request.code, request.language),
            timeout=30.0
        )
        return CodeExecutionResponse(**result)
    except asyncio.TimeoutError:
        return CodeExecutionResponse(success=False, error="Execution timed out (30s limit).", output="")
    except Exception as e:
        return CodeExecutionResponse(success=False, error=str(e), output="")

# ===========================================================================
# ENTRY POINT
# ===========================================================================

if __name__ == "__main__":
    port = int(os.getenv("COPILOT_PORT", "8500"))
    clean_port(port)
    uvicorn.run(
        "copilot_gateway:app",
        host="0.0.0.0",
        port=port,
        reload=DEBUG,
        log_level="debug" if DEBUG else "info",
    )
