"""Download daily continuous front-month futures from the Yahoo Finance chart API.

Tickers: OJ=F (ICE FCOJ-A), NG=F (Henry Hub), CL=F (WTI), RB=F (RBOB gasoline), CT=F (ICE cotton #2),
ZR=F (CBOT rough rice), SB=F (ICE sugar #11, world raw sugar -- context only).

Yahoo "=F" series are the unadjusted nearest contract: on the day Yahoo switches to the next
contract the series jumps by the calendar spread. `analyze_events.py` detects those roll days
(approximate exchange expiry calendar + volume/price-jump check) and removes them.

Output: data/prices/<TICKER>.csv  (date, open, high, low, close, volume)

Usage: python fetch_prices.py --out ../data/prices [--start 2004-01-01]
"""
import argparse
import json
import os
import subprocess
from datetime import datetime, timezone

import pandas as pd

TICKERS = ["OJ=F", "NG=F", "CL=F", "RB=F", "CT=F", "ZR=F", "SB=F"]
UA = "Mozilla/5.0"


def fetch(t, start):
    p1 = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp())
    p2 = int(datetime.now(timezone.utc).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{t}?period1={p1}&period2={p2}&interval=1d"
    raw = subprocess.run(["curl", "-sS", "-f", "-A", UA, url], capture_output=True, check=True).stdout
    r = json.loads(raw)["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    df = pd.DataFrame({"date": pd.to_datetime(r["timestamp"], unit="s").normalize(),
                       "open": q["open"], "high": q["high"], "low": q["low"],
                       "close": q["close"], "volume": q["volume"]})
    return df.dropna(subset=["close"]).drop_duplicates("date", keep="last")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", default="2004-01-01")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for t in TICKERS:
        df = fetch(t, a.start)
        df.to_csv(os.path.join(a.out, t.replace("=F", "") + ".csv"), index=False)
        print(t, len(df), df.date.min().date(), df.date.max().date())


if __name__ == "__main__":
    main()
