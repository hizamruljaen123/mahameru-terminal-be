import requests
import math
from typing import List, Any, Dict, Optional

BINANCE_KLINE_URL = "https://api.binance.com/api/v3/klines"

class CryptoAnalyzer:
    def __init__(self):
        self.timeframes = { "5m": "5m", "15m": "15m", "1h": "1h", "1d": "1d" }

    def get_klines(self, symbol: str, interval: str, limit: int = 100) -> Optional[List[List[Any]]]:
        try:
            bin_symbol = f"{symbol}USDT"
            resp = requests.get(BINANCE_KLINE_URL, params={"symbol": bin_symbol, "interval": interval, "limit": limit}, timeout=5)
            if resp.status_code == 200: 
                data = resp.json()
                if isinstance(data, list): return data
        except: pass
        return None

    # --- Math Helpers ---
    def calculate_sma(self, data: List[float], period: int) -> float:
        if len(data) < period: return 0.0
        return sum(data[-period:]) / period

    def calculate_ema(self, data: List[float], period: int) -> float:
        if not data: return 0.0
        if len(data) < period: return self.calculate_sma(data, period)
        alpha = 2 / (period + 1)
        ema = data[0]
        for price in data[1:]: ema = (price * alpha) + (ema * (1 - alpha))
        return ema

    def calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        if len(prices) < period + 1: return 50.0
        gains = [max(0.0, prices[i] - prices[i-1]) for i in range(1, len(prices))]
        losses = [max(0.0, prices[i-1] - prices[i]) for i in range(1, len(prices))]
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0: return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def calculate_stoch(self, klines: List[List[Any]], period: int = 14) -> float:
        if len(klines) < period: return 50.0
        recent = klines[-period:]
        closes = [float(k[4]) for k in recent]
        highs = [float(k[2]) for k in recent]
        lows = [float(k[3]) for k in recent]
        low_min = min(lows); high_max = max(highs)
        if high_max == low_min: return 50.0
        return 100.0 * (closes[-1] - low_min) / (high_max - low_min)

    def calculate_cci(self, klines: List[List[Any]], period: int = 20) -> float:
        if len(klines) < period: return 0.0
        tp = [(float(k[2]) + float(k[3]) + float(k[4])) / 3.0 for k in klines[-period:]]
        sma_tp = sum(tp) / period
        mean_dev = sum([abs(x - sma_tp) for x in tp]) / period
        if mean_dev == 0: return 0.0
        return (tp[-1] - sma_tp) / (0.015 * mean_dev)

    def calculate_williams_r(self, klines: List[List[Any]], period: int = 14) -> float:
        if len(klines) < period: return -50.0
        recent = klines[-period:]
        highs = [float(k[2]) for k in recent]
        lows = [float(k[3]) for k in recent]
        closes = [float(k[4]) for k in recent]
        h_max = max(highs); l_min = min(lows)
        if h_max == l_min: return -50.0
        return -100.0 * (h_max - closes[-1]) / (h_max - l_min)

    def calculate_atr(self, klines: List[List[Any]], period: int = 14) -> float:
        if len(klines) < period + 1: return 0.0
        tr_list = []
        for i in range(1, len(klines)):
            h = float(klines[i][2]); l = float(klines[i][3]); pc = float(klines[i-1][4])
            tr = max(h - l, abs(h - pc), abs(l - pc))
            tr_list.append(tr)
        return sum(tr_list[-period:]) / period

    def calculate_roc(self, closes: List[float], period: int = 12) -> float:
        if len(closes) < period: return 0.0
        return ((closes[-1] - closes[-period]) / closes[-period]) * 100.0

    def calculate_bull_bear(self, klines: List[List[Any]], period: int = 13) -> tuple:
        if len(klines) < period: return 0.0, 0.0
        closes = [float(k[4]) for k in klines]
        ema = self.calculate_ema(closes, period)
        bull = float(klines[-1][2]) - ema
        bear = float(klines[-1][3]) - ema
        return bull, bear

    # --- Aggregation Methods ---
    def get_detailed_indicators(self, klines: List[List[Any]]) -> List[Dict[str, Any]]:
        closes = [float(k[4]) for k in klines]
        rsi = self.calculate_rsi(closes)
        stoch = self.calculate_stoch(klines)
        cci = self.calculate_cci(klines)
        wr = self.calculate_williams_r(klines)
        roc = self.calculate_roc(closes)
        bull, bear = self.calculate_bull_bear(klines)
        macd = self.calculate_ema(closes, 12) - self.calculate_ema(closes, 26)
        atr = self.calculate_atr(klines)

        return [
            {"name": "RSI (14)", "value": float(round(rsi, 2)), "action": "BUY" if rsi < 30 else "SELL" if rsi > 70 else "NEUTRAL"},
            {"name": "STOCH (14, 3)", "value": float(round(stoch, 2)), "action": "BUY" if stoch < 20 else "SELL" if stoch > 80 else "NEUTRAL"},
            {"name": "CCI (20)", "value": float(round(cci, 2)), "action": "BUY" if cci < -100 else "SELL" if cci > 100 else "NEUTRAL"},
            {"name": "Williams %R", "value": float(round(wr, 2)), "action": "BUY" if wr < -80 else "SELL" if wr > -20 else "NEUTRAL"},
            {"name": "MACD (12, 26)", "value": float(round(macd, 4)), "action": "BUY" if macd > 0 else "SELL"},
            {"name": "ROC", "value": float(round(roc, 2)), "action": "BUY" if roc > 0 else "SELL"},
            {"name": "Bull Power", "value": float(round(bull, 4)), "action": "BUY" if bull > 0 else "SELL"},
            {"name": "Bear Power", "value": float(round(bear, 4)), "action": "BUY" if bear > 0 else "SELL"},
            {"name": "ATR (14)", "value": float(round(atr, 4)), "action": "STABLE" if atr < (closes[-1] * 0.01) else "VOLATILE"},
            {"name": "Momentum", "value": float(round(closes[-1] - closes[-10], 2)) if len(closes) >= 10 else 0.0, "action": "BUY" if (len(closes) >= 10 and closes[-1] > closes[-10]) else "SELL"}
        ]

    def evaluate_ma(self, current_price: float, closes: List[float]) -> str:
        periods = [5, 10, 20, 50, 100, 200]
        buys = 0; sells = 0
        for p in periods:
            if len(closes) >= p:
                sma = self.calculate_sma(closes, p)
                ema = self.calculate_ema(closes, p)
                if current_price > sma: buys += 1
                else: sells += 1
                if current_price > ema: buys += 1
                else: sells += 1
        return self._get_signal(buys, sells)

    def _get_signal(self, buys: int, sells: int) -> str:
        ratio = buys - sells
        if ratio > 4: return "STRONG BUY"
        if ratio > 1: return "BUY"
        if ratio < -4: return "STRONG SELL"
        if ratio < -1: return "SELL"
        return "NEUTRAL"

    def analyze(self, symbol: str) -> Dict[str, Dict[str, Any]]:
        res = {}
        for tf_k, tf_b in self.timeframes.items():
            klines = self.get_klines(symbol, tf_b)
            if not klines: 
                res[tf_k] = {"ma": "N/A", "indicators": "N/A", "summary": "N/A", "details": []}
                continue
            closes = [float(k[4]) for k in klines]
            ma_s = self.evaluate_ma(closes[-1], closes)
            details = self.get_detailed_indicators(klines)
            buys = sum(1 for d in details if d["action"] == "BUY")
            sells = sum(1 for d in details if d["action"] == "SELL")
            ind_s = self._get_signal(buys, sells)
            
            res[tf_k] = {
                "ma": ma_s, "indicators": ind_s, 
                "summary": "STRONG BUY" if (ma_s == "STRONG BUY" or ind_s == "STRONG BUY") else "BUY" if (ma_s == "BUY" or ind_s == "BUY") else "SELL",
                "details": details
            }
        return res

analyzer = CryptoAnalyzer()
