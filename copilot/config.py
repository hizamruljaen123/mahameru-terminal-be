"""
============================================================================
  Copilot Configuration — Environment, Constants, Logging
============================================================================
"""

import os
import logging
import subprocess
import time
from dotenv import load_dotenv

load_dotenv()

DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# --- LLM Provider Configuration ---
LLM_PROVIDER = os.getenv("COPILOT_LLM_PROVIDER", "deepseek").lower()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DIT_API_KEY = os.getenv("DIT_API_KEY", "")
DIT_API_URL = "https://api.dit.ai"

if LLM_PROVIDER == "dit":
    LLM_API_KEY = os.getenv("COPILOT_LLM_API_KEY") or DIT_API_KEY
    LLM_BASE_URL = os.getenv("COPILOT_LLM_BASE_URL") or f"{DIT_API_URL}/v1"
    LLM_MODEL = os.getenv("COPILOT_LLM_MODEL", "gpt-5.4-mini")
elif LLM_PROVIDER == "deepseek":
    LLM_API_KEY = os.getenv("COPILOT_LLM_API_KEY") or DEEPSEEK_API_KEY
    LLM_BASE_URL = os.getenv("COPILOT_LLM_BASE_URL") or "https://api.deepseek.com/v1"
    LLM_MODEL = os.getenv("COPILOT_LLM_MODEL", "deepseek-chat")
else:
    LLM_API_KEY = os.getenv("COPILOT_LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
    LLM_BASE_URL = os.getenv("COPILOT_LLM_BASE_URL") or "https://api.openai.com/v1"
    LLM_MODEL = os.getenv("COPILOT_LLM_MODEL", "gpt-4o")

LLM_MAX_TOKENS = int(os.getenv("COPILOT_MAX_TOKENS", "4096"))
API_BASE = os.getenv("COPILOT_API_BASE", "https://api.asetpedia.online")
ENABLE_STREAMING = os.getenv("COPILOT_ENABLE_STREAMING", "true").lower() == "true"
ENABLE_LLM = os.getenv("COPILOT_ENABLE_LLM", "true").lower() == "true"

LOCAL_DEV = os.getenv("LOCAL_DEV", "false").lower() == "true"
if LOCAL_DEV:
    print("[LOCAL DEV] Routing TA service to http://127.0.0.1:5007")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("copilot_gateway")

# Port
COPILOT_PORT = int(os.getenv("COPILOT_PORT", "8500"))


# ===========================================================================
# PORT CLEANUP
# ===========================================================================

def clean_port(port: int):
    """Detect and kill any existing process listening on `port` (Windows)."""
    try:
        cmd = f'netstat -ano | findstr LISTENING | findstr :{port}'
        output = subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout
        pids = set()
        for line in output.splitlines():
            parts = line.strip().split()
            if len(parts) >= 5 and parts[-1] != '0':
                pids.add(parts[-1])
        for pid in pids:
            logger.info(f"[PORT] Port {port} in use by PID {pid} — killing...")
            subprocess.run(f'taskkill /F /PID {pid}', shell=True, capture_output=True)
            time.sleep(1.0)
        if pids:
            logger.info(f"[PORT] Port {port} freed (killed {len(pids)} process(es))")
    except Exception as e:
        logger.warning(f"[PORT] Error cleaning port {port}: {e}")
