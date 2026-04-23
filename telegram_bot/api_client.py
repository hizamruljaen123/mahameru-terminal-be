import requests
import os

# Base URLs for backend services
MARKET_SERVICE = os.getenv('MARKET_SERVICE_URL', 'http://localhost:8088')
CRYPTO_SERVICE = os.getenv('CRYPTO_SERVICE_URL', 'http://localhost:8085')
FOREX_SERVICE = os.getenv('FOREX_SERVICE_URL', 'http://localhost:8086')
SENTIMENT_SERVICE = os.getenv('SENTIMENT_SERVICE_URL', 'http://localhost:5008')

class AsetpediaAPI:
    @staticmethod
    def get_market_history(symbol, range_val="1M"):
        url = f"{MARKET_SERVICE}/api/market/history?symbol={symbol}&range={range_val}"
        try:
            resp = requests.get(url, timeout=10)
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def get_market_fundamental(symbol):
        url = f"{MARKET_SERVICE}/api/market/fundamental?symbol={symbol}"
        try:
            resp = requests.get(url, timeout=10)
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def get_crypto_detail(symbol):
        url = f"{CRYPTO_SERVICE}/api/crypto/detail/{symbol}"
        try:
            resp = requests.get(url, timeout=10)
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def get_ai_analyze(symbol):
        url = f"{CRYPTO_SERVICE}/api/ai/analyze?symbol={symbol}"
        try:
            resp = requests.get(url, timeout=30) # AI takes longer
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def get_market_watchlist():
        url = f"{MARKET_SERVICE}/api/market/watchlist"
        try:
            resp = requests.get(url, timeout=10)
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def get_forex_list():
        url = f"{FOREX_SERVICE}/api/forex/list"
        try:
            resp = requests.get(url, timeout=10)
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}
