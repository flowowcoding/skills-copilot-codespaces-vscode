#!/usr/bin/env python3
"""Download daily wheat futures prices from the Yahoo chart API (browser User-Agent)
and flag continuous-contract roll artefacts.

Series
  ZW=F   CBOT SRW wheat, continuous front month (2000-)
  KE=F   KC HRW wheat, continuous front month (2000-)
  EBM=F  Euronext (Matif) milling wheat, continuous, as served by Yahoo (history
         length is whatever Yahoo has; reported in the README)
  WEAT   Teucrium Wheat Fund ETF (holds 2nd/3rd CBOT contracts + next Dec; roll-free,
         2011-09-)
  RUB=X  USD/RUB (context only)

Roll handling (as in soy_research/benchmark/scripts/fetch_prices.py): Yahoo's continuous
series jumps to the next contract at expiry (CBOT wheat: H K N U Z; Matif: H K U Z).
In each expiry month the session (day 8-24) with the largest volume jump (>2.5x) is
taken as the switch; it and the following session are flagged roll=1, falling back to
the first session after the 14th. Analyses drop roll days.

Usage:  python fetch_prices.py --out data/prices [--start 2000-01-01]
Writes  OUT/<name>_daily.csv  (date, open, high, low, close, volume, ret, roll)
"""
import argparse
import json
import os
import subprocess
import time

import numpy as np
import pandas as pd

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
SERIES = {"ZW=F": ("cbot_wheat_zw", {3, 5, 7, 9, 12}), "KE=F": ("kc_wheat_ke", {3, 5, 7, 9, 12}),
          "EBM=F": ("matif_wheat_ebm", {3, 5, 9, 12}), "WEAT": ("teucrium_weat", None), "RUB=X": ("usdrub", None)}


def yahoo(sym, start):
    p1 = int(pd.Timestamp(start).timestamp())
    p2 = int(time.time())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}&interval=1d&events=history"
    for i in range(6):
        r = subprocess.run(["curl", "-sS", "-A", UA, "-H", "Accept: application/json", url], capture_output=True)
        try:
            d = json.loads(r.stdout)["chart"]["result"][0]
            break
        except Exception:
            time.sleep(10 * (i + 1))
    else:
        raise RuntimeError(f"yahoo failed for {sym}: {r.stdout[:200]}")
    tz = d["meta"].get("exchangeTimezoneName", "America/New_York")
    q = d["indicators"]["quote"][0]
    df = pd.DataFrame({"ts": d["timestamp"], "open": q["open"], "high": q["high"], "low": q["low"],
                       "close": q["close"], "volume": q["volume"]})
    df["date"] = pd.to_datetime(df.ts, unit="s", utc=True).dt.tz_convert(tz).dt.date
    df = df.dropna(subset=["close"]).drop_duplicates("date", keep="last").drop(columns="ts")
    return df.set_index("date").sort_index()


def flag_rolls(df, months):
    df = df.copy()
    df["roll"] = 0
    if not months:
        return df
    idx = pd.to_datetime(df.index)
    vr = df.volume / df.volume.shift(1).replace(0, np.nan)
    for (y, m), g in df.groupby([idx.year, idx.month]):
        if m not in months:
            continue
        gi = pd.to_datetime(g.index)
        win = g[(gi.day >= 8) & (gi.day <= 24)]
        lv = np.log(vr.reindex(win.index))
        if lv.notna().any() and lv.max() > np.log(2.5):
            day = lv.idxmax()
        else:
            after = g[gi.day > 14]
            if after.empty:
                continue
            day = after.index[0]
        pos = df.index.get_loc(day)
        df.iloc[pos, df.columns.get_loc("roll")] = 1
        if pos + 1 < len(df):
            df.iloc[pos + 1, df.columns.get_loc("roll")] = 1
    return df


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", default="2000-01-01")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for sym, (name, months) in SERIES.items():
        try:
            df = yahoo(sym, a.start)
        except RuntimeError as e:
            print("FAILED", e)
            continue
        df["ret"] = np.log(df.close).diff()
        df = flag_rolls(df, months)
        df.index.name = "date"
        df.to_csv(os.path.join(a.out, f"{name}_daily.csv"))
        r = df.ret
        print(f"{sym} {df.index.min()}..{df.index.max()} n={len(df)} rolls={df.roll.sum()} "
              f"|ret| roll={r[df.roll == 1].abs().mean():.4f} other={r[df.roll == 0].abs().mean():.4f}")
        time.sleep(3)


if __name__ == "__main__":
    main()
