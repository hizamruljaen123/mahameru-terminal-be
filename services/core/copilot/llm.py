"""
LLM Agent — Function Calling Loop for Mahameru Copilot.
Handles LLM communication, tool execution, and multi-round agent loop.
"""

import json
import re
import asyncio
import time
import uuid
import logging
import os
from services.code_interpreter.service import CodeInterpreterService
from typing import List, Dict, Optional, Any, AsyncGenerator

import httpx

from copilot.provider_transformer import ProviderTransformer

from copilot.config import (
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_MAX_TOKENS, logger,
)
from copilot.tools import TOOL_DEFINITIONS as _STATIC_TOOL_DEFINITIONS
from copilot.system_prompt import SYSTEM_PROMPT
from copilot.helpers import (
    _discover_services_handler, _call_api_handler,
    _build_route, _call_microservice,
)
from copilot.transformers import _build_rich_response
from copilot.models import get_model_config
from copilot.models.definitions import MODEL_PROVIDERS


def _get_tool_definitions():
    """Get the current tool definitions, preferring ToolRegistry if available.
    
    This resolves the divergence between the gateway's ToolRegistry-based
    definitions and the static copilot.tools.TOOL_DEFINITIONS.
    """
    try:
        from mahameru.tools import ToolRegistry
        registry = ToolRegistry()
        defs = registry.to_function_definitions()
        if defs:
            return defs
    except Exception:
        pass
    return _STATIC_TOOL_DEFINITIONS

# Osiris Fallback Mapping
OSIRIS_FALLBACK_MAP = {
    "claude-opus-4-6": "claude-opus-4-6:osiris",
    "claude-opus-4-5-20251101": "claude-opus-4-6:osiris",
    "claude-sonnet-4-6": "claude-sonnet-4-5:osiris",
    "claude-sonnet-4-5-20250929": "claude-sonnet-4-5:osiris",
    "gpt-5.4": "gpt-5-4:osiris",
    "gpt-5.5": "gpt-5-5:osiris",
    "gpt-5.2": "gpt-5-4:osiris",
    "gemini-3.1-pro-preview": "gemini-3-1-pro:osiris",
    "gemini-3-pro-preview": "gemini-3-1-pro:osiris",
    "gpt-5.3-codex": "gpt-5-4:osiris",
    "glm-5": "glm-5v-turbo:osiris",
}



