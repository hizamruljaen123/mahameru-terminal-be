import os
import time
import requests
import logging
from dotenv import load_dotenv
from telegram_bot.handlers import BotHandlers

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

class DirectTelegramBot:
    def __init__(self, token):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.offset = 0

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
        text = message.get("text", "")
        chat_id = message["chat"]["id"]
        
        if not text:
            return

        # Simple command dispatcher
        parts = text.split()
        command = parts[0].lower()
        args = parts[1:]

        if command == "/start":
            BotHandlers.start(self.token, chat_id, message)
        elif command == "/update":
            BotHandlers.update_entity(self.token, chat_id, args)
        elif command == "/analyze":
            BotHandlers.analyze(self.token, chat_id, args)
        elif command == "/market_pulse":
            BotHandlers.market_pulse(self.token, chat_id)

    def run(self):
        print("=:: ASETPEDIA INTELLIGENCE BOT (DIRECT API) IS ONLINE ::= ")
        while True:
            updates = self.get_updates()
            for update in updates:
                self.offset = update["update_id"] + 1
                if "message" in update:
                    self.handle_message(update["message"])
            time.sleep(0.5)

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or "YOUR_TELEGRAM_BOT_TOKEN_HERE" in token:
        print("CRITICAL ERROR: TELEGRAM_BOT_TOKEN not configured correctly in .env")
        return

    bot = DirectTelegramBot(token)
    bot.run()

if __name__ == '__main__':
    main()
