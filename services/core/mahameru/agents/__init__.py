"""
Mahameru Agent System - Modular Agent Implementations

This module contains specialized agents for the Mahameru Copilot system,
following the OpenCode multi-agent architecture pattern.
"""

from .registry import AgentRegistry, agent_registry
from .plan_agent import PlanAgent
from .explore_agent import ExploreAgent
from .compaction_agent import CompactionAgent
from .general_agent import GeneralAgent

__all__ = [
    "AgentRegistry",
    "agent_registry",
    "PlanAgent",
    "ExploreAgent",
    "CompactionAgent", 
    "GeneralAgent",
]