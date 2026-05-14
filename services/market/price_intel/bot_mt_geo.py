"""
bot_mt_geo.py — /mt_ Geo, Maritime, News & Entity Commands
──────────────────────────────────────────────────────────
Handles:
  /mt_disaster       - Bencana alam real-time
  /mt_vessel_find    - Cek koordinat kapal by MMSI
  /mt_oil_reserves   - Status kilang minyak global
  /mt_oil_trades     - Aktivitas jalur perdagangan minyak
  /mt_port_traffic   - Kepadatan pelabuhan logistik
  /mt_news_brief     - Ringkasan berita terkini
  /mt_sentiment      - Skor sentimen entitas
  /mt_entity_map     - Korelasi tokoh/korporasi
"""
from datetime import datetime
from .bot_helpers import send_message, safe_get, _api, fmt_number


# ─── /mt_disaster ─────────────────────────────────────────────────────────────
def handle_mt_disaster(chat_id):
    data = safe_get(_api("disaster", "/api/disasters/recent"))
    if not data:
        send_message(chat_id, "⚠️ Disaster service unavailable (port 8095)", auto_delete_seconds=60)
        return
    events = data.get("events", data if isinstance(data, list) else [])[:8]
    if not events:
        send_message(chat_id, "🌿 No significant disaster events found.", auto_delete_seconds=60)
        return
    rows = []
    for ev in events:
        mag  = ev.get("magnitude", "?")
        loc  = ev.get("location", ev.get("place", "Unknown"))[:30]
        etype = ev.get("type", "EQ")[:6].upper()
        rows.append(f"  [{etype}] M{mag} — {loc}")
    send_message(chat_id,
        f"🌋 <b>DISASTER INTELLIGENCE REPORT</b>\n"
        f"⏱ {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"<pre>" + "\n".join(rows) + "</pre>",
        auto_delete_seconds=60
    )


# ─── /mt_vessel_find <MMSI> ───────────────────────────────────────────────────
def handle_mt_vessel_find(chat_id, args):
    if not args:
        send_message(chat_id, "⚠️ Usage: <code>/mt_vessel_find &lt;MMSI&gt;</code>", auto_delete_seconds=60)
        return
    mmsi = args[0].strip()
    data = safe_get(_api("ais", f"/api/ais/vessel/{mmsi}"))
    if not data:
        send_message(chat_id, f"⚠️ No vessel found for MMSI: <code>{mmsi}</code>", auto_delete_seconds=60)
        return
    msg = (
        f"🚢 <b>VESSEL INTELLIGENCE</b>\n\n"
        f"MMSI      : <code>{mmsi}</code>\n"
        f"Name      : <b>{data.get('name','N/A')}</b>\n"
        f"Type      : {data.get('ship_type', data.get('type','N/A'))}\n"
        f"Flag      : {data.get('flag','N/A')}\n"
        f"Position  : {data.get('lat','?')}, {data.get('lon','?')}\n"
        f"Speed     : {data.get('speed','N/A')} knots\n"
        f"Course    : {data.get('course','N/A')}°\n"
        f"Dest      : {data.get('destination','N/A')}\n"
        f"ETA       : {data.get('eta','N/A')}\n"
        f"Status    : {data.get('status','N/A')}\n"
        f"Updated   : {data.get('timestamp', datetime.now().strftime('%H:%M'))}"
    )
    send_message(chat_id, msg)


# ─── /mt_oil_reserves ─────────────────────────────────────────────────────────
def handle_mt_oil_reserves(chat_id):
    data = safe_get(_api("oil_refinery", "/api/oil/refineries/summary"))
    if not data:
        send_message(chat_id, "⚠️ Oil refinery data unavailable (port 8089)", auto_delete_seconds=60)
        return
    refineries = data.get("refineries", data if isinstance(data, list) else [])[:10]
    rows = []
    for r in refineries:
        name  = str(r.get("name", "?"))[:25]
        cap   = fmt_number(r.get("capacity_bpd", r.get("capacity", 0)))
        util  = r.get("utilization", "?")
        rows.append(f"  {name:<25} Cap:{cap}  Util:{util}%")
    send_message(chat_id,
        f"🛢️ <b>OIL REFINERY STATUS</b>\n\n<pre>" + "\n".join(rows) + "</pre>",
        auto_delete_seconds=60
    )


# ─── /mt_oil_trades ───────────────────────────────────────────────────────────
def handle_mt_oil_trades(chat_id):
    data = safe_get(_api("oil_trade", "/api/oil/trades/active"))
    if not data:
        send_message(chat_id, "⚠️ Oil trade data unavailable (port 8090)", auto_delete_seconds=60)
        return
    trades = data.get("trades", data if isinstance(data, list) else [])[:8]
    rows = []
    for t in trades:
        route  = f"{t.get('origin','?')[:10]} → {t.get('destination','?')[:10]}"
        volume = fmt_number(t.get("volume_bbl", t.get("volume", 0)))
        grade  = t.get("grade", t.get("type", "?"))
        rows.append(f"  {route:<25} {volume} bbl  [{grade}]")
    send_message(chat_id,
        f"🚢 <b>OIL TRADE ROUTES (ACTIVE)</b>\n\n<pre>" + "\n".join(rows) + "</pre>",
        auto_delete_seconds=60
    )


