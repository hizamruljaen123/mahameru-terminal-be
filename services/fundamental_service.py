import yfinance as yf
import requests

def clean_data(val):
    import numpy as np
    import pandas as pd
    if val is None:
        return None
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return None
        return f
    except:
        return None

def fetch_wikipedia_summary(company_name):
    """
    Fetches a summary from Wikipedia for the given company name.
    Uses a two-step process: search for the best matching title, then fetch the summary.
    """
    headers = {
        'User-Agent': 'AsetpediaTerminal/1.0 (https://asetpedia.online; research@asetpedia.online)'
    }
    try:
        # Step 1: Search for the best matching title
        search_url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": company_name,
            "format": "json",
            "srlimit": 1
        }
        search_res = requests.get(search_url, params=search_params, headers=headers, timeout=5)
        
        if search_res.status_code == 200:
            search_data = search_res.json()
            search_results = search_data.get('query', {}).get('search', [])
            
            if search_results:
                best_title = search_results[0]['title']
                
                # Step 2: Fetch the summary for the found title
                summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{best_title.replace(' ', '_')}"
                summary_res = requests.get(summary_url, headers=headers, timeout=5)
                
                if summary_res.status_code == 200:
                    summary_data = summary_res.json()
                    return summary_data.get('extract', "Tidak ada ringkasan Wikipedia.")
    except Exception as e:
        print(f"Wikipedia fetch error for {company_name}: {e}")
    
    return None


