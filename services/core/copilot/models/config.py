"""
Centralized model definitions for Mahameru Copilot.
Includes labels, icons, providers, and descriptions.
"""

AVAILABLE_MODELS = [
    {
        "value": "deepseek-v4-flash",
        "label": "DeepSeek V4 Flash (Fastest)",
        "provider": "DeepInfra",
        "description": "Ultra-low latency, optimized for real-time chat",
        "icon": "⚡"
    },
    {
        "value": "deepseek-v4-reasoner",
        "label": "DeepSeek V4 Reasoner (R1)",
        "provider": "DeepInfra",
        "description": "Advanced reasoning with full thought tracing",
        "icon": "🧠"
    },
    {
        "value": "gemini-2.0-flash-exp",
        "label": "Gemini 2.0 Flash (Agentic)",
        "provider": "Gemini",
        "description": "Google's next-gen multimodal flagship",
        "icon": "💎"
    },
    {
        "value": "gemini-2.0-flash-thinking-exp",
        "label": "Gemini 2.0 Thinking (Experimental)",
        "provider": "Gemini",
        "description": "Enhanced reasoning with experimental pipeline",
        "icon": "🔮"
    },
    {
        "value": "openai/gpt-oss-20b",
        "label": "GPT OSS 20B (Free)",
        "provider": "OpenRouter",
        "description": "Low-latency agentic capabilities",
        "icon": "⚡"
    },
    {
        "value": "google/gemma-3-27b-it",
        "label": "Gemma 3 27B (Free)",
        "provider": "OpenRouter",
        "description": "Multimodal vision & text outputs",
        "icon": "🔮"
    },
    {
        "value": "google/gemma-3-12b-it",
        "label": "Gemma 3 12B (Free)",
        "provider": "OpenRouter",
        "description": "Balanced multimodal performance",
        "icon": "💎"
    },
    {
        "value": "meta-llama/llama-3.3-70b-instruct",
        "label": "Llama 3.3 70B (Free)",
        "provider": "OpenRouter",
        "description": "Multilingual dialogue & reasoning",
        "icon": "🦙"
    },
    {
        "value": "meta-llama/llama-3.2-3b-instruct",
        "label": "Llama 3.2 3B (Free)",
        "provider": "OpenRouter",
        "description": "Efficient multilingual dialogue",
        "icon": "🐑"
    },
    {
        "value": "nvidia/nemotron-3-super",
        "label": "Nemotron 3 Super (Free)",
        "provider": "OpenRouter",
        "description": "NVIDIA 120B MoE — High efficiency",
        "icon": "🟢"
    },
    {
        "value": "nvidia/nemotron-3-nano-omni",
        "label": "Nemotron 3 Nano Omni (Free)",
        "provider": "OpenRouter",
        "description": "Multimodal perception sub-agent",
        "icon": "👁️"
    },
    {
        "value": "nvidia/nemotron-3-nano-30b-a3b",
        "label": "Nemotron 3 Nano 30B (Free)",
        "provider": "OpenRouter",
        "description": "Specialized small language MoE model",
        "icon": "🧪"
    },
    {
        "value": "nvidia/nemotron-nano-12b-2-vl",
        "label": "Nemotron Nano 12B VL (Free)",
        "provider": "OpenRouter",
        "description": "Video & document intelligence",
        "icon": "📽️"
    },
    {
        "value": "nvidia/nemotron-nano-9b-v2",
        "label": "Nemotron Nano 9B V2 (Free)",
        "provider": "OpenRouter",
        "description": "Unified reasoning trace model",
        "icon": "🧬"
    },
    {
        "value": "qwen/qwen3-coder-480b-a35b-instruct",
        "label": "Qwen 3 Coder (Free)",
        "provider": "OpenRouter",
        "description": "Optimized for agentic coding tasks",
        "icon": "💻"
    },
    {
        "value": "qwen/qwen3-next-80b-a35b-instruct",
        "label": "Qwen 3 Next 80B (Free)",
        "provider": "OpenRouter",
        "description": "Fast, stable responses for RAG",
        "icon": "🚀"
    },
    {
        "value": "z-ai/glm-4.5-air",
        "label": "GLM 4.5 Air (Free)",
        "provider": "OpenRouter",
        "description": "Lightweight agent-centric variant",
        "icon": "🌪️"
    },
    {
        "value": "nousresearch/hermes-3-405b",
        "label": "Hermes 3 405B (Free)",
        "provider": "OpenRouter",
        "description": "Frontier-level steerable model",
        "icon": "🎭"
    }
]
