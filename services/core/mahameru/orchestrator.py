import json
import os
import uuid
import logging
import asyncio
import httpx
from typing import List, Dict, Optional, Any, AsyncGenerator

from copilot.config import LLM_MODEL, logger
from copilot.system_prompt import SYSTEM_PROMPT, CHAT_SYSTEM_PROMPT
from copilot.llm import (
    _call_llm, _stream_llm, _execute_tool_plan, 
    _deduplicate_tool_calls, _trim_tool_result, _llm_plan_tools
)
from copilot.transformers import _build_rich_response
from mahameru.agents.registry import agent_registry
from mahameru.agents.compaction_agent import CompactionAgent
from mahameru.history_service import history_service
from mahameru.instructions import InstructionInjectionMiddleware

instruction_middleware = InstructionInjectionMiddleware()

from mahameru.agents.plan_agent import PlanAgent
from mahameru.agents.explore_agent import ExploreAgent
from copilot.llm import _llm_agent_loop

class CopilotOrchestrator:
    def __init__(self, tool_definitions: List[Dict]):
        self.tool_definitions = tool_definitions

    async def handle_chat(self, request: Any, http_client: httpx.AsyncClient, permissions: Dict) -> Dict:
        """
        Non-streaming chat handler.
        """
        agent_id, domains = await self._resolve_agent_context(request.metadata)
        
        # 1. Specialized Agent Dispatch
        if agent_id == "plan-agent":
            return await self._handle_plan_agent(request, permissions)
        if agent_id == "explore-agent":
            return await self._handle_explore_agent(request)

        # 2. Regular Chat Logic
        active_model = request.model or LLM_MODEL
        messages_dict = [m.model_dump(exclude_none=True) for m in request.messages]
        messages_dict = await self._maybe_compact_messages(messages_dict)

        base_prompt = SYSTEM_PROMPT if request.use_tools else CHAT_SYSTEM_PROMPT
        enhanced_system_prompt = instruction_middleware.inject_into_system_prompt(
            base_prompt=base_prompt,
            agent_type=agent_id if request.use_tools else "chat-agent",
            context={"domains": domains, "working_dir": os.getcwd(), "session_id": request.session_id}
        )

        # Persistence
        should_save = getattr(request, "save_history", True)
        if request.session_id and should_save:
            await history_service.add_message(request.session_id, "user", request.messages[-1].content, model=active_model)

        if not request.use_tools:
            full_messages = [{"role": "system", "content": enhanced_system_prompt}]
            
            # Phase 5 Transition: Check for plan file to read
            plan_path = request.metadata.get("plan_path") if request.metadata else None
            if plan_path and agent_id == "build-agent":
                from mahameru.agents.plan_agent import PlanAgent
                reminder = PlanAgent().get_build_switch(plan_path)
                full_messages.append({"role": "system", "content": reminder})
                
            full_messages.extend(messages_dict)
            response = await _call_llm(http_client, full_messages, None, active_model)
            content = response["choices"][0]["message"].get("content", "")
            
            if request.session_id and should_save:
                await history_service.add_message(request.session_id, "assistant", content, model=active_model, metadata={"model": active_model})
            
            return {
                "response_id": str(uuid.uuid4()),
                "message": content,
                "components": _build_rich_response(content, [], []),
                "latency_ms": 0,
                "model": active_model,
                "tool_calls_made": [],
                "agent_id": agent_id
            }

        # 3. Agentic Loop (Analytics mode)
        result = await _llm_agent_loop(
            messages_dict,
            client=http_client,
            model=active_model,
            permissions=permissions,
            system_prompt=enhanced_system_prompt,
            agent_id=agent_id,
        )
        
        if request.session_id and should_save:
            await history_service.add_message(
                request.session_id, 
                "assistant", 
                result["message"], 
                tool_calls=result.get("tool_calls_made"), 
                model=active_model,
                metadata={"model": active_model}
            )
        return result

    async def _handle_plan_agent(self, request: Any, permissions: Dict) -> Dict:
        agent_def = agent_registry.get_agent("plan-agent") or {"identifier": "plan-agent"}
        plan_agent = PlanAgent(agent_def)
        plan_result = await plan_agent.create_plan(
            task=request.messages[-1].content if request.messages else "",
            context={
                "agents": agent_registry.list_agents(),
                "tools": [td["function"]["name"] for td in self.tool_definitions],
                "session_id": request.session_id,
                "permissions": permissions,
            },
        )
        markdown = plan_result.get("plan_content") or plan_result.get("summary") or "Plan created."
        return {
            "response_id": str(uuid.uuid4()),
            "message": markdown,
            "components": [
                {"type": "markdown", "data": markdown, "metadata": {"agent_id": "plan-agent"}},
                {"type": "plan_switch", "data": {"plan_path": plan_result.get("plan_path"), "text": "Switch to Build?"}}
            ],
            "latency_ms": 0,
            "model": request.model or LLM_MODEL,
            "tool_calls_made": [],
            "agent_id": "plan-agent",
        }

    async def _handle_explore_agent(self, request: Any) -> Dict:
        agent_def = agent_registry.get_agent("explore-agent") or {"identifier": "explore-agent"}
        explore_agent = ExploreAgent(agent_def)
        explore_result = await explore_agent.explore(
            query=request.messages[-1].content if request.messages else "",
            limit=10,
        )
        markdown = json.dumps(explore_result, indent=2, default=str)
        return {
            "response_id": str(uuid.uuid4()),
            "message": markdown,
            "components": [{"type": "markdown", "data": f"```json\n{markdown}\n```", "metadata": {"agent_id": "explore-agent"}}],
            "latency_ms": 0,
            "model": request.model or LLM_MODEL,
            "tool_calls_made": [],
            "agent_id": "explore-agent",
        }

    async def _maybe_compact_messages(self, messages: List[Dict]) -> List[Dict]:
        compactor = CompactionAgent(agent_registry.get_agent("compaction-agent") or {"identifier": "compaction-agent"})
        compaction_check = compactor.check_compaction_needed(messages)
        if compaction_check.get("needed"):
            summary = await compactor._create_summary(messages, token_budget=8000)
            tail = messages[-20:]
            auto_cont = {"role": "system", "content": compactor.get_auto_continue_message()}
            return [{"role": "system", "content": summary}] + tail + [auto_cont]
        return messages

    async def _resolve_agent_context(self, request_metadata: Optional[Dict]) -> tuple:
        agent_id = "build-agent"
        domains = []
        if request_metadata:
            agent_id = request_metadata.get("agent_id", "build-agent")
            domains = request_metadata.get("domains", [])
        return agent_id, domains

    async def generate_chat_stream(self, request: Any, http_client: httpx.AsyncClient, permissions: Dict) -> AsyncGenerator[str, None]:
        """
        Refactored event generator for chat streaming.
        """
        try:
            messages_dict = [m.model_dump(exclude_none=True) for m in request.messages]
            messages_dict = await self._maybe_compact_messages(messages_dict)
            
            agent_id, domains = await self._resolve_agent_context(request.metadata)
            active_model = request.model or LLM_MODEL

            # Build enhanced system prompt
            base_prompt = SYSTEM_PROMPT if request.use_tools else CHAT_SYSTEM_PROMPT
            enhanced_system_prompt = instruction_middleware.inject_into_system_prompt(
                base_prompt=base_prompt,
                agent_type=agent_id if request.use_tools else "chat-agent",
                context={
                    "domains": domains,
                    "working_dir": os.getcwd(),
                    "session_id": request.session_id,
                }
            )

            full_messages = [{"role": "system", "content": enhanced_system_prompt}]
            
            # Phase 5 Transition: Check for plan file to read
            plan_path = request.metadata.get("plan_path") if request.metadata else None
            if plan_path and agent_id == "build-agent":
                from mahameru.agents.plan_agent import PlanAgent
                reminder = PlanAgent().get_build_switch(plan_path)
                full_messages.append({"role": "system", "content": reminder})

            full_messages.extend(messages_dict)

            # ─── PERSISTENCE (Async) ───
            should_save = getattr(request, "save_history", True)
            if request.session_id and should_save:
                # Add user message
                await history_service.add_message(request.session_id, "user", request.messages[-1].content, model=active_model)
                
                # Check for session title update
                session = await history_service.get_session(request.session_id)
                if not session or session.get("title") == "New Chat":
                    # (Optional: Generate title asynchronously)
                    pass

            # ─── PHASE 1 & 2: PLANNING & EXECUTION ───
            tool_calls = []
            tool_results = []
            planned_tools = []

            if request.use_tools:
                yield self._sse_event("meta", {"model": active_model, "status": "thinking"})
                yield self._sse_event("step", {"step": 1, "label": "🧠 Menganalisis permintaan...", "progress": 5})
                yield self._sse_event("step", {"step": 2, "label": "📋 Merencanakan tools yang diperlukan...", "progress": 10})

                planned_tools = await _llm_plan_tools(messages_dict, http_client, model=active_model)
                
                if planned_tools:
                    yield self._sse_event("plan", {"tools": planned_tools, "count": len(planned_tools)})
                    
                    tool_label_map = {
                        "get_market_quote": "Market Quote",
                        "get_technical_analysis": "Technical Analysis",
                        "get_market_history": "Price History",
                        "get_watchlist": "Market Watchlist",
                        "get_crypto_analysis": "Crypto Analysis",
                        "get_crypto_onchain": "On-Chain Data",
                        "get_forex_rates": "Forex Rates",
                        "get_vessel_radar": "Vessel Radar",
                        "get_news_feed": "News Feed",
                        "discover_services": "Discover Services",
                        "call_api": "Dynamic API",
                    }
                    plan_labels = [tool_label_map.get(t, t.replace("get_", "").replace("_", " ").title()) for t in planned_tools]
                    yield self._sse_event("reasoning", {"content": f"📋 **Tool Plan**: {', '.join(plan_labels)}\n"})
                
                active_tool_defs = self.tool_definitions
                if planned_tools:
                    valid_names = {td["function"]["name"] for td in self.tool_definitions}
                    planned_filtered = [t for t in planned_tools if t in valid_names]
                    if planned_filtered:
                        active_tool_defs = [td for td in self.tool_definitions if td["function"]["name"] in planned_filtered]

                yield self._sse_event("step", {"step": 3, "label": "🔍 Mengeksekusi tools...", "progress": 20})

                # Execution Round 1
                response = await _call_llm(http_client, full_messages, active_tool_defs, model=active_model)
                assistant_msg = response["choices"][0]["message"]
                raw_tool_calls = assistant_msg.get("tool_calls", [])
                
                reasoning = assistant_msg.get("reasoning_content")
                if reasoning:
                    yield self._sse_event("reasoning", {"content": reasoning})

                if raw_tool_calls:
                    tool_calls = _deduplicate_tool_calls(raw_tool_calls)
                    tool_names = [tc["function"]["name"] for tc in tool_calls]
                    yield self._sse_event("step", {"step": 4, "label": f"🔍 Menjalankan {len(tool_calls)} tools...", "sub": tool_names, "progress": 30})

                    for tc in tool_calls:
                        yield self._sse_event("tool_call", {"tool": tc['function']['name'], "status": "start"})

                    full_messages.append({
                        "role": "assistant",
                        "content": assistant_msg.get("content") or "",
                        "tool_calls": [{"id": tc["id"], "type": "function", "function": tc["function"]} for tc in tool_calls],
                    })

                    tool_results = await _execute_tool_plan(http_client, tool_calls, permissions=permissions)
                    
                    for tc, tr in zip(tool_calls, tool_results):
                        t_name = tc["function"]["name"]
                        trimmed_tr = _trim_tool_result(t_name, tr)
                        full_messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "name": t_name,
                            "content": json.dumps(trimmed_tr, default=str),
                        })

                    yield self._sse_event("tools_complete", {"tool_results": tool_results})
                    yield self._sse_event("step", {"step": 5, "label": "📊 Menganalisis data...", "progress": 60})

            # ─── PHASE 3: FINAL SYNTHESIS ───
            final_message = ""
            async for chunk in _stream_llm(http_client, full_messages, None, active_model):
                c = chunk.get("content")
                r = chunk.get("reasoning")
                if r: yield self._sse_event("reasoning", {"content": r})
                if c:
                    final_message += c
                    yield self._sse_event("chunk", {"content": c})

            # Save assistant message (Async)
            if request.session_id and should_save:
                await history_service.add_message(
                    request.session_id, 
                    "assistant", 
                    final_message, 
                    tool_calls=[tc["function"]["name"] for tc in tool_calls] if tool_calls else None,
                    model=active_model,
                    metadata={"model": active_model}
                )
            
            if request.use_tools:
                yield self._sse_event("step", {"step": 7, "label": "✅ Selesai", "progress": 100})

            # Emit final payload
            final_payload = {
                "response_id": str(uuid.uuid4()),
                "message": final_message,
                "components": _build_rich_response(final_message, tool_results if tool_calls else [], []),
                "model": active_model,
                "tool_calls_made": [tc["function"]["name"] for tc in tool_calls] if tool_calls else [],
                "planned_tools": planned_tools,
            }
            yield self._sse_event("complete", final_payload)
            yield "event: done\ndata: {}\n\n"

        except Exception as e:
            logger.error(f"[Orchestrator] Error: {e}", exc_info=True)
            yield self._sse_event("error", {"message": str(e)})

    def _sse_event(self, event_type: str, data: Any) -> str:
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
