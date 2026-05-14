"""
Plan Agent - Read-Only Planning Mode

The Plan Agent is responsible for creating detailed implementation plans
without executing them. It operates in READ-ONLY mode and can only write
to plan files (.mahameru/plans/).

Based on OpenCode's plan agent architecture.
"""

import os
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class PlanAgent:
    """
    Plan Agent - Read-only agent for creating implementation plans.
    
    Constrains:
    - CANNOT edit any files
    - CANNOT execute any write operations
    - CAN read files, search, and analyze
    - CAN only write to .mahameru/plans/*.md files
    
    The Plan Agent follows a 5-phase workflow:
    1. Initial Understanding - Explore and gather context
    2. Design - Create detailed implementation plan
    3. Review - Verify plan aligns with user request
    4. Final Plan - Write plan to file
    5. Exit - Hand off to build agent for execution
    """
    
    PLAN_REMINDER = """
    <system-reminder>
    CRITICAL: Plan mode ACTIVE - you are in READ-ONLY phase.
    STRICTLY FORBIDDEN: ANY file edits, modifications, or system changes.
    You are ONLY permitted to:
    - Read files and search code
    - Analyze and reason about the request
    - Write plans to .mahameru/plans/*.md
    
    All edit/write operations are DENIED by permission system.
    </system-reminder>
    """
    
    BUILD_SWITCH_REMINDER = """
    <system-reminder>
    Your operational mode has changed from plan to build.
    You are no longer in read-only mode.
    You are now permitted to make file changes, run shell commands,
    and execute the plan defined in the plan file.
    
    Read the plan file at {plan_path} before proceeding.
    Execute the plan step by step.
    After completing each step, run verification commands.
    </system-reminder>
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.agent_id = self.config.get("identifier", "plan-agent")
        self.name = self.config.get("name", "Mahameru Planner")
        self.description = self.config.get("description", "Read-only planning agent")
        self.model = self.config.get("model", "gemini-2.0-flash")
        self.temperature = self.config.get("temperature", 0.3)
        self.steps = self.config.get("steps", 15)
        
        # Plan directory
        self.plan_root = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            ".mahameru",
            "plans"
        )
        os.makedirs(self.plan_root, exist_ok=True)
        
    def get_plan_reminder(self) -> str:
        """Returns the plan mode reminder prompt."""
        return self.PLAN_REMINDER
    
    def get_build_switch(self, plan_path: str) -> str:
        """Returns the build switch reminder when transitioning to build mode."""
        return self.BUILD_SWITCH_REMINDER.format(plan_path=plan_path)
    
    async def create_plan(
        self,
        task: str,
        context: Dict[str, Any],
        explore_func=None
    ) -> Dict[str, Any]:
        """
        Create a detailed implementation plan for the given task.
        
        Args:
            task: The user's request/task description
            context: Additional context (available agents, tools, session info)
            explore_func: Optional async function to explore data sources
            
        Returns:
            Dict with:
            - success: bool
            - plan_path: str (path to the plan file)
            - plan_content: str
            - steps: list of planned steps
            - summary: str
        """
        logger.info(f"[PlanAgent] Creating plan for task: {task[:100]}...")
        
        try:
            # Phase 1: Gather context if explore_func provided
            gathered_context = {}
            if explore_func and callable(explore_func):
                logger.info("[PlanAgent] Phase 1: Exploring context...")
                gathered_context = await explore_func(task, context)
            
            # Phase 2: Design the plan
            plan_content = self._design_plan(task, context, gathered_context)
            
            # Phase 3: Write plan to file
            plan_filename = self._generate_plan_filename(task)
            plan_path = os.path.join(self.plan_root, plan_filename)
            
            with open(plan_path, 'w', encoding='utf-8') as f:
                f.write(plan_content)
            
            # Extract steps from plan
            steps = self._extract_steps(plan_content)
            
            logger.info(f"[PlanAgent] Plan created at: {plan_path}")
            
            return {
                "success": True,
                "plan_path": plan_path,
                "plan_content": plan_content,
                "steps": steps,
                "summary": f"Plan created with {len(steps)} steps"
            }
            
        except Exception as e:
            logger.error(f"[PlanAgent] Failed to create plan: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "plan_path": None,
                "plan_content": None,
                "steps": [],
                "summary": f"Plan creation failed: {str(e)}"
            }
    
    def _design_plan(
        self,
        task: str,
        context: Dict[str, Any],
        gathered_context: Dict[str, Any]
    ) -> str:
        """
        Design a detailed implementation plan in markdown format.
        
        Format follows OpenCode's structured plan template:
        - Goal
        - Constraints
        - Progress
        - Key Decisions
        - Next Steps
        - Critical Context
        - Relevant Files
        """
        timestamp = datetime.utcnow().isoformat()
        
        plan = f"""# Implementation Plan

