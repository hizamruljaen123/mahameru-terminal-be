"""
Crypto High-Speed Stream Service — EXPANDED
- 25 symbols (top market cap)
- kline_1m, kline_5m, kline_15m, kline_1h
- trade, bookTicker
- !miniTicker@arr (all USDT pairs 24hr ticker)
- !forceOrder@arr (real-time liquidations)
- @markPrice (funding rate + mark price)
- Liquidation tracking + REST endpoints
"""
import asyncio
import websockets
import json
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional
import os
from collections import deque

# --- CONFIG ---
SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
    'ADAUSDT', 'DOGEUSDT', 'TRXUSDT', 'DOTUSDT', 'LINKUSDT',
    'AVAXUSDT', 'MATICUSDT', 'UNIUSDT', 'ATOMUSDT', 'LTCUSDT',
    'ETCUSDT', 'XLMUSDT', 'APTUSDT', 'ARBUSDT', 'FILUSDT',
    'NEARUSDT', 'OPUSDT', 'SUIUSDT', 'PEPEUSDT', 'INJUSDT'
]
CACHE_LIMIT = 300

# Timeframes to track
TIMEFRAMES = ['1m', '5m', '15m', '1h']

# --- Cache ---
market_cache = {
    s: {
        "klines": {tf: deque(maxlen=CACHE_LIMIT) for tf in TIMEFRAMES},
        "trades": deque(maxlen=CACHE_LIMIT),
        "depth": {"bid_q": 0.0, "ask_q": 0.0, "bid_p": 0.0, "ask_p": 0.0},
        "last_price": 0.0,
        "mark_price": 0.0,
        "funding_rate": 0.0,
        "24hr": {"price_change": 0.0, "price_change_pct": 0.0, "volume": 0.0, "high": 0.0, "low": 0.0}
    } for s in SYMBOLS
}

# Global caches
mini_ticker_cache = {}  # All USDT pairs 24hr ticker
liquidation_cache = deque(maxlen=1000)  # Recent liquidations
mark_price_cache = {}  # Mark prices for all tracked symbols

connected_clients = set()

import requests

async def prefill_cache():
    """Prefills kline caches using Binance REST API."""
    print(f"[CRYPTO-STREAM] Pre-filling cache for {len(SYMBOLS)} symbols...")
    for s in SYMBOLS:
        try:
            for tf in TIMEFRAMES:
                url = f"https://api.binance.com/api/v3/klines?symbol={s}&interval={tf}&limit={CACHE_LIMIT}"
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
                    market_cache[s]["klines"][tf].append(candle)
                if market_cache[s]["klines"][tf]:
                    market_cache[s]["last_price"] = market_cache[s]["klines"][tf][-1]["close"]
            print(f"  Prefilled {s}: {len(market_cache[s]['klines']['1m'])} candles")
        except Exception as e:
            print(f"[CRYPTO-STREAM] Failed to prefill {s}: {e}")

