"""
Crypto Derivatives & Market Structure Module
Estimates funding rates, open interest, and liquidation zones from Binance data.
"""
import requests
import numpy as np
import time
from typing import Dict, Any

BINANCE_FAPI = "https://fapi.binance.com"


class DerivativesAnalyzer:
    def __init__(self):
        self._cache = {}
        self._ttl = 300

    def _cached(self, key):
        if key in self._cache and time.time() - self._cache[key]['ts'] < self._ttl:
            return self._cache[key]['data']
        return None

    def _store(self, key, data):
        self._cache[key] = {'ts': time.time(), 'data': data}
        return data

    def get_funding_rates(self, symbol="BTCUSDT"):
        ck = f"funding_{symbol}"
        c = self._cached(ck)
        if c: return c
        try:
            resp = requests.get(f"{BINANCE_FAPI}/fapi/v1/fundingRate",
                params={"symbol": symbol, "limit": 100}, timeout=10)
            if resp.status_code != 200: return {"error": "API error"}
            data = resp.json()
            history = [{"time": int(d['fundingTime']),
                "rate": round(float(d['fundingRate'])*100, 4),
                "mark_price": round(float(d.get('markPrice', 0)), 2)} for d in data]
            current = history[-1] if history else {"rate": 0}
            avg_rate = np.mean([h['rate'] for h in history]) if history else 0
            return self._store(ck, {"symbol": symbol, "current_rate": current['rate'],
                "avg_rate": round(float(avg_rate), 4),
                "sentiment": "OVER-LEVERAGED LONGS" if current['rate'] > 0.01 else (
                    "OVER-LEVERAGED SHORTS" if current['rate'] < -0.01 else "NEUTRAL"),
                "history": history})
        except Exception as e: return {"error": str(e)}

    def get_open_interest(self, symbol="BTCUSDT"):
        ck = f"oi_{symbol}"
        c = self._cached(ck)
        if c: return c
        try:
            resp = requests.get(f"{BINANCE_FAPI}/futures/data/openInterestHist",
                params={"symbol": symbol, "period": "1h", "limit": 100}, timeout=10)
            if resp.status_code != 200:
                # Fallback to current OI
                r2 = requests.get(f"{BINANCE_FAPI}/fapi/v1/openInterest",
                    params={"symbol": symbol}, timeout=10)
                if r2.status_code == 200:
                    d = r2.json()
                    return self._store(ck, {"symbol": symbol,
                        "current_oi": float(d.get('openInterest', 0)),
                        "history": [], "trend": "N/A"})
                return {"error": "API error"}
            data = resp.json()
            history = [{"time": int(d['timestamp']),
                "oi": float(d['sumOpenInterest']),
                "oi_value": float(d['sumOpenInterestValue'])} for d in data]
            current = history[-1]['oi'] if history else 0
            prev = history[-24]['oi'] if len(history) >= 24 else history[0]['oi'] if history else 1
            change = ((current - prev) / prev * 100) if prev > 0 else 0
            return self._store(ck, {"symbol": symbol, "current_oi": current,
                "current_oi_value": history[-1]['oi_value'] if history else 0,
                "change_24h": round(change, 2),
                "trend": "RISING" if change > 2 else ("FALLING" if change < -2 else "STABLE"),
                "history": history})
        except Exception as e: return {"error": str(e)}

    def estimate_liquidation_zones(self, symbol="BTCUSDT"):
        """Estimate liquidation zones from price + OI data."""
        ck = f"liq_{symbol}"
        c = self._cached(ck)
        if c: return c
        try:
            # Get current price
            resp = requests.get(f"{BINANCE_FAPI}/fapi/v1/ticker/price",
                params={"symbol": symbol}, timeout=10)
            if resp.status_code != 200: return {"error": "API error"}
            price = float(resp.json()['price'])

            # Estimate liquidation clusters at common leverage levels
            leverages = [2, 3, 5, 10, 20, 25, 50, 100]
            long_liqs = []
            short_liqs = []
            for lev in leverages:
                # Long liquidation = price * (1 - 1/leverage)
                long_liq = price * (1 - 1/lev)
                short_liq = price * (1 + 1/lev)
                long_liqs.append({"leverage": lev, "price": round(long_liq, 2),
                    "pct_from_current": round((long_liq/price - 1)*100, 2)})
                short_liqs.append({"leverage": lev, "price": round(short_liq, 2),
                    "pct_from_current": round((short_liq/price - 1)*100, 2)})

            return self._store(ck, {"symbol": symbol, "current_price": price,
                "long_liquidations": long_liqs, "short_liquidations": short_liqs,
                "danger_zone_long": f"${long_liqs[3]['price']:,.0f} (10x)",
                "danger_zone_short": f"${short_liqs[3]['price']:,.0f} (10x)"})
        except Exception as e: return {"error": str(e)}

    def get_long_short_ratio(self, symbol="BTCUSDT"):
        ck = f"lsr_{symbol}"
        c = self._cached(ck)
        if c: return c
        try:
            resp = requests.get(f"{BINANCE_FAPI}/futures/data/globalLongShortAccountRatio",
                params={"symbol": symbol, "period": "1h", "limit": 50}, timeout=10)
            if resp.status_code != 200: return {"error": "API error"}
            data = resp.json()
            history = [{"time": int(d['timestamp']),
                "long_pct": round(float(d['longAccount'])*100, 2),
                "short_pct": round(float(d['shortAccount'])*100, 2),
                "ratio": round(float(d['longShortRatio']), 4)} for d in data]
            current = history[-1] if history else {"long_pct": 50, "short_pct": 50, "ratio": 1}
            return self._store(ck, {"symbol": symbol, "current": current, "history": history,
                "bias": "LONG HEAVY" if current['ratio'] > 1.5 else (
                    "SHORT HEAVY" if current['ratio'] < 0.67 else "BALANCED")})
        except Exception as e: return {"error": str(e)}

    def get_full_derivatives(self, symbol):
        sym = symbol.replace("-USD","") + "USDT"
        return {"funding_rates": self.get_funding_rates(sym),
            "open_interest": self.get_open_interest(sym),
            "liquidation_zones": self.estimate_liquidation_zones(sym),
            "long_short_ratio": self.get_long_short_ratio(sym)}

derivatives_analyzer = DerivativesAnalyzer()
