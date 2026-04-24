"""
Crypto On-Chain Intelligence Module
Computes on-chain analytics from yfinance market data.
"""
import numpy as np
import pandas as pd
import yfinance as yf
import time
from typing import Dict, Any, Optional


class OnChainAnalyzer:
    def __init__(self):
        self._cache = {}
        self._ttl = 600

    def _cached(self, key):
        if key in self._cache and time.time() - self._cache[key]['ts'] < self._ttl:
            return self._cache[key]['data']
        return None

    def _store(self, key, data):
        self._cache[key] = {'ts': time.time(), 'data': data}
        return data

    def compute_exchange_flow(self, symbol, period="3mo"):
        ck = f"flow_{symbol}_{period}"
        c = self._cached(ck)
        if c: return c
        try:
            df = yf.Ticker(f"{symbol}-USD").history(period=period)
            if df.empty or len(df) < 5: return {"error": "Insufficient data"}
            df['ret'] = df['Close'].pct_change()
            df['vol_ma'] = df['Volume'].rolling(20).mean()
            df['vol_ratio'] = df['Volume'] / df['vol_ma']
            df['flow_sig'] = df['ret'] * df['vol_ratio']
            df['net_flow'] = -df['flow_sig'] * df['Volume']
            df['cum_flow'] = df['net_flow'].cumsum()
            df['flow_type'] = df['flow_sig'].apply(lambda x: 'INFLOW' if x < -0.01 else ('OUTFLOW' if x > 0.01 else 'NEUTRAL'))
            hist = []
            for ts, r in df.dropna().iterrows():
                hist.append({"date": ts.strftime('%Y-%m-%d'), "net_flow": round(float(r['net_flow']),2),
                    "cumulative": round(float(r['cum_flow']),2), "volume": float(r['Volume']),
                    "vol_ratio": round(float(r['vol_ratio']),2), "type": r['flow_type']})
            rec = df.tail(7).dropna()
            ti = float(rec[rec['net_flow']<0]['net_flow'].sum())
            to = float(rec[rec['net_flow']>0]['net_flow'].sum())
            return self._store(ck, {"symbol": symbol, "flow_history": hist[-90:],
                "summary": {"7d_net_flow": round(ti+to,2), "7d_inflow": round(abs(ti),2), "7d_outflow": round(to,2),
                    "trend": "ACCUMULATION" if (ti+to)>0 else "DISTRIBUTION",
                    "inflow_days": int(rec['flow_type'].value_counts().get('INFLOW',0)),
                    "outflow_days": int(rec['flow_type'].value_counts().get('OUTFLOW',0))}})
        except Exception as e: return {"error": str(e)}

    def detect_whale_activity(self, symbol, period="1mo"):
        ck = f"whale_{symbol}_{period}"
        c = self._cached(ck)
        if c: return c
        try:
            df = yf.Ticker(f"{symbol}-USD").history(period=period)
            if df.empty or len(df) < 20: return {"error": "Insufficient data"}
            df['vol_ma20'] = df['Volume'].rolling(20).mean()
            df['vol_std'] = df['Volume'].rolling(20).std()
            df['z_score'] = (df['Volume'] - df['vol_ma20']) / df['vol_std']
            df['ret'] = df['Close'].pct_change()
            events = []
            for ts, r in df.dropna().iterrows():
                if abs(r['z_score']) > 2:
                    events.append({"date": ts.strftime('%Y-%m-%d'), "volume_usd": round(r['Volume']*r['Close'],0),
                        "z_score": round(float(r['z_score']),2), "price": round(float(r['Close']),2),
                        "change": round(float(r['ret']*100),2),
                        "type": "ACCUMULATION" if r['ret']>0 else "DISTRIBUTION",
                        "magnitude": "MEGA" if abs(r['z_score'])>3 else "LARGE"})
            acc = sum(1 for e in events if e['type']=='ACCUMULATION')
            return self._store(ck, {"symbol": symbol, "whale_events": events[-20:],
                "stats": {"total_events": len(events), "accumulation_events": acc,
                    "distribution_events": len(events)-acc,
                    "whale_pressure": "BUYING" if acc > len(events)/2 else "SELLING"}})
        except Exception as e: return {"error": str(e)}

    def compute_nvt_ratio(self, symbol):
        ck = f"nvt_{symbol}"
        c = self._cached(ck)
        if c: return c
        try:
            t = yf.Ticker(f"{symbol}-USD")
            info = t.info
            df = t.history(period="6mo")
            if df.empty: return {"error": "No data"}
            mcap = float(info.get('marketCap', 0))
            df['tx_vol'] = df['Volume'] * df['Close']
            df['nvt'] = mcap / df['tx_vol'].where(df['tx_vol']>0, 1)
            df['nvt_sig'] = df['nvt'].rolling(28).mean()
            hist = []
            for ts, r in df.dropna().iterrows():
                hist.append({"date": ts.strftime('%Y-%m-%d'), "nvt": round(float(r['nvt']),2),
                    "nvt_signal": round(float(r['nvt_sig']),2) if not np.isnan(r['nvt_sig']) else None,
                    "price": round(float(r['Close']),2)})
            cn = float(df['nvt'].iloc[-1]) if not np.isnan(df['nvt'].iloc[-1]) else 0
            an = float(df['nvt'].mean())
            return self._store(ck, {"symbol": symbol, "current_nvt": round(cn,2), "avg_nvt_6m": round(an,2),
                "assessment": "OVERVALUED" if cn > an*1.5 else ("UNDERVALUED" if cn < an*0.6 else "FAIR VALUE"),
                "history": hist[-90:]})
        except Exception as e: return {"error": str(e)}

    def compute_address_activity(self, symbol):
        ck = f"activity_{symbol}"
        c = self._cached(ck)
        if c: return c
        try:
            df = yf.Ticker(f"{symbol}-USD").history(period="6mo")
            if df.empty or len(df) < 30: return {"error": "Insufficient data"}
            df['ret'] = df['Close'].pct_change()
            df['vol20'] = df['ret'].rolling(20).std() * np.sqrt(365)
            df['vol_ma20'] = df['Volume'].rolling(20).mean()
            df['act_idx'] = (df['Volume']/df['vol_ma20']) / df['vol20'].where(df['vol20']>0, 1)
            mn = df['act_idx'].rolling(30).min()
            mx = df['act_idx'].rolling(30).max()
            df['act_norm'] = (df['act_idx']-mn)/(mx-mn)*100
            hist = []
            for ts, r in df.dropna().iterrows():
                hist.append({"date": ts.strftime('%Y-%m-%d'),
                    "activity_index": round(float(r['act_norm']),1) if not np.isnan(r['act_norm']) else 50,
                    "volume": float(r['Volume']), "price": round(float(r['Close']),2)})
            ca = hist[-1]['activity_index'] if hist else 50
            return self._store(ck, {"symbol": symbol, "current_activity": round(ca,1),
                "trend": "INCREASING" if ca>60 else ("DECREASING" if ca<40 else "STABLE"), "history": hist[-90:]})
        except Exception as e: return {"error": str(e)}

    def get_full_report(self, symbol):
        return {"exchange_flow": self.compute_exchange_flow(symbol),
            "whale_activity": self.detect_whale_activity(symbol),
            "nvt_ratio": self.compute_nvt_ratio(symbol),
            "address_activity": self.compute_address_activity(symbol)}

onchain_analyzer = OnChainAnalyzer()
