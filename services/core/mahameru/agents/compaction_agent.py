"""
Compaction Agent - Context Window Management

The Compaction Agent is a hidden agent responsible for summarizing
conversation history when the context window approaches its limit.

Based on OpenCode's compaction agent architecture.

COMPACTION PROCESS:
1. PRUNE: Quick removal of old tool outputs (no LLM)
2. SUMMARIZE: LLM-based summarization of remaining history
3. REBUILD: Inject summary + recent messages as new context
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class CompactionAgent:
    """
    Compaction Agent - Hidden agent for context window management.
    
    This agent has NO tool access (all tools denied).
    It only produces text summaries of the conversation.
    
    Compaction is triggered when:
    - Token count exceeds 80% of model context limit
    - Manual trigger via API
    
    OUTPUT FORMAT (Anchored Summary):
    ## Goal        - Task summary in 1 sentence
    ## Constraints - User constraints and preferences
    ## Progress    - Done / In Progress / Blocked
    ## Key Decisions - Decisions made and rationale
    ## Next Steps  - Remaining work
    ## Critical Context - Important technical facts
    ## Relevant Files - Relevant data sources
    """
    
    # Compaction thresholds
    PRUNE_MINIMUM = 20000       # Min tokens saved to trigger prune
    PRUNE_PROTECT = 40000       # Buffer protecting recent tool outputs
    MIN_PRESERVE_RECENT = 2000  # Min tokens in "tail" (recent messages)
    MAX_PRESERVE_RECENT = 8000  # Max tokens in "tail"
    TOOL_OUTPUT_MAX_CHARS = 2000  # Max chars per tool output after prune
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.agent_id = self.config.get("identifier", "compaction-agent")
        self.name = self.config.get("name", "Context Compactor")
        self.description = self.config.get(
            "description",
            "Hidden agent for summarizing conversation history"
        )
        self.model = self.config.get("model", "deepseek-v4-flash")
        self.temperature = self.config.get("temperature", 0.3)
        
    def get_compaction_prompt(self) -> str:
        """
        Returns the system prompt for the compaction agent.
        This guides the LLM to produce structured summaries.
        """
        return """You are Mahameru Compaction Agent - an anchored context summarization assistant.

Your task is to summarize the conversation history into a structured,
anchored summary that preserves critical information while dramatically
reducing token usage.

SUMMARY FORMAT (MUST FOLLOW):
---
## Goal
[Ringkasan task dalam 1 kalimat]

## Constraints  
[Constraints dan preferensi user]

## Progress
- [DONE] Task yang sudah selesai
- [IN_PROGRESS] Task yang sedang berjalan
- [BLOCKED] Task yang terblokir

## Key Decisions
[Keputusan penting dan alasannya]

## Next Steps
[Langkah selanjutnya yang perlu dilakukan]

## Critical Context
[Fakta teknis penting yang masih relevan]

## Relevant Data Sources
[Sumber data yang digunakan dan kenapa]
---

