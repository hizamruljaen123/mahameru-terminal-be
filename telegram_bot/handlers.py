import requests
import os
from .api_client import AsetpediaAPI
from .visualizer import MarketVisualizer
from .utils import format_ohlcv_table, format_news, format_fundamental

class BotHandlers:
    @staticmethod
    def _send_message(token, chat_id, text, parse_mode="Markdown", disable_preview=False):
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_preview
        }
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"Error sending message: {e}")

    @staticmethod
    def _send_photo(token, chat_id, photo_path, caption=""):
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        try:
            with open(photo_path, 'rb') as photo:
                files = {'photo': photo}
                data = {'chat_id': chat_id, 'caption': caption}
                requests.post(url, data=data, files=files, timeout=20)
        except Exception as e:
            print(f"Error sending photo: {e}")

    @staticmethod
    def start(token, chat_id, message):
        user_name = message["from"].get("first_name", "User")
        BotHandlers._send_message(token, chat_id, f"Halo *{user_name}*! Welcome to Asetpedia Intelligence Bot.")

    @staticmethod
    def update_entity(token, chat_id, args):
        if not args:
            BotHandlers._send_message(token, chat_id, "Please provide a symbol. Example: /update AAPL")
            return

        symbol = args[0].upper()
        BotHandlers._send_message(token, chat_id, f"🔍 Fetching institutional intelligence for {symbol}...")

        # 1. Fetch History
        history_res = AsetpediaAPI.get_market_history(symbol)
        if history_res.get("status") != "success":
            BotHandlers._send_message(token, chat_id, f"❌ Error: {history_res.get('message')}")
            return

        history = history_res.get("history", [])
        
        # 2. Generate & Send Chart
        chart_path = MarketVisualizer.generate_ohlc_chart(symbol, history)
        if chart_path:
            BotHandlers._send_photo(token, chat_id, chart_path, caption=f"📊 Intraday Chart: {symbol}")
            MarketVisualizer.cleanup(chart_path)

        # 3. Table
        table_text = format_ohlcv_table(history, limit=20)
        BotHandlers._send_message(token, chat_id, f"📋 *Last 20 OHLCV Data:*\n{table_text}")

        # 4. News
        is_crypto = "-USD" in symbol or len(symbol) <= 5
        news = []
        if is_crypto:
            crypto_res = AsetpediaAPI.get_crypto_detail(symbol.replace("-USD", ""))
            if crypto_res.get("status") == "success":
                news = crypto_res.get("data", {}).get("news", [])
        
        news_text = format_news(news, limit=5)
        BotHandlers._send_message(token, chat_id, f"📰 *Latest Intelligence Headlines:*\n\n{news_text}", disable_preview=True)

    @staticmethod
    def analyze(token, chat_id, args):
        if not args:
            BotHandlers._send_message(token, chat_id, "Please provide a symbol. Example: /analyze BTC")
            return
            
        symbol = args[0].upper()
        BotHandlers._send_message(token, chat_id, f"🤖 Running AI Multi-Agent analysis for {symbol}...")
        
        res = AsetpediaAPI.get_ai_analyze(symbol)
        if res.get("status") == "success":
            verdict = res.get("data", "No analysis available.")
            BotHandlers._send_message(token, chat_id, f"🔮 *AI Technical Verdict for {symbol}:*\n\n{verdict}")
        else:
            BotHandlers._send_message(token, chat_id, f"❌ AI Analysis failed.")

    @staticmethod
    def market_pulse(token, chat_id):
        BotHandlers._send_message(token, chat_id, "🌐 Fetching global market pulse...")
        res = AsetpediaAPI.get_market_watchlist()
        if res.get("status") == "success":
            data = res.get("data", {})
            summary = []
            for cat, items in data.items():
                top = items[:3]
                summary.append(f"*{cat.upper()}*")
                for item in top:
                    change = item.get('change_pct', 0)
                    sign = "+" if change > 0 else ""
                    summary.append(f"• {item['name']}: {item['price']} ({sign}{change:.2f}%)")
            
            BotHandlers._send_message(token, chat_id, "\n".join(summary))
