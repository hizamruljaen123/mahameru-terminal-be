"""
LLM Agent — Function Calling Loop for Mahameru Copilot.
Handles LLM communication, tool execution, and multi-round agent loop.
"""

import json
import asyncio
import time
import uuid
import logging
from typing import List, Dict, Optional, Any, AsyncGenerator

import httpx

from copilot.config import (
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_MAX_TOKENS, logger,
)
from copilot.tools import TOOL_DEFINITIONS
from copilot.system_prompt import SYSTEM_PROMPT
from copilot.helpers import (
    _discover_services_handler, _call_api_handler,
    _build_route, _call_microservice,
)
from copilot.transformers import _build_rich_response


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


async def _stream_llm(
    client: httpx.AsyncClient,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    model: Optional[str] = None,
):
    """Call the configured LLM and yield response chunks (content and reasoning)."""
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    active_model = model or LLM_MODEL
    payload = {
        "model": active_model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": LLM_MAX_TOKENS,
        "stream": True
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    try:
        async with client.stream(
            "POST",
            f"{LLM_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120.0
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                
                try:
                    chunk = json.loads(data_str)
                    if not chunk.get("choices"):
                        continue
                    
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content")
                    reasoning = delta.get("reasoning_content")
                    tool_calls = delta.get("tool_calls")
                    
                    if reasoning or content or tool_calls:
                        yield {"content": content, "reasoning": reasoning, "tool_calls": tool_calls}
                except Exception:
                    continue
    except Exception as e:
        logger.error(f"[LLM STREAM] Error: {e}")
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
    client: httpx.AsyncClient,
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
