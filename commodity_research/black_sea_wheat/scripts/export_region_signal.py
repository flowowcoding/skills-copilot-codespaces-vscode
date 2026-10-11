#!/usr/bin/env python3
"""Region-level point-in-time indicators (the regional layer of the signal dataset).

For each region, harvest year Y (2008-2026) and forecast date T (the same WASDE-eve and weekly dates
as model.py), the raw region features are computed exactly as model.py sees them (composites usable
at T, weather to T-5, winter mask w121 once usable else w89) and expressed as anomalies against the
same region's values at the same seasonal offset in the years 2003..Y-1 only (no look-ahead):

  evi_w_anom   mean over usable winter-window composites of (EVI - prior-years mean) (winter mask)
  evi_s_anom   same for the spring mask, composites DOY 153-233 (spring-wheat regions only)
  prcp_w_rel   Apr 1..min(T-5, Jun 30) precipitation / prior-years mean - 1
  hdd_w_anom   May 1..min(T-5, Jun 30) heat degree days (>30 C), minus prior-years mean
  frost_w_anom winterkill + spring-frost cell-days, minus prior-years mean
  prcp_s_rel, hdd_s_anom   spring-zone windows (May 1-Jul 31, Jun 1-Aug 10)
  winter_share share of the region's sample cells in the winter mask that year
There is no regional yield truth (Rosstat/Ukrstat regional data were not reachable), so these are
indicators, not regional yield forecasts.

Usage: python export_region_signal.py   ->  data/signal/bsw_region_indicators_v1.csv
"""
import os

import numpy as np
import pandas as pd

import model as M

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "..", "data")


def raw(F, reg, y, t):
    f, ew, es, wsh = F.region(reg, y, t)
    return f, ew, es, wsh


def main():
    T = M.Truth()
    F = M.Feats()
    regions = sorted(F.wx)
    dates = []
    for Y in range(2008, 2027):
        for r in T.releases:
            r = pd.Timestamp(r)
            sm = (r.year - Y) * 12 + r.month - 4
            if 1 <= sm <= 9:
                dates.append((Y, r - pd.Timedelta(days=1), "wasde", r.date()))
        for k in range(40):
            dates.append((Y, pd.Timestamp(Y, 4, 1) + pd.Timedelta(days=7 * k), "weekly", None))
    today = pd.Timestamp("2026-10-11")
    out = []
    cache = {}
    for Y, t, kind, rel in dates:
        if t > today:
            continue
        off = (t - pd.Timestamp(Y, 1, 1)).days
        for reg in regions:
            f, ew, es, wsh = raw(F, reg, Y, t)
            hist = []
            for y in range(M.FIRST_TRAIN, Y):
                key = (reg, y, off)
                if key not in cache:
                    cache[key] = raw(F, reg, y, pd.Timestamp(y, 1, 1) + pd.Timedelta(days=off))
                hist.append(cache[key])
            row = dict(region=reg, year=Y, forecast_date=t.date(), kind=kind, next_release=rel, winter_share=wsh)
            for nm, idx, cur in [("evi_w_anom", 1, ew), ("evi_s_anom", 2, es)]:
                an = []
                for k, v in cur.items():
                    h = [hh[idx][k] for hh in hist if k in hh[idx]]
                    if len(h) >= 4:
                        an.append(v - np.mean(h))
                row[nm] = np.mean(an) if an else np.nan
            for k in ["prcp_w", "prcp_s"]:
                m = np.nanmean([hh[0][k] for hh in hist]) if hist else np.nan
                row[k + "_rel"] = f[k] / m - 1 if np.isfinite(f[k]) and m > 0 else np.nan
            for k in ["hdd_w", "frost_w", "hdd_s"]:
                m = np.nanmean([hh[0][k] for hh in hist]) if hist else np.nan
                row[k + "_anom"] = f[k] - m if np.isfinite(f[k]) else np.nan
            if reg not in M.SPRING_REG:
                row["evi_s_anom"] = row["prcp_s_rel"] = row["hdd_s_anom"] = np.nan
            row["data_cutoff_vi"] = (t - pd.Timedelta(days=14)).date()
            row["data_cutoff_weather"] = (t - pd.Timedelta(days=5)).date()
            row["dataset_version"] = "bsw_region_indicators_v1"
            out.append(row)
    o = pd.DataFrame(out)
    fn = os.path.join(D, "signal", "bsw_region_indicators_v1.csv")
    o.to_csv(fn, index=False, float_format="%.4f")
    print(len(o), "rows ->", fn)


if __name__ == "__main__":
    main()
