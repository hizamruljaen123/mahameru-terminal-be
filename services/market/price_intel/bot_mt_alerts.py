"""
bot_mt_alerts.py — PUSH Auto-Alert Engine (Mahameru Intelligence)
──────────────────────────────────────────────────────────────────
Monitors & broadcasts:
  - Crypto Flash Crash / Pump (>5% in 15 min)
  - Whale On-Chain Movements
  - Extreme Market Volatility
  - AIS Transponder Anomaly
  - Disaster/Earthquake Alert
  - Sentiment Drop
"""
import time
from datetime import datetime
from .bot_helpers import broadcast_alert, safe_get, _api, fmt_number

# ─── State Tracking ───────────────────────────────────────────────────────────
_prev_prices: dict      = {}   # sym -> price
_prev_sentiment: dict   = {}   # entity -> score
_alert_cooldown: dict   = {}   # key -> epoch

def _cooldown_ok(key: str, seconds: int = 900) -> bool:
    now = time.time()
    if now - _alert_cooldown.get(key, 0) > seconds:
        _alert_cooldown[key] = now
        return True
    return False


# ─── Crypto Flash Crash / Pump ────────────────────────────────────────────────
def check_crypto_flash(threshold_pct: float = 5.0):
    data = safe_get(_api("crypto", "/api/crypto/summary"))
    if not data:
        return
    for sym in ["BTC", "ETH", "SOL", "BNB"]:
        info = data.get(sym) or data.get(sym.lower()) or {}
        price = info.get("price")
        if not price:
            continue
        prev = _prev_prices.get(sym)
        _prev_prices[sym] = price
        if prev:
            pct_change = ((price - prev) / prev) * 100
            if abs(pct_change) >= threshold_pct and _cooldown_ok(f"flash_{sym}", 600):
                direction = "🚀 PUMP" if pct_change > 0 else "💥 CRASH"
                broadcast_alert(
                    f"🚨 <b>[MT_CRYPTO] {direction} DETECTED</b>\n\n"
                    f"Asset    : <b>{sym}</b>\n"
                    f"Change   : <b>{pct_change:+.2f}%</b>\n"
                    f"Price    : ${fmt_number(price)}\n"
                    f"Time     : {datetime.now().strftime('%H:%M:%S')}\n\n"
                    f"<i>Significant movement detected. Review TA: /mt_ta_score {sym}-USD</i>"
                )


# ─── Whale Tracker ────────────────────────────────────────────────────────────
def check_whale_movements(min_value_usd: float = 1_000_000):
    data = safe_get(_api("crypto", "/api/crypto/onchain/whales"))
    if not data:
        return
    txns = data.get("transactions", data if isinstance(data, list) else [])
    for tx in txns:
        val = tx.get("value_usd") or tx.get("amount_usd", 0)
        tx_hash = tx.get("hash", tx.get("id", "unknown"))
        if val and val >= min_value_usd and _cooldown_ok(f"whale_{tx_hash}", 3600):
            sym = tx.get("symbol", "UNKNOWN")
            fr  = tx.get("from", "?")
            to  = tx.get("to", "?")
            broadcast_alert(
                f"🐋 <b>[MT_WHALE] LARGE TRANSFER DETECTED</b>\n\n"
                f"Asset    : <b>{sym}</b>\n"
                f"Amount   : <b>${fmt_number(val)}</b>\n"
                f"From     : <code>{fr}</code>\n"
                f"To       : <code>{to}</code>\n"
                f"Time     : {datetime.now().strftime('%H:%M:%S')}"
            )


# ─── Extreme Market Volatility ────────────────────────────────────────────────
def check_market_volatility():
    data = safe_get(_api("market", "/api/market/volatility"))
    if not data:
        return
    for sym, info in (data.items() if isinstance(data, dict) else []):
        hv = info.get("hv20") or info.get("volatility")
        if hv and float(hv) > 80 and _cooldown_ok(f"vol_{sym}", 1800):
            broadcast_alert(
                f"⚠️ <b>[MT_MARKET] EXTREME VOLATILITY</b>\n\n"
                f"Asset    : <b>{sym}</b>\n"
                f"HV20     : <b>{hv:.1f}%</b> (extreme threshold: 80%)\n"
                f"Time     : {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"<i>Exercise caution. Market conditions are highly unstable.</i>"
            )


