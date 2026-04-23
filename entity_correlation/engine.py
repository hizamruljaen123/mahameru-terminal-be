import yfinance as yf
import pandas as pd
import numpy as np

class CorrelationEngine:
    def __init__(self):
        pass

    def search_entities(self, query):
        if not query:
            return []
        try:
            search = yf.Search(query, max_results=10)
            return search.quotes
        except Exception as e:
            print(f"Error searching entities: {e}")
            return []

    def get_entity_details(self, symbol):
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            return {
                "symbol": symbol,
                "name": info.get('longName', symbol),
                "sector": info.get('sector'),
                "industry": info.get('industry'),
                "country": info.get('country'),
                "businessSummary": info.get('longBusinessSummary')
            }
        except Exception as e:
            print(f"Error getting entity details: {e}")
            return None

    def get_management(self, symbol):
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            officers = info.get('companyOfficers', [])
            
            management = []
            for officer in officers:
                management.append({
                    "name": officer.get('name'),
                    "title": officer.get('title'),
                    "age": officer.get('age'),
                    "total_pay": officer.get('totalPay')
                })
            return management
        except Exception as e:
            print(f"Management fetch error for {symbol}: {e}")
            return []

    def get_history(self, symbol, period="1mo"):
        """
        Fetch historical price data.
        period can be: 1d, 5d, 1mo, 3mo, 6mo, 1y, 5y
        """
        try:
            ticker = yf.Ticker(symbol)
            # Use interval based on period
            interval = "1h" if period == "1d" else ("1h" if period == "5d" else "1d")
            hist = ticker.history(period=period, interval=interval)
            
            if hist.empty:
                return []
                
            # Formatting data for frontend chart
            data = []
            for date, row in hist.iterrows():
                data.append({
                    "date": date.strftime('%Y-%m-%d %H:%M'),
                    "price": round(float(row['Close']), 2)
                })
            return data
        except Exception as e:
            print(f"History fetch error for {symbol}: {e}")
            return []
