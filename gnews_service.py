import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from gnews import GNews
from datetime import datetime
import time

app = Flask(__name__)
CORS(app)

@app.route('/api/gnews/search')
def search_gnews():
    q = request.args.get('q', '')
    lang = request.args.get('lang', 'en')
    country = request.args.get('country', 'US')
    period = request.args.get('period') # If 'None' or empty, we won't pass it to GNews for all-time search
    
    if period == 'None' or not period:
        period = None

    if not q:
        return jsonify({"news": []})
        
    try:
        # Dynamic settings based on request parameters
        google_news = GNews(language=lang, country=country, period=period, max_results=100)
        gn_results = google_news.get_news(q)
        
        news_normalized = []
        if gn_results:
            for item in gn_results:
                title = item.get("title")
                if not title or title == "No Title": continue
                
                try:
                    # GNews usually provides 'published date' in its dictionary results
                    pub_date = item.get('published date') or item.get('publishedAt')
                    if pub_date:
                        # Attempt standard parsing, fallback to current time
                        dt = datetime.strptime(pub_date, '%a, %d %b %Y %H:%M:%S %Z')
                        ts = int(dt.timestamp())
                    else:
                        ts = int(time.time())
                except: 
                    ts = int(time.time())
                
                news_normalized.append({
                    "title": title,
                    "publisher": item.get("publisher", {}).get("title") if isinstance(item.get("publisher"), dict) else item.get("publisher", "INFRA_SOURCE"),
                    "time": ts,
                    "link": item.get("url", item.get("link", "#")),
                    "description": item.get("description", item.get("snippet", ""))
                })
        
        # Sort by time
        news_normalized.sort(key=lambda x: x['time'], reverse=True)
        return jsonify({"status": "success", "data": news_normalized})
    except Exception as e:
        print(f"GNews Service Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host=os.getenv('API_HOST', '0.0.0.0'), debug=True, port=5006)
