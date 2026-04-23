import requests
import os
import threading
import time
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
            else:
                print(f"Telegram API Error: {resp.text}")
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
    def _send_temp_message(token, chat_id, text, delay=5, reply_to_id=None):
        """Sends a message and schedules its deletion after 'delay' seconds."""
        msg_id = BotHandlers._send_message(token, chat_id, text, reply_to_id)
        if msg_id:
            # Menggunakan threading agar bot tidak block (tidak macet)
            threading.Timer(delay, BotHandlers._delete_message, args=[token, chat_id, msg_id]).start()
        return msg_id

    @staticmethod
    def _send_photo(token, chat_id, photo_path, reply_to_id=None, caption=""):
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        try:
            with open(photo_path, 'rb') as photo:
                files = {'photo': photo}
                data = {'chat_id': chat_id, 'caption': caption}
                if reply_to_id:
                    data["reply_to_message_id"] = reply_to_id
                resp = requests.post(url, data=data, files=files, timeout=25)
                return resp.status_code == 200
        except Exception as e:
            print(f"Error sending photo: {e}")
        return False

    @staticmethod
    def start(token, chat_id, message_id, message):
        user_name = message["from"].get("first_name", "User")
        welcome = (
            f"👋 Halo *{user_name}*!\n\n"
            "Saya adalah *Mahameru Intelligence Bot*.\n"
            "Gunakan perintah berikut:\n"
            "• `/update SYMBOL` - Data pasar & berita terbaru\n"
            "• `/analyze SYMBOL` - Analisis AI Teknikal\n"
            "• `/market_pulse` - Ringkasan kondisi pasar\n"
            "• `/get_id` - Cek ID Chat ini"
        )
        BotHandlers._send_message(token, chat_id, welcome, reply_to_id=message_id)

    @staticmethod
    def update_entity(token, chat_id, message_id, args):
        if not args:
            BotHandlers._send_temp_message(token, chat_id, "⚠️ *Input Salah:* Masukkan simbol aset. Contoh: `/update TSLA`", reply_to_id=message_id)
            return

        symbol = args[0].upper()
        status_msg_id = None
        
        try:
            # --- TAHAP 1: SEARCHING ---
            status_msg_id = BotHandlers._send_message(token, chat_id, f"🔍 `Searching Intelligence: {symbol}...`", reply_to_id=message_id)
            
            history_res = AsetpediaAPI.get_market_history(symbol)
            if history_res.get("status") != "success":
                # Detail error untuk user, akan terhapus dlm 5 detik
                raise Exception(f"Service Error: {history_res.get('message', 'No response from market service')}")

            history = history_res.get("history", [])
            if not history:
                raise Exception(f"Simbol '{symbol}' tidak ditemukan di database kami.")

            # --- TAHAP 2: CHARTING ---
            BotHandlers._delete_message(token, chat_id, status_msg_id)
            status_msg_id = BotHandlers._send_message(token, chat_id, f"📊 `Generating Strategic Chart for {symbol}...`", reply_to_id=message_id)
            
            chart_path = MarketVisualizer.generate_ohlc_chart(symbol, history)
            if chart_path:
                BotHandlers._send_photo(token, chat_id, chart_path, caption=f"🏛 *MAHAMERU STRATEGIC REPORT: {symbol}*", reply_to_id=message_id)
                MarketVisualizer.cleanup(chart_path)
            
            # --- TAHAP 3: NEWS & FINALIZING ---
            BotHandlers._delete_message(token, chat_id, status_msg_id)
            status_msg_id = BotHandlers._send_message(token, chat_id, f"📰 `Compiling News & Data for {symbol}...`", reply_to_id=message_id)
            
            # Cek apakah crypto (kasus khusus di API)
            is_crypto = "-USD" in symbol
            news = []
            if is_crypto:
                crypto_res = AsetpediaAPI.get_crypto_detail(symbol.replace("-USD", ""))
                news = crypto_res.get("data", {}).get("news", []) if crypto_res.get("status") == "success" else []
            
            table_text = format_ohlcv_table(history, limit=12)
            news_text = format_news(news, limit=3)
            
            report = (
                f"📋 *TECHNICAL DOSSIER: {symbol}*\n"
                f"{table_text}\n\n"
                f"📰 *INTELLIGENCE FEED:*\n"
                f"{news_text if news_text else '_No recent headlines found for this asset._'}"
            )
            
            BotHandlers._send_message(token, chat_id, report, reply_to_id=message_id, disable_preview=True)
            # Cleanup status message
            BotHandlers._delete_message(token, chat_id, status_msg_id)

        except Exception as e:
            # Hapus status loading terakhir jika ada
            if status_msg_id: BotHandlers._delete_message(token, chat_id, status_msg_id)
            # Lapor error dan hapus dalam 5 detik
            err_text = f"❌ *COMMAND FAILED*\n\n*Reason:* `{str(e)}`"
            BotHandlers._send_temp_message(token, chat_id, err_text, delay=5, reply_to_id=message_id)

    @staticmethod
    def analyze(token, chat_id, message_id, args):
        if not args:
            BotHandlers._send_temp_message(token, chat_id, "⚠️ Masukkan simbol. Contoh: `/analyze BTC-USD`", reply_to_id=message_id)
            return
            
        symbol = args[0].upper()
        status_id = BotHandlers._send_message(token, chat_id, f"🤖 `AI Analysis in progress: {symbol}...`", reply_to_id=message_id)
        
        try:
            res = AsetpediaAPI.get_ai_analyze(symbol)
            BotHandlers._delete_message(token, chat_id, status_id)
            
            if res.get("status") == "success":
                verdict = res.get("data", "No analysis available.")
                BotHandlers._send_message(token, chat_id, f"🔮 *AI VERDICT FOR {symbol}:*\n\n{verdict}", reply_to_id=message_id)
            else:
                raise Exception(res.get("message", "AI Analysis timed out or service offline"))
        except Exception as e:
            if status_id: BotHandlers._delete_message(token, chat_id, status_id)
            BotHandlers._send_temp_message(token, chat_id, f"❌ *AI Error:* `{str(e)}`", delay=5, reply_to_id=message_id)

    @staticmethod
    def market_pulse(token, chat_id, message_id):
        status_id = BotHandlers._send_message(token, chat_id, "🌐 `Scanning Market Pulse...`", reply_to_id=message_id)
        try:
            res = AsetpediaAPI.get_market_watchlist()
            BotHandlers._delete_message(token, chat_id, status_id)
            
            if res.get("status") == "success":
                data = res.get("data", {})
                summary = ["🌐 *GLOBAL MARKET PULSE*"]
                for cat, items in data.items():
                    if not items: continue
                    summary.append(f"\n*[{cat.upper()}]*")
                    for item in items[:4]:
                        change = item.get('change_pct', 0)
                        sign = "+" if change > 0 else ""
                        summary.append(f"• {item['name']}: `{item['price']}` ({sign}{change:.2f}%)")
                
                BotHandlers._send_message(token, chat_id, "\n".join(summary), reply_to_id=message_id)
            else:
                raise Exception("Watchlist service unavailable.")
        except Exception as e:
            if status_id: BotHandlers._delete_message(token, chat_id, status_id)
            BotHandlers._send_temp_message(token, chat_id, f"❌ *Pulse Error:* `{str(e)}`", delay=5, reply_to_id=message_id)

    @staticmethod
    def get_id(token, chat_id, message_id):
        msg = f"🆔 *CHAT CONFIGURATION*\n\nChat ID: `{chat_id}`\nStatus: `Authorized`"
        BotHandlers._send_message(token, chat_id, msg, reply_to_id=message_id)
