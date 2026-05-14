from typing import Dict, Any, List

class ProviderTransformer:
    """
    Transforms payload (messages, tools, parameters) based on the LLM provider.
    Handles differences in Anthropic, OpenAI, Google Gemini, DeepSeek schemas.
    """
    
    @staticmethod
    def transform_payload(
        provider: str, 
        base_payload: Dict[str, Any], 
        agent_type: str = "general"
    ) -> Dict[str, Any]:
        """
        Transforms a standard OpenAI-like payload for specific providers.
        Also optimizes parameters (temperature) based on the agent type / use case.
        """
        payload = base_payload.copy()
        
        # Optimize temperature based on use case / agent type
        if agent_type in ["analyst-agent", "data-agent"]:
            payload["temperature"] = 0.1  # Analytical, precise
        elif agent_type in ["explore-agent", "build-agent"]:
            payload["temperature"] = 0.7  # Creative, broad
        elif agent_type == "plan-agent":
            payload["temperature"] = 0.3  # Structured
            
        provider = provider.lower() if provider else ""
        
        # Provider specific transformations
        if "anthropic" in provider:
            # Anthropic handles system messages differently, and expects top_k, top_p usually
            # Some gateways translate this automatically, but if direct to Anthropic:
            # - Extract system prompt to top-level "system" parameter
            messages = payload.get("messages", [])
            system_msg = None
            if messages and messages[0].get("role") == "system":
                system_msg = messages.pop(0)["content"]
                payload["system"] = system_msg
                payload["messages"] = messages
                
            payload["top_p"] = 0.95
            
        elif "google" in provider or "gemini" in provider:
            # Gemini typically ignores system role in older APIs but new APIs support it.
            # Set specific safety settings or specific top_p for Gemini
            payload["top_p"] = 0.8
            payload["top_k"] = 40
            
        elif "deepseek" in provider:
            # DeepSeek reasoner model does not support temperature > 0 in some APIs
            # or requires exact schema.
            if "reasoner" in str(payload.get("model", "")).lower():
                payload["temperature"] = 0.0 # Reasoner often forces 0
            payload["top_p"] = 0.9
            
        return payload