async def binance_stream_manager():
    """Manages connection to Binance for all streams."""
    await prefill_cache()

    # Build streams for individual symbols
    symbol_streams = []
    for s in SYMBOLS:
        sl = s.lower()
        symbol_streams.append(f"{sl}@kline_1m/{sl}@kline_5m/{sl}@kline_15m/{sl}@kline_1h/{sl}@trade/{sl}@bookTicker/{sl}@markPrice")

    # Global streams
    global_streams = ["!miniTicker@arr", "!forceOrder@arr"]

    all_streams = symbol_streams + global_streams
    stream_path = "/".join(all_streams)
    url = f"wss://stream.binance.com:9443/stream?streams={stream_path}"

    print(f"[CRYPTO-STREAM] Connecting: {len(SYMBOLS)} symbols x {len(TIMEFRAMES)} timeframes + miniTicker + forceOrder + markPrice")
    print(f"[CRYPTO-STREAM] Stream URL length: {len(url)} chars")

    while True:
        try:
            async with websockets.connect(url, max_size=5 * 1024 * 1024) as ws:
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    stream = data.get("stream", "")
                    payload = data.get("data", {})

                    if not stream: continue

                    # Handle global streams
                    if stream == "!miniTicker@arr":
                        await handle_mini_ticker_arr(payload)
                        continue
                    elif stream == "!forceOrder@arr":
                        await handle_force_order(payload)
                        continue

                    # Individual symbol streams
                    symbol = stream.split("@")[0].upper()
                    if symbol not in market_cache:
                        continue

                    processed_data = None
                    event = payload.get("e")

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
                        tf = k["i"]  # interval
                        candle = {
                            "time": k["t"] / 1000,
                            "open": float(k["o"]),
                            "high": float(k["h"]),
                            "low": float(k["l"]),
                            "close": float(k["c"]),
                            "volume": float(k["v"])
                        }
                        if tf in market_cache[symbol]["klines"]:
                            market_cache[symbol]["klines"][tf].append(candle)
                        market_cache[symbol]["last_price"] = candle["close"]
                        processed_data = {"type": "kline", "symbol": symbol, "timeframe": tf, "data": candle}

                    elif event == "trade":
                        trade = {
                            "p": float(payload["p"]),
                            "q": float(payload["q"]),
                            "m": payload.get("m", False),
                            "T": payload.get("T", 0)
                        }
                        market_cache[symbol]["trades"].append(trade)
                        processed_data = {"type": "trade", "symbol": symbol, "data": trade}

                    elif event == "markPriceUpdate":
                        mp = {
                            "mark_price": float(payload.get("p", 0)),
                            "funding_rate": float(payload.get("r", 0)),
                            "funding_time": payload.get("T", 0)
                        }
                        market_cache[symbol]["mark_price"] = mp["mark_price"]
                        market_cache[symbol]["funding_rate"] = mp["funding_rate"]
                        mark_price_cache[symbol] = mp
                        processed_data = {"type": "mark_price", "symbol": symbol, "data": mp}

                    # Broadcast to WS clients
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


async def handle_mini_ticker_arr(payload):
    """Process !miniTicker@arr — update 24hr ticker for all symbols."""
    if not isinstance(payload, list):
        return

    for item in payload:
        symbol = item.get("s", "")
        if symbol in market_cache:
            market_cache[symbol]["24hr"] = {
                "price_change": float(item.get("p", 0)),
                "price_change_pct": float(item.get("P", 0)),
                "volume": float(item.get("v", 0)),
                "high": float(item.get("h", 0)),
                "low": float(item.get("l", 0)),
                "last_price": float(item.get("c", 0))
            }
            market_cache[symbol]["last_price"] = float(item.get("c", 0))

        # Store all for global scan
        mini_ticker_cache[symbol] = {
            "symbol": symbol,
            "last_price": float(item.get("c", 0)),
            "price_change_pct": float(item.get("P", 0)),
            "volume": float(item.get("v", 0)),
            "high": float(item.get("h", 0)),
            "low": float(item.get("l", 0))
        }

    # Broadcast condensed miniTicker to clients
    if connected_clients:
        ticker_snapshot = {s: market_cache[s]["24hr"] for s in SYMBOLS}
        message = json.dumps({"type": "mini_ticker", "data": ticker_snapshot})
        dead_clients = set()
        for client in connected_clients:
            try:
                await client.send_text(message)
            except:
                dead_clients.add(client)
        for c in dead_clients:
            connected_clients.remove(c)


