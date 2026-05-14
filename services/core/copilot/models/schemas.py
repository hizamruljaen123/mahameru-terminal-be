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
    use_tools: bool = Field(default=True, description="Enable tool planning and execution")
    session_id: Optional[str] = Field(default=None, description="Unique session ID for chat history")
    save_history: bool = Field(default=True, description="If False, this request will not be saved to chat history")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Optional metadata for the request")


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
    session_id: Optional[str] = Field(default=None, description="Session ID for history")


class SlashCommandResponse(BaseModel):
    response_id: str
    command: str
    message: str
    components: List[Dict[str, Any]]


class SessionInfo(BaseModel):
    session_id: str
    title: str
    created_at: str
    updated_at: str
    model: str
    mode: str


class HistoryUpdate(BaseModel):
    title: str


class CodeExecutionRequest(BaseModel):
    language: str = Field(..., description="Programming language (python, javascript, bash, etc.)")
    code: str = Field(..., description="The source code to execute")
    timeout: int = Field(default=30, ge=1, le=300)


class CodeExecutionResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float
    images: List[str] = Field(default_factory=list, description="Base64 encoded images (Data URIs)")

