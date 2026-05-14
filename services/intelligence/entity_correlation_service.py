import os
import sys
from flask import Flask
from flask_cors import CORS

# Add current directory to path so we can import the module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from entity_correlation.api import correlation_bp

app = Flask(__name__)
CORS(app)

# Register the modular blueprint
app.register_blueprint(correlation_bp, url_prefix='/api/correlation')

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8200)
    args = parser.parse_args()
    
    print(f"[*] Entity Correlation Service starting on port {args.port}")
    app.run(host='0.0.0.0', port=args.port, debug=True)
