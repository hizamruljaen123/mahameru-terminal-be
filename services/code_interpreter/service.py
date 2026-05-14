from typing import Dict, Any, Type
from .executors.base import BaseExecutor
from .executors.python_executor import PythonExecutor
from .executors.nodejs_executor import NodeExecutor
from .executors.shell_executor import ShellExecutor

class CodeInterpreterService:
    """Manager for various code executors."""
    
    _executors: Dict[str, Type[BaseExecutor]] = {
        "python": PythonExecutor,
        "javascript": NodeExecutor,
        "nodejs": NodeExecutor,
        "bash": ShellExecutor,
        "shell": ShellExecutor,
        "cmd": ShellExecutor
    }
    
    @classmethod
    async def run_code(cls, language: str, code: str, timeout: int = 30) -> Dict[str, Any]:
        """Execute code in the specified language with production safety checks."""
        from copilot.config import LOCAL_DEV
        
        lang = language.lower().strip()
        
        # Production Safety: Disable shell/bash for public servers
        if not LOCAL_DEV and lang in ["bash", "shell", "cmd"]:
            return {
                "stdout": "",
                "stderr": "CRITICAL SECURITY ERROR: Shell execution is disabled in production environments for security reasons.",
                "exit_code": 1,
                "duration_ms": 0
            }
            
        executor_cls = cls._executors.get(lang)
        
        if not executor_cls:
            return {
                "stdout": "",
                "stderr": f"Unsupported language: {language}",
                "exit_code": 1,
                "duration_ms": 0
            }
            
        executor = executor_cls()
        
        # In non-local dev, we should log every execution for audit trails
        if not LOCAL_DEV:
            import logging
            audit_logger = logging.getLogger("code_interpreter_audit")
            audit_logger.warning(f"[AUDIT] Public user requested execution of {lang} code (Length: {len(code)})")
            
        return await executor.execute(code, timeout=timeout)