def get_fundamental_data(symbol):
    ticker = yf.Ticker(symbol)
    info = ticker.info
    
    financials = {}
    if ticker.financials is not None and not ticker.financials.empty:
        for col in ticker.financials.columns[:4]: # Last 4 years
            year = str(col)[:4]
            financials[year] = {str(idx): clean_data(ticker.financials.loc[idx, col]) for idx in ticker.financials.index}

    company_name = info.get("longName") or info.get("shortName", symbol)
    wiki_summary = fetch_wikipedia_summary(company_name)

    snapshot = {
        "symbol": symbol,
        "name": company_name,
        "sector": info.get("sector", "N/A"),
        "industry": info.get("industry", "N/A"),
        "currency": info.get("currency", "USD"),
        "country": info.get("country", "N/A"),
        "website": info.get("website", ""),
        "fullTimeEmployees": clean_data(info.get("fullTimeEmployees")),
        "marketCap": clean_data(info.get("marketCap")),
        "enterpriseValue": clean_data(info.get("enterpriseValue")),
        "trailingPE": clean_data(info.get("trailingPE")),
        "forwardPE": clean_data(info.get("forwardPE")),
        "pegRatio": clean_data(info.get("pegRatio")),
        "priceToBook": clean_data(info.get("priceToBook")),
        "priceToSales": clean_data(info.get("priceToSalesTrailing12Months")),
        "evToEbitda": clean_data(info.get("enterpriseToEbitda")),
        "evToRevenue": clean_data(info.get("enterpriseToRevenue")),
        "grossMargins": clean_data(info.get("grossMargins")),
        "operatingMargins": clean_data(info.get("operatingMargins")),
        "profitMargins": clean_data(info.get("profitMargins")),
        "returnOnEquity": clean_data(info.get("returnOnEquity")),
        "returnOnAssets": clean_data(info.get("returnOnAssets")),
        "trailingEps": clean_data(info.get("trailingEps")),
        "forwardEps": clean_data(info.get("forwardEps")),
        "bookValue": clean_data(info.get("bookValue")),
        "revenuePerShare": clean_data(info.get("revenuePerShare")),
        "dividendYield": clean_data(info.get("dividendYield")),
        "dividendRate": clean_data(info.get("dividendRate")),
        "payoutRatio": clean_data(info.get("payoutRatio")),
        "trailingAnnualDividendYield": clean_data(info.get("trailingAnnualDividendYield")),
        "debtToEquity": clean_data(info.get("debtToEquity")),
        "currentRatio": clean_data(info.get("currentRatio")),
        "quickRatio": clean_data(info.get("quickRatio")),
        "totalCash": clean_data(info.get("totalCash")),
        "totalCashPerShare": clean_data(info.get("totalCashPerShare")),
        "totalDebt": clean_data(info.get("totalDebt")),
        "freeCashflow": clean_data(info.get("freeCashflow")),
        "leveredFreeCashflow": clean_data(info.get("leveredFreeCashflow")),
        "operatingCashflow": clean_data(info.get("operatingCashflow")),
        "totalRevenue": clean_data(info.get("totalRevenue")),
        "revenueGrowth": clean_data(info.get("revenueGrowth")),
        "quarterlyRevenueGrowth": clean_data(info.get("quarterlyRevenueGrowth")),
        "earningsGrowth": clean_data(info.get("earningsGrowth")),
        "earningsQuarterlyGrowth": clean_data(info.get("earningsQuarterlyGrowth")),
        "ebitda": clean_data(info.get("ebitda")),
        "grossProfits": clean_data(info.get("grossProfits")),
        "netIncomeToCommon": clean_data(info.get("netIncomeToCommon")),
        "week52High": clean_data(info.get("fiftyTwoWeekHigh")),
        "week52Low": clean_data(info.get("fiftyTwoWeekLow")),
        "fiftyDayAverage": clean_data(info.get("fiftyDayAverage")),
        "twoHundredDayAverage": clean_data(info.get("twoHundredDayAverage")),
        "beta": clean_data(info.get("beta")),
        "floatShares": clean_data(info.get("floatShares")),
        "sharesOutstanding": clean_data(info.get("sharesOutstanding")),
        "shortRatio": clean_data(info.get("shortRatio")),
        "shortPercentOfFloat": clean_data(info.get("shortPercentOfFloat")),
        "recommendationKey": info.get("recommendationKey", "N/A"),
        "wikipedia_summary": wiki_summary,
        "companyOfficers": info.get("companyOfficers", [])[:10]
    }
    # Sector mapping and global indices
    SECTOR_ETF = {
        'Technology': 'XLK',
        'Financial Services': 'XLF',
        'Communication Services': 'XLC',
        'Consumer Cyclical': 'XLY',
        'Industrials': 'XLI',
        'Healthcare': 'XLV',
        'Energy': 'XLE',
        'Consumer Defensive': 'XLP',
        'Basic Materials': 'XLB',
        'Utilities': 'XLU',
        'Real Estate': 'XLRE'
    }
    
    sector = snapshot.get("sector")
    sector_etf = SECTOR_ETF.get(sector, 'SPY') # fallback to SPY
    
    macro_data = {}
    
    # Fetch Sector ETF close
    try:
        etf_ticker = yf.Ticker(sector_etf)
        etf_hist = etf_ticker.history(period="5d")
        if not etf_hist.empty:
            macro_data["sector_etf"] = {
                "ticker": sector_etf,
                "sector": sector,
                "price": clean_data(etf_hist['Close'].iloc[-1]),
                "prev_close": clean_data(etf_hist['Close'].iloc[-2]) if len(etf_hist) > 1 else None
            }
    except:
        pass

    # Fetch Global Indices
    indices = {
        "^GSPC": "S&P 500",
        "^NDX": "Nasdaq 100",
        "^JKSE": "IHSG"
    }
    macro_data["indices"] = []
    
    for idx_sym, idx_name in indices.items():
        try:
            idx_ticker = yf.Ticker(idx_sym)
            idx_hist = idx_ticker.history(period="5d")
            if not idx_hist.empty:
                close_p = clean_data(idx_hist['Close'].iloc[-1])
                prev_p = clean_data(idx_hist['Close'].iloc[-2]) if len(idx_hist) > 1 else close_p
                chg = ((close_p - prev_p) / prev_p) * 100 if prev_p else 0
                
                macro_data["indices"].append({
                    "symbol": idx_sym,
                    "name": idx_name,
                    "price": close_p,
                    "change_pct": clean_data(chg)
                })
        except:
            pass

    return {"snapshot": snapshot, "financials": financials, "macro_data": macro_data}
