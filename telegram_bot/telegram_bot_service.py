import os
import time
import requests
import logging
import sys
import threading
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram_bot.handlers import BotHandlers

# Load environment variables
load_dotenv()

# Professional Logging Configuration
logging.basicConfig(
    format='[%(asctime)s] %(levelname)s [%(name)s] %(message)s', 
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("MahameruBot")

class DirectTelegramBot:
    def __init__(self, token):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.offset = 0
        self.bot_username = self._get_me()
        self.allowed_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if self.allowed_chat_id:
            logger.info(f"🛡️ SECURITY: Locked to Chat ID: {self.allowed_chat_id}")
        else:
            logger.warning("🔓 SECURITY: No TELEGRAM_CHAT_ID set. Bot is in OPEN mode.")

    def _get_me(self):
        """Fetch bot identity from Telegram."""
        try:
            resp = requests.get(f"{self.base_url}/getMe", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                username = data.get("result", {}).get("username")
                logger.info(f"✅ Bot Active: @{username}")
                return username
        except Exception as e:
            logger.error(f"Failed to fetch bot info: {e}")
        return None

    def get_updates(self):
        url = f"{self.base_url}/getUpdates"
        params = {"offset": self.offset, "timeout": 20}
        try:
            resp = requests.get(url, params=params, timeout=25)
            if resp.status_code == 200:
                return resp.json().get("result", [])
            elif resp.status_code == 409:
                logger.error("Conflict: Another bot instance might be running.")
        except Exception as e:
            logger.error(f"Update error: {e}")
        return []

    def handle_message(self, message):
        """Core message processing logic."""
        try:
            chat_id = message["chat"]["id"]
            chat_type = message["chat"]["type"]
            message_id = message["message_id"]
            # 0. DETECT GROUP JOIN (WELCOME MESSAGE)
            if "new_chat_members" in message:
                for member in message["new_chat_members"]:
                    if member.get("username") == self.bot_username:
                        logger.info(f"✨ Bot joined new group: {chat_id}")
                        welcome_text = (
                            "👋 *Greetings, Mahameru Terminal Intelligence is Online!*\n\n"
                            "Saya telah berhasil terintegrasi dengan grup ini. Saya siap menyajikan data pasar, "
                            "analisis AI, dan intelijen pasar terbaru.\n\n"
                            "📌 *Cara Menggunakan:* Tag saya dan masukkan perintah.\n"
                            "Contoh: `@mahameruTerminal_bot /update TSLA`\n\n"
                            "Ketik `/start` untuk melihat daftar lengkap perintah."
                        )
                        BotHandlers._send_message(self.token, chat_id, welcome_text)
                        return

            # Jika bukan pesan teks (dan bukan join member), abaikan
            text = message.get("text", "")
            if not text: return

            # 1. SPECIAL COMMAND: /get_id (Always Allowed)
            if text.strip().startswith("/get_id"):
                BotHandlers.get_id(self.token, chat_id, message_id)
                return

            # 2. SECURITY CHECK
            if self.allowed_chat_id and str(chat_id) != str(self.allowed_chat_id):
                # Optional: Send a temp message if unauthorized
                # BotHandlers._send_temp_message(self.token, chat_id, "🚫 *Unauthorized Access*", delay=3)
                logger.warning(f"Rejected access from Chat ID: {chat_id}")
                return

            # 3. TAG & MENTION HANDLING (MANDATORY FOR GROUPS)
            is_mentioned = False
            bot_tag = f"@{self.bot_username}".lower() if self.bot_username else ""
            
            if chat_type in ["group", "supergroup"]:
                # Wajib ada mention @botname di dalam teks
                if bot_tag and bot_tag in text.lower():
                    is_mentioned = True
                    # Bersihkan tag agar tidak mengganggu argumen perintah
                    import re
                    text = re.compile(re.escape(bot_tag), re.IGNORECASE).sub("", text).strip()
                else:
                    # Abaikan jika tidak di-tag di grup
                    return
            else:
                # Di Private Chat (DM), tidak perlu tag
                is_mentioned = True

            # 4. COMMAND DISPATCHER
            parts = text.split()
            if not parts: return
            
            command = parts[0].lower()
            # Handle /update@botname style
            if "@" in command:
                command = command.split("@")[0]
                
            args = parts[1:]

            logger.info(f"Command: {command} | Args: {args} | From: {chat_id}")

            if command == "/start":
                BotHandlers.start(self.token, chat_id, message_id, message)
            elif command == "/update":
                BotHandlers.update_entity(self.token, chat_id, message_id, args)
            elif command == "/analyze":
                BotHandlers.analyze(self.token, chat_id, message_id, args)
            elif command == "/market_pulse":
                BotHandlers.market_pulse(self.token, chat_id, message_id)

        except Exception as e:
            logger.error(f"Handling Error: {e}")
            # If possible, notify user of a critical internal error
            try:
                BotHandlers._send_temp_message(self.token, chat_id, "🔥 *Internal Bot Error:* Check server logs.", delay=5)
            except: pass

    def run(self):
        logger.info("🚀 MAHAMERU INTELLIGENCE SYSTEM IS ONLINE")
        while True:
            try:
                updates = self.get_updates()
                for update in updates:
                    self.offset = update["update_id"] + 1
                    msg = update.get("message") or update.get("edited_message")
                    if msg:
                        # Process in a separate thread if you want higher concurrency, 
                        # but for simple bot, serial is safer for state.
                        self.handle_message(msg)
                time.sleep(0.3)
            except KeyboardInterrupt:
                logger.info("Shutting down...")
                break
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                time.sleep(5) # Cooldown before retry

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or "YOUR_TELEGRAM_BOT_TOKEN_HERE" in token:
        print("CRITICAL: TELEGRAM_BOT_TOKEN not set!")
        return

    bot = DirectTelegramBot(token)
    bot.run()

if __name__ == '__main__':
    main()
