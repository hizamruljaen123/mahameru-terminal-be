"""
Crypto Macro & Institutional Flow Module
ETF tracking, stablecoin metrics, fear/greed index, macro indicators.
"""
import requests
import numpy as np
import yfinance as yf
import time
from typing import Dict, Any


ETF_TICKERS = {
    "IBIT": {"name": "iShares Bitcoin Trust (BlackRock)", "type": "BTC"},
    "FBTC": {"name": "Fidelity Wise Origin Bitcoin", "type": "BTC"},
    "GBTC": {"name": "Grayscale Bitcoin Trust", "type": "BTC"},
    "ARKB": {"name": "ARK 21Shares Bitcoin ETF", "type": "BTC"},
    "BITB": {"name": "Bitwise Bitcoin ETF", "type": "BTC"},
    "ETHA": {"name": "iShares Ethereum Trust", "type": "ETH"},
    "ETHE": {"name": "Grayscale Ethereum Trust", "type": "ETH"},
    "FETH": {"name": "Fidelity Ethereum Fund", "type": "ETH"},
}

STABLECOIN_TICKERS = ["USDT-USD", "USDC-USD", "DAI-USD", "BUSD-USD"]


class MacroAnalyzer:
    def __init__(self):
        self._cache = {}
        self._ttl = 900

    def _cached(self, key):
        if key in self._cache and time.time() - self._cache[key]['ts'] < self._ttl:
            return self._cache[key]['data']
        return None

    def _store(self, key, data):
        self._cache[key] = {'ts': time.time(), 'data': data}
        return data

    def get_etf_flows(self):
        ck = "etf_flows"
        c = self._cached(ck)
        if c: return c
        try:
            etf_data = []
            for ticker, meta in ETF_TICKERS.items():
                try:
                    t = yf.Ticker(ticker)
                    info = t.info
                    hist = t.history(period="1mo")
                    if hist.empty: continue
                    price = float(hist['Close'].iloc[-1])
                    prev = float(hist['Close'].iloc[-2]) if len(hist) > 1 else price
                    change = ((price - prev) / prev * 100) if prev > 0 else 0
                    vol = float(hist['Volume'].iloc[-1])
                    avg_vol = float(hist['Volume'].mean())
                    # Volume trend as proxy for flow
                    vol_hist = [{"date": ts.strftime('%Y-%m-%d'),
                        "volume": float(r['Volume']),
                        "close": round(float(r['Close']),2)} for ts, r in hist.iterrows()]
                    etf_data.append({"ticker": ticker, "name": meta['name'],
                        "type": meta['type'], "price": round(price, 2),
                        "change_1d": round(change, 2), "volume": vol,
                        "avg_volume": round(avg_vol, 0),
                        "vol_ratio": round(vol/avg_vol, 2) if avg_vol > 0 else 1,
                        "aum": float(info.get('totalAssets', 0)),
                        "history": vol_hist[-30:]})
                except: continue
            # Aggregate
            total_btc_vol = sum(e['volume'] for e in etf_data if e['type'] == 'BTC')
            total_eth_vol = sum(e['volume'] for e in etf_data if e['type'] == 'ETH')
            return self._store(ck, {"etfs": etf_data,
                "aggregate": {"btc_total_volume": total_btc_vol,
                    "eth_total_volume": total_eth_vol,
                    "total_etfs": len(etf_data)}})
        except Exception as e: return {"error": str(e)}

    def get_stablecoin_metrics(self):
        ck = "stablecoin"
        c = self._cached(ck)
        if c: return c
        try:
            metrics = []
            for ticker in STABLECOIN_TICKERS:
                try:
                    t = yf.Ticker(ticker)
                    info = t.info
                    hist = t.history(period="3mo")
                    if hist.empty: continue
                    name = ticker.replace("-USD", "")
                    mcap = float(info.get('marketCap', 0))
                    price = float(hist['Close'].iloc[-1])
                    vol = float(hist['Volume'].iloc[-1])
                    # Price deviation from $1
                    peg_dev = round((price - 1.0) * 100, 4)
                    hist_data = [{"date": ts.strftime('%Y-%m-%d'),
                        "price": round(float(r['Close']),6),
                        "volume": float(r['Volume'])} for ts, r in hist.iterrows()]
                    metrics.append({"symbol": name, "market_cap": mcap,
                        "price": round(price, 6), "peg_deviation": peg_dev,
                        "volume_24h": vol, "peg_status": "STABLE" if abs(peg_dev) < 0.1 else "DEPEGGED",
                        "history": hist_data[-90:]})
                except: continue
            total_mcap = sum(m['market_cap'] for m in metrics)
            # SSR: BTC Market Cap / Total Stablecoin Market Cap
            try:
                btc_mcap = float(yf.Ticker("BTC-USD").info.get('marketCap', 0))
                ssr = btc_mcap / total_mcap if total_mcap > 0 else 0
            except: ssr = 0
            return self._store(ck, {"stablecoins": metrics,
                "total_market_cap": total_mcap,
                "ssr": round(ssr, 2),
                "ssr_signal": "LOW BUYING POWER" if ssr > 5 else (
                    "HIGH BUYING POWER" if ssr < 2 else "MODERATE")})
        except Exception as e: return {"error": str(e)}

    def get_fear_greed_index(self):
        ck = "fgi"
        c = self._cached(ck)
        if c: return c
        try:
            resp = requests.get("https://api.alternative.me/fng/?limit=30", timeout=10)
            if resp.status_code != 200: return {"error": "API error"}
            data = resp.json().get('data', [])
            history = [{"date": d['timestamp'], "value": int(d['value']),
                "label": d['value_classification']} for d in data]
            current = history[0] if history else {"value": 50, "label": "Neutral"}
            return self._store(ck, {"current": current, "history": history})
        except Exception as e: return {"error": str(e)}

    def get_market_dominance(self):
        ck = "dominance"
        c = self._cached(ck)
        if c: return c
        try:
            major = ["BTC-USD", "ETH-USD", "USDT-USD", "BNB-USD", "SOL-USD",
                     "XRP-USD", "USDC-USD", "ADA-USD", "DOGE-USD", "AVAX-USD"]
            mcaps = {}
            for t in major:
                try:
                    info = yf.Ticker(t).info
                    mcaps[t.replace("-USD","")] = float(info.get('marketCap', 0))
                except: continue
            total = sum(mcaps.values())
            dominance = {k: round(v/total*100, 2) if total > 0 else 0 for k, v in mcaps.items()}
            return self._store(ck, {"dominance": dominance, "total_market_cap": total})
        except Exception as e: return {"error": str(e)}

    def get_full_macro(self):
        return {"etf_flows": self.get_etf_flows(),
            "stablecoin": self.get_stablecoin_metrics(),
            "fear_greed": self.get_fear_greed_index(),
            "dominance": self.get_market_dominance()}

macro_analyzer = MacroAnalyzer()
