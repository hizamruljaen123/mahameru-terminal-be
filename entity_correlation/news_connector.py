import requests

class NewsConnector:
    def __init__(self, gnews_url="https://api.asetpedia.online/gnews"):
        self.gnews_url = gnews_url

    def get_entity_news(self, query):
        """
        Fetch current news for an entity from the GNews service, 
        prioritizing Indonesian and Global results.
        """
        try:
            # Mengambil berita lokal Indonesia
            params_id = {
                "q": query,
                "lang": "id",
                "country": "id",
                "max_results": 5
            }
            
            # Mengambil berita Global (Inggris)
            params_en = {
                "q": query,
                "lang": "en",
                "max_results": 5
            }

            news_results = []

            # Request ID
            resp_id = requests.get(f"{self.gnews_url}/api/gnews/search", params=params_id, timeout=8)
            if resp_id.status_code == 200:
                news_results.extend(resp_id.json().get("news", []))

            # Request EN
            resp_en = requests.get(f"{self.gnews_url}/api/gnews/search", params=params_en, timeout=8)
            if resp_en.status_code == 200:
                news_results.extend(resp_en.json().get("news", []))

            return news_results[:10]
        except Exception as e:
            print(f"Error connecting to GNews via Connector: {e}")
            return []
