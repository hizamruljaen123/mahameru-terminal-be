from .registry import agent_registry

def get_analyst_agent_config():
    return agent_registry.get_agent("analyst-agent")

class AnalystAgent:
    def __init__(self):
        self.config = get_analyst_agent_config()
        self.system_prompt = self.config.get("system_prompt")

    async def execute(self, datasets):
        # Implementation of quantitative analysis (TA, risk, etc.)
        pass
