from .registry import agent_registry

def get_data_agent_config():
    return agent_registry.get_agent("data-agent")

class DataAgent:
    def __init__(self):
        self.config = get_data_agent_config()
        self.system_prompt = self.config.get("system_prompt")

    async def execute(self, tool_requests):
        # Implementation of data aggregation from microservices
        pass
        
    def check_write_permission(self, tool_id):
        # All write tools are denied by default for data agent
        return "deny"
