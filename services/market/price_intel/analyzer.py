import yfinance as yf
import pandas as pd
import talib as ta
import logging
from typing import Optional

logger = logging.getLogger("PriceIntel.Analyzer")

class PriceAnalyzer:
    @staticmethod
    def perform_analysis(symbol: str, period: str = "6mo") -> Optional[dict]:
        """Quantitative analysis using TA-Lib and metadata fetching"""
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval="1d")
            
            if df.empty:
                logger.warning(f"No data found for {symbol}")
                return None
            
            # Fetch company info
            info = ticker.info
            company_info = {
                "name": info.get("longName") or info.get("shortName") or symbol,
                "country": info.get("country", "Unknown")
            }

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # Ensure clean data for TA-Lib
            close = df['Close'].astype(float).values
            high = df['High'].astype(float).values
            low = df['Low'].astype(float).values
            open_p = df['Open'].astype(float).values
            
            # Indicators
            df['upper'], df['middle'], df['lower'] = ta.BBANDS(close, timeperiod=20)
            df['ADX'] = ta.ADX(high, low, close, timeperiod=14)
            df['RSI'] = ta.RSI(close, timeperiod=14)
            
            # Patterns
            df['CDL_ENGULFING'] = ta.CDLENGULFING(open_p, high, low, close)
            df['CDL_DOJI'] = ta.CDLDOJI(open_p, high, low, close)
            
            return {
                "df": df,
                "info": company_info
            }
        except Exception as e:
            logger.error(f"Analysis error for {symbol}: {e}")
            return None
