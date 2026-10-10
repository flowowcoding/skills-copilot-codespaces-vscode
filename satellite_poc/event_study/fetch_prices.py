"""Download daily prices for every stock and benchmark in the event list.

Usage: fetch_prices.py EVENTS.csv OUT_DIR

Reads the columns `ticker_used` and `benchmark` from EVENTS.csv and saves one CSV per symbol
(date, open, high, low, close, adjclose, volume) from the Yahoo Finance chart API, 2013-01-01
to today. Symbols Yahoo no longer serves (typically delisted companies) are reported and
skipped; the event study records them as missing data instead of dropping them silently.
"""
import sys, os, json, time, datetime as dt, urllib.request
import pandas as pd

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"


def fetch(sym, p1=1356998400, p2=None):
    """Return a DataFrame of daily bars for `sym`, or None if Yahoo has no data."""
    p2 = p2 or int(time.time())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}"
           f"?period1={p1}&period2={p2}&interval=1d&events=div%2Csplit")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        j = json.load(urllib.request.urlopen(req, timeout=30))
    except Exception as e:  # 404 for delisted symbols
        return None
    r = (j.get("chart") or {}).get("result")
    if not r or not r[0].get("timestamp"):
        return None
    r = r[0]
    off = r["meta"].get("gmtoffset", 0)
    q = r["indicators"]["quote"][0]
    adj = r["indicators"].get("adjclose", [{}])[0].get("adjclose", q["close"])
    d = pd.DataFrame({"date": [dt.datetime.fromtimestamp(t + off, dt.timezone.utc).date() for t in r["timestamp"]],
                      "open": q["open"], "high": q["high"], "low": q["low"],
                      "close": q["close"], "adjclose": adj, "volume": q["volume"]})
    return d.dropna(subset=["close"]).drop_duplicates("date", keep="last")


def fname(sym):
    return sym.replace("^", "_").replace("/", "_") + ".csv"


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    ev, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    e = pd.read_csv(ev)
    syms = sorted(set(e.ticker_used.dropna()) | set(e.benchmark.dropna()))
    missing = []
    for s in syms:
        d = fetch(s)
        if d is None:
            missing.append(s); print(f"{s:12s} MISSING"); continue
        d.to_csv(os.path.join(out, fname(s)), index=False)
        print(f"{s:12s} {len(d):5d} rows {d.date.iloc[0]} .. {d.date.iloc[-1]}")
        time.sleep(0.3)
    print("missing:", missing)
