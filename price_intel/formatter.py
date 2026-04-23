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
    def get_news(symbol: str, company_name: str, country: str, count: int = 4) -> List[Dict]:
        """Fetch latest news using company name and localization"""
        try:
            is_indonesia = country.lower() == "indonesia"
            
            # Build better query using name instead of just symbol
            search_query = f"{company_name} market analysis"
            if is_indonesia:
                search_query = f"berita saham {company_name}"
            
            query = quote(search_query)
            
            # Localize if Indonesia
            if is_indonesia:
                rss_url = f"https://news.google.com/rss/search?q={query}&hl=id-ID&gl=ID&ceid=ID:id"
            else:
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
    def format_caption(df: pd.DataFrame, symbol: str, company_name: str, country: str, news: List[Dict]) -> str:
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

        flag = "🇮🇩" if country.lower() == "indonesia" else "🌍"
        caption = f"<b>🏛️ {company_name} ({symbol}) {flag}</b>\n"
        caption += f"<code>Update: {datetime.now().strftime('%H:%M')} | {country}</code>\n"
        caption += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        caption += f"<b>Price:</b> {price_now:.2f} ({pct_change:+.2f}%)\n"
        caption += f"<b>ADX:</b> {last['ADX']:.1f} ({'Strong Trend' if last['ADX'] > 25 else 'Weak Trend'})\n"
        caption += f"<b>RSI:</b> {last['RSI']:.1f}\n"
        caption += f"<b>Candle Pattern:</b> <code>{pattern_msg}</code>\n"
        caption += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        caption += f"<b>📰 RECENT NEWS:</b>\n{news_html}\n"
        caption += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        caption += f"<b>HISTORICAL DATA:</b>\n<pre>{table_str}</pre>\n"
        caption += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        caption += "<i>Powered by Mahameru Intelligence</i>"
        return caption

    @staticmethod
    def format_sentiment_report(symbol: str, company_name: str, country: str, sentiment_dist: Dict[str, int], news: List[Dict]) -> str:
        """Format the Telegram sentiment report"""
        total = sum(sentiment_dist.values())
        if total == 0: total = 1
        
        pos_pct = (sentiment_dist['POSITIVE'] / total) * 100
        neg_pct = (sentiment_dist['NEGATIVE'] / total) * 100
        neu_pct = (sentiment_dist['NEUTRAL'] / total) * 100
        
        flag = "🇮🇩" if country.lower() == "indonesia" else "🌍"
        
        # Build sentiment bar
        bar_len = 15
        pos_chars = int((pos_pct / 100) * bar_len)
        neg_chars = int((neg_pct / 100) * bar_len)
        neu_chars = bar_len - pos_chars - neg_chars
        bar = "🟢" * pos_chars + "⚪" * neu_chars + "🔴" * neg_chars

        caption = f"<b>📊 {company_name} ({symbol}) SENTIMENT ANALYSIS {flag}</b>\n"
        caption += f"<code>Update: {datetime.now().strftime('%H:%M')} | {country}</code>\n"
        caption += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        caption += f"<b>Score: {bar}</b>\n"
        caption += f"🟢 Positive: {pos_pct:.1f}%\n"
        caption += f"⚪ Neutral: {neu_pct:.1f}%\n"
        caption += f"🔴 Negative: {neg_pct:.1f}%\n"
        caption += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        caption += "<b>📰 ANALYZED NEWS:</b>\n"
        
        for n in news:
            s = n.get('sentiment', 'NEUTRAL')
            icon = "🟢" if s == "POSITIVE" else ("🔴" if s == "NEGATIVE" else "⚪")
            caption += f"{icon} <a href='{n['link']}'>{n['title']}</a>\n"
            
        caption += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        caption += "<i>Source: Google News & AI Sentiment Engine</i>"
        
        return caption

    @staticmethod
    def create_deep_ta_chart(ohlcv_data: List[Dict], analysis: Any, method_id: str, symbol: str) -> io.BytesIO:
        """Create advanced institutional-grade charts for Deep TA"""
        df = pd.DataFrame(ohlcv_data)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        
        # We only plot the last 100 bars for clarity
        plot_df = df.tail(100).copy()
        
        # Prepare analysis data
        try:
            ana_df = pd.DataFrame(analysis)
            # Find the index if not present
            if 'index' in ana_df.columns:
                ana_df.set_index(pd.to_datetime(ana_df['index']), inplace=True)
            else:
                ana_df.index = df.index[-len(ana_df):]
            
            ana_plot = ana_df.tail(100)
        except:
            ana_plot = pd.DataFrame()

        fig, axes = mpf.plot(
            plot_df,
            type='candle',
            style='charles',
            title=f"\nDeep Analysis: {method_id.upper()} - {symbol}",
            ylabel='Price',
            volume=True,
            returnfig=True,
            figsize=(12, 8),
            tight_layout=True,
            facecolor='#121212'
        )
        
        ax_main = axes[0]
        ax_vol = axes[2]
        
        # Specialized Overlays
        if method_id == "master" and not ana_plot.empty and 'master_signal_score' in ana_plot.columns:
            ax_vol.set_visible(False)
            ax_master = fig.add_axes(ax_vol.get_position())
            ax_master.plot(ana_plot.index, ana_plot['master_signal_score'], color='gold', lw=2, label='Master Score')
            ax_master.fill_between(ana_plot.index, 0, ana_plot['master_signal_score'], color='gold', alpha=0.2)
            ax_master.set_ylabel('Master Score', color='white')
            ax_master.tick_params(axis='y', colors='white')
            ax_master.axhline(0, color='white', ls='--', alpha=0.3)

        elif method_id == "market_regime" and not ana_plot.empty and 'market_regime' in ana_plot.columns:
            # 0=Ranging, 1=TrendUp, 2=TrendDown, 3=Volatile
            colors = {0: 'gray', 1: 'green', 2: 'red', 3: 'purple'}
            for i in range(len(ana_plot)):
                regime = ana_plot['market_regime'].iloc[i]
                if not np.isnan(regime):
                    ax_main.axvspan(ana_plot.index[-len(ana_plot)+i], ana_plot.index[-len(ana_plot)+i], 
                                   color=colors.get(int(regime), 'white'), alpha=0.1)

        elif method_id == "vdelta" and not ana_plot.empty and 'imbalance_ratio' in ana_plot.columns:
            ax_vol.set_visible(False)
            ax_delta = fig.add_axes(ax_vol.get_position())
            colors = ['green' if x > 0 else 'red' for x in ana_plot['imbalance_ratio']]
            ax_delta.bar(ana_plot.index, ana_plot['imbalance_ratio'], color=colors, alpha=0.8)
            ax_delta.set_ylabel('Delta Ratio', color='white')
            ax_delta.tick_params(axis='y', colors='white')

        elif method_id == "spectral" and not ana_plot.empty and 'dominant_cycle_period' in ana_plot.columns:
            ax_vol.set_visible(False)
            ax_spec = fig.add_axes(ax_vol.get_position())
            ax_spec.plot(ana_plot.index, ana_plot['dominant_cycle_period'], color='cyan', lw=1.5)
            ax_spec.set_ylabel('Cycle Period', color='white')
            ax_spec.tick_params(axis='y', colors='white')
            
        elif method_id == "smc" and not ana_plot.empty and 'break_of_structure' in ana_plot.columns:
            bos = ana_plot[ana_plot['break_of_structure'] != 0]
            for idx, row in bos.iterrows():
                try:
                    price_pt = plot_df.loc[idx, 'high' if row['break_of_structure'] > 0 else 'low']
                    color = 'lime' if row['break_of_structure'] > 0 else 'magenta'
                    ax_main.plot(idx, price_pt, marker='o', color=color, markersize=8)
                except: continue

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=120, facecolor='#121212')
        buf.seek(0)
        plt.close(fig)
        return buf
