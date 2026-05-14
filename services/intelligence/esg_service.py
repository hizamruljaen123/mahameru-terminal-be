"""
ESG & Sustainability Risk Monitor Microservice
ESG scores, environmental metrics, social scores, governance scores, carbon footprint.
Powered by yfinance sustainability data.
"""
import os
import time
import threading
import logging

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
log = logging.getLogger('esg_service')

import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import Dict, Any, List, Optional

app = FastAPI(debug=True, title="ESG & Sustainability Risk Monitor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ESG Watchlist ---
ESG_WATCHLIST = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA",
    "JPM", "BAC", "WFC", "GS", "MS",
    "XOM", "CVX", "COP", "SLB",
    "CAT", "DE", "GE", "MMM",
    "PG", "KO", "PEP", "WMT",
    "UNH", "JNJ", "PFE", "MRK", "ABBV",
    "V", "MA", "DIS", "NFLX", "BA",
]

# --- Cache ---
ESG_CACHE = {}
_CACHE_LOCK = threading.Lock()
CACHE_TTL = 3600  # 1 hour (ESG data changes slowly)

def clean(val):
    if val is None or (isinstance(val, (float, int, np.floating, np.integer)) and (np.isnan(val) or np.isinf(val))):
        return None
    try: return float(val)
    except: return None

def _get_cached(key):
    with _CACHE_LOCK:
        if key in ESG_CACHE and time.time() - ESG_CACHE[key]['ts'] < CACHE_TTL:
            return ESG_CACHE[key]['data']
    return None

def _set_cached(key, data):
    with _CACHE_LOCK:
        ESG_CACHE[key] = {'ts': time.time(), 'data': data}


# ===================== ENDPOINTS =====================