RULES:
1. FOCUS on preserving actionable information
2. REMOVE conversational filler and redundant explanations
3. PRESERVE key numbers, timestamps, and identifiers
4. USE the same language as the conversation (Indonesian/English)
5. KEEP summary under 2000 tokens
6. DO NOT invent new information - only summarize what's in the history
"""

    async def compact(
        self,
        messages: List[Dict[str, Any]],
        previous_summary: Optional[str] = None,
        token_budget: int = 8000
    ) -> Dict[str, Any]:
        """
        Compact the conversation history into a summary.
        
        Args:
            messages: List of conversation messages
            previous_summary: Optional previous summary to update
            token_budget: Maximum tokens for the summary
            
        Returns:
            Dict with:
            - summary: str (the compacted summary)
            - pruned: bool (whether pruning was done)
            - tokens_saved: int (estimated tokens saved)
            - tail_messages: list (recent messages preserved verbatim)
        """
        logger.info(f"[CompactionAgent] Starting compaction. Messages: {len(messages)}")
        
        try:
            # Step 1: Identify "head" and "tail" messages
            head_messages, tail_messages, tail_tokens = self._split_messages(
                messages, 
                self.MAX_PRESERVE_RECENT
            )
            
            # Step 2: Prune old tool outputs if beneficial
            pruned_head, tokens_saved = self._prune_old_outputs(head_messages)
            
            # Step 3: Build summary (either update previous or create new)
            if previous_summary and tokens_saved < self.PRUNE_MINIMUM:
                # Not enough savings - update existing summary
                summary = await self._update_summary(
                    previous_summary,
                    pruned_head + tail_messages,
                    token_budget
                )
            else:
                # Create new summary from scratch
                summary = await self._create_summary(
                    pruned_head + tail_messages,
                    token_budget
                )
            
            result = {
                "success": True,
                "summary": summary,
                "pruned": tokens_saved >= self.PRUNE_MINIMUM,
                "tokens_saved": tokens_saved,
                "tail_count": len(tail_messages),
                "tail_tokens": tail_tokens,
                "summary_tokens": len(summary) // 4,  # Approximate
                "timestamp": datetime.utcnow().isoformat(),
            }
            
            logger.info(
                f"[CompactionAgent] Compaction complete. "
                f"Tokens saved: {tokens_saved}, Tail messages: {len(tail_messages)}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"[CompactionAgent] Compaction failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "summary": None,
                "pruned": False,
                "tokens_saved": 0,
            }
    
    def _split_messages(
        self,
        messages: List[Dict[str, Any]],
        max_tail_tokens: int
    ) -> tuple:
        """
        Split messages into head (to be summarized) and tail (preserved).
        
        Returns:
            (head_messages, tail_messages, tail_tokens)
        """
        tail = []
        tail_tokens = 0
        
        # Work backwards to build the tail
        for msg in reversed(messages):
            msg_tokens = self._estimate_tokens(msg)
            
            if tail_tokens + msg_tokens <= max_tail_tokens:
                tail.insert(0, msg)
                tail_tokens += msg_tokens
            else:
                break
        
        # Rest goes to head
        head = messages[:-len(tail)] if tail else messages
        
        return head, tail, tail_tokens
    
    def _prune_old_outputs(
        self,
        messages: List[Dict[str, Any]]
    ) -> tuple:
        """
        Quick prune of old tool outputs that exceed character limit.
        Includes Tiered Compaction for Financial Data.
        """
        import json
        
        if not messages:
            return [], 0
        
        pruned = []
        total_saved = 0
        
        for msg in messages:
            pruned_msg = msg.copy()
            
            if msg.get("role") == "tool":
                content = msg.get("content", "")
                tool_name = msg.get("name", "")
                original_len = len(content)
                
                # Try JSON parsing for structural pruning
                try:
                    data = json.loads(content)
                    is_json = True
                except:
                    data = {}
                    is_json = False
                
                if is_json and isinstance(data, dict):
                    # Level 1: News Pruning (headline + sentiment only)
                    if tool_name == "get_news_feed" and isinstance(data.get("data"), list):
                        for article in data["data"]:
                            if "content" in article: del article["content"]
                            if "summary" in article: del article["summary"]
                    
                    # Level 2 & 3: Market Data Pruning & Summary Replacement
                    if tool_name in ["get_technical_analysis", "get_market_quote", "get_crypto_analysis", "get_market_history"]:
                        if isinstance(data.get("data"), dict):
                            # Remove huge arrays
                            if "indicators" in data["data"]: del data["data"]["indicators"]
                            if "dates" in data["data"]: del data["data"]["dates"]
                            # Keep only the last candle
                            if "ohlcv" in data["data"] and isinstance(data["data"]["ohlcv"], list) and len(data["data"]["ohlcv"]) > 0:
                                data["data"]["ohlcv"] = [data["data"]["ohlcv"][-1]]
                            
                    # Re-serialize and check savings
                    pruned_content = json.dumps(data)
                    if len(pruned_content) < original_len:
                        pruned_msg["content"] = pruned_content
                        total_saved += original_len - len(pruned_content)
                        content = pruned_content
                        
                # Generic fallback pruning
                if len(content) > self.TOOL_OUTPUT_MAX_CHARS:
                    # Truncate and mark
                    pruned_msg["content"] = (
                        content[:self.TOOL_OUTPUT_MAX_CHARS] 
                        + f"\n...[truncated, saved {len(content) - self.TOOL_OUTPUT_MAX_CHARS} chars]"
                    )
                    total_saved += len(content) - len(pruned_msg["content"])
            
            # Also check for long assistant responses
            elif msg.get("role") == "assistant":
                content = msg.get("content", "")
                if len(content) > self.TOOL_OUTPUT_MAX_CHARS * 2:
                    pruned_msg["content"] = (
                        content[:self.TOOL_OUTPUT_MAX_CHARS * 2] 
                        + f"\n...[content truncated]"
                    )
                    total_saved += len(content) - len(pruned_msg["content"])
            
            pruned.append(pruned_msg)
        
        return pruned, total_saved
    
    async def _create_summary(
        self,
        messages: List[Dict[str, Any]],
        token_budget: int
    ) -> str:
        """
        Create a new summary from scratch.
        
        This would be enhanced with actual LLM call in production.
        For now, returns a basic structured summary.
        """
        if not messages:
            return "## Summary\nNo messages to summarize."
        
        # Extract key information
        user_messages = [m for m in messages if m.get("role") == "user"]
        assistant_messages = [m for m in messages if m.get("role") == "assistant"]
        tool_messages = [m for m in messages if m.get("role") == "tool"]
        
        # Build basic summary structure
        summary = "## Compaction Summary\n\n"
        
        # Goal (from first user message)
        if user_messages:
            first_query = user_messages[0].get("content", "")[:200]
            summary += f"## Goal\n{first_query}\n\n"
        
        # Progress (from last assistant message)
        if assistant_messages:
            last_response = assistant_messages[-1].get("content", "")[:300]
            summary += f"## Last Response\n{last_response}\n\n"
        
        # Tool usage count
        summary += f"## Statistics\n"
        summary += f"- User messages: {len(user_messages)}\n"
        summary += f"- Assistant messages: {len(assistant_messages)}\n"
        summary += f"- Tool calls: {len(tool_messages)}\n"
        summary += f"- Total messages: {len(messages)}\n"
        
        return summary
    
    async def _update_summary(
        self,
        previous_summary: str,
        new_messages: List[Dict[str, Any]],
        token_budget: int
    ) -> str:
        """
        Update an existing summary with new information.
        
        The update should:
        1. Preserve still-relevant parts of previous summary
        2. Add new information from recent messages
        3. Remove outdated information
        4. Maintain the structured format
        """
        # Simple update: append new messages to existing summary
        update = "\n\n## Update "
        update += f"({datetime.utcnow().strftime('%Y-%m-%d %H:%M')})\n"
        
        for msg in new_messages[-10:]:  # Last 10 messages
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:200]
            
            if role == "user":
                update += f"- User: {content}\n"
            elif role == "assistant" and content:
                update += f"- Assistant: {content[:150]}...\n"
            elif role == "tool":
                tool_name = msg.get("name", "unknown")
                update += f"- Tool {tool_name} called\n"
        
        return previous_summary + update
    
    def _estimate_tokens(self, message: Dict[str, Any]) -> int:
        """Estimate token count for a message."""
        content = message.get("content", "")
        # Rough estimate: 4 chars per token
        return len(content) // 4
    
    def check_compaction_needed(
        self,
        messages: List[Dict[str, Any]],
        context_limit: int = 128000,
        threshold: float = 0.80
    ) -> Dict[str, Any]:
        """
        Check if compaction is needed based on token usage.
        
        Args:
            messages: Current conversation messages
            context_limit: Model's context window limit
            threshold: Percentage of context to trigger compaction
            
        Returns:
            Dict with:
            - needed: bool
            - current_tokens: int
            - threshold_tokens: int
            - utilization: float (0.0 - 1.0)
        """
        total_tokens = sum(self._estimate_tokens(m) for m in messages)
        threshold_tokens = int(context_limit * threshold)
        
        return {
            "needed": total_tokens >= threshold_tokens,
            "current_tokens": total_tokens,
            "threshold_tokens": threshold_tokens,
            "utilization": total_tokens / context_limit if context_limit > 0 else 0,
            "message_count": len(messages),
        }
    
    def get_auto_continue_message(self) -> str:
        """
        Returns the message to inject after compaction to continue work.
        """
        return (
            "Continue if you have next steps. "
            "Your context has been compacted to allow continued work. "
            "Refer to the summary above for context."
        )