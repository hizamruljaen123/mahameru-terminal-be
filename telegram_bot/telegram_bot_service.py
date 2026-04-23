import os
import time
import requests
import logging
import sys
from dotenv import load_dotenv

# Add project root to sys.path to allow 'telegram_bot' package imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram_bot.handlers import BotHandlers

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='[TELEGRAM_BOT] %(asctime)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger("telegram_bot")

class DirectTelegramBot:
    def __init__(self, token):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.offset = 0
        self.bot_username = self._get_me()
        self.allowed_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if self.allowed_chat_id and "YOUR_CHAT_ID_HERE" not in self.allowed_chat_id:
            print(f"SECURITY: Bot restricted to Chat ID: {self.allowed_chat_id}")
        else:
            print("SECURITY WARNING: No TELEGRAM_CHAT_ID set. Bot will respond to everyone to allow /get_id.")
            self.allowed_chat_id = None

    def _get_me(self):
        """Get bot info to know its username for mentions."""
        try:
            resp = requests.get(f"{self.base_url}/getMe", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                username = data.get("result", {}).get("username")
                print(f"BOT_INFO: @{username} is active.")
                return username
        except Exception as e:
            logger.error(f"Error getting bot info: {e}")
        return None

    def get_updates(self):
        url = f"{self.base_url}/getUpdates"
        params = {"offset": self.offset, "timeout": 30}
        try:
            resp = requests.get(url, params=params, timeout=35)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("result", [])
        except Exception as e:
            logger.error(f"Error getting updates: {e}")
        return []

    def handle_message(self, message):
        chat_id = message["chat"]["id"]
        chat_type = message["chat"]["type"]
        message_id = message["message_id"]
        text = message.get("text", "")
        
        if not text:
            return

        # --- SECURITY CHECK: RESTRICT TO ALLOWED CHAT ID ---
        # Special case for /get_id (always allowed)
        if text.strip().startswith("/get_id"):
            BotHandlers.get_id(self.token, chat_id, message_id)
            return

        if self.allowed_chat_id:
            if str(chat_id) != str(self.allowed_chat_id):
                return

        # --- TAG CHECK: MUST MENTION BOT IN GROUPS ---
        is_mentioned = False
        bot_tag = f"@{self.bot_username}".lower() if self.bot_username else ""
        
        if chat_type in ["group", "supergroup"]:
            # Check if bot username is mentioned in text (case insensitive)
            if bot_tag and bot_tag in text.lower():
                is_mentioned = True
                # Remove tag from text for cleaner command parsing
                # Use a case-insensitive replace
                import re
                text = re.compile(re.escape(bot_tag), re.IGNORECASE).sub("", text).strip()
        else:
            # Private chat: always respond
            is_mentioned = True

        if not is_mentioned:
            return

        # Command dispatcher
        parts = text.split()
        if not parts: return
        
        command = parts[0].lower()
        args = parts[1:]

        # Handle commands that might still have @bot attached (e.g. /update@bot)
        if "@" in command:
            command = command.split("@")[0]

        if command == "/start":
            BotHandlers.start(self.token, chat_id, message_id, message)
        elif command == "/update":
            BotHandlers.update_entity(self.token, chat_id, message_id, args)
        elif command == "/analyze":
            BotHandlers.analyze(self.token, chat_id, message_id, args)
        elif command == "/market_pulse":
            BotHandlers.market_pulse(self.token, chat_id, message_id)

    def run(self):
        print("=:: ASETPEDIA INTELLIGENCE BOT (RESTRICTED MODE) IS ONLINE ::= ")
        while True:
            updates = self.get_updates()
            for update in updates:
                self.offset = update["update_id"] + 1
                
                # Check both new messages and edited messages
                msg = update.get("message") or update.get("edited_message")
                if msg:
                    self.handle_message(msg)
            time.sleep(0.5)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Asetpedia Telegram Bot Service")
    parser.add_argument("--port", type=int, help="Dummy port for launcher consistency")
    args = parser.parse_args()
    
    if args.port:
        logger.info(f"Service initialized with virtual port control: {args.port}")

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or "YOUR_TELEGRAM_BOT_TOKEN_HERE" in token:
        print("CRITICAL ERROR: TELEGRAM_BOT_TOKEN not configured correctly in .env")
        return

    bot = DirectTelegramBot(token)
    bot.run()

if __name__ == '__main__':
    main()
