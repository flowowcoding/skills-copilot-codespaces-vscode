#!/usr/bin/env python3
"""Download CBOT corn and soybean futures prices from Yahoo Finance.

  * Continuous front month ZC=F (corn) and ZS=F (soybeans), daily, 2000-07 onward.
  * Individual new-crop contracts that Yahoo still serves: it serves LIVE
    contracts and a few recently expired ones (ZSX25.CBT works; ZCZ25.CBT,
    ZCZ24.CBT, ZSX24.CBT ... return "No data found, symbol may be delisted").
    So the true new-crop contract (Dec corn ZCZ, Nov soy ZSX) is available
    only for the 2025 (soy) and 2026 (both) seasons.
  * Teucrium CORN / SOYB ETFs (daily): roll-free new-crop-weighted proxy, 2010/11+.
  * 60-minute bars for the last 730 days (Yahoo limit) for ZC=F, ZS=F and the
    live new-crop contracts: used for an intraday check around the 12:00 ET release.

Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/<sym>?period1=..&period2=..&interval=1d
(browser User-Agent). Daily bars are stamped 00:00 exchange time; `date` is the
CBOT session date. Settlement-based close (13:15 CT, 14:15 ET) comes after a 12:00 ET release,
so a report's event day is the release date itself (and, before 2013, the 08:30 ET
release preceded the 09:30 ET day-session open: also the release date).

Roll handling for the continuous series: Yahoo switches contract at expiry
(business day before the 15th of the expiry month). Corn expiry months H K N U Z,
soybean F H K N Q U X. In each expiry month the session with the largest
volume jump (>2.5x) on days 8-20, else the first session after the 14th, and
the following session are flagged roll=1 (Yahoo's volume switches one session
before the price jump). Analyses drop roll days.

Which contract the continuous series holds on report days (important!):
  corn  Aug report -> Sep (U) contract;  Sep report -> Sep (U) contract if released
        before Sep expiry (always, releases are on the 9th-12th) -> old/new-crop spread risk.
  soy   Aug report -> Aug (Q) contract (expires ~14 Aug);  Sep report -> Sep (U).
  Oct/Nov reports -> Dec corn / Nov soy (new crop) ;  Jan report -> Mar corn / Jan or Mar soy.
fetch_prices.py writes the series as-is; analysis.py quantifies the tracking error
versus ZCZ26/ZSX26/ZSX25 on the report days where both exist.

Usage:
    python -I fetch_prices.py --out OUT_DIR [--start 2000-01-01]
Writes OUT_DIR/cbot_{corn_zc,soy_zs}_daily.csv, OUT_DIR/contracts_daily.csv,
OUT_DIR/etf_daily.csv (Teucrium CORN, SOYB), OUT_DIR/intraday_60m.csv
"""
import argparse
import json
import os
import subprocess
import time

import numpy as np
import pandas as pd

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
EXPIRY = {"corn": {3, 5, 7, 9, 12}, "soy": {1, 3, 5, 7, 8, 9, 11}}
CONTRACTS = ["ZCZ24.CBT", "ZCZ25.CBT", "ZCZ26.CBT", "ZCH27.CBT", "ZSX24.CBT", "ZSX25.CBT", "ZSX26.CBT", "ZSF27.CBT"]


def yahoo(sym, start=None, interval="1d", rng=None):
    if rng:
        q = f"range={rng}&interval={interval}"
    else:
        q = f"period1={int(pd.Timestamp(start).timestamp())}&period2={int(time.time())}&interval={interval}"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?{q}&events=history"
    for i in range(4):
        r = subprocess.run(["curl", "-sS", "-A", UA, "-H", "Accept: application/json", url], capture_output=True)
        try:
            j = json.loads(r.stdout)["chart"]
            if j["result"] is None:
                return None  # e.g. expired contract: "No data found, symbol may be delisted"
            d = j["result"][0]
            break
        except Exception:
            time.sleep(4 * (i + 1))
    else:
        raise RuntimeError(f"yahoo failed for {sym}")
    tz = d["meta"].get("exchangeTimezoneName", "America/Chicago")
    q = d["indicators"]["quote"][0]
    df = pd.DataFrame({"ts": d["timestamp"], "open": q["open"], "high": q["high"], "low": q["low"],
                       "close": q["close"], "volume": q["volume"]})
    t = pd.to_datetime(df.ts, unit="s", utc=True)
    if interval == "1d":
        df["date"] = t.dt.tz_convert(tz).dt.date
        df = df.dropna(subset=["close"]).drop_duplicates("date", keep="last").drop(columns="ts")
        return df.set_index("date").sort_index()
    df["ts_utc"] = t
    return df.dropna(subset=["close"]).drop(columns="ts")


def flag_rolls(df, months):
    df = df.copy()
    idx = pd.to_datetime(df.index)
    df["roll"] = 0
    vr = df.volume / df.volume.shift(1).replace(0, np.nan)
    for (y, m), g in df.groupby([idx.year, idx.month]):
        if m not in months:
            continue
        gi = pd.to_datetime(g.index)
        win = g[(gi.day >= 8) & (gi.day <= 20)]
        lv = np.log(vr.reindex(win.index).astype(float))
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
    for sym, crop, fn in [("ZC=F", "corn", "cbot_corn_zc_daily.csv"), ("ZS=F", "soy", "cbot_soy_zs_daily.csv")]:
        df = yahoo(sym, a.start)
        df["ret"] = np.log(df.close).diff()
        df = flag_rolls(df, EXPIRY[crop])
        df.index.name = "date"
        df.round(6).to_csv(os.path.join(a.out, fn))
        r = df.ret
        print(f"{sym} {df.index.min()}..{df.index.max()} n={len(df)} rolls={df.roll.sum()} "
              f"|ret| roll={r[df.roll == 1].abs().mean():.4f} other={r[df.roll == 0].abs().mean():.4f}")
    rows = []
    for c in CONTRACTS:
        df = yahoo(c, "2018-01-01")
        if df is None:
            print(c, "not available")
            continue
        df["symbol"] = c
        df["ret"] = np.log(df.close).diff()
        rows.append(df.reset_index())
        print(c, df.index.min(), df.index.max(), len(df))
    pd.concat(rows).round(6).to_csv(os.path.join(a.out, "contracts_daily.csv"), index=False)
    # Teucrium single-commodity ETFs (NYSE Arca, close 16:00 ET): CORN holds the 2nd- and
    # 3rd-to-expire corn futures and the following December (approx. 35/30/35); SOYB the
    # 2nd, 3rd and following November soybean contracts. They are a liquid, roll-free
    # NEW-CROP proxy for 2010-06 (CORN) / 2011-09 (SOYB) onward.
    etf = []
    for s in ["CORN", "SOYB"]:
        df = yahoo(s, "2010-01-01")
        df["symbol"] = s
        df["ret"] = np.log(df.close).diff()
        etf.append(df.reset_index())
        print(s, df.index.min(), df.index.max(), len(df))
    pd.concat(etf).round(6).to_csv(os.path.join(a.out, "etf_daily.csv"), index=False)
    intr = []
    for c in ["ZC=F", "ZS=F", "ZCZ26.CBT", "ZSX26.CBT"]:
        df = yahoo(c, interval="60m", rng="730d")
        if df is not None:
            df["symbol"] = c
            intr.append(df)
    x = pd.concat(intr)
    x["ts_utc"] = x.ts_utc.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    x.round(4).to_csv(os.path.join(a.out, "intraday_60m.csv"), index=False)
    print("intraday rows", len(x))


if __name__ == "__main__":
    main()
