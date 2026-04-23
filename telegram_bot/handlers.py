import requests
import os
from .api_client import AsetpediaAPI
from .visualizer import MarketVisualizer
from .utils import format_ohlcv_table, format_news, format_fundamental

class BotHandlers:
    @staticmethod
    def _send_message(token, chat_id, text, reply_to_id=None, parse_mode="Markdown", disable_preview=False):
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_preview
        }
        if reply_to_id:
            payload["reply_to_message_id"] = reply_to_id
            
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                return resp.json().get("result", {}).get("message_id")
        except Exception as e:
            print(f"Error sending message: {e}")
        return None

    @staticmethod
    def _delete_message(token, chat_id, message_id):
        if not message_id: return
        url = f"https://api.telegram.org/bot{token}/deleteMessage"
        payload = {"chat_id": chat_id, "message_id": message_id}
        try:
            requests.post(url, json=payload, timeout=5)
        except:
            pass

    @staticmethod
    def _send_photo(token, chat_id, photo_path, reply_to_id=None, caption=""):
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        try:
            with open(photo_path, 'rb') as photo:
                files = {'photo': photo}
                data = {'chat_id': chat_id, 'caption': caption}
                if reply_to_id:
                    data["reply_to_message_id"] = reply_to_id
                requests.post(url, data=data, files=files, timeout=20)
        except Exception as e:
            print(f"Error sending photo: {e}")

    @staticmethod
    def start(token, chat_id, message_id, message):
        user_name = message["from"].get("first_name", "User")
        BotHandlers._send_message(token, chat_id, f"Halo *{user_name}*! Welcome to Asetpedia Intelligence Bot.", reply_to_id=message_id)

    @staticmethod
    def update_entity(token, chat_id, message_id, args):
        if not args:
            BotHandlers._send_message(token, chat_id, "Please provide a symbol. Example: /update AAPL", reply_to_id=message_id)
            return

        symbol = args[0].upper()
        
        # --- PHASE 1: LOADING DATA ---
        status_id = BotHandlers._send_message(token, chat_id, "⏳ `Loading data pasar...`", reply_to_id=message_id)
        
        history_res = AsetpediaAPI.get_market_history(symbol)
        BotHandlers._delete_message(token, chat_id, status_id)
        
        if history_res.get("status") != "success":
            BotHandlers._send_message(token, chat_id, f"❌ Error: {history_res.get('message')}", reply_to_id=message_id)
            return

        history = history_res.get("history", [])
        
        # --- PHASE 2: PREPARING CHART ---
        status_id = BotHandlers._send_message(token, chat_id, "📈 `Menyiapkan grafik...`", reply_to_id=message_id)
        chart_path = MarketVisualizer.generate_ohlc_chart(symbol, history)
        BotHandlers._delete_message(token, chat_id, status_id)

        if chart_path:
            BotHandlers._send_photo(token, chat_id, chart_path, caption=f"📊 Intraday Chart: {symbol}", reply_to_id=message_id)
            MarketVisualizer.cleanup(chart_path)

        # --- PHASE 3: FETCHING NEWS ---
        status_id = BotHandlers._send_message(token, chat_id, "📰 `Mengumpulkan berita...`", reply_to_id=message_id)
        
        is_crypto = "-USD" in symbol or len(symbol) <= 5
        news = []
        if is_crypto:
            crypto_res = AsetpediaAPI.get_crypto_detail(symbol.replace("-USD", ""))
            if crypto_res.get("status") == "success":
                news = crypto_res.get("data", {}).get("news", [])
        
        BotHandlers._delete_message(token, chat_id, status_id)

        # --- PHASE 4: ASSEMBLING REPORT ---
        status_id = BotHandlers._send_message(token, chat_id, "📄 `Menyusun laporan...`", reply_to_id=message_id)
        
        table_text = format_ohlcv_table(history, limit=20)
        BotHandlers._send_message(token, chat_id, f"📋 *Last 20 OHLCV Data:*\n{table_text}", reply_to_id=message_id)

        news_text = format_news(news, limit=5)
        BotHandlers._send_message(token, chat_id, f"📰 *Latest Intelligence Headlines:*\n\n{news_text}", reply_to_id=message_id, disable_preview=True)
        
        BotHandlers._delete_message(token, chat_id, status_id)

    @staticmethod
    def analyze(token, chat_id, message_id, args):
        if not args:
            BotHandlers._send_message(token, chat_id, "Please provide a symbol. Example: /analyze BTC", reply_to_id=message_id)
            return
            
        symbol = args[0].upper()
        status_id = BotHandlers._send_message(token, chat_id, f"🤖 `AI sedang menganalisis {symbol}...`", reply_to_id=message_id)
        
        res = AsetpediaAPI.get_ai_analyze(symbol)
        BotHandlers._delete_message(token, chat_id, status_id)
        
        if res.get("status") == "success":
            verdict = res.get("data", "No analysis available.")
            BotHandlers._send_message(token, chat_id, f"🔮 *AI Technical Verdict for {symbol}:*\n\n{verdict}", reply_to_id=message_id)
        else:
            BotHandlers._send_message(token, chat_id, f"❌ AI Analysis failed.", reply_to_id=message_id)

    @staticmethod
    def market_pulse(token, chat_id, message_id):
        status_id = BotHandlers._send_message(token, chat_id, "🌐 `Mengkalkulasi denyut pasar...`", reply_to_id=message_id)
        res = AsetpediaAPI.get_market_watchlist()
        BotHandlers._delete_message(token, chat_id, status_id)
        
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
            
            BotHandlers._send_message(token, chat_id, "\n".join(summary), reply_to_id=message_id)

    @staticmethod
    def get_id(token, chat_id, message_id):
        """Returns the current chat/group ID."""
        msg = f"🆔 *Chat Intelligence Info*\n\nThis Chat ID: `{chat_id}`"
        BotHandlers._send_message(token, chat_id, msg, reply_to_id=message_id)
