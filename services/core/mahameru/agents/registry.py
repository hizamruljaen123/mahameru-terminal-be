import os
import json
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class AgentRegistry:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.agents: Dict[str, Dict[str, Any]] = {}
        self._load_agents()

    def _load_agents(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    self.agents = json.load(f)
                logger.info(f"Loaded {len(self.agents)} agents from {self.config_path}")
            except Exception as e:
                logger.error(f"Failed to load agents config: {e}")
                self.agents = {}
        else:
            logger.warning(f"Config file {self.config_path} not found. Starting with empty registry.")
            self.agents = {}

    def _save_agents(self):
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(self.agents, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save agents config: {e}")

    def register_agent(self, agent_id: str, config: Dict[str, Any]):
        """
        Register or update an agent configuration.
        Expected config structure:
        - identifier (string, lowercase, hyphens)
        - mode: "primary" | "subagent" | "hidden"
        - model (optional)
        - temperature (optional)
        - steps (maximum execution steps)
        - permission (ruleset access tool)
        - system_prompt (custom prompt)
        """
        agent_id = agent_id.lower().replace(" ", "-")
        config["identifier"] = agent_id
        self.agents[agent_id] = config
        self._save_agents()
        return agent_id

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        return self.agents.get(agent_id)

    def list_agents(self) -> List[Dict[str, Any]]:
        return list(self.agents.values())

# Global instance
CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
AGENT_CONFIG_PATH = os.path.join(CONFIG_DIR, "agents.json")
agent_registry = AgentRegistry(AGENT_CONFIG_PATH)
