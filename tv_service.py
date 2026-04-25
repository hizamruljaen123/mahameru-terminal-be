import os
import json
import time
import urllib.request
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for Solid JS FE

# Location of the data directory relative to this service
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

@app.route('/api/tv/sources', methods=['GET'], strict_slashes=False)
def get_tv_sources():
    """Unified endpoint for IPTV and YouTube resources."""
    try:
        iptv_path = os.path.join(DATA_DIR, 'iptv-sources.json')
        youtube_path = os.path.join(DATA_DIR, 'youtube_streams.json')
        
        sources = []
        
        # 1. Load IPTV sources
        if os.path.exists(iptv_path):
            with open(iptv_path, 'r', encoding='utf-8') as f:
                sources.extend(json.load(f))
                
        # 2. Add individual YouTube streams as sources (marked for direct toggle)
        if os.path.exists(youtube_path):
            with open(youtube_path, 'r', encoding='utf-8') as f:
                yt_streams = json.load(f)
                for stream in yt_streams:
                    stream['group'] = 'LIVE_INTEL'
                    stream['isYoutube'] = True
                    stream['directToggle'] = True
                    sources.append(stream)
                    
        print(f"[{time.strftime('%H:%M:%S')}] SYNC_RESOURCE_MAP: {len(sources)} NODES_READY")
        return jsonify(sources)
    except Exception as e:
        print(f"ERROR_RESOURCE_MAP: {e}")
        return jsonify([]), 500

@app.route('/api/tv/channels', methods=['GET'], strict_slashes=False)
def get_tv_channels():
    """Fetches and parses an M3U playlist URL on the backend."""
    source_url = request.args.get('url')
    
    if not source_url:
        return jsonify({"error": "Missing URL"}), 400
        
    try:
        # Auto-detect YouTube from URL pattern
        is_youtube = "youtube.com/" in source_url
        
        if is_youtube:
            stream_name = request.args.get('name')
            if not stream_name:
                # Extract ID from embed URL for a basic name if missing
                stream_name = source_url.split('/')[-1].split('?')[0]
            return jsonify([{"url": source_url, "name": stream_name, "isYoutube": True}])

        print(f"[{time.strftime('%H:%M:%S')}] PULLING_REMOTE_PLAYLIST: {source_url}")
        
        # Fetch external M3U
        with urllib.request.urlopen(source_url, timeout=10) as response:
            text = response.read().decode('utf-8')
            
        # Parse M3U
        lines = text.split('\n')
        all_channels = []
        current = {}
        
        for line in lines:
            line = line.strip()
            if line.startswith('#EXTINF:'):
                name = line.split(',')[-1].strip() or 'Unknown Node'
                current = {"name": name}
            elif line.strip().startswith('http'):
                if current.get('name'):
                    current['url'] = line
                    all_channels.append(current)
                    current = {}
                    
        # Apply Search Filtering
        search_query = request.args.get('search', '').lower()
        if search_query:
            all_channels = [c for c in all_channels if search_query in c['name'].lower()]
            
        # Pagination
        try:
            page = int(request.args.get('page', 1))
            page_size = int(request.args.get('pageSize', 30))
        except ValueError:
            page = 1
            page_size = 30
            
        total_count = len(all_channels)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        
        paginated_channels = all_channels[start_idx:end_idx]
        
        output = {
            "channels": paginated_channels,
            "totalCount": total_count,
            "page": page,
            "totalPages": (total_count + page_size - 1) // page_size if total_count > 0 else 0
        }
        
        print(f"[{time.strftime('%H:%M:%S')}] DISPATCHING_SEGMENT: {len(paginated_channels)} of {total_count} NODES")
        return jsonify(output)
        
    except Exception as e:
        print(f"ERROR_PLAYLIST_PARSING: {e}")
        return jsonify([]), 500

if __name__ == '__main__':
    print("Initializing Unified TV Intelligence Backend v2.0...")
    print("Listening on https://api.asetpedia.online/tv")
    app.run(host=os.getenv('API_HOST', '0.0.0.0'), debug=True, port=5003, use_reloader=False)
