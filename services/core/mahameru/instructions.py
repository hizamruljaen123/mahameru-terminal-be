"""
Mahameru Instruction System - AGENTS.md Pattern

This module implements the OpenCode instruction file pattern where
context is injected automatically from instruction files in the
project structure.

Based on OpenCode's Instruction Injection System (instruction.ts).

PATTERN:
- AGENTS.md / MAHAMERU.md files in project directories
- Hierarchical lookup from current directory to root
- Automatic injection into system prompt
- Per-domain instruction files for specialized knowledge
"""

import os
import re
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class InstructionLoader:
    """
    Loads and manages instruction files (AGENTS.md pattern).
    
    Instructions are auto-loaded from:
    1. Global config: ~/.config/mahameru/AGENTS.md
    2. Project root: {project_root}/MAHAMERU.md
    3. Domain-specific: {project_root}/instructions/{domain}.md
    4. Working directory: .MAHAMERU in current path hierarchy
    
    The loader walks up the directory tree looking for instruction files.
    """
    
    INSTRUCTION_FILENAMES = [
        "MAHAMERU.md",
        "AGENTS.md", 
        "CLAUDE.md",
        ".mahameru",
        ".mahameru_instructions",
    ]
    
    DOMAIN_INSTRUCTIONS = {
        "banking": "instructions/banking-analysis.md",
        "vessel": "instructions/vessel-intelligence.md",
        "crypto": "instructions/crypto-analysis.md",
        "macro": "instructions/macro-analysis.md",
        "osint": "instructions/osint-research.md",
        "ta": "instructions/technical-analysis.md",
        "sentiment": "instructions/sentiment-analysis.md",
    }
    
    def __init__(self, project_root: Optional[str] = None):
        self.project_root = project_root or self._detect_project_root()
        self.global_config_path = self._get_global_config_path()
        self._cache: Dict[str, str] = {}
        self._claims: Dict[str, bool] = {}  # Track which files have been attached

    def _detect_project_root(self) -> str:
        """Detect Mahameru project root.

        Falls back to `mahameru-terminal-be/` (4 levels up from this file).
        """
        default_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        )
        return default_root
    
    def _get_global_config_path(self) -> str:
        """Get the global configuration path."""
        home = os.path.expanduser("~")
        return os.path.join(home, ".config", "mahameru", "AGENTS.md")
    
    def load_instructions(
        self,
        working_dir: Optional[str] = None,
        domains: Optional[List[str]] = None
    ) -> str:
        """
        Load all relevant instructions for the given context.
        
        Args:
            working_dir: Current working directory for hierarchy walk
            domains: Optional list of domain-specific instructions to load
            
        Returns:
            Combined instruction text
        """
        instructions = []
        
        # 1. Load global instructions
        global_inst = self._load_global_instructions()
        if global_inst:
            instructions.append(global_inst)
        
        # 2. Load project-level instructions (walk up hierarchy)
        project_inst = self._load_project_instructions(working_dir)
        if project_inst:
            instructions.append(project_inst)
        
        # 3. Load domain-specific instructions
        if domains:
            domain_inst = self._load_domain_instructions(domains)
            if domain_inst:
                instructions.append(domain_inst)
        
        return "\n\n".join(instructions) if instructions else ""
    
    def _load_global_instructions(self) -> Optional[str]:
        """Load global instructions from ~/.config/mahameru/AGENTS.md"""
        cache_key = f"global:{self.global_config_path}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        if os.path.exists(self.global_config_path):
            try:
                with open(self.global_config_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    self._cache[cache_key] = content
                    logger.debug(f"[InstructionLoader] Loaded global instructions from {self.global_config_path}")
                    return content
            except Exception as e:
                logger.warning(f"[InstructionLoader] Failed to load global instructions: {e}")
        
        return None
    
    def _load_project_instructions(self, working_dir: Optional[str] = None) -> Optional[str]:
        """Load project-level instructions by walking up the directory hierarchy."""
        if not working_dir:
            working_dir = self.project_root
        
        # Walk up from working directory to project root
        current_dir = Path(working_dir).resolve()
        project_path = Path(self.project_root).resolve()
        
        instructions = []
        
        # Check for MAHAMERU.md in project root
        mahameru_md = project_path / "MAHAMERU.md"
        if mahameru_md.exists():
            content = self._read_instruction_file(mahameru_md)
            if content:
                instructions.append(f"# Project Instructions (from {mahameru_md.name})\n\n{content}")
        
        # Walk up the directory tree looking for instruction files
        while current_dir != current_dir.parent and current_dir in project_path.parents:
            for filename in self.INSTRUCTION_FILENAMES:
                instruction_file = current_dir / filename
                if instruction_file.exists():
                    content = self._read_instruction_file(instruction_file)
                    if content and instruction_file.name not in self._claims:
                        instructions.append(f"# Directory: {current_dir.name}\n\n{content}")
                        self._claims[instruction_file.name] = True
            
            current_dir = current_dir.parent
        
        return "\n\n".join(instructions) if instructions else None
    
    def _load_domain_instructions(self, domains: List[str]) -> Optional[str]:
        """Load domain-specific instruction files."""
        instructions = []
        
        for domain in domains:
            domain_path = self.DOMAIN_INSTRUCTIONS.get(domain.lower())
            if not domain_path:
                continue
            
            full_path = os.path.join(self.project_root, domain_path)
            cache_key = f"domain:{domain}"
            
            if cache_key in self._cache:
                content = self._cache[cache_key]
            elif os.path.exists(full_path):
                content = self._read_instruction_file(Path(full_path))
                self._cache[cache_key] = content or ""
            else:
                content = None
            
            if content:
                instructions.append(f"# {domain.title()} Domain Instructions\n\n{content}")
        
        return "\n\n".join(instructions) if instructions else None
    
    def _read_instruction_file(self, filepath: Path) -> Optional[str]:
        """Read an instruction file with error handling."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                # Skip empty files or files with only comments
                if content and not content.startswith('#'):
                    return content
                elif content:
                    # Has content, return as-is
                    return content
        except Exception as e:
            logger.warning(f"[InstructionLoader] Failed to read {filepath}: {e}")
        
        return None
    
    def resolve_for_file(self, filepath: str) -> str:
        """
        Resolve instructions relevant to a specific file.
        
        Called when an agent reads a file - inject relevant instructions.
        """
        file_path = Path(filepath)
        directory = file_path.parent
        
        # Determine which domain based on file path
        domain = self._detect_domain_from_path(filepath)
        
        return self.load_instructions(
            working_dir=str(directory),
            domains=[domain] if domain else None
        )
    
    def _detect_domain_from_path(self, filepath: str) -> Optional[str]:
        """Detect which domain instruction file is relevant based on file path."""
        filepath_lower = filepath.lower()
        
        domain_map = {
            "banking": ["bank", "perbankan", "saham"],
            "vessel": ["vessel", "ais", "maritime", "ship"],
            "crypto": ["crypto", "bitcoin", "blockchain"],
            "macro": ["macro", "bond", "volatility", "economics"],
            "ta": ["technical", "ta_", "indicator"],
            "sentiment": ["sentiment", "news", "berita"],
            "osint": ["conflict", "military", "government"],
        }
        
        for domain, keywords in domain_map.items():
            if any(kw in filepath_lower for kw in keywords):
                return domain
        
        return None
    
    def get_system_prompt_overlay(self, agent_type: str) -> str:
        """
        Get agent-specific system prompt overlay.
        
        This adds behavioral instructions based on agent type.
        """
        overlays = {
            "plan-agent": """
# Plan Agent Behavior
- You are in READ-ONLY mode. STRICTLY FORBIDDEN to edit files.
- Only write to .mahameru/plans/ directory.
- Always include verification steps in plans.
- Consider user constraints and available tools.
""",
            "explore-agent": """
# Explore Agent Behavior
- Focus on discovery and data retrieval, not deep analysis.
- Use parallel searches for independent data types.
- Return structured summaries with confidence levels.
- Do not make assumptions about data quality.
""",
            "compaction-agent": """
# Compaction Agent Behavior
- Preserve actionable information, remove conversational filler.
- Keep key numbers, timestamps, and identifiers.
- Use same language as the conversation.
- Summary must be under 2000 tokens.
""",
            "general-agent": """
# General Agent Behavior
- Execute independent tasks in parallel.
- Batch tool calls for optimal performance.
- Aggregate results from all tasks.
- Do not use todowrite (task management denied).
""",
            "build-agent": """
# Build Agent Behavior
- Be proactive but don't surprise the user.
- Follow existing code conventions.
- Always cite data sources and timestamps.
- Verify output before presenting.
""",
            "research-agent": """
# Research Agent Behavior
- Follow the 7 Mandatory Rules for banking stocks.
- Use chain prompting: TA → Fundamental → Sentiment → Report.
- Streaming SSE output for progressive results.
- Zero-placeholder policy: always use real data.
"""
        }
        
        return overlays.get(agent_type, "")
    
    def clear_cache(self):
        """Clear the instruction cache."""
        self._cache.clear()
        self._claims.clear()
        logger.debug("[InstructionLoader] Cache cleared")


class InstructionInjectionMiddleware:
    """
    Middleware that injects instructions into LLM calls.
    
    Works with the copilot gateway to automatically inject
    relevant instructions based on:
    - Current agent type
    - Working context (domains, file being edited)
    - Session state
    """
    
    def __init__(self, loader: Optional[InstructionLoader] = None):
        self.loader = loader or InstructionLoader()
    
    def inject_into_system_prompt(
        self,
        base_prompt: str,
        agent_type: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Inject instructions into the base system prompt.
        
        Args:
            base_prompt: The base system prompt
            agent_type: Current agent type (plan, explore, build, etc.)
            context: Optional context dict with domains, working_dir, etc.
            
        Returns:
            Enhanced system prompt with instructions injected
        """
        parts = [base_prompt]
        
        # Add agent-specific overlay
        overlay = self.loader.get_system_prompt_overlay(agent_type)
        if overlay:
            parts.append(overlay)
        
        # Add domain-specific instructions
        domains = context.get("domains", []) if context else []
        if domains:
            domain_inst = self.loader.load_instructions(
                working_dir=context.get("working_dir"),
                domains=domains
            )
            if domain_inst:
                parts.append(domain_inst)
        
        # Add general instructions
        general_inst = self.loader.load_instructions(
            working_dir=context.get("working_dir") if context else None
        )
        if general_inst:
            parts.append(general_inst)
        
        return "\n\n".join(parts)
    
    def inject_into_messages(
        self,
        messages: List[Dict[str, Any]],
        agent_type: str,
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Inject instruction messages into the message list.
        
        For read operations, inject relevant file instructions.
        """
        if not context:
            return messages
        
        # Check if we should inject based on context type
        if context.get("type") == "file_read":
            filepath = context.get("filepath")
            if filepath:
                instructions = self.loader.resolve_for_file(filepath)
                if instructions:
                    # Insert as a system message before the read
                    messages = [
                        {
                            "role": "system",
                            "content": f"# Context Instructions\n\n{instructions}"
                        }
                    ] + messages
        
        return messages


# Global instances
instruction_loader = InstructionLoader()


def get_instruction_loader() -> InstructionLoader:
    """Get the global instruction loader instance."""
    return instruction_loader