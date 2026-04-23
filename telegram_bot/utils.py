def format_ohlcv_table(history_data, limit=20):
    """
    Formats the last N rows of OHLCV data into a readable string table.
    """
    if not history_data:
        return "No data available."
    
    # Take last N rows
    data = history_data[-limit:]
    
    header = "DATE       | OPEN      | HIGH      | LOW       | CLOSE     \n"
    separator = "-" * 55 + "\n"
    
    rows = []
    for item in data:
        # Shorten date if it's too long
        d = item['date'][:10]
        o = f"{item['open']:>10.2f}"
        h = f"{item['high']:>10.2f}"
        l = f"{item['low']:>10.2f}"
        c = f"{item['close']:>10.2f}"
        rows.append(f"{d} | {o} | {h} | {l} | {c}")
    
    table = header + separator + "\n".join(rows)
    return f"```\n{table}\n```"

def format_news(news_list, limit=5):
    """Formats news items into a string."""
    if not news_list:
        return "No recent news found."
    
    formatted = []
    for item in news_list[:limit]:
        title = item.get('title', 'No Title')
        source = item.get('source', 'Unknown')
        url = item.get('url', '#')
        formatted.append(f"• *{title}*\n  Source: {source} | [Link]({url})")
    
    return "\n\n".join(formatted)

def format_fundamental(snap):
    """Formats fundamental snapshot."""
    if not snap:
        return "Fundamental data not available."
    
    lines = [
        f"🏢 *{snap.get('name', 'N/A')}* ({snap.get('symbol', 'N/A')})",
        f"Sector: {snap.get('sector', 'N/A')}",
        f"Price: {snap.get('currency', 'USD')} {snap.get('week52High', 0):.2f} (52W High)",
        "-" * 20,
        f"Market Cap: {snap.get('marketCap', 0):,.0f}",
        f"P/E Ratio: {snap.get('trailingPE', 0):.2f}",
        f"Div Yield: {snap.get('dividendYield', 0):.2f}%",
        f"Rev Growth: {snap.get('revenueGrowth', 0):.2f}%"
    ]
    return "\n".join(lines)
