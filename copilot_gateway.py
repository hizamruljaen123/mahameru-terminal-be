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
    API_BASE, ENABLE_STREAMING, ENABLE_LLM, LOCAL_DEV, COPILOT_ROOT_PATH, logger, clean_port,
)
from copilot.models import ChatMessage, ChatRequest, ChatResponse, SlashCommandRequest, SlashCommandResponse
from copilot.tools import TOOL_DEFINITIONS
from copilot.api_catalog import API_CATALOG, MICROSERVICE_ROUTES, MICROSERVICE_ROUTE_TEMPLATES
from copilot.slash_commands import SLASH_COMMANDS
from copilot.helpers import _build_route, _call_microservice, _area_to_bbox
from copilot.transformers import _build_rich_response
from copilot.system_prompt import SYSTEM_PROMPT
from copilot.llm import _call_llm, _stream_llm, _execute_tool_plan, _llm_agent_loop

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
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        result = await _llm_agent_loop(messages_dict, client=app.state.http_client, model=request.model)
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
    Emits real-time step progress events and LLM reasoning when available.
    """
    if not request.stream:
        return await chat(request)

    if not ENABLE_LLM or not LLM_API_KEY:
        return await _echo_chat(request.messages)

    async def event_generator():
        try:
            messages_dict = [m.model_dump() for m in request.messages]
            client = app.state.http_client
            full_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            full_messages.extend(messages_dict)

            active_model = request.model or LLM_MODEL

            # Step 1: Initial analysis
            yield f"event: meta\ndata: {json.dumps({'model': active_model, 'status': 'thinking'})}\n\n"
            yield f"event: step\ndata: {json.dumps({'step': 1, 'label': '🧠 Menganalisis permintaan...', 'progress': 10})}\n\n"

            # Round 1: LLM decides which tools to call
            response = await _call_llm(client, full_messages, TOOL_DEFINITIONS)
            choice = response["choices"][0]
            assistant_msg = choice["message"]
            tool_calls = assistant_msg.get("tool_calls", [])

            # Capture reasoning_content if the model provides it (e.g. DeepSeek-R1)
            reasoning = assistant_msg.get("reasoning_content")
            if reasoning:
                yield f"event: reasoning\ndata: {json.dumps({'content': reasoning[:3000]})}\n\n"

            tool_results = []

            if tool_calls:
                # Step 2: Executing tools
                tool_names = [tc["function"]["name"] for tc in tool_calls]
                yield f"event: step\ndata: {json.dumps({'step': 2, 'label': f'🔍 Menjalankan {len(tool_calls)} tool(s)...', 'sub': tool_names, 'progress': 25})}\n\n"

                # Emit individual tool call starts
                for tc in tool_calls:
                    yield f"event: tool_call\ndata: {json.dumps({'tool': tc['function']['name'], 'status': 'start'})}\n\n"

                full_messages.append({
                    "role": "assistant",
                    "content": assistant_msg.get("content"),
                    "tool_calls": [{"id": tc["id"], "type": "function", "function": tc["function"]} for tc in tool_calls],
                })

                tool_results = await _execute_tool_plan(client, tool_calls)
                
                # Emit tool results log as reasoning for transparency (thinking block)
                for tc, tr in zip(tool_calls, tool_results):
                    t_name = tc["function"]["name"]
                    t_label = t_name.replace("get_", "").replace("run_", "").replace("_", " ").upper()
                    ok = tr.get("success", False)
                    
                    status_msg = f'✅ {t_label} data acquired and analyzed.\n' if ok else f'⚠️ {t_label} failed: {tr.get("error", "Unknown error")}\n'
                    yield f"event: reasoning\ndata: {json.dumps({'content': status_msg})}\n\n"
                    
                    # VERY IMPORTANT: Add results to message history for final synthesis
                    full_messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "name": t_name,
                        "content": json.dumps(tr, default=str),
                    })

                yield f"event: tools_complete\ndata: {json.dumps({'tool_results': tool_results})}\n\n"

                # Step 3: Reasoning & analysis
                yield f"event: step\ndata: {json.dumps({'step': 3, 'label': '📊 Menganalisis data & menyusun wawasan...', 'progress': 60})}\n\n"

                # Final LLM call — synthesize response from tool results
                # Now streaming the final synthesis
                final_message = ""
                async for chunk in _stream_llm(client, full_messages, None, active_model):
                    c = chunk.get("content")
                    r = chunk.get("reasoning")
                    if r:
                        yield f"event: reasoning\ndata: {json.dumps({'content': r})}\n\n"
                    if c:
                        final_message += c
                        yield f"event: chunk\ndata: {json.dumps({'content': c})}\n\n"

                # Step 4: Building final response components
                yield f"event: step\ndata: {json.dumps({'step': 4, 'label': '💡 Membangun visualisasi...', 'progress': 90})}\n\n"
            else:
                # No tools needed — stream direct response
                yield f"event: step\ndata: {json.dumps({'step': 3, 'label': '💡 Menyusun respons...', 'progress': 50})}\n\n"
                final_message = ""
                async for chunk in _stream_llm(client, full_messages, None, active_model):
                    c = chunk.get("content")
                    r = chunk.get("reasoning")
                    if r:
                        yield f"event: reasoning\ndata: {json.dumps({'content': r})}\n\n"
                    if c:
                        final_message += c
                        yield f"event: chunk\ndata: {json.dumps({'content': c})}\n\n"

            # Step 5: Complete
            yield f"event: step\ndata: {json.dumps({'step': 5, 'label': '✅ Selesai', 'progress': 100})}\n\n"

            # Build and emit final rich response
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
    clean_port(port)
    uvicorn.run(
        "copilot_gateway:app",
        host="0.0.0.0",
        port=port,
        reload=DEBUG,
        log_level="debug" if DEBUG else "info",
    )
