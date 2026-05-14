import yfinance as yf
import json

def test():
    symbol = "BBCA.JK"
    print(f"Testing yfinance for {symbol}...")
    ticker = yf.Ticker(symbol)
    info = ticker.info
    if info:
        print("Success! Data acquired.")
        # print(json.dumps(info, indent=2, default=str))
        print(f"Name: {info.get('longName')}")
        print(f"Price: {info.get('currentPrice')}")
    else:
        print("Failed. No data returned.")

if __name__ == "__main__":
    test()
