import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class PermissionService:
    DEFAULT_RULES = {
        "read_market_data": "allow",
        "read_news": "allow",
        "run_technical_analysis": "allow",
        "run_sentiment": "allow",
        "run_llm_research": "ask",
        "vessel_intelligence": "ask",
        "military_intelligence": "ask",
        "export_data": "ask",
        "write_reports": "allow"
    }

    TIER_OVERRIDES = {
        "GUEST": {
            "run_llm_research": "deny",
            "vessel_intelligence": "deny",
            "military_intelligence": "deny",
            "export_data": "deny",
            "write_reports": "deny"
        },
        "USER": {
            "run_llm_research": "ask",
            "export_data": "ask"
        },
        "INSTITUTIONAL": {
            "run_llm_research": "allow",
            "vessel_intelligence": "allow",
            "military_intelligence": "allow",
            "export_data": "allow"
        }
    }

    def __init__(self):
        self.session_permissions: Dict[str, Dict[str, str]] = {}

    def get_ruleset_for_tier(self, tier: str) -> Dict[str, str]:
        rules = self.DEFAULT_RULES.copy()
        overrides = self.TIER_OVERRIDES.get(tier.upper(), {})
        rules.update(overrides)
        return rules

    def check_permission(self, agent_id: str, tool_id: str, session_id: Optional[str] = None) -> str:
        """
        Check if an agent has permission to use a tool.
        Returns: "allow" | "ask" | "deny"
        """
        # Load session specific permissions if available
        ruleset = self.DEFAULT_RULES
        if session_id and session_id in self.session_permissions:
            ruleset = self.session_permissions[session_id]
        
        # Check tool specific permission
        permission = ruleset.get(tool_id, "ask") # Default to ask if tool not in ruleset
        
        logger.info(f"Permission check: agent={agent_id}, tool={tool_id}, result={permission}")
        return permission

    def inject_permission_to_session(self, session_id: str, ruleset: Dict[str, str]):
        self.session_permissions[session_id] = ruleset

# Global instance
permission_service = PermissionService()