async def _call_llm(
    client: httpx.AsyncClient,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Call the configured LLM with messages and tools."""
    # Resolve configuration via centralized model manager
    config = get_model_config(model or LLM_MODEL)
    active_model = config["model"]
    base_url = config["base_url"]
    api_key = config["api_key"]
    is_openrouter = config["is_openrouter"]


    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "MahameruTerminal/2.0",
    }
    
    if is_openrouter or "dit.ai" in base_url:
        headers["HTTP-Referer"] = "http://localhost:8500" if os.getenv("LOCAL_DEV") == "true" else "https://asetpedia.online"
        headers["X-Title"] = "Mahameru Terminal"
        headers["Origin"] = "http://localhost:8500" if os.getenv("LOCAL_DEV") == "true" else "https://asetpedia.online"

    payload = {
        "model": active_model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": LLM_MAX_TOKENS,
    }
    
    # Only add tools/tool_choice if tools are provided
    if tools is not None:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    payload = ProviderTransformer.transform_payload(
        provider=config.get("provider", ""),
        base_payload=payload
    )

    try:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60.0,
        )
        resp.raise_for_status()
        
        # Guard against empty or non-JSON responses
        if not resp.content:
            logger.error(f"[LLM] Received empty response from {base_url}")
            raise ValueError(f"Empty response from {config['provider']}")
            
        try:
            return resp.json()
        except json.JSONDecodeError:
            logger.error(f"[LLM] Failed to parse JSON response. Content: {resp.text[:500]}")
            raise ValueError(f"Invalid JSON response from {config['provider']}")

    except httpx.TimeoutException:
        logger.error("[LLM] Request timed out")
        raise
    except httpx.HTTPStatusError as e:
        error_body = e.response.text[:1000]
        logger.error(f"[LLM] HTTP {e.response.status_code}: {error_body}")
        
        # --- OSIRIS FALLBACK LOGIC (only on HTTP errors from DIT) ---
        if config["provider"] == MODEL_PROVIDERS["DIT"]:
            fallback_model = OSIRIS_FALLBACK_MAP.get(active_model)
            if fallback_model:
                logger.warning(f"[LLM_FALLBACK] DIT.ai HTTP {e.response.status_code}. Attempting Osiris fallback: {fallback_model}")
                return await _call_llm(client, messages, tools, fallback_model)
        
        raise
    except Exception as e:
        logger.error(f"[LLM] Unexpected error: {e}")
        raise


async def _stream_llm(
    client: httpx.AsyncClient,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    model: Optional[str] = None,
):
    """Call the configured LLM and yield response chunks (content and reasoning)."""
    # Resolve configuration via centralized model manager
    config = get_model_config(model or LLM_MODEL)
    active_model = config["model"]
    base_url = config["base_url"]
    api_key = config["api_key"]
    is_openrouter = config["is_openrouter"]


    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "MahameruTerminal/2.0",
    }
    
    if is_openrouter or "dit.ai" in base_url:
        headers["HTTP-Referer"] = "http://localhost:8500" if os.getenv("LOCAL_DEV") == "true" else "https://asetpedia.online"
        headers["X-Title"] = "Mahameru Terminal"
        headers["Origin"] = "http://localhost:8500" if os.getenv("LOCAL_DEV") == "true" else "https://asetpedia.online"
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

    payload = ProviderTransformer.transform_payload(
        provider=config.get("provider", ""),
        base_payload=payload
    )

    try:
        async with client.stream(
            "POST",
            f"{base_url}/chat/completions",
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
    except httpx.HTTPStatusError as e:
        await e.response.aread()
        logger.error(f"[LLM STREAM] HTTP {e.response.status_code}: {e.response.text[:500]}")
        
        # --- OSIRIS FALLBACK LOGIC (only on HTTP errors from DIT) ---
        if config["provider"] == MODEL_PROVIDERS["DIT"]:
            fallback_model = OSIRIS_FALLBACK_MAP.get(active_model)
            if fallback_model:
                logger.warning(f"[LLM_STREAM_FALLBACK] DIT.ai HTTP error. Attempting Osiris fallback: {fallback_model}")
                async for chunk in _stream_llm(client, messages, tools, fallback_model):
                    yield chunk
                return

        raise
    except httpx.TimeoutException:
        logger.error("[LLM STREAM] Request timed out")
        raise
    except Exception as e:
        logger.error(f"[LLM STREAM] Unexpected error: {e}")
        raise


def _deduplicate_tool_calls(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate tool calls based on name and arguments.
    Ensures we don't call the exact same service with exact same params twice.
    """
    if not tool_calls:
        return []
        
    unique_calls = []
    seen_keys = set()
    
    logger.info(f"[DEDUPLICATOR] Input: {len(tool_calls)} tool calls")
    
    for tc in tool_calls:
        try:
            fn_name = tc["function"]["name"]
            raw_args = tc["function"]["arguments"]
            
            # Normalize arguments for comparison
            if isinstance(raw_args, str):
                args_obj = json.loads(raw_args)
            else:
                args_obj = raw_args
                
            # Deep normalization: sort keys and lowercase symbols if present
            # This prevents BBRI.JK and bbri.jk from being treated as different
            normalized_args = {}
            for k, v in args_obj.items():
                if k in ["symbol", "query", "pair", "ticker"] and isinstance(v, str):
                    normalized_args[k] = v.upper().strip()
                else:
                    normalized_args[k] = v
                    
            args_str = json.dumps(normalized_args, sort_keys=True)
            key = f"{fn_name}:{args_str}"
            
            if key not in seen_keys:
                seen_keys.add(key)
                unique_calls.append(tc)
                logger.debug(f"[DEDUPLICATOR] Kept: {key}")
            else:
                logger.info(f"[DEDUPLICATOR] Removed duplicate: {key}")
        except Exception as e:
            logger.warning(f"[DEDUPLICATOR] Error parsing tool call: {e}")
            unique_calls.append(tc)
            
    logger.info(f"[DEDUPLICATOR] Output: {len(unique_calls)} unique tool calls")
    return unique_calls


def _trim_tool_result(tool_name: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Trim large tool results to save LLM tokens while keeping insights."""
    if not result.get("success") or "data" not in result:
        # Return a cleaner error message instead of raw dump
        if not result.get("success"):
            err = result.get("error", "Unknown error")
            return {"success": False, "tool": tool_name, "error": f"Service offline ({err}). Inform user this specific data is unavailable."}
        return result

    data = result["data"]
    
    # 1. Technical Analysis Trimming
    if tool_name == "get_technical_analysis":
        # Keep only essential keys for textual analysis
        essential_keys = ["current", "ma_table", "signals", "support_resistance", "returns", "info", "symbol"]
        trimmed_data = {k: data[k] for k in essential_keys if k in data}
        
        # Explicitly remove massive arrays if they leaked into essential keys
        for array_key in ["indicators", "ohlcv", "dates"]:
            if array_key in trimmed_data:
                del trimmed_data[array_key]
        
        return {"success": True, "tool": tool_name, "data": trimmed_data}

    # 2. Market History Trimming (LLM only needs high-level status, UI handles the rest)
    if tool_name == "get_market_history":
        return {
            "success": True, 
            "tool": tool_name, 
            "data": {
                "symbol": data.get("symbol"),
                "period": data.get("range"),
                "status": "Chart data acquired. DO NOT request row-by-row prices; the UI handles visualization."
            }
        }

    return result


async def _execute_tool_plan(
    client: httpx.AsyncClient,
    tool_calls: List[Dict[str, Any]],
    permissions: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Execute all tool calls in parallel and return results."""
    tasks = []
    for tc in tool_calls:
        fn_name = tc["function"]["name"]
        
        # Permission check
        if permissions:
            # Simple mapping of tool names to permission keys if needed
            # For now, use the tool name as the permission key
            permission = permissions.get(fn_name, "ask")
            if permission == "deny":
                logger.warning(f"[PERMISSION] Tool {fn_name} denied.")
                # We'll create a task that returns a denial result
                async def denied_task(name):
                    return {"success": False, "tool": name, "error": "Permission denied by system policy."}
                tasks.append(denied_task(fn_name))
                continue
            elif permission == "ask":
                # In a real scenario, this would trigger a UI confirmation
                # For now, we'll allow it but log it
                logger.info(f"[PERMISSION] Tool {fn_name} requires confirmation (simulated allow).")

        try:
            fn_args = json.loads(tc["function"]["arguments"])
        except json.JSONDecodeError:
            fn_args = {}

        if fn_name == "discover_services":
            tasks.append(_discover_services_handler(client, fn_args))
        elif fn_name == "call_api":
            tasks.append(_call_api_handler(client, fn_args))
        elif fn_name == "execute_code":
            tasks.append(CodeInterpreterService.run_code(
                fn_args.get("language", "python"),
                fn_args.get("code", ""),
                fn_args.get("timeout", 30)
            ))
        elif fn_name == "dispatch_subagent":
            async def subagent_task(args):
                agent_id = args.get("agent_id")
                task_query = args.get("task")
                if not agent_id or not task_query:
                    return {"success": False, "tool": "dispatch_subagent", "error": "Missing agent_id or task"}
                
                logger.info(f"[SUBAGENT] Dispatching {agent_id} for task: {task_query}")
                sub_messages = [{"role": "user", "content": task_query}]
                
                try:
                    result = await _llm_agent_loop(
                        messages=sub_messages,
                        client=client,
                        agent_id=agent_id,
                        permissions=permissions
                    )
                    return {
                        "success": True,
                        "tool": "dispatch_subagent",
                        "agent_id": agent_id,
                        "data": result.get("message")
                    }
                except Exception as e:
                    return {"success": False, "tool": "dispatch_subagent", "error": str(e)}
            
            tasks.append(subagent_task(fn_args))
        elif fn_name == "use_skill":
            async def load_skill_task(args):
                skill_name = args.get("skill_name")
                if not skill_name:
                    return {"success": False, "tool": "use_skill", "error": "Missing skill_name"}
                
                # Check .mahameru/skills directory
                skill_path = os.path.join(os.getcwd(), ".mahameru", "skills", f"{skill_name}.md")
                if os.path.exists(skill_path):
                    try:
                        with open(skill_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        return {"success": True, "tool": "use_skill", "data": content}
                    except Exception as e:
                        return {"success": False, "tool": "use_skill", "error": str(e)}
                else:
                    return {"success": False, "tool": "use_skill", "error": f"Skill {skill_name} not found"}
            
            tasks.append(load_skill_task(fn_args))
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


_PLANNING_PROMPT = """You are the Mahameru Strategic Planner. Your mission is to analyze complex natural language prompts and determine the optimal sequence of microservice tools to resolve them.

## THOUGHT PROCESS:
1. **Analyze Intent**: What is the user actually asking for? (e.g. "cari berita BBRI" means "fetch news for symbol BBRI.JK").
2. **Context Resolution**: Identify entities, tickers, locations, or timeframes.
3. **Tool Selection**: Map the resolved intent to the MINIMUM required set of specialized tools.
4. **Logical Consistency**: Ensure selected tools are complementary, not redundant.

## RULES:
- Use `<thinking>` tags to explain your analysis before providing the final tool list.
- Return ONLY a valid JSON array of tool names AFTER the thinking block.
- For Indonesian stocks, identify the 4-letter ticker and assume `.JK` suffix.
- If the user wants research/analysis, use `run_deep_research`.
- If the user wants a visual radar, use `get_vessel_radar`.
- If you need multiple data types (e.g. TA + News), select both tools.
- If you're unsure, include `discover_services`.

## OUTPUT FORMAT:
<thinking>
[Your step-by-step reasoning about the prompt, tickers, and tool selection]
</thinking>
["tool_name_1", "tool_name_2", ...]

## EXAMPLES:
User: "cari berita tentang BBRI.JK dan analisa teknikalnya"
Response:
<thinking>
User wants news and technical analysis for BBRI.JK.
- News: get_news_feed(query='BBRI.JK')
- Technical: get_technical_analysis(symbol='BBRI.JK')
Result: ['get_news_feed', 'get_technical_analysis']
</thinking>
["get_news_feed", "get_technical_analysis"]
"""


async def _llm_plan_tools(
    messages: List[Dict[str, Any]],
    client: httpx.AsyncClient,
    model: Optional[str] = None,
) -> List[str]:
    """
    Phase 1: Planning — Analyze the user's request and determine which tools are needed.
    Returns a list of tool names to use for execution.
    """
    planning_messages = [{"role": "system", "content": _PLANNING_PROMPT}]
    
    _tool_defs = _get_tool_definitions()
    tool_names = [td["function"]["name"] for td in _tool_defs]
    tool_list_str = "\n".join(f"  - {name}" for name in sorted(tool_names))
    planning_messages.append({
        "role": "system",
        "content": f"## REGISTERED MAHAMERU TOOLS:\n{tool_list_str}"
    })
    
    # Add last 2 messages for context
    for m in messages[-2:]:
        msg_role = m.get("role", "user")
        msg_content = m.get("content", "")
        if msg_content:
            planning_messages.append({"role": msg_role, "content": msg_content})

    try:
        logger.info(f"[PLANNER] Orchestrating tool strategy...")
        response = await _call_llm(client, planning_messages, tools=None, model=model)
        content = response["choices"][0]["message"].get("content", "").strip()
        
        # 1. Capture Thinking (for logs/reasoning)
        thinking_match = re.search(r'<thinking>(.*?)</thinking>', content, re.DOTALL)
        if thinking_match:
            thinking = thinking_match.group(1).strip()
            logger.info(f"[PLANNER] Strategic Thinking: {thinking}")
            # Optional: yield thinking to frontend if caller supports it
            
        # 2. Parse JSON array
        # Remove thinking block to avoid JSON parse errors
        json_content = re.sub(r'<thinking>.*?</thinking>', '', content, flags=re.DOTALL).strip()
        
        try:
            planned_tools = json.loads(json_content)
        except json.JSONDecodeError:
            # Fallback patterns
            json_match = re.search(r'\[\s*".*?"\s*\]', json_content, re.DOTALL)
            if json_match:
                planned_tools = json.loads(json_match.group(0))
            else:
                logger.warning(f"[PLANNER] Failed to parse JSON: {json_content[:200]}")
                return []
        
        if not isinstance(planned_tools, list):
            return []
        
        valid_tool_names = {td["function"]["name"] for td in _tool_defs}
        validated = [name for name in planned_tools if name in valid_tool_names]
        
        logger.info(f"[PLANNER] Final Strategy: {validated}")
        return validated
        
    except Exception as e:
        logger.error(f"[PLANNER] Planning failed: {e}")
        return []


async def _llm_agent_loop(
    messages: List[Dict[str, Any]],
    client: httpx.AsyncClient,
    model: Optional[str] = None,
    permissions: Optional[Dict[str, str]] = None,
    system_prompt: Optional[str] = None,
    agent_id: str = "build-agent",
) -> Dict[str, Any]:
    """
    Main LLM agent loop with two-phase planning and max step execution.
    """
    start_time = time.time()
    
    # Task 4: Auto Model Selection from Agent Config
    from mahameru.agents.registry import agent_registry
    agent_def = agent_registry.get_agent(agent_id) or {}
    max_steps = agent_def.get("steps", 10)
    agent_model = agent_def.get("model")
    
    if agent_model:
        logger.info(f"[AGENT] Auto-selecting model {agent_model} for {agent_id}")
        active_model = agent_model
    else:
        active_model = model or LLM_MODEL

    from mahameru.doom_loop_detector import DoomLoopDetector
    doom_detector = DoomLoopDetector(threshold=3)

    # Build message list with system prompt
    full_messages = [{"role": "system", "content": system_prompt or SYSTEM_PROMPT}]
    for m in messages:
        msg = {"role": m["role"], "content": m.get("content", "")}
        if m.get("tool_calls"):
            msg["tool_calls"] = m["tool_calls"]
        if m.get("tool_call_id"):
            msg["tool_call_id"] = m["tool_call_id"]
        if m.get("name"):
            msg["name"] = m["name"]
        full_messages.append(msg)

    # ─── Phase 1: PLANNING ────────────────────────────────────────────────
    planned_tool_names = await _llm_plan_tools(messages, client, model=active_model)
    
    _all_tool_defs = _get_tool_definitions()
    if planned_tool_names:
        active_tool_defs = [
            td for td in _all_tool_defs
            if td["function"]["name"] in planned_tool_names
        ]
        logger.info(f"[AGENT] Using PLANNED tools ({len(active_tool_defs)}/{len(_all_tool_defs)}): {planned_tool_names}")
    else:
        active_tool_defs = _all_tool_defs
        logger.info(f"[AGENT] Planning returned empty, using ALL {len(_all_tool_defs)} tools")

    # ─── Phase 2: EXECUTION LOOP ──────────────────────────────────────────
    tool_calls_made = []
    tool_results = []
    final_message = ""
    
    for step in range(max_steps):
        logger.info(f"[AGENT] Step {step + 1}/{max_steps}: LLM executing tools with model={active_model}...")
        
        # In subsequent steps, we might want to expose all tools if the LLM needs them, 
        # or stick to active_tool_defs. Let's stick to active_tool_defs for step 0, and _all_tool_defs for later.
        current_tool_defs = active_tool_defs if step == 0 else _all_tool_defs

        response = await _call_llm(client, full_messages, current_tool_defs, model=active_model)
        choice = response["choices"][0]
        assistant_msg = choice["message"]
        
        tool_calls = assistant_msg.get("tool_calls", [])
        
        # Add assistant message to conversation
        full_messages.append({
            "role": "assistant",
            "content": assistant_msg.get("content") or "",
            "tool_calls": [{"id": tc["id"], "type": "function", "function": tc["function"]} for tc in tool_calls] if tool_calls else None,
        })
        
        if not tool_calls:
            # LLM responded directly without tools (done)
            final_message = assistant_msg.get("content", "")
            break

        # Deduplicate tool calls
        tool_calls = _deduplicate_tool_calls(tool_calls)
        logger.info(f"[AGENT] LLM requested {len(tool_calls)} unique tool(s)")

        # Doom Loop Detection
        safe_tool_calls = []
        is_doom_loop = False
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            fn_args = tc["function"]["arguments"]
            if doom_detector.check(fn_name, fn_args):
                logger.warning(f"[DOOM LOOP DETECTED] Tool {fn_name} called repeatedly with same args. Breaking.")
                is_doom_loop = True
                break
            safe_tool_calls.append(tc)

        if is_doom_loop:
            # Inject a system message to stop and answer
            full_messages.append({
                "role": "system", 
                "content": "DOOM LOOP DETECTED. You have called the exact same tool with the exact same parameters 3 times. Stop calling tools and provide the best answer you can with the current data."
            })
            continue # Go to next step to let LLM respond

        if not safe_tool_calls:
            final_message = assistant_msg.get("content", "")
            break

        # Execute safe tools in parallel
        step_results = await _execute_tool_plan(client, safe_tool_calls, permissions=permissions)
        for tc, tr in zip(safe_tool_calls, step_results):
            tool_calls_made.append(tr["tool"])
            tool_results.append(tr)
            
            # Trim result for LLM consumption
            trimmed_tr = _trim_tool_result(tc["function"]["name"], tr)
            full_messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": tc["function"]["name"],
                "content": json.dumps(trimmed_tr, default=str),
            })
            
    else:
        # Reached max_steps
        logger.warning(f"[AGENT] Max steps ({max_steps}) reached for {agent_id}. Forcing termination.")
        full_messages.append({
            "role": "system", 
            "content": "Maximum execution steps reached. Please synthesize a final response immediately."
        })
        response = await _call_llm(client, full_messages, None, model=active_model)
        final_message = response["choices"][0]["message"].get("content", "")

    # Build rich response components from raw tool results
    components = _build_rich_response(final_message, tool_results, tool_calls_made)

    latency = (time.time() - start_time) * 1000
    logger.info(f"[AGENT] Complete in {latency:.0f}ms with {len(tool_calls_made)} tool(s) over {step + 1} steps")

    return {
        "response_id": str(uuid.uuid4()),
        "message": final_message,
        "components": components,
        "latency_ms": round(latency, 1),
        "model": active_model,
        "tool_calls_made": tool_calls_made,
        "planned_tools": planned_tool_names,
    }
