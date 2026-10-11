"""Daily COMEX copper futures (HG=F, continuous front month) from Yahoo's public chart API.

Usage:
    python prices.py OUT.csv [--start 2016-01-01]
"""
import argparse, time, datetime as dt
import requests
import pandas as pd


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out"); ap.add_argument("--start", default="2016-01-01"); ap.add_argument("--symbol", default="HG=F")
    a = ap.parse_args()
    p1 = int(dt.datetime.fromisoformat(a.start).timestamp()); p2 = int(time.time())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{a.symbol}?period1={p1}&period2={p2}&interval=1d"
    j = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60).json()["chart"]["result"][0]
    q = j["indicators"]["quote"][0]
    df = pd.DataFrame({"date": pd.to_datetime(j["timestamp"], unit="s").strftime("%Y-%m-%d"), "close": q["close"]}).dropna()
    adj = j["indicators"].get("adjclose")
    df.drop_duplicates("date", keep="last").to_csv(a.out, index=False)
    print(df.date.min(), df.date.max(), len(df))


if __name__ == "__main__":
    main()
