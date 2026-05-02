"""
============================================================================
  Pydantic Models for Copilot Gateway
============================================================================
"""

from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

from copilot.config import LLM_MAX_TOKENS


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant|tool)$")
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., description="Conversation history")
    stream: bool = Field(default=False, description="Enable SSE streaming for response")
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=LLM_MAX_TOKENS, ge=64, le=16384)
    model: Optional[str] = Field(default=None, description="Override LLM model (e.g. deepseek-chat, gpt-5.4-mini)")


class ChatResponse(BaseModel):
    response_id: str
    message: str
    components: List[Dict[str, Any]]
    latency_ms: float
    model: str
    tool_calls_made: List[str]


class SlashCommandRequest(BaseModel):
    command: str = Field(..., description="Slash command e.g. /ta BBRI.JK")
    stream: bool = Field(default=False)


class SlashCommandResponse(BaseModel):
    response_id: str
    command: str
    message: str
    components: List[Dict[str, Any]]
