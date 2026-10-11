"""EXPLORATORY (not pre-registered): drift after a hurricane actually reaches the region.

The pre-registered event study showed OJ abnormal returns of about +7% over the 20 trading days after
best-track landfall for citrus hits (8 of 8 positive). That split uses hindsight (the best track).
This script asks whether a real-time rule could have caught it:

  entry  : close of the first trading day (17:00 UTC cutoff) after the first advisory whose
           position is within 100 km of the region at >= 64 kt (a hurricane arriving),
  exit   : 5, 10 or 20 trading days later; long; net of the pre-registered round-trip costs.
  placebo: the same calendar entry day and holding in every other year 2005-2025 with no hurricane
           arrival in that region within +-30 days. Event mean vs placebo distribution by
           resampling one placebo year per event (20,000 draws).

Because the effect was found by looking at all years, the design/holdout split here is NOT an
out-of-sample test. The rule goes to forward testing (README) instead.

Output: results/explore_postlandfall.csv (per event), results/explore_postlandfall_summary.csv

Usage: python explore_postlandfall.py --data ../data --out ../results
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_events import MARKETS, day_on_or_after, load_prices, span_ret, ttest_1s  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    P, R, _ = load_prices(a.data)
    ov = pd.read_csv(os.path.join(a.data, "forecast_overlap.csv"), parse_dates=["init", "avail_utc"])
    arr = ov[(ov.dist0_km <= 100) & (ov.vmax0 >= 64)].sort_values("init").groupby(["region", "storm_id"]).first().reset_index()
    rng = np.random.default_rng(7)
    rows, summ = [], []
    for tk, (region, cost, _) in MARKETS.items():
        r = R[tk]
        dates = r.index
        ar = arr[arr.region == region].sort_values("init")
        ent = []
        for _, e in ar.iterrows():
            i = day_on_or_after(dates, e.avail_utc)
            if i is None or i + 20 >= len(dates):
                continue
            if ent and i <= ent[-1][1] + 5:      # a second arrival within 5 days of the last is skipped
                continue
            ent.append((e, i))
        arr_days = pd.DatetimeIndex([dates[i] for _, i in ent])
        for H in (5, 10, 20):
            ev_ret, plc = [], []
            for e, i in ent:
                x = span_ret(r, i, i + H) * 100 - cost
                ev_ret.append(x)
                d0 = dates[i]
                pl = []
                for y in range(2005, 2026):
                    if y == d0.year:
                        continue
                    try:
                        d = pd.Timestamp(y, d0.month, d0.day)
                    except ValueError:
                        continue
                    j = dates.searchsorted(d)
                    if j + H >= len(dates) or (abs((arr_days - dates[j]).days) <= 30).any():
                        continue
                    pl.append(span_ret(r, j, j + H) * 100 - cost)
                plc.append(pl)
                if H == 20:
                    rows.append(dict(market=tk, storm_id=e.storm_id, name=e["name"], year=e.init.year,
                                     arrival_adv_utc=e.avail_utc, entry=d0.date(), vmax0=e.vmax0,
                                     net_5=span_ret(r, i, i + 5) * 100 - cost, net_10=span_ret(r, i, i + 10) * 100 - cost,
                                     net_20=x, placebo_mean_20=np.mean(pl) if pl else np.nan))
            ev_ret = np.array(ev_ret)
            if len(ev_ret) == 0:
                continue
            draws = np.array([np.mean([rng.choice(p) for p in plc if p]) for _ in range(20000)])
            for smp, msk in [("all", np.ones(len(ent), bool)),
                             ("2005-2017", np.array([e.init.year <= 2017 for e, _ in ent])),
                             ("2018-2026", np.array([e.init.year > 2017 for e, _ in ent]))]:
                x = ev_ret[msk]
                if len(x) == 0:
                    continue
                summ.append(dict(market=tk, hold=H, sample=smp, n=len(x), net_mean=x.mean(), net_median=np.median(x),
                                 hit_rate=(x > 0).mean(), t=ttest_1s(x)[0],
                                 placebo_mean=draws.mean() if smp == "all" else np.nan,
                                 p_vs_placebo=(draws >= ev_ret.mean()).mean() if smp == "all" else np.nan))
    pd.DataFrame(rows).round(3).to_csv(os.path.join(a.out, "explore_postlandfall.csv"), index=False)
    s = pd.DataFrame(summ).round(3)
    s.to_csv(os.path.join(a.out, "explore_postlandfall_summary.csv"), index=False)
    print(s.to_string())


if __name__ == "__main__":
    main()
