import requests

def search_entities(query):
    try:
        # Panggil backend mahameru-terminal-be (port 8088)
        # Sesuai route @app.get("/api/entity/search")
        res = requests.get(f"https://api.asetpedia.online/entity/api/entity/search?q={query}", timeout=5)
        if res.status_code == 200:
            return res.json().get('quotes', [])
    except:
        pass
    return []
