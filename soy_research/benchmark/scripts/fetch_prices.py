#!/usr/bin/env python3
"""Download CBOT soybean futures (Yahoo continuous front month ZS=F) and USD/BRL,
and flag roll artefacts.

Why continuous: Yahoo only serves *live* individual contracts (e.g. ZSK27.CBT);
expired contracts (ZSK24.CBT ...) return "No data found", so a properly rolled
series from individual contract settlements cannot be built from free sources
here (CME/Barchart history is paywalled; Stooq/Quandl were unreachable).

Roll handling. Yahoo's ZS=F follows the nearest contract until it expires
(last trading day = business day before the 15th of F,H,K,N,Q,U,X), then jumps
to the next contract; the jump (old/new contract spread) contaminates that day's
return. We locate the roll day in each expiry month as the session in
days 8-20 of the month with the largest volume jump (>2.5x) versus the previous session
(front-month volume collapses into expiry, then recovers on the new contract),
falling back to the first session after the 14th. Yahoo's volume switches one
session before the price jump, so the volume-jump day AND the next session are
flagged ``roll=1``; analyses drop them (results reported both ways).

Usage:
    python fetch_prices.py --out OUT_DIR [--start 2000-01-01]
Writes OUT_DIR/cbot_soy_zs_daily.csv and OUT_DIR/usdbrl_daily.csv
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import time

import numpy as np
import pandas as pd

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
EXPIRY_MONTHS = {1, 3, 5, 7, 8, 9, 11}


def yahoo(sym, start):
    p1 = int(pd.Timestamp(start).timestamp())
    p2 = int(time.time())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={p1}&period2={p2}&interval=1d&events=history"
    for i in range(5):
        r = subprocess.run(["curl", "-sS", "-A", UA, "-H", "Accept: application/json", url], capture_output=True)
        try:
            d = json.loads(r.stdout)["chart"]["result"][0]
            break
        except Exception:
            time.sleep(5 * (i + 1))
    else:
        raise RuntimeError(f"yahoo failed for {sym}: {r.stdout[:200]}")
    tz = d["meta"].get("exchangeTimezoneName", "America/New_York")  # bars stamped 00:00 exchange-local
    q = d["indicators"]["quote"][0]
    df = pd.DataFrame({"ts": d["timestamp"], "open": q["open"], "high": q["high"], "low": q["low"],
                       "close": q["close"], "volume": q["volume"]})
    df["date"] = pd.to_datetime(df.ts, unit="s", utc=True).dt.tz_convert(tz).dt.date
    df = df.dropna(subset=["close"]).drop_duplicates("date", keep="last").drop(columns="ts")
    return df.set_index("date").sort_index()


def flag_rolls(df):
    df = df.copy()
    idx = pd.to_datetime(df.index)
    df["roll"] = 0
    vr = df.volume / df.volume.shift(1).replace(0, np.nan)
    for (y, m), g in df.groupby([idx.year, idx.month]):
        if m not in EXPIRY_MONTHS:
            continue
        gi = pd.to_datetime(g.index)
        win = g[(gi.day >= 8) & (gi.day <= 20)]
        lv = np.log(vr.reindex(win.index))
        if lv.notna().any() and lv.max() > np.log(2.5):
            day = lv.idxmax()  # largest volume jump = switch to the new contract
        else:
            after = g[gi.day > 14]
            if after.empty:
                continue
            day = after.index[0]
        df.loc[day, "roll"] = 1
        # Yahoo's volume switches one session before the price does, so the
        # contract-spread jump in `close` usually lands on the NEXT session:
        # flag both.
        pos = df.index.get_loc(day)
        if pos + 1 < len(df):
            df.iloc[pos + 1, df.columns.get_loc("roll")] = 1
    return df


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", default="2000-01-01")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    zs = yahoo("ZS=F", a.start)
    zs["ret"] = np.log(zs.close).diff()
    zs = flag_rolls(zs)
    zs.index.name = "date"
    zs.to_csv(os.path.join(a.out, "cbot_soy_zs_daily.csv"))
    fx = yahoo("BRL=X", a.start)
    fx.index.name = "date"
    fx[["close"]].to_csv(os.path.join(a.out, "usdbrl_daily.csv"))
    r = zs.ret
    print(f"ZS=F {zs.index.min()}..{zs.index.max()} n={len(zs)} rolls={zs.roll.sum()} "
          f"|ret| roll days={r[zs.roll == 1].abs().mean():.4f} other={r[zs.roll == 0].abs().mean():.4f}")


if __name__ == "__main__":
    main()
