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

import threading
import time

def delete_message(chat_id, message_id, token):
    """Helper to delete a message after a delay."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/deleteMessage",
            json={"chat_id": chat_id, "message_id": message_id},
            timeout=5
        )
    except: pass

def send_message(chat_id, text, parse_mode="HTML", auto_delete_seconds=None):
    """Send a Telegram message, optionally scheduling it for deletion."""
    if not TELEGRAM_TOKEN:
        return None
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=8
        )
        if resp.status_code == 200:
            msg_data = resp.json().get("result", {})
            msg_id = msg_data.get("message_id")
            
            if auto_delete_seconds and msg_id:
                threading.Timer(auto_delete_seconds, delete_message, [chat_id, msg_id, TELEGRAM_TOKEN]).start()
            
            return msg_id
    except Exception as e:
        print(f"[Bot] send_message error: {e}")
    return None

# ─── Path Map for Mahameru Backend Services ───────────────────────────────────
MAHAMERU_PATHS = {
    "crypto":       "/crypto",
    "crypto_stream":"/ws/crypto",
    "ta":           "/ta",
    "deep_ta":      "/deep-ta",
    "news":         "/news",
    "sentiment":    "/sentiment",
    "entity":       "/entity",
    "forex":        "/forex",
    "commodity":    "/commodity",
    "market":       "/market",
    "ais":          "/ais",
    "oil_refinery": "/refinery",
    "oil_trade":    "/oil-trade",
    "port":         "/port",
    "mines":        "/mines",
    "disaster":     "/disaster",
    "geo":          "/geo",
    "conflict":     "/conflict",
    "military":     "/military",
    "gov_facility": "/government",
    "vessel":       "/vessel",
    "datacenter":   "/datacenter",
    "infrastructure":"/infra",
    "dashboard":    "/dashboard",
}

def _api(service: str, path: str = ""):
    base_path = MAHAMERU_PATHS.get(service, f"/{service}")
    return f"https://api.asetpedia.online{base_path}{path}"

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
