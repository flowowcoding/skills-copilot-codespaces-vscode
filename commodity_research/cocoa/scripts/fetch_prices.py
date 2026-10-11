"""Fetch daily ICE cocoa futures (front-month continuous, Yahoo CC=F) and write data/prices_cc.csv.

Yahoo's CC=F is the rolled front-month ICE US cocoa contract (USD/t). London cocoa (C=F) returned
"No data found, symbol may be delisted" when tried on 2026-10-11, so only NY is used.
Note: a front-month continuous series contains roll gaps; returns across roll dates are contaminated
by the calendar spread. We use monthly returns, where roll noise is small relative to cocoa volatility,
and flag it as a caveat in the README.

Usage: python fetch_prices.py [--out ../data/prices_cc.csv] [--ticker CC=F]
"""
import argparse, os, time
import pandas as pd, requests

HERE = os.path.dirname(os.path.abspath(__file__))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"


def fetch(ticker, p1=946684800, p2=None):
    p2 = p2 or int(time.time())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1={p1}&period2={p2}&interval=1d"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=60); r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    d = pd.DataFrame({"date": pd.to_datetime(res["timestamp"], unit="s").normalize(),
                      "open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"], "volume": q["volume"]})
    return d.dropna(subset=["close"]).drop_duplicates("date", keep="last")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ticker", default="CC=F")
    ap.add_argument("--out", default=os.path.join(HERE, "..", "data", "prices_cc.csv"))
    a = ap.parse_args()
    d = fetch(a.ticker)
    d.to_csv(a.out, index=False, float_format="%.2f")
    print(a.ticker, len(d), d.date.min().date(), d.date.max().date(), "->", a.out)


if __name__ == "__main__":
    main()