# ─── AIS Anomaly ─────────────────────────────────────────────────────────────
def check_ais_anomaly():
    data = safe_get(_api("ais", "/api/ais/anomalies"))
    if not data:
        return
    anomalies = data.get("anomalies", data if isinstance(data, list) else [])
    for a in anomalies[:3]:
        mmsi = a.get("mmsi", "?")
        name = a.get("name", "UNKNOWN VESSEL")
        reason = a.get("reason", "Transponder anomaly")
        lat = a.get("lat", "?")
        lon = a.get("lon", "?")
        if _cooldown_ok(f"ais_{mmsi}", 3600):
            broadcast_alert(
                f"🚢 <b>[MT_MARITIME] AIS ANOMALY DETECTED</b>\n\n"
                f"Vessel   : <b>{name}</b>\n"
                f"MMSI     : <code>{mmsi}</code>\n"
                f"Location : {lat}, {lon}\n"
                f"Reason   : {reason}\n"
                f"Time     : {datetime.now().strftime('%H:%M:%S')}"
            )


# ─── Disaster Alert ───────────────────────────────────────────────────────────
def check_disaster_alerts(min_magnitude: float = 6.0):
    data = safe_get(_api("disaster", "/api/disasters/recent"))
    if not data:
        return
    events = data.get("events", data if isinstance(data, list) else [])
    for ev in events:
        mag  = ev.get("magnitude", 0) or 0
        evid = ev.get("id", str(ev.get("lat", "?")))
        if float(mag) >= min_magnitude and _cooldown_ok(f"disaster_{evid}", 3600):
            etype = ev.get("type", "EARTHQUAKE").upper()
            loc   = ev.get("location", ev.get("place", "Unknown"))
            broadcast_alert(
                f"🌋 <b>[MT_DISASTER] {etype} ALERT</b>\n\n"
                f"Magnitude : <b>M{mag}</b>\n"
                f"Location  : {loc}\n"
                f"Lat/Lon   : {ev.get('lat','?')}, {ev.get('lon','?')}\n"
                f"Time      : {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"<i>Check tsunami warning status and regional impact.</i>"
            )


# ─── Sentiment Drop ───────────────────────────────────────────────────────────
def check_sentiment_drops(drop_threshold: float = -20.0):
    data = safe_get(_api("sentiment", "/api/sentiment/entities/latest"))
    if not data:
        return
    entities = data.get("entities", data if isinstance(data, list) else [])
    for ent in entities:
        name  = ent.get("name", "?")
        score = ent.get("score", 0) or 0
        prev  = _prev_sentiment.get(name, score)
        _prev_sentiment[name] = score
        delta = score - prev
        if delta <= drop_threshold and _cooldown_ok(f"sent_{name}", 1800):
            broadcast_alert(
                f"📉 <b>[MT_SENTIMENT] SHARP DROP DETECTED</b>\n\n"
                f"Entity   : <b>{name}</b>\n"
                f"Current  : {score:.1f}\n"
                f"Delta    : <b>{delta:+.1f}</b>\n"
                f"Time     : {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"<i>Possible PR crisis or breaking negative news. Check /mt_sentiment {name}</i>"
            )


# ─── Main Alert Loop ─────────────────────────────────────────────────────────

def run_mt_alert_loop():
    """Run this in a daemon thread from app.py."""
    print("[*] MT Alert Loop started.")
    tick = 0
    while True:
        try:
            if tick % 3 == 0:    # every 15 sec
                check_crypto_flash()

            if tick % 6 == 0:    # every 30 sec
                check_whale_movements()
                check_ais_anomaly()

            if tick % 12 == 0:   # every 1 min
                check_disaster_alerts()
                check_sentiment_drops()
                check_market_volatility()

        except Exception as e:
            print(f"[MT Alert Loop] Error: {e}")

        time.sleep(5)
        tick += 1