**Created**: {timestamp}  
**Task**: {task}

---

## 🎯 Goal

{self._summarize_goal(task)}

---

## 📋 Constraints

- Read-only planning phase - no file modifications allowed
- Must identify all required tools from Mahameru microservices
- Must include verification steps for each implementation phase

---

## 🔍 Context Gathered

{self._format_context(gathered_context)}

---

## 📌 Implementation Steps

"""
        steps = self._suggest_steps(task, context)
        for i, step in enumerate(steps, 1):
            plan += f"{i}. [ ] **{step['title']}**\n   - {step['description']}\n"
        
        plan += f"""

---

## 🔧 Tools Required

{self._identify_tools(task, context)}

---

## ✅ Verification Plan

1. After each step, verify the output
2. Run lint/typecheck if applicable
3. Validate data integrity with source services
4. Test integration points

---

## ⚠️ Risks & Considerations

{self._identify_risks(task, context)}

---

## 📊 Success Criteria

- All steps completed successfully
- Output verified against expectations
- No errors or warnings in logs
- User approved plan for execution

---

*Plan created by Mahameru Plan Agent*
"""
        return plan
    
    def _summarize_goal(self, task: str) -> str:
        """Summarize the task in one clear sentence."""
        # Simple truncation + cleanup
        if len(task) <= 200:
            return task
        return task[:197] + "..."
    
    def _format_context(self, gathered_context: Dict[str, Any]) -> str:
        """Format gathered context for the plan."""
        if not gathered_context:
            return "No additional context gathered (explore function not provided)."
        
        lines = []
        for key, value in gathered_context.items():
            lines.append(f"- **{key}**: {value}")
        
        return "\n".join(lines) if lines else "No additional context gathered."
    
    def _suggest_steps(self, task: str, context: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Suggest implementation steps based on task analysis.
        This is a simple heuristic - can be enhanced with LLM later.
        """
        task_lower = task.lower()
        
        steps = []
        
        # Research/Analysis tasks
        if any(kw in task_lower for kw in ["research", "analisa", "analysis", "deep"]):
            steps.extend([
                {"title": "Detect Tickers", "description": "Extract stock/crypto symbols from query"},
                {"title": "Fetch Technical Analysis", "description": "Get TA data from ta_service"},
                {"title": "Fetch Fundamental Data", "description": "Get fundamental data from yfinance"},
                {"title": "Run Sentiment Analysis", "description": "BERT sentiment on related news"},
                {"title": "Synthesize Analysis", "description": "Combine all data into insights"},
            ])
        
        # Trading/Strategy tasks
        if any(kw in task_lower for kw in ["trading", "strategy", "position", "buy", "sell"]):
            steps.extend([
                {"title": "Analyze Market Regime", "description": "Determine trend/ranging/sideways"},
                {"title": "Calculate Risk Metrics", "description": "VaR, position sizing"},
                {"title": "Generate Trade Plan", "description": "Entry, exit, stop-loss levels"},
                {"title": "Validate with Sentiment", "description": "Cross-check with news sentiment"},
            ])
        
        # Vessel/Geospatial tasks
        if any(kw in task_lower for kw in ["vessel", "ship", "maritime", "ais"]):
            steps.extend([
                {"title": "Parse Location", "description": "Extract port/strait coordinates"},
                {"title": "Query AIS Service", "description": "Fetch vessel tracking data"},
                {"title": "Identify Anomalies", "description": "Dark vessel, speed anomalies"},
                {"title": "Generate Intel Report", "description": "Summary with coordinates"},
            ])
        
        # Macro/Economic tasks
        if any(kw in task_lower for kw in ["macro", "economic", "fed", "inflation", "gdp"]):
            steps.extend([
                {"title": "Fetch FRED Data", "description": "Get economic indicators"},
                {"title": "Analyze Yield Curve", "description": "Bond service data"},
                {"title": "Check Market Regime", "description": "HMM regime detection"},
                {"title": "Synthesize View", "description": "Combined macro analysis"},
            ])
        
        # Default fallback steps
        if not steps:
            steps = [
                {"title": "Understand Request", "description": "Analyze user intent and scope"},
                {"title": "Gather Data", "description": "Fetch required data from services"},
                {"title": "Analyze", "description": "Process and analyze gathered data"},
                {"title": "Report", "description": "Format findings as response"},
            ]
        
        return steps[:10]  # Max 10 steps
    
    def _identify_tools(self, task: str, context: Dict[str, Any]) -> str:
        """Identify required tools based on task type."""
        task_lower = task.lower()
        tools = []
        
        tool_map = {
            "ta": "get_technical_analysis",
            "technical": "get_technical_analysis",
            "price": "get_market_quote",
            "quote": "get_market_quote",
            "sentiment": "get_sentiment_analysis",
            "news": "get_news_feed",
            "vessel": "get_vessel_radar",
            "vessel_intelligence": "get_vessel_intelligence",
            "crypto": "get_crypto_analysis",
            "on-chain": "get_crypto_onchain",
            "forex": "get_forex_rates",
            "macro": "get_macro_economics",
            "regime": "get_market_regime",
            "bond": "get_bond_yield_curve",
            "deep": "run_deep_research",
            "research": "run_deep_research",
        }
        
        for keyword, tool in tool_map.items():
            if keyword in task_lower and tool not in tools:
                tools.append(tool)
        
        if not tools:
            return "- No specific tools identified (general query)"
        
        return "\n".join([f"- `{t}`" for t in tools])
    
    def _identify_risks(self, task: str, context: Dict[str, Any]) -> str:
        """Identify potential risks and considerations."""
        risks = []
        
        task_lower = task.lower()
        
        if any(kw in task_lower for kw in ["trading", "strategy"]):
            risks.append("- Market volatility may affect strategy validity")
            risks.append("- Past performance does not guarantee future results")
        
        if any(kw in task_lower for kw in ["vessel", "maritime"]):
            risks.append("- AIS data may have 1-hour delay for dark vessels")
            risks.append("- Vessel positions are estimates based on AIS transponders")
        
        if any(kw in task_lower for kw in ["research", "analysis"]):
            risks.append("- Data freshness depends on upstream service availability")
            risks.append("- Sentiment analysis accuracy varies by language")
        
        if not risks:
            risks.append("- No specific risks identified for this task type")
        
        return "\n".join(risks)
    
    def _generate_plan_filename(self, task: str) -> str:
        """Generate a clean filename from the task."""
        import re
        import uuid
        
        # Take first 50 chars, remove special chars
        clean = re.sub(r'[^\w\s-]', '', task[:50])
        clean = re.sub(r'\s+', '-', clean)
        clean = clean.strip('-')
        
        if not clean:
            clean = "plan"
        
        # Add unique ID to prevent collisions
        uid = uuid.uuid4().hex[:8]
        timestamp = datetime.utcnow().strftime("%Y%m%d")
        
        return f"{timestamp}-{clean[:30]}-{uid}.md"
    
    def _extract_steps(self, plan_content: str) -> List[Dict[str, Any]]:
        """Extract steps from plan content."""
        steps = []
        lines = plan_content.split('\n')
        
        for line in lines:
            # Look for numbered steps like "1. [ ] **Title**"
            import re
            match = re.match(r'^\d+\.\s+\[[\sx]\]\s+\*\*([^*]+)\*\*', line)
            if match:
                steps.append({
                    "title": match.group(1).strip(),
                    "status": "pending"
                })
        
        return steps
    
    async def explore_data_sources(
        self,
        task: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Explore available data sources for the task.
        
        This is a default implementation - can be overridden with
        actual data fetching logic.
        """
        logger.info("[PlanAgent] Exploring data sources...")
        
        # Simple keyword-based exploration
        task_lower = task.lower()
        results = {}
        
        if any(kw in task_lower for kw in ["stock", "saham", "equity"]):
            results["data_type"] = "equity_market"
            results["services"] = ["ta_service", "market_service", "sentiment_service"]
        
        if any(kw in task_lower for kw in ["crypto", "bitcoin", "btc"]):
            results["data_type"] = "cryptocurrency"
            results["services"] = ["crypto_analysis", "crypto_onchain", "crypto_derivatives"]
        
        if any(kw in task_lower for kw in ["vessel", "ship", "maritime"]):
            results["data_type"] = "maritime_intelligence"
            results["services"] = ["ais_service", "vessel_intelligence_service"]
        
        if any(kw in task_lower for kw in ["macro", "economic", "fed"]):
            results["data_type"] = "macro_economics"
            results["services"] = ["macro_economics_service", "bond_service", "volatility_service"]
        
        results["exploration_complete"] = True
        results["timestamp"] = datetime.utcnow().isoformat()
        
        return results