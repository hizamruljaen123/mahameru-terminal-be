from flask import Blueprint, jsonify, request
from .engine import CorrelationEngine
from .news_connector import NewsConnector

correlation_bp = Blueprint('entity_correlation', __name__)
engine = CorrelationEngine()
news_connector = NewsConnector()

@correlation_bp.route('/search', methods=['GET'])
def search():
    query = request.args.get('q', '')
    results = engine.search_entities(query)
    return jsonify({"success": True, "data": results})

@correlation_bp.route('/details/<symbol>', methods=['GET'])
def details(symbol):
    info = engine.get_entity_details(symbol)
    if info:
        return jsonify({"success": True, "data": info})
    else:
        return jsonify({"success": False, "message": "Entity not found"}), 404

@correlation_bp.route('/news/<query>', methods=['GET'])
def get_news(query):
    results = news_connector.get_entity_news(query)
    return jsonify({"success": True, "data": results})

@correlation_bp.route('/management/<symbol>', methods=['GET'])
def get_management(symbol):
    results = engine.get_management(symbol)
    return jsonify({"success": True, "data": results})

@correlation_bp.route('/history/<symbol>', methods=['GET'])
def get_history(symbol):
    period = request.args.get('period', '1mo')
    results = engine.get_history(symbol, period=period)
    return jsonify({"success": True, "data": results})

@correlation_bp.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "active", "module": "entity_correlation"})
