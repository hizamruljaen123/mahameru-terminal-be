from flask import Flask, render_template
import os

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    # Using port 5500 for the scratch tool
    print("=:: LAUNCHING ASETPEDIA LIVE TERMINAL (FLASK container) ::= ")
    print("Open http://localhost:5500 in your browser")
    app.run(host='0.0.0.0', port=5500, debug=True)
