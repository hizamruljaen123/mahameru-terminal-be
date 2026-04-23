import io
import feedparser
import mplfinance as mpf
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
from urllib.parse import quote
from tabulate import tabulate
import logging
from typing import List, Dict, Any

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
        """Create highly specialized institutional-grade charts tailored to each method"""
        df = pd.DataFrame(ohlcv_data)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        plot_df = df.tail(100).copy()
        
        try:
            ana_df = pd.DataFrame(analysis)
            if 'index' in ana_df.columns:
                ana_df.set_index(pd.to_datetime(ana_df['index']), inplace=True)
            else:
                ana_df.index = df.index[-len(ana_df):]
            ana_plot = ana_df.tail(100)
        except:
            ana_plot = pd.DataFrame()

        # Define specialized styles and subplots based on method
        apds = []
        fig_height = 8
        
        if method_id == "master" and 'master_signal_score' in ana_plot.columns:
            # Oscillator style with fill
            score = ana_plot['master_signal_score']
            apds.append(mpf.make_addplot(score, panel=1, color='gold', secondary_y=False, ylabel='Master Score'))
            # Fill logic handled after plot via axes
            
        elif method_id == "market_regime" and 'hurst_exponent' in ana_plot.columns:
            # Hurst exponent as a secondary sub-indicator
            apds.append(mpf.make_addplot(ana_plot['hurst_exponent'], panel=1, color='cyan', ylabel='Hurst'))
            apds.append(mpf.make_addplot([0.5]*len(ana_plot), panel=1, color='white', linestyle='--', alpha=0.3))

        elif method_id == "vdelta" and 'cumulative_delta' in ana_plot.columns:
            # Cumulative Delta as an area plot on panel 1
            apds.append(mpf.make_addplot(ana_plot['cumulative_delta'], panel=1, type='line', color='lime', ylabel='Cum Delta'))

        elif method_id == "spectral" and 'dominant_cycle_period' in ana_plot.columns:
            # Cycle Period line
            apds.append(mpf.make_addplot(ana_plot['dominant_cycle_period'], panel=1, color='magenta', ylabel='Cycle Period'))

        elif method_id == "smc":
            # Just price with specific markers/levels
            pass

        # Create Plot
        fig, axes = mpf.plot(
            plot_df,
            type='candle',
            style='charles',
            title=f"\nMAHAMERU DEEP ENGINE: {method_id.upper()} - {symbol}",
            ylabel='Price',
            volume=True if method_id != "vdelta" else False,
            addplot=apds,
            returnfig=True,
            figsize=(12, 10 if method_id != "smc" else 8),
            tight_layout=True,
            facecolor='#0a0a0a' # Setting dark background for the whole figure
        )
        
        ax_main = axes[0]
        fig.set_facecolor('#0a0a0a')
        for ax in axes:
            ax.set_facecolor('#121212')
            ax.tick_params(colors='white', which='both')
            ax.yaxis.label.set_color('white')
            ax.xaxis.label.set_color('white')

        # Post-Processing: Tailored touches
        if method_id == "master" and len(axes) > 2:
            ax_score = axes[2]
            # Fill color based on positive/negative
            ax_score.fill_between(range(len(ana_plot)), 0, ana_plot['master_signal_score'], 
                                 where=(ana_plot['master_signal_score'] >= 0), color='green', alpha=0.3)
            ax_score.fill_between(range(len(ana_plot)), 0, ana_plot['master_signal_score'], 
                                 where=(ana_plot['master_signal_score'] < 0), color='red', alpha=0.3)
            ax_score.axhline(0, color='white', alpha=0.2)

        elif method_id == "market_regime":
            # Robust background coloring
            colors = {0: '#404040', 1: '#004d00', 2: '#4d0000', 3: '#4d004d'}
            for i in range(len(ana_plot)):
                reg = ana_plot['market_regime'].iloc[i]
                if not np.isnan(reg):
                    ax_main.axvspan(i-0.5, i+0.5, color=colors.get(int(reg), '#000'), alpha=0.2)

        elif method_id == "vdelta" and len(axes) > 2:
            ax_delta = axes[2]
            ax_delta.fill_between(range(len(ana_plot)), 0, ana_plot['cumulative_delta'], color='lime', alpha=0.2)

        elif method_id == "smc":
            # Draw potential Order Blocks from recent data
            # Check for high volume bars or extrema
            bos = ana_plot[ana_plot['break_of_structure'] != 0]
            for i, (idx, row) in enumerate(bos.iterrows()):
                pos = plot_df.index.get_loc(idx)
                color = 'lime' if row['break_of_structure'] > 0 else 'magenta'
                ax_main.plot(pos, plot_df.iloc[pos]['high' if row['break_of_structure'] > 0 else 'low'], 
                            marker='o', color=color, markersize=10, alpha=0.8)
                # Draw a short horizontal line for the BOS level
                level = plot_df.iloc[pos]['close']
                ax_main.axhline(level, xmin=pos/len(plot_df), xmax=(pos+10)/len(plot_df), color=color, ls='--', alpha=0.5)

        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=120, facecolor='#0a0a0a')
        buf.seek(0)
        plt.close(fig)
        return buf

    @staticmethod
    def format_deep_ta_table(analysis: Any, method_id: str) -> str:
        """Format the latest deep analysis values into a clean table"""
        try:
            ana_df = pd.DataFrame(analysis)
            latest = ana_df.iloc[-1].to_dict()
            
            rows = []
            if method_id == "master":
                rows = [
                    ["Master Score", f"{latest.get('master_signal_score', 0):.2f}"],
                    ["Confidence", "High" if abs(latest.get('master_signal_score', 0)) > 1.5 else "Moderate"]
                ]
            elif method_id == "market_regime":
                regimes = {0: "Ranging", 1: "Trend Up", 2: "Trend Down", 3: "Volatile"}
                rows = [
                    ["Regime", regimes.get(int(latest.get('market_regime', 0)), "Unknown")],
                    ["Confidence", f"{latest.get('regime_confidence', 0)*100:.1f}%"],
                    ["Hurst Exp", f"{latest.get('hurst_exponent', 0.5):.2f}"]
                ]
            elif method_id == "vdelta":
                rows = [
                    ["Delta Ratio", f"{latest.get('imbalance_ratio', 0):.2f}"],
                    ["Cum Delta", f"{latest.get('cumulative_delta', 0):.0f}"],
                    ["Buy Vol", f"{latest.get('buy_volume', 0):.0f}"]
                ]
            elif method_id == "spectral":
                rows = [
                    ["Dom. Period", f"{latest.get('dominant_cycle_period', 0):.1f}"],
                    ["Cycle Score", f"{latest.get('spectral_density_score', 0):.2f}"],
                    ["Entropy", f"{latest.get('spectral_entropy', 0):.2f}"]
                ]
            elif method_id == "smc":
                rows = [
                    ["BOS Signal", "Bullish" if latest.get('break_of_structure', 0) > 0 else ("Bearish" if latest.get('break_of_structure', 0) < 0 else "None")],
                    ["Character", "Changing" if latest.get('change_of_character', 0) != 0 else "Steady"]
                ]

            table_str = tabulate(rows, headers=["METRIC", "VALUE"], tablefmt="simple")
            return f"<pre>{table_str}</pre>"
        except Exception as e:
            logger.error(f"Error formatting deep ta table: {e}")
            return "<i>Detailed data unavailable</i>"