@app.get("/api/esg/score/{symbol}")
def get_esg_score(symbol: str):
    """Full ESG score breakdown for a symbol."""
    cache_key = f"esg_{symbol}"
    cached = _get_cached(cache_key)
    if cached: return {"status": "success", "data": cached}

    try:
        t = yf.Ticker(symbol)

        # Get sustainability data
        try:
            sustainability = t.sustainability
        except:
            sustainability = None

        # Get basic info
        info = t.info

        if sustainability is None or sustainability.empty:
            # Return available info as fallback
            result = {
                "symbol": symbol,
                "company": info.get('longName', info.get('shortName', symbol)),
                "sector": info.get('sector', 'N/A'),
                "industry": info.get('industry', 'N/A'),
                "esg_available": False,
                "note": "ESG data not available from yfinance for this symbol",
                "governance": {
                    "board_size": clean(info.get('boardMembers')),
                    "audit_risk": info.get('auditRisk', 'N/A'),
                    "compensation_risk": info.get('compensationRisk', 'N/A'),
                    "shareholder_rights_risk": info.get('shareHolderRightsRisk', 'N/A'),
                },
                "last_updated": int(time.time())
            }
            _set_cached(cache_key, result)
            return {"status": "success", "data": result}

        # Parse sustainability DataFrame
        esg_data = {}
        for idx, row in sustainability.iterrows():
            key = idx
            val = row.iloc[0] if len(row) > 0 else None
            if isinstance(val, (float, int)):
                if not np.isnan(val) and not np.isinf(val):
                    esg_data[key] = round(float(val), 3) if isinstance(val, float) else int(val)
            else:
                esg_data[key] = str(val) if val is not None else None

        result = {
            "symbol": symbol,
            "company": info.get('longName', info.get('shortName', symbol)),
            "sector": info.get('sector', 'N/A'),
            "industry": info.get('industry', 'N/A'),
            "esg_available": True,
            "esg_scores": {
                "total_esg": esg_data.get('totalEsg'),
                "environment_score": esg_data.get('environmentScore'),
                "social_score": esg_data.get('socialScore'),
                "governance_score": esg_data.get('governanceScore'),
            },
            "raw_data": esg_data,
            "percentile": {
                "esg_percentile": esg_data.get('highestControversy'),
                "peer_group": esg_data.get('peerGroup'),
            },
            "governance": {
                "board_size": clean(info.get('boardMembers')),
                "audit_risk": info.get('auditRisk', 'N/A'),
                "compensation_risk": info.get('compensationRisk', 'N/A'),
                "shareholder_rights_risk": info.get('shareHolderRightsRisk', 'N/A'),
            },
            "last_updated": int(time.time())
        }
        _set_cached(cache_key, result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/esg/sector-average")
def get_sector_averages():
    """Aggregate ESG scores by sector."""
    cached = _get_cached("sector_esg")
    if cached: return {"status": "success", "data": cached}

    try:
        sector_data = {}
        for symbol in ESG_WATCHLIST:
            try:
                cache_key = f"esg_{symbol}"
                cached_esg = _get_cached(cache_key)
                if cached_esg and cached_esg.get('esg_available'):
                    esg_data = cached_esg
                else:
                    t = yf.Ticker(symbol)
                    try:
                        sustainability = t.sustainability
                    except:
                        sustainability = None
                    if sustainability is None or sustainability.empty:
                        continue
                    info = t.info
                    sector = info.get('sector', 'Unknown')
                    total_esg = None
                    for idx, row in sustainability.iterrows():
                        if idx == 'totalEsg':
                            val = row.iloc[0]
                            if isinstance(val, (float, int)) and not np.isnan(val):
                                total_esg = round(float(val), 2)
                    if total_esg is None:
                        continue

                    if sector not in sector_data:
                        sector_data[sector] = {"scores": [], "count": 0}
                    sector_data[sector]["scores"].append(total_esg)
                    sector_data[sector]["count"] += 1
            except Exception as e:
                log.warning(f"SECTOR_ESG[{symbol}]: {e}")
                continue

        # Compute averages
        sectors = []
        for sector, data in sector_data.items():
            avg = np.mean(data['scores']) if data['scores'] else 0
            sectors.append({
                "sector": sector,
                "average_esg_score": round(float(avg), 2),
                "companies_tracked": data['count'],
                "min_score": round(float(min(data['scores'])), 2) if data['scores'] else 0,
                "max_score": round(float(max(data['scores'])), 2) if data['scores'] else 0,
            })

        sectors.sort(key=lambda x: x['average_esg_score'], reverse=True)

        result = {
            "sectors": sectors,
            "total_sectors": len(sectors),
            "last_updated": int(time.time())
        }
        _set_cached("sector_esg", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/esg/controversy")
def get_esg_controversy():
    """Companies with highest ESG controversy."""
    cached = _get_cached("esg_controversy")
    if cached: return {"status": "success", "data": cached}

    try:
        controversies = []
        for symbol in ESG_WATCHLIST:
            try:
                t = yf.Ticker(symbol)
                try:
                    sustainability = t.sustainability
                except:
                    sustainability = None

                if sustainability is None or sustainability.empty:
                    continue

                info = t.info
                controversy = None
                for idx, row in sustainability.iterrows():
                    if idx in ['highestControversy', 'controversyLevel']:
                        val = row.iloc[0]
                        if isinstance(val, (float, int)) and not np.isnan(val):
                            controversy = round(float(val), 2)
                            break

                if controversy and controversy > 0:
                    controversies.append({
                        "symbol": symbol,
                        "company": info.get('longName', info.get('shortName', symbol)),
                        "sector": info.get('sector', 'N/A'),
                        "controversy_score": controversy,
                        "controversy_level": "HIGH" if controversy > 3 else ("MEDIUM" if controversy > 1 else "LOW")
                    })
            except Exception as e:
                log.warning(f"CONTROVERSY[{symbol}]: {e}")
                continue

        controversies.sort(key=lambda x: x['controversy_score'], reverse=True)

        result = {
            "controversies": controversies[:20],
            "total_with_controversy": len(controversies),
            "last_updated": int(time.time())
        }
        _set_cached("esg_controversy", result)
        return {"status": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/esg/summary")
def get_esg_summary():
    """Aggregated ESG overview."""
    try:
        sectors = _get_cached("sector_esg") or {}
        controversy = _get_cached("esg_controversy") or {}

        return {
            "status": "success",
            "data": {
                "sectors": sectors,
                "controversies": controversy,
                "last_updated": int(time.time())
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "esg_service_online", "timestamp": int(time.time())}


if __name__ == "__main__":
    log.info("ESG Risk Monitor starting on port 8190")
    uvicorn.run(app, host="0.0.0.0", port=8190)
