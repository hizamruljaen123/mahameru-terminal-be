from .registry import agent_registry

def get_build_agent_config():
    return agent_registry.get_agent("build-agent")

# Logic for build agent will go here
class BuildAgent:
    def __init__(self):
        self.config = get_build_agent_config()
        self.system_prompt = self.config.get("system_prompt")
        
    async def execute(self, query):
        # Implementation of build agent execution
        pass
