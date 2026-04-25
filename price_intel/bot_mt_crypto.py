"""
bot_mt_crypto.py — /mt_ Crypto, Market & Finance Commands
──────────────────────────────────────────────────────────
Handles:
  /mt_crypto_pulse  - BTC, ETH, SOL, dominance, Fear/Greed
  /mt_ta_score      - TA signal score for any symbol
  /mt_deep_ai       - Deep TA AI prediction
  /mt_whale_track   - On-chain whale transactions
  /mt_derivatives   - Funding rates & liquidations
  /mt_macro_index   - Macro economic data
  /mt_forex_fx      - Major forex pairs
  /mt_commodities   - Gold, Oil, Gas, Nickel
"""
from datetime import datetime
from .bot_helpers import send_message, safe_get, _api, fmt_number


# ─── /mt_crypto_pulse ─────────────────────────────────────────────────────────
def handle_mt_crypto_pulse(chat_id):
    data = safe_get(_api("crypto", "/api/crypto/summary"))
    if not data:
        send_message(chat_id, "⚠️ Crypto service unavailable (port 8085)")
        return

    lines = [f"📊 <b>CRYPTO MARKET PULSE</b>", f"⏱ {datetime.now().strftime('%H:%M:%S')}", ""]

    for sym in ["BTC", "ETH", "SOL", "BNB", "XRP"]:
        c = data.get(sym) or data.get(sym.lower()) or {}
        if c:
            pct = c.get("change_24h", 0) or 0
            arrow = "🟢" if pct >= 0 else "🔴"
            lines.append(
                f"{arrow} <b>{sym}</b>  ${fmt_number(c.get('price', 0))}  "
                f"({pct:+.2f}%)  Vol: ${fmt_number(c.get('volume_24h', 0))}"
            )

    dom = data.get("dominance", {})
    if dom:
        lines += ["", f"🏆 BTC Dom: <b>{dom.get('btc', 'N/A')}%</b>  ETH: {dom.get('eth', 'N/A')}%"]

    fg = data.get("fear_greed")
    if fg:
        lines.append(f"😱 Fear & Greed: <b>{fg.get('value', '?')} — {fg.get('classification', '?')}</b>")

    send_message(chat_id, "\n".join(lines))


# ─── /mt_ta_score <symbol> ────────────────────────────────────────────────────
def handle_mt_ta_score(chat_id, args):
    symbol = args[0].upper() if args else "BTC-USD"
    data = safe_get(_api("ta", f"/api/ta/analyze/{symbol}?period=3mo"))
    if not data:
        send_message(chat_id, f"⚠️ TA service unavailable for <code>{symbol}</code>")
        return

    signals = data.get("signals", {})
    score = signals.get("score", "N/A")
    verdict = signals.get("verdict", "N/A")
    regime = signals.get("regime", "N/A")
    cur = data.get("current", {})

    verdict_emoji = {"STRONG BUY": "🟢🟢", "BUY": "🟢", "NEUTRAL": "⚪", "SELL": "🔴", "STRONG SELL": "🔴🔴"}.get(verdict, "⚪")

    msg = (
        f"📈 <b>TECHNICAL ANALYSIS — {symbol}</b>\n\n"
        f"Signal   : {verdict_emoji} <b>{verdict}</b>\n"
        f"Score    : <b>{score}/100</b>\n"
        f"Regime   : <code>{regime}</code>\n\n"
        f"Price    : ${fmt_number(cur.get('price'))}\n"
        f"RSI-14   : {cur.get('rsi14') or 'N/A'}\n"
        f"MACD     : {fmt_number(cur.get('macd'))}\n"
        f"ADX      : {cur.get('adx') or 'N/A'}\n"
        f"BB %     : {cur.get('bb_pct') or 'N/A'}\n"
        f"ATR      : {fmt_number(cur.get('atr'))}\n"
        f"HV20     : {cur.get('hv20') or 'N/A'}%\n"
    )

    # MA Table summary
    ma_table = data.get("ma_table", {})
    if ma_table:
        ma_rows = []
        for k, v in list(ma_table.items())[:6]:
            above = "↑" if v.get("above") else "↓"
            ma_rows.append(f"  {k.upper():<8} {above} {v.get('pct',0):+.2f}%")
        msg += f"\n<b>Moving Averages:</b>\n<pre>{'\n'.join(ma_rows)}</pre>"

    send_message(chat_id, msg)


