"""
General Agent - Multi-Task Parallel Execution

The General Agent is a subagent capable of executing multiple units of
work in parallel. It does not have access to task management (todowrite)
but can coordinate parallel tool calls.

Based on OpenCode's general agent architecture.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class GeneralAgent:
    """
    General Agent - Subagent for parallel task execution.
    
    This agent is used when:
    - Multiple independent tasks need to be executed
    - Data fetching can be parallelized (e.g., TA + Fundamentals + News)
    - User requests complex analysis that can be broken into parallel streams
    
    Permission Scope:
    - ALL read tools allowed
    - write_reports: allowed
    - todowrite: DENIED (cannot manage tasks)
    - execute_code: ask (requires confirmation)
    
    Key Feature: PARALLEL EXECUTION
    - Multiple tools can be called in a single response
    - Independent data fetching happens concurrently
    - Results are aggregated for synthesis
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.agent_id = self.config.get("identifier", "general-agent")
        self.name = self.config.get("name", "Mahameru General Agent")
        self.description = self.config.get(
            "description",
            "Multi-task agent for parallel execution of independent work units"
        )
        self.model = self.config.get("model", "gemini-2.0-flash")
        self.temperature = self.config.get("temperature", 0.3)
        self.steps = self.config.get("steps", 8)
        
    async def execute_parallel(
        self,
        tasks: List[Dict[str, Any]],
        max_concurrent: int = 3
    ) -> Dict[str, Any]:
        """
        Execute multiple tasks in parallel.
        
        Args:
            tasks: List of task definitions, each containing:
                   - task_id: unique identifier
                   - tool: tool name to call
                   - params: parameters for the tool
                   - priority: optional priority (higher = earlier)
            max_concurrent: Maximum concurrent executions
            
        Returns:
            Dict with:
            - results: dict of task_id -> result
            - errors: dict of task_id -> error
            - completed: list of completed task_ids
            - total_time: execution time in seconds
        """
        logger.info(f"[GeneralAgent] Starting parallel execution of {len(tasks)} tasks")
        start_time = datetime.utcnow()
        
        results = {}
        errors = {}
        
        try:
            # Sort by priority (higher first)
            sorted_tasks = sorted(
                tasks, 
                key=lambda t: t.get("priority", 0), 
                reverse=True
            )
            
            # Execute in batches
            for i in range(0, len(sorted_tasks), max_concurrent):
                batch = sorted_tasks[i:i + max_concurrent]
                
                logger.info(f"[GeneralAgent] Batch {i//max_concurrent + 1}: {len(batch)} tasks")
                
                # Execute batch concurrently
                batch_results = await asyncio.gather(
                    *[self._execute_single_task(task) for task in batch],
                    return_exceptions=True
                )
                
                # Process results
                for task, result in zip(batch, batch_results):
                    task_id = task.get("task_id", task.get("tool", "unknown"))
                    
                    if isinstance(result, Exception):
                        logger.error(f"[GeneralAgent] Task {task_id} failed: {result}")
                        errors[task_id] = str(result)
                    else:
                        results[task_id] = result
                        logger.info(f"[GeneralAgent] Task {task_id} completed")
            
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            
            return {
                "success": True,
                "results": results,
                "errors": errors,
                "completed": list(results.keys()),
                "failed": list(errors.keys()),
                "total_tasks": len(tasks),
                "completed_count": len(results),
                "failed_count": len(errors),
                "total_time_seconds": elapsed,
            }
            
        except Exception as e:
            logger.error(f"[GeneralAgent] Parallel execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "results": results,
                "errors": errors,
            }
    
    async def _execute_single_task(self, task: Dict[str, Any]) -> Any:
        """
        Execute a single task.
        
        In production, this would call the actual tool through
        the tool execution system. Here we provide the structure.
        """
        tool = task.get("tool")
        params = task.get("params", {})
        
        if not tool:
            raise ValueError("Task must specify a 'tool' name")
        
        logger.debug(f"[GeneralAgent] Executing tool: {tool} with params: {params}")
        
        # This is where actual tool execution would happen
        # For now, return a mock result structure
        return {
            "tool": tool,
            "params": params,
            "status": "completed",
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    async def aggregate_results(
        self,
        results: Dict[str, Any],
        synthesis_type: str = "default"
    ) -> Dict[str, Any]:
        """
        Aggregate multiple results into a unified response.
        
        Args:
            results: Dict of task_id -> result
            synthesis_type: Type of synthesis to perform
            
        Returns:
            Aggregated result with summary
        """
        logger.info(f"[GeneralAgent] Aggregating {len(results)} results")
        
        aggregated = {
            "total_results": len(results),
            "data_sources": list(results.keys()),
            "synthesis_type": synthesis_type,
            "data": {},
            "summary": "",
        }
        
        # Merge data based on synthesis type
        if synthesis_type == "market_analysis":
            aggregated["data"] = self._merge_market_data(results)
            aggregated["summary"] = self._generate_market_summary(results)
        elif synthesis_type == "research":
            aggregated["data"] = self._merge_research_data(results)
            aggregated["summary"] = self._generate_research_summary(results)
        else:
            aggregated["data"] = results
            aggregated["summary"] = f"Aggregated {len(results)} data sources"
        
        return aggregated
    
    def _merge_market_data(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Merge market data from multiple sources."""
        merged = {
            "quotes": {},
            "technical": {},
            "sentiment": None,
            "news_count": 0,
        }
        
        for source, data in results.items():
            source_lower = source.lower()
            
            if "quote" in source_lower or "market" in source_lower:
                merged["quotes"].update(data if isinstance(data, dict) else {})
            elif "ta" in source_lower or "technical" in source_lower:
                merged["technical"].update(data if isinstance(data, dict) else {})
            elif "sentiment" in source_lower:
                merged["sentiment"] = data
            elif "news" in source_lower:
                if isinstance(data, dict) and "articles" in data:
                    merged["news_count"] += len(data.get("articles", []))
        
        return merged
    
    def _merge_research_data(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Merge research data from multiple sources."""
        merged = {
            "fundamental": {},
            "technical": {},
            "sentiment": {},
            "macro": {},
            "chains": [],
        }
        
        for source, data in results.items():
            if isinstance(data, dict):
                if "fundamental" in source.lower():
                    merged["fundamental"].update(data)
                elif "technical" in source.lower():
                    merged["technical"].update(data)
                elif "sentiment" in source.lower():
                    merged["sentiment"].update(data)
                elif "macro" in source.lower():
                    merged["macro"].update(data)
                
                # Collect chain stages
                if "chain" in source.lower():
                    merged["chains"].append(data)
        
        return merged
    
    def _generate_market_summary(self, results: Dict[str, Any]) -> str:
        """Generate summary for market analysis aggregation."""
        sources = list(results.keys())
        return f"Market analysis completed with data from: {', '.join(sources)}"
    
    def _generate_research_summary(self, results: Dict[str, Any]) -> str:
        """Generate summary for research aggregation."""
        sources = list(results.keys())
        return f"Research aggregation completed. Sources: {', '.join(sources)}"
    
    def get_parallel_execution_prompt(self, tasks: List[str]) -> str:
        """
        Generate a prompt for parallel execution context.
        
        Args:
            tasks: List of task descriptions
        """
        task_list = "\n".join([f"- {t}" for t in tasks])
        
        return f"""You are Mahameru General Agent executing multiple tasks in parallel.

TASKS TO EXECUTE:
{task_list}

EXECUTION STRATEGY:
1. Execute all independent tasks concurrently
2. Each task should be treated as a separate work unit
3. Aggregate results after all tasks complete
4. Generate unified summary combining all findings

TOOL USAGE:
- Use parallel tool calls when possible (batch them in single response)
- Do not wait for one tool to complete before calling the next
- If tasks are independent, execute them simultaneously

OUTPUT:
Return a structured response with:
- Individual task results (brief)
- Aggregated findings
- Unified summary
- Any correlations or patterns noticed across data sources
"""