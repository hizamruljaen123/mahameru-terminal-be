import os
import logging
from typing import Dict, Any, Optional
from copilot.models.definitions import AVAILABLE_MODELS, DEFAULT_MODEL_ID, MODEL_PROVIDERS

logger = logging.getLogger(__name__)

def get_model_config(model_id: str) -> Dict[str, Any]:
    """
    Retrieve configuration for a specific model ID.
    If model_id is not found, falls back to dynamic routing or default.
    """
    config = next((m for m in AVAILABLE_MODELS if m["id"] == model_id), None)
    
    if config:
        # Resolve API Key from Environment
        env_key = config.get("api_key_env")
        api_key = os.getenv(env_key) if env_key else None
        
        # Strip suffix for actual API call if present
        actual_model = config["id"].split(":")[0] if ":" in config["id"] else config["id"]
        
        return {
            "model": actual_model,
            "base_url": config["base_url"],
            "api_key": api_key,
            "provider": config["provider"],
            "is_openrouter": config["provider"] == MODEL_PROVIDERS["OPENROUTER"]
        }
    
    # --- FALLBACK: Dynamic Routing Logic (for OpenRouter or unregistered models) ---
    logger.info(f"[MODEL_MANAGER] Model '{model_id}' not in registry. Applying dynamic fallback.")
    
    # Default values
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    is_openrouter = False
    provider = "Unknown"
    actual_model = model_id.split(":")[0] if ":" in model_id else model_id

    if ":osiris" in model_id:
        api_key = os.getenv("OSIRIS_API_KEY")
        base_url = os.getenv("OSIRIS_BASE_URL", "https://osiris-code.com/api/v1")
        provider = MODEL_PROVIDERS["OSIRIS"]
    elif "/" in model_id or any(x in model_id for x in ["nvidia", "qwen", "meta", "hermes", "llama"]):
        api_key = os.getenv("OPENROUTER_API_KEY", api_key)
        base_url = "https://openrouter.ai/api/v1"
        is_openrouter = True
        provider = MODEL_PROVIDERS["OPENROUTER"]
    elif model_id.startswith("gemini"):
        api_key = os.getenv("GEMINI_API_KEY", api_key)
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
        provider = MODEL_PROVIDERS["GOOGLE"]
    elif model_id.startswith("gpt") or model_id.startswith("o1"):
        api_key = os.getenv("OPENAI_API_KEY", api_key)
        base_url = "https://api.openai.com/v1"
        provider = MODEL_PROVIDERS["OPENAI"]
    elif "deepseek" in model_id:
        api_key = os.getenv("DEEPSEEK_API_KEY", api_key)
        base_url = "https://api.deepseek.com/v1"
        provider = MODEL_PROVIDERS["DEEPSEEK"]
    
    return {
        "model": actual_model,
        "base_url": base_url,
        "api_key": api_key,
        "provider": provider,
        "is_openrouter": is_openrouter
    }

def get_available_models_list():
    """Return a clean list of models for API exposure."""
    return [{"id": m["id"], "name": m["name"], "provider": m["provider"]} for m in AVAILABLE_MODELS]