# ─── /mt_port_traffic ─────────────────────────────────────────────────────────
def handle_mt_port_traffic(chat_id):
    data = safe_get(_api("port", "/api/ports/traffic"))
    if not data:
        send_message(chat_id, "⚠️ Port service unavailable (port 8098)", auto_delete_seconds=60)
        return
    ports = data.get("ports", data if isinstance(data, list) else [])[:10]
    rows = []
    for p in ports:
        name    = str(p.get("name","?"))[:22]
        vessels = p.get("vessel_count", p.get("traffic", "?"))
        country = p.get("country","?")[:3].upper()
        rows.append(f"  {name:<22} [{country}]  {vessels} vessels")
    send_message(chat_id,
        f"⚓ <b>PORT TRAFFIC INTELLIGENCE</b>\n\n<pre>" + "\n".join(rows) + "</pre>",
        auto_delete_seconds=60
    )


# ─── /mt_news_brief <topic?> ──────────────────────────────────────────────────
def handle_mt_news_brief(chat_id, args):
    topic = " ".join(args) if args else ""
    url = _api("news", f"/api/news/latest?q={topic}&limit=5") if topic else _api("news", "/api/news/latest?limit=5")
    data = safe_get(url)
    if not data:
        send_message(chat_id, "⚠️ News service unavailable (port 5101)", auto_delete_seconds=60)
        return
    articles = data.get("articles", data.get("data", data if isinstance(data, list) else []))[:5]
    if not articles:
        send_message(chat_id, f"📰 No articles found{' for: ' + topic if topic else ''}.", auto_delete_seconds=60)
        return
    lines = [f"📰 <b>NEWS INTELLIGENCE BRIEF</b>"]
    if topic:
        lines.append(f"🔍 Topic: <i>{topic}</i>")
    lines.append("")
    for i, art in enumerate(articles, 1):
        title   = art.get("title", "No title")[:80]
        source  = art.get("source", art.get("publisher", "?"))
        cat     = art.get("category", "")
        lines.append(f"<b>{i}.</b> {title}\n     <i>{source}</i> {('| ' + cat) if cat else ''}")
    send_message(chat_id, "\n".join(lines), auto_delete_seconds=60)


# ─── /mt_sentiment <entity> ───────────────────────────────────────────────────
def handle_mt_sentiment(chat_id, args):
    if not args:
        send_message(chat_id, "⚠️ Usage: <code>/mt_sentiment &lt;entity name&gt;</code>", auto_delete_seconds=60)
        return
    entity = " ".join(args)
    data = safe_get(_api("sentiment", f"/api/sentiment/entity?name={entity}"))
    if not data:
        send_message(chat_id, f"⚠️ Sentiment data unavailable for: <b>{entity}</b>", auto_delete_seconds=60)
        return
    score    = data.get("score", data.get("sentiment_score", "N/A"))
    verdict  = data.get("verdict", data.get("label", "N/A"))
    positive = data.get("positive_pct", "?")
    negative = data.get("negative_pct", "?")
    neutral  = data.get("neutral_pct", "?")
    articles = data.get("article_count", "?")
    msg = (
        f"💬 <b>ENTITY SENTIMENT ANALYSIS</b>\n\n"
        f"Entity   : <b>{entity}</b>\n"
        f"Score    : <b>{score}</b>\n"
        f"Verdict  : {verdict}\n\n"
        f"Positive : {positive}%\n"
        f"Negative : {negative}%\n"
        f"Neutral  : {neutral}%\n"
        f"Articles : {articles}\n"
        f"Time     : {datetime.now().strftime('%H:%M:%S')}"
    )
    send_message(chat_id, msg)


# ─── /mt_entity_map <entity> ──────────────────────────────────────────────────
def handle_mt_entity_map(chat_id, args):
    if not args:
        send_message(chat_id, "⚠️ Usage: <code>/mt_entity_map &lt;entity name&gt;</code>", auto_delete_seconds=60)
        return
    entity = " ".join(args)
    data = safe_get(_api("entity", f"/api/entity/correlations?name={entity}"))
    if not data:
        send_message(chat_id, f"⚠️ Entity data unavailable for: <b>{entity}</b>", auto_delete_seconds=60)
        return
    corrs = data.get("correlations", data if isinstance(data, list) else [])[:8]
    rows  = [f"  → {c.get('name','?'):<25} [{c.get('relation','?')}]" for c in corrs]
    send_message(chat_id,
        f"🕸️ <b>ENTITY CORRELATION MAP</b>\n"
        f"Entity: <b>{entity}</b>\n\n"
        f"<pre>" + ("\n".join(rows) if rows else 'No correlations found.') + "</pre>",
        auto_delete_seconds=60
    )
