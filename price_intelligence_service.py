import os
import logging
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import uvicorn
from datetime import datetime

# Import modular components
from price_intel import PriceAnalyzer, PriceFormatter, PriceIntelligenceBot

# --- SETUP LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("PriceIntelService")

# --- LOAD CONFIG ---
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN", "8266806716:AAHTDeGwNUcG97nOzggDu-oryPLqGsrPLG8")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "-1003777663997")
PORT = 8170

app = FastAPI(title="Mahameru Price Intelligence Service", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Bot
bot = PriceIntelligenceBot(TOKEN, CHAT_ID)

# --- API ENDPOINTS ---

@app.get("/api/price/analyze/{symbol}")
async def get_analysis(symbol: str):
    result = PriceAnalyzer.perform_analysis(symbol)
    if result is None:
        raise HTTPException(status_code=404, detail="Symbol not found or no data")
    
    df = result["df"]
    info = result["info"]
    company_name = info["name"]
    country = info["country"]

    news = PriceFormatter.get_news(symbol, company_name, country)
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    price_now = float(last['Close'])
    pct_change = float(((price_now - prev['Close']) / prev['Close']) * 100)
    
    pattern = "Neutral"
    if last['CDL_ENGULFING'] > 0: pattern = "Bullish Engulfing"
    elif last['CDL_ENGULFING'] < 0: pattern = "Bearish Engulfing"
    elif last['CDL_DOJI'] > 0: pattern = "Doji"

    return {
        "symbol": symbol,
        "company_name": company_name,
        "country": country,
        "price": price_now,
        "change_pct": pct_change,
        "adx": float(last['ADX']),
        "rsi": float(last['RSI']),
        "pattern": pattern,
        "news": news,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/price/chart/{symbol}")
async def get_chart(symbol: str):
    result = PriceAnalyzer.perform_analysis(symbol)
    if result is None:
        raise HTTPException(status_code=404, detail="Symbol not found or no data")
    
    df = result["df"]
    chart_buf = PriceFormatter.create_chart(df, symbol)
    return StreamingResponse(chart_buf, media_type="image/png")

@app.post("/api/price/report/{symbol}")
async def trigger_report(symbol: str, background_tasks: BackgroundTasks):
    """Trigger a Telegram report in background"""
    background_tasks.add_task(bot.send_report, symbol, CHAT_ID)
    return {"status": "Report triggered", "symbol": symbol}

# --- HEALTH CHECK ---
@app.get("/")
def health():
    return {"status": "online", "service": "price_intelligence_service", "bot_running": bot.running}

@app.on_event("startup")
async def startup_event():
    # Start Telegram Bot polling in a separate thread
    bot.start_in_thread()
    logger.info("Price Intelligence Bot thread started")

if __name__ == "__main__":
    logger.info(f"Starting Price Intelligence Service on port {PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
