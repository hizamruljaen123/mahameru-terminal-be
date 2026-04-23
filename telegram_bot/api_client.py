import requests
import os

# Base URLs are fetched at call-time so load_dotenv() is guaranteed to have run first
def _market():   return os.getenv('MARKET_SERVICE_URL',    'http://127.0.0.1:8088')
def _crypto():   return os.getenv('CRYPTO_SERVICE_URL',    'http://127.0.0.1:8085')
def _forex():    return os.getenv('FOREX_SERVICE_URL',     'http://127.0.0.1:8086')
def _sentiment():return os.getenv('SENTIMENT_SERVICE_URL', 'http://127.0.0.1:5008')

class AsetpediaAPI:
    @staticmethod
    def get_market_history(symbol, range_val="1M"):
        url = f"{_market()}/api/market/history?symbol={symbol}&range={range_val}"
        try:
            resp = requests.get(url, timeout=10)
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def get_market_fundamental(symbol):
        url = f"{_market()}/api/market/fundamental?symbol={symbol}"
        try:
            resp = requests.get(url, timeout=10)
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def get_crypto_detail(symbol):
        url = f"{_crypto()}/api/crypto/detail/{symbol}"
        try:
            resp = requests.get(url, timeout=10)
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def get_ai_analyze(symbol):
        url = f"{_crypto()}/api/ai/analyze?symbol={symbol}"
        try:
            resp = requests.get(url, timeout=30) # AI takes longer
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def get_market_watchlist():
        url = f"{_market()}/api/market/watchlist"
        try:
            resp = requests.get(url, timeout=10)
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @staticmethod
    def get_forex_list():
        url = f"{_forex()}/api/forex/list"
        try:
            resp = requests.get(url, timeout=10)
            return resp.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}
