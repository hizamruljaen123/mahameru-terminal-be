from .registry import agent_registry

def get_research_agent_config():
    return agent_registry.get_agent("research-agent")

class ResearchAgent:
    def __init__(self):
        self.config = get_research_agent_config()
        self.system_prompt = self.config.get("system_prompt")

    async def execute(self, query):
        # Implementation of research agent with multi-source chain prompting
        pass