# ─── /mt_deep_ai <symbol> ─────────────────────────────────────────────────────
def handle_mt_deep_ai(chat_id, args):
    symbol = args[0].upper() if args else "BTC-USD"
    data = safe_get(_api("deep_ta", f"/api/deep-ta/predict/{symbol}"), timeout=15)
    if not data:
        send_message(chat_id, f"⚠️ Deep TA AI service unavailable for <code>{symbol}</code>")
        return
    pred = data.get("prediction") or data.get("result") or data
    send_message(chat_id, f"🤖 <b>DEEP AI PREDICTION — {symbol}</b>\n\n<pre>{str(pred)[:1500]}</pre>")


# ─── /mt_whale_track ─────────────────────────────────────────────────────────
def handle_mt_whale_track(chat_id):
    data = safe_get(_api("crypto", "/api/crypto/onchain/whales"))
    if not data:
        send_message(chat_id, "⚠️ On-chain whale data unavailable.")
        return
    txns = data.get("transactions", data if isinstance(data, list) else [])
    if not txns:
        send_message(chat_id, "🐋 No recent whale transactions found.")
        return
    rows = []
    for tx in txns[:8]:
        val = fmt_number(tx.get("value_usd") or tx.get("amount_usd", 0))
        fr  = tx.get("from", "?")[:12]
        to  = tx.get("to", "?")[:12]
        sym = tx.get("symbol", "?")
        rows.append(f"  💰 {sym} ${val}  {fr} → {to}")
    send_message(chat_id, f"🐋 <b>WHALE TRACKER (On-Chain)</b>\n\n<pre>" + "\n".join(rows) + "</pre>")


# ─── /mt_derivatives ─────────────────────────────────────────────────────────
def handle_mt_derivatives(chat_id):
    data = safe_get(_api("crypto", "/api/crypto/derivatives/summary"))
    if not data:
        send_message(chat_id, "⚠️ Derivatives data unavailable.")
        return
    rows = []
    for sym, info in (data.items() if isinstance(data, dict) else []):
        fr = info.get("funding_rate", 0) * 100 if info.get("funding_rate") else 0
        oi = fmt_number(info.get("open_interest"))
        liq = fmt_number(info.get("liquidations_24h"))
        rows.append(f"  {sym:<6} FR:{fr:+.4f}%  OI:{oi}  Liq:{liq}")
    send_message(chat_id, f"📉 <b>DERIVATIVES DASHBOARD</b>\n\n<pre>" + "\n".join(rows[:10]) + "</pre>")


# ─── /mt_macro_index ─────────────────────────────────────────────────────────
def handle_mt_macro_index(chat_id):
    data = safe_get(_api("crypto", "/api/crypto/macro"))
    if not data:
        send_message(chat_id, "⚠️ Macro data unavailable.")
        return
    lines = [f"🌐 <b>MACRO ECONOMIC INDEX</b>"]
    for k, v in data.items():
        lines.append(f"  {str(k).replace('_',' ').upper():<25}: {v}")
    send_message(chat_id, lines[0] + "\n<pre>" + "\n".join(lines[1:]) + "</pre>")


# ─── /mt_forex_fx ────────────────────────────────────────────────────────────
def handle_mt_forex_fx(chat_id):
    data = safe_get(_api("forex", "/api/forex/rates"))
    if not data:
        send_message(chat_id, "⚠️ Forex service unavailable (port 8086)")
        return
    pairs = data.get("rates", data) if isinstance(data, dict) else {}
    rows = [f"  {pair:<10}: {rate}" for pair, rate in list(pairs.items())[:12]]
    send_message(chat_id, f"💱 <b>FOREX RATES</b>\n⏱ {datetime.now().strftime('%H:%M')}\n\n<pre>" + "\n".join(rows) + "</pre>")


# ─── /mt_commodities ─────────────────────────────────────────────────────────
def handle_mt_commodities(chat_id):
    data = safe_get(_api("commodity", "/api/commodities/summary"))
    if not data:
        send_message(chat_id, "⚠️ Commodity service unavailable (port 8087)")
        return
    items = data.get("commodities", data) if isinstance(data, dict) else {}
    lines = [f"🛢️ <b>COMMODITIES DASHBOARD</b>"]
    for name, info in (items.items() if isinstance(items, dict) else []):
        price = info.get("price", info) if isinstance(info, dict) else info
        pct   = info.get("change_pct", "") if isinstance(info, dict) else ""
        arrow = "🟢" if str(pct).startswith("+") or (isinstance(pct, (int, float)) and pct >= 0) else "🔴"
        lines.append(f"  {arrow} {name:<15}: {fmt_number(price)} USD  ({pct}%)")
    send_message(chat_id, lines[0] + "\n<pre>" + "\n".join(lines[1:]) + "</pre>")
