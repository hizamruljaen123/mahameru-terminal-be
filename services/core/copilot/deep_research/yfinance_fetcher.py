"""
yFinance Data Fetcher — Real technical & fundamental data from Yahoo Finance.

Provides two functions:
  - fetch_yfinance_technical(symbol) — OHLCV, RSI, MACD, SMA, support/resistance, volatility
  - fetch_yfinance_fundamental(symbol) — P/E, P/B, ROE, market cap, dividend, analyst targets
"""

import logging
import numpy as np
import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_yfinance_technical(symbol: str) -> dict:
    """Fetch real technical analysis data from yfinance for a symbol.
    
    Returns a dict with:
      - success (bool), symbol, company_name
      - current_price, prev_close, change, change_pct
      - high_6m, low_6m, volume_avg
      - sma20, sma50, rsi_14, macd, macd_signal
      - support, resistance, volatility_20d, data_points
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="6mo")
        
        if hist.empty:
            return {"success": False, "error": f"No historical data for {symbol}"}
        
        # Get current price info
        info = ticker.info or {}
        current_price = info.get("currentPrice") or info.get("regularMarketPrice") or (
            hist["Close"].iloc[-1] if not hist.empty else None
        )
        prev_close = info.get("previousClose") or info.get("regularMarketPreviousClose")
        
        # Calculate basic technical indicators
        close_prices = hist["Close"].values
        high_prices = hist["High"].values
        low_prices = hist["Low"].values
        volumes = hist["Volume"].values
        
        # SMA
        sma20 = np.mean(close_prices[-20:]) if len(close_prices) >= 20 else None
        sma50 = np.mean(close_prices[-50:]) if len(close_prices) >= 50 else None
        
        # RSI (14)
        rsi = None
        if len(close_prices) > 14:
            deltas = np.diff(close_prices)
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            avg_gain = np.mean(gains[-14:])
            avg_loss = np.mean(losses[-14:])
            if avg_loss != 0:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            else:
                rsi = 100 if avg_gain > 0 else 50
        
        # MACD
        macd = None
        macd_signal = None
        if len(close_prices) >= 26:
            ema12 = np.mean(close_prices[-12:])
            ema26 = np.mean(close_prices[-26:])
            macd = ema12 - ema26
            macd_signal = np.mean([ema12 - ema26 for _ in range(9)]) if len(close_prices) >= 34 else macd
        
        # Support & Resistance
        support = float(np.min(low_prices[-20:])) if len(low_prices) >= 20 else float(np.min(low_prices))
        resistance = float(np.max(high_prices[-20:])) if len(high_prices) >= 20 else float(np.max(high_prices))
        
        # Price change
        price_change = float(close_prices[-1] - close_prices[0]) if len(close_prices) > 1 else 0
        price_change_pct = float((price_change / close_prices[0]) * 100) if close_prices[0] != 0 else 0
        
        # Volatility (20-day)
        volatility = float(np.std(close_prices[-20:]) / np.mean(close_prices[-20:]) * 100) if len(close_prices) >= 20 else None
        
        return {
            "success": True,
            "symbol": symbol,
            "current_price": float(current_price) if current_price else None,
            "prev_close": float(prev_close) if prev_close else None,
            "change": price_change,
            "change_pct": round(price_change_pct, 2),
            "high_6m": float(np.max(high_prices)),
            "low_6m": float(np.min(low_prices)),
            "volume_avg": float(np.mean(volumes[-20:])) if len(volumes) >= 20 else float(np.mean(volumes)),
            "sma20": float(sma20) if sma20 else None,
            "sma50": float(sma50) if sma50 else None,
            "rsi_14": round(float(rsi), 2) if rsi else None,
            "macd": float(macd) if macd else None,
            "macd_signal": float(macd_signal) if macd_signal else None,
            "support": support,
            "resistance": resistance,
            "volatility_20d": round(volatility, 2) if volatility else None,
            "data_points": len(hist),
            "company_name": info.get("longName") or info.get("shortName", symbol),
        }
    except Exception as e:
        logger.error(f"[YFINANCE] Technical fetch error for {symbol}: {e}")
        return {"success": False, "error": str(e), "symbol": symbol}


def fetch_yfinance_fundamental(symbol: str) -> dict:
    """Fetch real fundamental data from yfinance for a symbol.
    
    Returns a dict with:
      - success (bool), symbol, company_name
      - sector, industry, market_cap, enterprise_value
      - pe_ratio, forward_pe, pb_ratio, ps_ratio
      - dividend_yield, payout_ratio, eps, forward_eps, book_value
      - revenue, revenue_growth, profit_margins, operating_margins
      - return_on_equity, return_on_assets, debt_to_equity
      - current_ratio, quick_ratio, free_cash_flow
      - beta, 52_week_high, 52_week_low, 50_day_ma, 200_day_ma
      - analyst_target, analyst_high, analyst_low
      - recommendation, number_of_analysts
      - short_ratio, float_shares, shares_outstanding
      - country, currency, exchange, quote_type
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        
        # Key fundamental metrics
        fundamental = {
            "success": True,
            "symbol": symbol,
            "company_name": info.get("longName") or info.get("shortName", symbol),
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "market_cap": info.get("marketCap"),
            "enterprise_value": info.get("enterpriseValue"),
            "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
            "forward_pe": info.get("forwardPE"),
            "pb_ratio": info.get("priceToBook"),
            "ps_ratio": info.get("priceToSalesTrailing12Months"),
            "dividend_yield": info.get("dividendYield"),
            "payout_ratio": info.get("payoutRatio"),
            "eps": info.get("trailingEps"),
            "forward_eps": info.get("forwardEps"),
            "book_value": info.get("bookValue"),
            "revenue": info.get("totalRevenue"),
            "revenue_growth": info.get("revenueGrowth"),
            "profit_margins": info.get("profitMargins"),
            "operating_margins": info.get("operatingMargins"),
            "return_on_equity": info.get("returnOnEquity"),
            "return_on_assets": info.get("returnOnAssets"),
            "debt_to_equity": info.get("debtToEquity"),
            "current_ratio": info.get("currentRatio"),
            "quick_ratio": info.get("quickRatio"),
            "free_cash_flow": info.get("freeCashflow"),
            "operating_cash_flow": info.get("operatingCashflow"),
            "earnings_growth": info.get("earningsGrowth"),
            "beta": info.get("beta"),
            "52_week_high": info.get("fiftyTwoWeekHigh"),
            "52_week_low": info.get("fiftyTwoWeekLow"),
            "50_day_ma": info.get("fiftyDayAverage"),
            "200_day_ma": info.get("twoHundredDayAverage"),
            "analyst_target": info.get("targetMeanPrice"),
            "analyst_high": info.get("targetHighPrice"),
            "analyst_low": info.get("targetLowPrice"),
            "recommendation": info.get("recommendationKey"),
            "number_of_analysts": info.get("numberOfAnalystOpinions"),
            "short_ratio": info.get("shortRatio"),
            "float_shares": info.get("floatShares"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "country": info.get("country"),
            "currency": info.get("currency"),
            "exchange": info.get("exchange"),
            "quote_type": info.get("quoteType"),
        }
        
        # Clean NaN/inf values for presentation
        for k, v in fundamental.items():
            if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                fundamental[k] = None
        
        return fundamental
    except Exception as e:
        logger.error(f"[YFINANCE] Fundamental fetch error for {symbol}: {e}")
        return {"success": False, "error": str(e), "symbol": symbol}
