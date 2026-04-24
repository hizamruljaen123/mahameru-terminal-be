"""
Crypto Quantitative Analytics Module
Correlation matrix, drawdown analysis, beta, volatility surface, Sharpe ratio.
All derived from yfinance historical data.
"""
import numpy as np
import pandas as pd
import yfinance as yf
import time
from typing import Dict, Any


BENCHMARK_TICKERS = {
    "BTC": "BTC-USD", "ETH": "ETH-USD", "SPX": "^GSPC",
    "GOLD": "GC=F", "DXY": "DX-Y.NYB", "NASDAQ": "^IXIC",
    "CRUDE": "CL=F", "BONDS": "^TNX"
}


class QuantAnalyzer:
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

    def compute_correlation_matrix(self, symbol, period="6mo"):
        ck = f"corr_{symbol}_{period}"
        c = self._cached(ck)
        if c: return c
        try:
            tickers = [f"{symbol}-USD"] + list(BENCHMARK_TICKERS.values())
            tickers = list(dict.fromkeys(tickers))  # dedupe
            data = yf.download(tickers, period=period, progress=False)['Close']
            if data.empty: return {"error": "No data"}
            returns = data.pct_change().dropna()
            corr = returns.corr()
            labels = []
            for t in tickers:
                for k, v in BENCHMARK_TICKERS.items():
                    if v == t: labels.append(k); break
                else: labels.append(t.replace("-USD",""))
            matrix = []
            for i, r in enumerate(corr.values):
                row = []
                for j, v in enumerate(r):
                    row.append(round(float(v), 3) if not np.isnan(v) else 0)
                matrix.append(row)
            # Pairwise correlation list for the target asset
            target_corr = []
            target_idx = 0
            for i, lbl in enumerate(labels):
                if i == target_idx: continue
                target_corr.append({"asset": lbl, "correlation": matrix[target_idx][i]})
            target_corr.sort(key=lambda x: abs(x['correlation']), reverse=True)
            return self._store(ck, {"symbol": symbol, "labels": labels,
                "matrix": matrix, "target_correlations": target_corr})
        except Exception as e: return {"error": str(e)}

    def compute_drawdown_analysis(self, symbol, period="1y"):
        ck = f"dd_{symbol}_{period}"
        c = self._cached(ck)
        if c: return c
        try:
            df = yf.Ticker(f"{symbol}-USD").history(period=period)
            if df.empty: return {"error": "No data"}
            df['peak'] = df['Close'].cummax()
            df['drawdown'] = (df['Close'] - df['peak']) / df['peak'] * 100
            # Find top 5 drawdown events
            dd_events = []
            in_dd = False
            dd_start = None
            dd_max = 0
            dd_max_date = None
            for ts, r in df.iterrows():
                if r['drawdown'] < -1:
                    if not in_dd:
                        in_dd = True
                        dd_start = ts
                        dd_max = r['drawdown']
                        dd_max_date = ts
                    elif r['drawdown'] < dd_max:
                        dd_max = r['drawdown']
                        dd_max_date = ts
                else:
                    if in_dd:
                        dd_events.append({"start": dd_start.strftime('%Y-%m-%d'),
                            "bottom": dd_max_date.strftime('%Y-%m-%d'),
                            "recovery": ts.strftime('%Y-%m-%d'),
                            "max_drawdown": round(float(dd_max), 2),
                            "duration_days": (ts - dd_start).days})
                        in_dd = False
                        dd_max = 0
            # If still in drawdown
            if in_dd:
                dd_events.append({"start": dd_start.strftime('%Y-%m-%d'),
                    "bottom": dd_max_date.strftime('%Y-%m-%d'),
                    "recovery": "ONGOING",
                    "max_drawdown": round(float(dd_max), 2),
                    "duration_days": (df.index[-1] - dd_start).days})
            dd_events.sort(key=lambda x: x['max_drawdown'])
            # Drawdown history for chart
            dd_hist = [{"date": ts.strftime('%Y-%m-%d'),
                "drawdown": round(float(r['drawdown']),2),
                "price": round(float(r['Close']),2)} for ts, r in df.iterrows()]
            current_dd = round(float(df['drawdown'].iloc[-1]), 2)
            max_dd = round(float(df['drawdown'].min()), 2)
            return self._store(ck, {"symbol": symbol, "current_drawdown": current_dd,
                "max_drawdown": max_dd, "events": dd_events[:10],
                "history": dd_hist[-365:]})
        except Exception as e: return {"error": str(e)}

    def compute_beta(self, symbol, period="1y"):
        ck = f"beta_{symbol}_{period}"
        c = self._cached(ck)
        if c: return c
        try:
            tickers = [f"{symbol}-USD", "BTC-USD", "^GSPC"]
            data = yf.download(tickers, period=period, progress=False)['Close']
            if data.empty: return {"error": "No data"}
            returns = data.pct_change().dropna()
            asset_ret = returns[f"{symbol}-USD"] if f"{symbol}-USD" in returns.columns else returns.iloc[:,0]
            betas = {}
            for bench_name, bench_col in [("BTC", "BTC-USD"), ("SPX", "^GSPC")]:
                if bench_col in returns.columns:
                    bench_ret = returns[bench_col]
                    cov = asset_ret.cov(bench_ret)
                    var = bench_ret.var()
                    beta = cov / var if var > 0 else 0
                    betas[bench_name] = round(float(beta), 3)
            return self._store(ck, {"symbol": symbol, "betas": betas,
                "interpretation": {k: ("HIGH RISK" if abs(v) > 1.5 else
                    "MODERATE" if abs(v) > 0.8 else "LOW RISK") for k, v in betas.items()}})
        except Exception as e: return {"error": str(e)}

    def compute_volatility_metrics(self, symbol, period="1y"):
        ck = f"vol_{symbol}_{period}"
        c = self._cached(ck)
        if c: return c
        try:
            df = yf.Ticker(f"{symbol}-USD").history(period=period)
            if df.empty or len(df) < 30: return {"error": "Insufficient data"}
            df['ret'] = df['Close'].pct_change()
            # Rolling volatility windows
            for w in [7, 14, 30, 60, 90]:
                df[f'vol_{w}d'] = df['ret'].rolling(w).std() * np.sqrt(365) * 100
            # Volatility term structure
            latest = {}
            for w in [7, 14, 30, 60, 90]:
                v = df[f'vol_{w}d'].iloc[-1]
                latest[f"{w}d"] = round(float(v), 2) if not np.isnan(v) else 0
            # History for 30d rolling vol
            vol_hist = []
            for ts, r in df.dropna().iterrows():
                vol_hist.append({"date": ts.strftime('%Y-%m-%d'),
                    "vol_7d": round(float(r['vol_7d']),2) if not np.isnan(r['vol_7d']) else 0,
                    "vol_30d": round(float(r['vol_30d']),2) if not np.isnan(r['vol_30d']) else 0,
                    "vol_90d": round(float(r['vol_90d']),2) if not np.isnan(r['vol_90d']) else 0,
                    "price": round(float(r['Close']),2)})
            # Sharpe ratio (annualized, risk-free = 4.5%)
            ann_ret = float(df['ret'].mean() * 365)
            ann_vol = float(df['ret'].std() * np.sqrt(365))
            sharpe = (ann_ret - 0.045) / ann_vol if ann_vol > 0 else 0
            sortino_downside = float(df[df['ret']<0]['ret'].std() * np.sqrt(365))
            sortino = (ann_ret - 0.045) / sortino_downside if sortino_downside > 0 else 0
            return self._store(ck, {"symbol": symbol, "term_structure": latest,
                "annualized_return": round(ann_ret*100, 2),
                "annualized_vol": round(ann_vol*100, 2),
                "sharpe_ratio": round(float(sharpe), 3),
                "sortino_ratio": round(float(sortino), 3),
                "history": vol_hist[-180:]})
        except Exception as e: return {"error": str(e)}

    def get_full_quant(self, symbol):
        return {"correlation": self.compute_correlation_matrix(symbol),
            "drawdown": self.compute_drawdown_analysis(symbol),
            "beta": self.compute_beta(symbol),
            "volatility": self.compute_volatility_metrics(symbol)}

quant_analyzer = QuantAnalyzer()
