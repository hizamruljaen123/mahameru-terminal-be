import yfinance as yf
import pandas as pd
import talib as ta
import requests
import mplfinance as mpf
import io
import feedparser
from tabulate import tabulate
from datetime import datetime
from urllib.parse import quote

# --- KONFIGURASI ---
TOKEN = "8266806716:AAHTDeGwNUcG97nOzggDu-oryPLqGsrPLG8"
CHAT_ID = "-1003777663997"
SYMBOL = "AAPL"

def get_enhanced_news(symbol):
    """Mengambil berita terbaru dan memformatnya menjadi Clickable HTML Link"""
    query = quote(f"{symbol} stock market analysis")
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(rss_url)
    
    links = []
    # Ambil 4 berita teratas
    for entry in feed.entries[:4]:
        clean_title = entry.title.rsplit(' - ', 1)[0]
        # Format HTML Link untuk Telegram
        links.append(f"🔗 <a href='{entry.link}'>{clean_title}</a>")
    
    return "\n\n".join(links) if links else "No recent news found."

def perform_quant_analysis(symbol):
    """Download data dan hitung indikator menggunakan TA-Lib"""
    # Download data
    df = yf.download(symbol, period="6mo", interval="1d", progress=False)
    
    # PERBAIKAN: Jika yfinance mengembalikan MultiIndex, ratakan kolomnya
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # TA-Lib membutuhkan numpy array (float64) untuk menghindari TypeError
    # Kita pastikan data bersih dari NaN sebelum kalkulasi
    close_prices = df['Close'].astype(float).values
    high_prices = df['High'].astype(float).values
    low_prices = df['Low'].astype(float).values
    open_prices = df['Open'].astype(float).values
    
    # 1. Bollinger Bands
    df['upper'], df['middle'], df['lower'] = ta.BBANDS(close_prices, timeperiod=20)
    
    # 2. ADX (Trend Strength)
    df['ADX'] = ta.ADX(high_prices, low_prices, close_prices, timeperiod=14)
    
    # 3. RSI
    df['RSI'] = ta.RSI(close_prices, timeperiod=14)
    
    # 4. Pattern Recognition (Mendeteksi Engulfing & Doji)
    df['CDL_ENGULFING'] = ta.CDLENGULFING(open_prices, high_prices, low_prices, close_prices)
    df['CDL_DOJI'] = ta.CDLDOJI(open_prices, high_prices, low_prices, close_prices)
    
    return df

def create_advanced_chart(df, symbol):
    """Membuat grafik Candlestick dengan Bollinger Bands & Volume"""
    plot_df = df.tail(60) # Tampilkan jendela 60 hari
    
    # Tambahkan Bollinger Bands sebagai overlay
    apds = [
        mpf.make_addplot(plot_df['upper'], color='#404040', alpha=0.5, width=0.8),
        mpf.make_addplot(plot_df['lower'], color='#404040', alpha=0.5, width=0.8),
        mpf.make_addplot(plot_df['middle'], color='orange', alpha=0.3, width=0.5)
    ]
    
    # Custom Style
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

def send_ultra_report():
    print(f"🚀 Memulai analisis mendalam untuk {SYMBOL}...")
    
    try:
        # Eksekusi Analisis
        df = perform_quant_analysis(SYMBOL)
        news_html = get_enhanced_news(SYMBOL)
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Analisis Logika
        price_now = last['Close']
        pct_change = ((price_now - prev['Close']) / prev['Close']) * 100
        
        # Deteksi Pattern
        pattern_msg = "Neutral"
        if last['CDL_ENGULFING'] > 0: pattern_msg = "🔥 Bullish Engulfing"
        elif last['CDL_ENGULFING'] < 0: pattern_msg = "⚠️ Bearish Engulfing"
        elif last['CDL_DOJI'] > 0: pattern_msg = "⚖️ Doji Detected"

        # Tabel minimalis (Date, Open, Close)
        recent_tab = df.tail(5).copy()
        recent_tab.index = recent_tab.index.strftime('%d/%m')
        table_str = tabulate(recent_tab[['Open', 'Close']], headers=['DATE', 'OPEN', 'CLOSE'], 
                             tablefmt='simple', floatfmt=".2f")

        # Susun Pesan Telegram
        caption = f"<b>🏛️ {SYMBOL} QUANT DASHBOARD</b>\n"
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
        caption += "<i>Indicators: Candlestick, BBands, ADX, RSI</i>"

        # Buat Chart
        chart_buf = create_advanced_chart(df, SYMBOL)

        # Kirim ke Telegram
        url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
        files = {'photo': ('report.png', chart_buf, 'image/png')}
        payload = {
            'chat_id': CHAT_ID, 
            'caption': caption, 
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }
        
        response = requests.post(url, files=files, data=payload)
        
        if response.status_code == 200:
            print(f"✅ Laporan {SYMBOL} berhasil dikirim ke Telegram!")
        else:
            print(f"❌ Gagal kirim: {response.text}")

    except Exception as e:
        print(f"❌ Terjadi kesalahan: {str(e)}")

if __name__ == "__main__":
    send_ultra_report()