async def handle_force_order(payload):
    """Process !forceOrder@arr — real-time liquidation events."""
    try:
        o = payload.get("o", {})
        if not o:
            return

        liquidation = {
            "symbol": o.get("s", ""),
            "side": o.get("S", ""),        # SELL = long liq, BUY = short liq
            "order_type": o.get("o", ""),
            "time_in_force": o.get("f", ""),
            "original_qty": float(o.get("q", 0)),
            "price": float(o.get("p", 0)),
            "avg_price": float(o.get("ap", 0)),
            "order_status": o.get("X", ""),
            "last_fill_qty": float(o.get("l", 0)),
            "total_fill_qty": float(o.get("z", 0)),
            "total_fill_usd": float(o.get("z", 0)) * float(o.get("p", 0)),
            "timestamp": o.get("T", 0),
            "event_time": payload.get("E", 0)
        }
        liquidation_cache.append(liquidation)

        # Broadcast to clients
        if connected_clients:
            message = json.dumps({"type": "liquidation", "data": liquidation})
            dead_clients = set()
            for client in connected_clients:
                try:
                    await client.send_text(message)
                except:
                    dead_clients.add(client)
            for c in dead_clients:
                connected_clients.remove(c)

    except Exception as e:
        print(f"[FORCE_ORDER_ERROR] {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(binance_stream_manager())
    yield
    task.cancel()


app = FastAPI(title="Crypto High-Speed Stream Service (Expanded)", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===================== WEBSOCKET ENDPOINT =====================

@app.websocket("/ws/crypto")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)

    # Send full cache snapshot upon connection
    snapshot = {
        "type": "snapshot",
        "symbols": SYMBOLS,
        "timeframes": TIMEFRAMES,
        "data": {
            s: {
                "klines": {tf: list(market_cache[s]["klines"][tf]) for tf in TIMEFRAMES},
                "trades": list(market_cache[s]["trades"]),
                "depth": market_cache[s]["depth"],
                "mark_price": market_cache[s]["mark_price"],
                "funding_rate": market_cache[s]["funding_rate"],
                "24hr": market_cache[s]["24hr"]
            } for s in SYMBOLS
        }
    }
    try:
        await websocket.send_text(json.dumps(snapshot))
    except:
        pass

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in connected_clients:
            connected_clients.remove(websocket)


# ===================== REST ENDPOINTS =====================

@app.get("/api/stream/health")
async def health():
    return {
        "status": "online",
        "symbols": len(SYMBOLS),
        "timeframes": TIMEFRAMES,
        "clients": len(connected_clients),
        "liquidations_cached": len(liquidation_cache),
        "mini_ticker_symbols": len(mini_ticker_cache)
    }

@app.get("/api/stream/liquidations")
async def get_liquidations(limit: int = 50, min_usd: float = 0):
    """Get recent liquidations from the cache."""
    liq_list = list(liquidation_cache)
    if min_usd > 0:
        liq_list = [l for l in liq_list if l.get("total_fill_usd", 0) >= min_usd]
    liq_list = liq_list[-limit:] if limit else liq_list

    # Aggregate by symbol
    agg = {}
    for l in liq_list:
        sym = l["symbol"]
        if sym not in agg:
            agg[sym] = {"symbol": sym, "long_liq": 0, "short_liq": 0, "total_usd": 0, "count": 0}
        usd = l.get("total_fill_usd", 0)
        agg[sym]["total_usd"] += usd
        agg[sym]["count"] += 1
        if l["side"] == "SELL":
            agg[sym]["long_liq"] += usd
        else:
            agg[sym]["short_liq"] += usd

    return {
        "status": "success",
        "data": {
            "liquidations": liq_list,
            "aggregated": list(agg.values()),
            "total_count": len(liq_list),
            "total_usd": sum(l.get("total_fill_usd", 0) for l in liq_list)
        }
    }

@app.get("/api/stream/market-scan")
async def get_market_scan():
    """Scan all tracked symbols via miniTicker cache — top movers, volume leaders."""
    if not mini_ticker_cache:
        return {"status": "error", "detail": "Mini ticker cache not yet populated"}

    tickers = list(mini_ticker_cache.values())

    # Top gainers
    gainers = sorted(tickers, key=lambda x: x.get("price_change_pct", 0), reverse=True)[:10]
    # Top losers
    losers = sorted(tickers, key=lambda x: x.get("price_change_pct", 0))[:10]
    # Highest volume
    by_vol = sorted(tickers, key=lambda x: x.get("volume", 0), reverse=True)[:10]

    return {
        "status": "success",
        "data": {
            "total_symbols": len(tickers),
            "top_gainers": gainers,
            "top_losers": losers,
            "highest_volume": by_vol,
            "last_updated": int(asyncio.get_event_loop().time()) if hasattr(asyncio, 'get_event_loop') else 0
        }
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8092)
