import asyncio
import websockets
import json
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import List, Dict, Any
import os
from collections import deque

# --- CONFIG ---
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT', 'TRXUSDT', 'DOTUSDT', 'LINKUSDT']
CACHE_LIMIT = 300 

# Cache stores last 300 items per symbol
market_cache = {
    s: {
        "klines": deque(maxlen=CACHE_LIMIT),
        "trades": deque(maxlen=CACHE_LIMIT),
        "depth": {"bid_q": 0.0, "ask_q": 0.0, "bid_p": 0.0, "ask_p": 0.0},
        "last_price": 0.0
    } for s in SYMBOLS
}

connected_clients = set()

import requests

async def prefill_cache():
    """Prefills the kline cache using Binance REST API for immediate historical context."""
    print("[CRYPTO-STREAM] Pre-filling cache from Binance REST API...")
    for s in SYMBOLS:
        try:
            url = f"https://api.binance.com/api/v3/klines?symbol={s}&interval=1m&limit={CACHE_LIMIT}"
            resp = requests.get(url, timeout=10)
            data = resp.json()
            for k in data:
                candle = {
                    "time": k[0] / 1000,
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5])
                }
                market_cache[s]["klines"].append(candle)
            if market_cache[s]["klines"]:
                market_cache[s]["last_price"] = market_cache[s]["klines"][-1]["close"]
        except Exception as e:
            print(f"[CRYPTO-STREAM] Failed to prefill {s}: {e}")

async def binance_stream_manager():
    """Manages connection to Binance for all 10 assets, including depth ticker."""
    await prefill_cache()
    # Added @bookTicker for real-time depth visualization
    streams = "/".join([f"{s.lower()}@kline_1m/{s.lower()}@trade/{s.lower()}@bookTicker" for s in SYMBOLS])
    url = f"wss://stream.binance.com:9443/stream?streams={streams}"
    
    while True:
        try:
            print(f"[CRYPTO-STREAM] Connecting to Binance: {len(SYMBOLS)} assets (Price+Trade+Book)...")
            async with websockets.connect(url) as ws:
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    stream = data.get("stream", "")
                    payload = data.get("data", {})
                    
                    if not stream: continue
                    symbol = stream.split("@")[0].upper()
                    
                    processed_data = None
                    event = payload.get("e")

                    # Handle bookTicker (doesn't have "e" field always)
                    if "@bookTicker" in stream:
                        depth = {
                            "bid_p": float(payload["b"]),
                            "bid_q": float(payload["B"]),
                            "ask_p": float(payload["a"]),
                            "ask_q": float(payload["A"])
                        }
                        market_cache[symbol]["depth"] = depth
                        processed_data = {"type": "depth", "symbol": symbol, "data": depth}

                    elif event == "kline":
                        k = payload["k"]
                        candle = {
                            "time": k["t"] / 1000,
                            "open": float(k["o"]),
                            "high": float(k["h"]),
                            "low": float(k["l"]),
                            "close": float(k["c"]),
                            "volume": float(k["v"]) # Base asset volume
                        }
                        market_cache[symbol]["klines"].append(candle)
                        market_cache[symbol]["last_price"] = candle["close"]
                        processed_data = {"type": "kline", "symbol": symbol, "data": candle}
                        
                    elif event == "trade":
                        trade = {
                            "p": float(payload["p"]),
                            "q": float(payload["q"]),
                            "m": payload["m"],
                            "T": payload["T"]
                        }
                        market_cache[symbol]["trades"].append(trade)
                        processed_data = {"type": "trade", "symbol": symbol, "data": trade}

                    # Broadcast to clients
                    if processed_data and connected_clients:
                        message = json.dumps(processed_data)
                        dead_clients = set()
                        for client in connected_clients:
                            try:
                                await client.send_text(message)
                            except:
                                dead_clients.add(client)
                        for c in dead_clients:
                            connected_clients.remove(c)

        except Exception as e:
            print(f"[CRYPTO-STREAM] WebSocket Error: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(binance_stream_manager())
    yield
    task.cancel()

app = FastAPI(title="Crypto High-Speed Stream Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.websocket("/ws/crypto")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    
    # Send current cache snapshot (limit 300) upon connection
    snapshot = {
        "type": "snapshot",
        "data": {
            s: {
                "klines": list(market_cache[s]["klines"]),
                "trades": list(market_cache[s]["trades"]),
                "depth": market_cache[s]["depth"]
            } for s in SYMBOLS
        }
    }
    await websocket.send_text(json.dumps(snapshot))
    
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in connected_clients:
            connected_clients.remove(websocket)

@app.get("/api/health")
async def health():
    return {
        "status": "online",
        "assets": SYMBOLS,
        "clients": len(connected_clients)
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8092)
