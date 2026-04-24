"""
bot_helpers.py
─────────────────────────────────────────────
Shared utilities for all Telegram bot modules:
- send_message / send_typed
- broadcast_alert (used by push modules)
- Port registry for Mahameru services
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_message(chat_id, text, parse_mode="HTML"):
    """Send a Telegram message to a specific chat."""
    if not TELEGRAM_TOKEN:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=8
        )
    except Exception as e:
        print(f"[Bot] send_message error: {e}")

# ─── Port Map for Mahameru Backend Services ───────────────────────────────────
MAHAMERU_PORTS = {
    "crypto":       8085,
    "crypto_stream":8092,
    "ta":           5007,
    "deep_ta":      5200,
    "news":         5101,   # Node 1 (others: 5102-5105)
    "sentiment":    5008,
    "entity":       5005,
    "forex":        8086,
    "commodity":    8087,
    "market":       8088,
    "ais":          8080,
    "oil_refinery": 8089,
    "oil_trade":    8090,
    "port":         8098,
    "mines":        8082,
    "disaster":     8095,
    "geo":          8091,
    "conflict":     8140,
    "military":     8160,
    "gov_facility": 8150,
    "vessel":       8100,
    "datacenter":   8110,
    "infrastructure":8097,
    "dashboard":    8000,
}

def _api(service: str, path: str = ""):
    port = MAHAMERU_PORTS.get(service, 8000)
    return f"http://localhost:{port}{path}"

def broadcast_alert(text, parse_mode="HTML"):
    """Broadcast an auto-alert to the configured TELEGRAM_CHAT_ID."""
    if not TELEGRAM_CHAT_ID:
        return
    send_message(TELEGRAM_CHAT_ID, text, parse_mode)

def safe_get(url, timeout=8):
    """HTTP GET with error handling. Returns dict or None."""
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"[Bot] safe_get error {url}: {e}")
    return None

def fmt_number(n):
    """Format big numbers nicely."""
    if n is None:
        return "N/A"
    if abs(n) >= 1_000_000_000:
        return f"{n/1_000_000_000:.2f}B"
    if abs(n) >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"{n/1_000:.1f}K"
    return f"{n:.4f}"
