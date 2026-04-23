import os
import requests
import logging
import pandas as pd
from typing import Optional, Dict, Any

logger = logging.getLogger("PriceIntel.DeepTA")

# Deep TA Service URL (defined in .env or launcher)
DEEP_TA_URL = os.getenv("DEEP_TA_API_URL", "http://0.0.0.0:5200")

class DeepTAClient:
    """Client to interact with the local deep_ta_service.py"""
    
    @staticmethod
    def get_deep_analysis(symbol: str, method: str) -> Optional[Dict[str, Any]]:
        """
        Initialize session and run a deep analysis function.
        Returns the processed data and company info.
        """
        # 1. Map user methods to service function IDs
        method_map = {
            "master": "master_signal",
            "regime": "market_regime",
            "vdelta": "volume_delta",
            "spectral": "spectral_cycle",
            "smc": "smc_concepts"
        }
        
        func_id = method_map.get(method.lower())
        if not func_id:
            logger.error(f"Method {method} not supported in Deep TA.")
            return None

        try:
            # 2. Initialize Session
            init_url = f"{DEEP_TA_URL}/api/init"
            init_payload = {
                "entity_code": symbol,
                "period": "1y" # We need enough history for deep TA
            }
            init_resp = requests.post(init_url, json=init_payload, timeout=15)
            if init_resp.status_code != 200:
                logger.error(f"Deep TA Init failed: {init_resp.text}")
                return None
            
            init_data = init_resp.json()
            session_id = init_data["session_id"]
            
            # 3. Run Analysis Function
            run_url = f"{DEEP_TA_URL}/api/run/{func_id}?session_id={session_id}"
            run_resp = requests.get(run_url, timeout=30)
            if run_resp.status_code != 200:
                logger.error(f"Deep TA Run failed: {run_resp.text}")
                return None
            
            analysis_result = run_resp.json()
            
            # 4. Get OHLCV Data for Charting
            ohlcv_url = f"{DEEP_TA_URL}/api/data/ohlcv?session_id={session_id}"
            ohlcv_resp = requests.get(ohlcv_url, timeout=10)
            if ohlcv_resp.status_code != 200:
                logger.error(f"Deep TA OHLCV fetch failed: {ohlcv_resp.text}")
                return None
            
            ohlcv_data = ohlcv_resp.json()["data"]
            
            return {
                "method_name": analysis_result.get("function_name"),
                "method_id": func_id,
                "analysis": analysis_result.get("data"),
                "ohlcv": ohlcv_data,
                "symbol": symbol
            }
            
        except Exception as e:
            logger.error(f"Deep TA Client error: {e}")
            return None
