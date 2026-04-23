import os
import time
import threading
import requests
import logging
from .analyzer import PriceAnalyzer
from .formatter import PriceFormatter
from .sentiment import SentimentAnalyzer

logger = logging.getLogger("PriceIntel.Bot")

class PriceIntelligenceBot:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        self.offset = 0
        self.running = False
        self.sentiment_analyzer = SentimentAnalyzer()

    def get_updates(self):
        try:
            url = f"{self.api_url}/getUpdates?offset={self.offset}&timeout=30"
            resp = requests.get(url, timeout=35)
            if resp.status_code == 200:
                return resp.json().get("result", [])
        except Exception as e:
            logger.error(f"Error getting updates: {e}")
        return []

    def send_report(self, symbol: str, target_chat_id: str):
        logger.info(f"Generating report for {symbol} to chat {target_chat_id}...")
        result = PriceAnalyzer.perform_analysis(symbol)
        if result is None:
            self.send_message(target_chat_id, f"❌ Symbol <b>{symbol}</b> not found or no data available.")
            return
        
        df = result["df"]
        info = result["info"]
        company_name = info["name"]
        country = info["country"]

        news = PriceFormatter.get_news(symbol, company_name, country)
        caption = PriceFormatter.format_caption(df, symbol, company_name, country, news)
        chart_buf = PriceFormatter.create_chart(df, symbol)
        
        url = f"{self.api_url}/sendPhoto"
        files = {'photo': ('report.png', chart_buf, 'image/png')}
        payload = {
            'chat_id': target_chat_id, 
            'caption': caption, 
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }
        
        try:
            resp = requests.post(url, files=files, data=payload)
            if resp.status_code == 200:
                logger.info(f"✅ Report for {symbol} sent.")
            else:
                logger.error(f"❌ Telegram send failed: {resp.text}")
        except Exception as e:
            logger.error(f"❌ Error sending to Telegram: {e}")

    def send_sentiment_report(self, symbol: str, target_chat_id: str):
        logger.info(f"Generating sentiment report for {symbol} to chat {target_chat_id}...")
        result = PriceAnalyzer.perform_analysis(symbol)
        if result is None:
            self.send_message(target_chat_id, f"❌ Symbol <b>{symbol}</b> not found or no data available.")
            return
        
        df = result["df"]
        info = result["info"]
        company_name = info["name"]
        country = info["country"]

        news = PriceFormatter.get_news(symbol, company_name, country, count=6)
        dist = self.sentiment_analyzer.analyze_news_batch(news)
        caption = PriceFormatter.format_sentiment_report(symbol, company_name, country, dist, news)
        
        url = f"{self.api_url}/sendMessage"
        payload = {
            'chat_id': target_chat_id, 
            'text': caption, 
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }
        
        try:
            resp = requests.post(url, data=payload)
            if resp.status_code == 200:
                logger.info(f"✅ Sentiment report for {symbol} sent.")
            else:
                logger.error(f"❌ Telegram send failed: {resp.text}")
        except Exception as e:
            logger.error(f"❌ Error sending to Telegram: {e}")

    def send_message(self, target_chat_id: str, text: str):
        url = f"{self.api_url}/sendMessage"
        payload = {
            'chat_id': target_chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }
        requests.post(url, data=payload)

    def handle_message(self, update):
        message = update.get("message")
        if not message: return
        
        text = message.get("text", "")
        chat_id = message.get("chat", {}).get("id")
        
        # Check for command /mt_market_update
        # Support /mt_market_update and /mt_market_update@botname
        cmd = text.split()[0].split('@')[0] if text else ""
        
        if cmd == "/mt_market_update":
            parts = text.split()
            if len(parts) > 1:
                symbol = parts[1].upper()
                self.send_report(symbol, chat_id)
            else:
                self.send_message(chat_id, "ℹ️ Usage: <code>/mt_market_update [SYMBOL]</code>\nExample: <code>/mt_market_update AAPL</code>")
        
        elif cmd == "/mt_sentinews":
            parts = text.split()
            if len(parts) > 1:
                symbol = parts[1].upper()
                self.send_sentiment_report(symbol, chat_id)
            else:
                self.send_message(chat_id, "ℹ️ Usage: <code>/mt_sentinews [SYMBOL]</code>\nExample: <code>/mt_sentinews AAPL</code>")
        
        # Check if bot is tagged (assuming bot name is known, or just check for @botname)
        # For simplicity, we just look for the command since Telegram handles command routing
        # if the bot is in the group and privacy mode allows it.

    def start_polling(self):
        self.running = True
        logger.info("Bot polling started...")
        while self.running:
            updates = self.get_updates()
            for update in updates:
                self.offset = update["update_id"] + 1
                self.handle_message(update)
            time.sleep(1)

    def start_in_thread(self):
        thread = threading.Thread(target=self.start_polling, daemon=True)
        thread.start()
        return thread
