import os
from typing import Optional
import time
import threading
import requests
import logging
import queue
from .analyzer import PriceAnalyzer
from .formatter import PriceFormatter
from .sentiment import SentimentAnalyzer
from .deep_ta import DeepTAClient

# --- New Modular Handlers ---
from .bot_mt_crypto import (
    handle_mt_crypto_pulse, handle_mt_ta_score, handle_mt_deep_ai,
    handle_mt_whale_track, handle_mt_derivatives, handle_mt_macro_index,
    handle_mt_forex_fx, handle_mt_commodities
)
from .bot_mt_geo import (
    handle_mt_disaster, handle_mt_vessel_find, handle_mt_oil_reserves,
    handle_mt_oil_trades, handle_mt_port_traffic, handle_mt_news_brief,
    handle_mt_sentiment, handle_mt_entity_map
)
from .bot_mt_alerts import run_mt_alert_loop

logger = logging.getLogger("PriceIntel.Bot")

class PriceIntelligenceBot:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        self.offset = 0
        self.running = False
        self.sentiment_analyzer = SentimentAnalyzer()
        
        # Request Queueing System
        self.task_queue = queue.Queue()
        self.worker_thread = None

    def get_updates(self):
        try:
            url = f"{self.api_url}/getUpdates?offset={self.offset}&timeout=30"
            resp = requests.get(url, timeout=35)
            if resp.status_code == 200:
                return resp.json().get("result", [])
        except Exception as e:
            logger.error(f"Error getting updates: {e}")
        return []

    def send_loading_message(self, target_chat_id: str, symbol: str) -> Optional[int]:
        """Send a temporary loading message and return its ID"""
        url = f"{self.api_url}/sendMessage"
        payload = {
            'chat_id': target_chat_id,
            'text': f"⏳ <b>Processing {symbol}...</b>\n<i>Analyzing market data and AI sentiment...</i>",
            'parse_mode': 'HTML'
        }
        try:
            resp = requests.post(url, data=payload)
            if resp.status_code == 200:
                return resp.json().get("result", {}).get("message_id")
        except: pass
        return None

    def delete_message(self, target_chat_id: str, message_id: int):
        """Delete a message by ID"""
        if not message_id: return
        url = f"{self.api_url}/deleteMessage"
        payload = {'chat_id': target_chat_id, 'message_id': message_id}
        requests.post(url, data=payload)

    def process_report_task(self, task_type: str, symbol: str, target_chat_id: str):
        """Worker function to process a single report task"""
        loading_id = self.send_loading_message(target_chat_id, symbol)
        
        try:
            if task_type == "market_update":
                self.send_report(symbol, target_chat_id)
            elif task_type == "sentinews":
                self.send_sentiment_report(symbol, target_chat_id)
            elif task_type == "deep_ta":
                # For deep_ta, symbol is a tuple or we use extra args
                # Let's assume symbol for deep_ta is "METHOD:SYMBOL"
                method, actual_symbol = symbol.split(":")
                self.send_deep_ta_report(actual_symbol, method, target_chat_id)
            elif task_type == "news":
                self.send_keyword_news(symbol, target_chat_id)
        finally:
            # Always try to delete the loading message
            if loading_id:
                self.delete_message(target_chat_id, loading_id)

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
            if resp.status_code != 200:
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
            if resp.status_code != 200:
                logger.error(f"❌ Telegram send failed: {resp.text}")
        except Exception as e:
            logger.error(f"❌ Error sending sentiment report: {e}")

    def send_keyword_news(self, keyword: str, target_chat_id: str):
        logger.info(f"Generating keyword news for '{keyword}' to chat {target_chat_id}...")
        
        # Fetch 5 ID and 5 EN
        news_id = PriceFormatter.get_news(keyword, keyword, "indonesia", count=5)
        news_en = PriceFormatter.get_news(keyword, keyword, "global", count=5)
        all_news = news_id + news_en
        
        if not all_news:
            self.send_message(target_chat_id, f"❌ No news found for <b>{keyword}</b>.")
            return
            
        # Analyze
        self.sentiment_analyzer.analyze_news_batch(all_news)
        analyzed_news = all_news # analyze_news_batch modifies in place
        
        caption = f"<b>📰 NEWS FEED: {keyword.upper()}</b>\n"
        caption += f"<i>Analyzing 10 latest articles (Global & ID)</i>\n"
        caption += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        
        for n in analyzed_news:
            s = n.get('sentiment', 'NEUTRAL')
            icon = "🟢" if s == "POSITIVE" else ("🔴" if s == "NEGATIVE" else "⚪")
            # Truncate title for brevity
            title = n['title'][:60] + "..." if len(n['title']) > 63 else n['title']
            caption += f"{icon} <a href='{n['link']}'>{title}</a>\n"
            
        caption += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        caption += "<i>Source: AI Sentiment Engine</i>"
        
        self.send_message(target_chat_id, caption)

    def send_deep_ta_report(self, symbol: str, method: str, target_chat_id: str):
        logger.info(f"Generating Deep TA ({method}) for {symbol} to chat {target_chat_id}...")
        
        data = DeepTAClient.get_deep_analysis(symbol, method)
        if data is None:
            self.send_message(target_chat_id, f"❌ Deep Analysis failed for <b>{symbol}</b> using <b>{method}</b>. Ensure the Deep TA service is running.")
            return
        
        chart_buf = PriceFormatter.create_deep_ta_chart(
            data["ohlcv"], data["analysis"], data["method_id"], symbol
        )
        
        table_html = PriceFormatter.format_deep_ta_table(data["analysis"], data["method_id"])
        
        caption = f"<b>🔬 DEEP TA: {data['method_name']}</b>\n"
        caption += f"<code>Symbol: {symbol} | Method ID: {data['method_id']}</code>\n"
        caption += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        caption += f"{table_html}\n"
        caption += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        caption += "<i>Advanced institutional analysis processed from the last 100 data points.</i>"

        url = f"{self.api_url}/sendPhoto"
        files = {'photo': ('deep_ta.png', chart_buf, 'image/png')}
        payload = {'chat_id': target_chat_id, 'caption': caption, 'parse_mode': 'HTML'}
        
        try:
            requests.post(url, files=files, data=payload)
        except Exception as e:
            logger.error(f"❌ Error sending Deep TA to Telegram: {e}")

    def send_message(self, target_chat_id: str, text: str, auto_delete_seconds: Optional[int] = None):
        url = f"{self.api_url}/sendMessage"
        payload = {'chat_id': target_chat_id, 'text': text, 'parse_mode': 'HTML'}
        try:
            resp = requests.post(url, json=payload, timeout=8)
            if resp.status_code == 200 and auto_delete_seconds:
                msg_id = resp.json().get("result", {}).get("message_id")
                if msg_id:
                    threading.Timer(auto_delete_seconds, self.delete_message, [target_chat_id, msg_id]).start()
        except Exception as e:
            logger.error(f"Error in send_message: {e}")

    def handle_message(self, update):
        message = update.get("message")
        if not message: return
        
        text = message.get("text", "")
        chat_id = message.get("chat", {}).get("id")
        
        cmd_parts = text.split()
        if not cmd_parts: return
        
        cmd = cmd_parts[0].split('@')[0]
        
        if cmd == "/mt_market_update":
            if len(cmd_parts) > 1:
                self.task_queue.put(("market_update", cmd_parts[1].upper(), chat_id))
            else:
                self.send_message(chat_id, "ℹ️ Usage: <code>/mt_market_update [SYMBOL]</code>")
        
        elif cmd == "/mt_sentinews":
            if len(cmd_parts) > 1:
                self.task_queue.put(("sentinews", cmd_parts[1].upper(), chat_id))
            else:
                self.send_message(chat_id, "ℹ️ Usage: <code>/mt_sentinews [SYMBOL]</code>")
        
        elif cmd == "/mt_tda":
            if len(cmd_parts) > 2:
                method = cmd_parts[1].lower()
                symbol = cmd_parts[2].upper()
                # Use a specific format for the queue task
                self.task_queue.put(("deep_ta", f"{method}:{symbol}", chat_id))
            else:
                self.send_message(chat_id, "ℹ️ Usage: <code>/mt_tda [METHOD] [SYMBOL]</code>\nMethods: <code>master, regime, vdelta, spectral, smc</code>")

        elif cmd == "/mt_help":
            help_text = (
                "🏔️ <b>MAHAMERU TERMINAL — INTELLIGENCE</b>\n\n"
                "<b>── CRYPTO & FINANCE ──</b>\n"
                "<code>/mt_crypto_pulse</code>  Market pulse (Top 5 & Dom)\n"
                "<code>/mt_whale_track</code>   On-chain whale activities\n"
                "<code>/mt_derivatives</code>   Funding rates & liquidations\n"
                "<code>/mt_macro_index</code>   Global macro indicators\n"
                "<code>/mt_forex_fx</code>      Major FX pairs rates\n"
                "<code>/mt_commodities</code>   Gold, Oil, Gas & Metals\n\n"
                
                "<b>── GEO-INTELLIGENCE ──</b>\n"
                "<code>/mt_disaster</code>      Real-time disaster alerts\n"
                "<code>/mt_vessel_find</code>   [MMSI] Track AIS vessels\n"
                "<code>/mt_oil_reserves</code>  Refinery utilization stats\n"
                "<code>/mt_oil_trades</code>    Active oil trade routes\n"
                "<code>/mt_port_traffic</code>  Logistics port density\n\n"

                "<b>── QUANT & NEWS ──</b>\n"
                "<code>/mt_market_update</code> [SYM] Full quant report\n"
                "<code>/mt_sentinews</code>    [SYM] AI sentiment report\n"
                "<code>/mt_news</code>          [KEY] Latest news feed\n"
                "<code>/mt_ta_score</code>      [SYM] Technical TA score\n"
                "<code>/mt_deep_ai</code>       [SYM] Deep AI prediction\n"
                "<code>/mt_tda</code>           [MET] [SYM] Institutional TDA\n"
                "<code>/mt_sentiment</code>     [ENT] Entity sentiment analysis\n"
                "<code>/mt_entity_map</code>    [ENT] Corporate correlation map\n\n"
                
                "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
                "<i>Use yfinance symbols (e.g. .JK for IHSG, -USD for Crypto).</i>"
            )
            self.send_message(chat_id, help_text)
        
        elif cmd == "/mt_news":
            if len(cmd_parts) > 1:
                keyword = " ".join(cmd_parts[1:])
                self.task_queue.put(("news", keyword, chat_id))
            else:
                self.send_message(chat_id, "ℹ️ Usage: <code>/mt_news [KATA KUNCI]</code>")

        # --- NEW DISPATCHER MAPPINGS ---
        elif cmd == "/mt_crypto_pulse": handle_mt_crypto_pulse(chat_id)
        elif cmd == "/mt_ta_score":     handle_mt_ta_score(chat_id, args)
        elif cmd == "/mt_deep_ai":      handle_mt_deep_ai(chat_id, args)
        elif cmd == "/mt_whale_track":  handle_mt_whale_track(chat_id)
        elif cmd == "/mt_derivatives":  handle_mt_derivatives(chat_id)
        elif cmd == "/mt_macro_index":  handle_mt_macro_index(chat_id)
        elif cmd == "/mt_forex_fx":     handle_mt_forex_fx(chat_id)
        elif cmd == "/mt_commodities":  handle_mt_commodities(chat_id)
        elif cmd == "/mt_disaster":     handle_mt_disaster(chat_id)
        elif cmd == "/mt_vessel_find":  handle_mt_vessel_find(chat_id, args)
        elif cmd == "/mt_oil_reserves": handle_mt_oil_reserves(chat_id)
        elif cmd == "/mt_oil_trades":   handle_mt_oil_trades(chat_id)
        elif cmd == "/mt_port_traffic": handle_mt_port_traffic(chat_id)
        elif cmd == "/mt_news_brief":   handle_mt_news_brief(chat_id, args)
        elif cmd == "/mt_sentiment":    handle_mt_sentiment(chat_id, args)
        elif cmd == "/mt_entity_map":   handle_mt_entity_map(chat_id, args)

    def worker(self):
        """Background worker to process the task queue sequentially"""
        logger.info("Task worker started...")
        while self.running:
            try:
                # Wait for a task with a timeout so we can check self.running
                task = self.task_queue.get(timeout=1)
                task_type, symbol, chat_id = task
                self.process_report_task(task_type, symbol, chat_id)
                self.task_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Worker error: {e}")

    def start_polling(self):
        self.running = True
        
        # Start the sequential worker thread
        self.worker_thread = threading.Thread(target=self.worker, daemon=True)
        self.worker_thread.start()

        # Start the Intelligence Alert Loop
        alert_thread = threading.Thread(target=run_mt_alert_loop, daemon=True)
        alert_thread.start()
        
        logger.info("Bot polling and alert loops started...")
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
