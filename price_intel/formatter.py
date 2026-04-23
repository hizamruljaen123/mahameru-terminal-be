import io
import feedparser
import mplfinance as mpf
import pandas as pd
from datetime import datetime
from urllib.parse import quote
from tabulate import tabulate
import logging
from typing import List, Dict

logger = logging.getLogger("PriceIntel.Formatter")

class PriceFormatter:
    @staticmethod
    def get_news(symbol: str, count: int = 4) -> List[Dict]:
        """Fetch latest news for a symbol using Google News RSS"""
        try:
            query = quote(f"{symbol} stock market analysis")
            rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
            feed = feedparser.parse(rss_url)
            
            links = []
            for entry in feed.entries[:count]:
                clean_title = entry.title.rsplit(' - ', 1)[0]
                links.append({"title": clean_title, "link": entry.link})
            return links
        except Exception as e:
            logger.error(f"Error fetching news for {symbol}: {e}")
            return []

    @staticmethod
    def create_chart(df: pd.DataFrame, symbol: str) -> io.BytesIO:
        """Generate mpf chart as bytes"""
        plot_df = df.tail(60)
        
        apds = [
            mpf.make_addplot(plot_df['upper'], color='#404040', alpha=0.5, width=0.8),
            mpf.make_addplot(plot_df['lower'], color='#404040', alpha=0.5, width=0.8),
            mpf.make_addplot(plot_df['middle'], color='orange', alpha=0.3, width=0.5)
        ]
        
        mc = mpf.make_marketcolors(up='#26a69a', down='#ef5350', inherit=True)
        s = mpf.make_mpf_style(base_mpf_style='charles', marketcolors=mc, gridstyle='dotted')
        
        buf = io.BytesIO()
        mpf.plot(plot_df, 
                 type='candle', 
                 style=s, 
                 addplot=apds, 
                 volume=True, 
                 title=f'\n{symbol} QUANTITATIVE ANALYSIS',
                 figsize=(12, 8),
                 savefig=dict(fname=buf, format='png', dpi=180))
        buf.seek(0)
        return buf

    @staticmethod
    def format_caption(df: pd.DataFrame, symbol: str, news: List[Dict]) -> str:
        """Format the Telegram caption"""
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        price_now = float(last['Close'])
        pct_change = ((price_now - prev['Close']) / prev['Close']) * 100
        
        pattern_msg = "Neutral"
        if last['CDL_ENGULFING'] > 0: pattern_msg = "🔥 Bullish Engulfing"
        elif last['CDL_ENGULFING'] < 0: pattern_msg = "⚠️ Bearish Engulfing"
        elif last['CDL_DOJI'] > 0: pattern_msg = "⚖️ Doji Detected"

        recent_tab = df.tail(5).copy()
        recent_tab.index = recent_tab.index.strftime('%d/%m')
        table_str = tabulate(recent_tab[['Open', 'Close']], headers=['DATE', 'OPEN', 'CLOSE'], 
                             tablefmt='simple', floatfmt=".2f")

        news_html = "\n\n".join([f"🔗 <a href='{n['link']}'>{n['title']}</a>" for n in news]) if news else "No recent news found."

        caption = f"<b>🏛️ {symbol} QUANT DASHBOARD</b>\n"
        caption += f"<code>Update: {datetime.now().strftime('%H:%M')}</code>\n"
        caption += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        caption += f"<b>Price:</b> {price_now:.2f} ({pct_change:+.2f}%)\n"
        caption += f"<b>ADX:</b> {last['ADX']:.1f} ({'Strong Trend' if last['ADX'] > 25 else 'Weak Trend'})\n"
        caption += f"<b>RSI:</b> {last['RSI']:.1f}\n"
        caption += f"<b>Candle Pattern:</b> <code>{pattern_msg}</code>\n"
        caption += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        caption += f"<b>📰 RECENT NEWS:</b>\n{news_html}\n"
        caption += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        caption += f"<b>HISTORICAL DATA:</b>\n<pre>{table_str}</pre>\n"
        caption += "<i>Powered by Mahameru Intelligence</i>"
        
        return caption
