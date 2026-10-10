"""Rank-space metrics on an Umbra stack from umbra.py (tests A4 and B4).

All values are per-collect percentile ranks, so gain and scaling differences between collects
cancel. ZONE is a lon/lat box lon0,lat0,lon1,lat1. Control = valid pixels more than BUF_M metres
outside the zone. A collect is used only if it covers at least 70% of the zone.

    python umbra_metrics.py bright STACK.npz ZONE OUT.csv
        A4: per collect, the share of zone pixels brighter than the collect's 95th-percentile
        control pixel, minus 5% (the share expected by chance). Steel structures and buildings are
        strong radar reflectors, so this should grow as a plant is built.

    python umbra_metrics.py change STACK.npz ZONE OUT.csv [MAX_DINC]
        B4: for each collect, the previous collect with the same orbit direction and look side,
        and incidence within MAX_DINC degrees (default 10), taken within 45 days. Each image is
        smoothed 3x3, ranked over the pixels both cover, and scored as the share of zone pixels
        whose rank moved by more than 0.3 minus the same share in control.
"""
import sys

import numpy as np
import pandas as pd
from scipy import stats
from scipy.ndimage import uniform_filter

BUF_M, MINCOV = 200, 0.7


def load(stack, zone):
    d = np.load(stack)
    amp = d["amp"]
    lon0, lat0, lon1, lat1 = d["bbox"]
    T, H, W = amp.shape
    z = [float(v) for v in zone.split(",")]
    xs = lambda lon: (lon - lon0) / (lon1 - lon0) * W
    ys = lambda lat: (lat1 - lat) / (lat1 - lat0) * H
    yy, xx = np.mgrid[:H, :W]
    zm = (xx >= xs(z[0])) & (xx <= xs(z[2])) & (yy >= ys(z[3])) & (yy <= ys(z[1]))
    pad = BUF_M / float(d["res"])
    near = (xx >= xs(z[0]) - pad) & (xx <= xs(z[2]) + pad) & (yy >= ys(z[3]) - pad) & (yy <= ys(z[1]) + pad)
    meta = pd.DataFrame(dict(date=pd.to_datetime(d["dates"]), orbit=d["orbit"], look=d["look"],
                             incidence=d["incidence"]))
    return amp, zm, ~near, meta


def ranks(a, valid):
    r = np.full(a.shape, np.nan, np.float32)
    v = a[valid].astype(np.float64)
    r[valid] = stats.rankdata(v) / len(v)
    return r


def bright(stack, zone, out):
    amp, zm, ctrl, meta = load(stack, zone)
    rows = []
    for i in range(len(amp)):
        v = amp[i] > 0
        cov = v[zm].mean()
        if cov < MINCOV:
            continue
        a = uniform_filter(amp[i].astype(np.float32), 3)
        thr = np.percentile(a[v & ctrl], 95)
        rows.append(dict(meta.iloc[i], coverage=round(cov, 3),
                         bright_excess_pct=round(((a[v & zm] > thr).mean() - 0.05) * 100, 3)))
    df = pd.DataFrame(rows)
    df.to_csv(out, index=False)
    t = (df["date"] - df["date"].min()).dt.days
    rho, p = stats.spearmanr(t, df["bright_excess_pct"])
    print(df.to_string())
    print(f"A4: n={len(df)} Spearman rho vs time = {rho:+.3f} (p={p:.3g})")
    for (o, l), g in df.groupby(["orbit", "look"]):
        if len(g) >= 5:
            r, pp = stats.spearmanr((g["date"] - g["date"].min()).dt.days, g["bright_excess_pct"])
            print(f"   {o:10s} {l:5s} n={len(g):2d} rho={r:+.2f} p={pp:.3f}")


def change(stack, zone, out, max_dinc=10.0):
    amp, zm, ctrl, meta = load(stack, zone)
    sm = [uniform_filter(a.astype(np.float32), 3) for a in amp]
    rows = []
    for i in range(len(amp)):
        cand = meta.index[(meta.index < i) & (meta.orbit == meta.orbit[i]) & (meta.look == meta.look[i])
                          & ((meta.incidence - meta.incidence[i]).abs() <= max_dinc)
                          & ((meta.date[i] - meta.date).dt.days <= 45)]
        if not len(cand):
            continue
        j = cand.max()
        v = (amp[i] > 0) & (amp[j] > 0)
        if v[zm].mean() < MINCOV:
            continue
        dr = np.abs(ranks(sm[i], v) - ranks(sm[j], v))
        big = dr > 0.3
        rows.append(dict(date=meta.date[i], prev=meta.date[j], orbit=meta.orbit[i], look=meta.look[i],
                         d_inc=round(abs(meta.incidence[i] - meta.incidence[j]), 1),
                         zone_pct=round(big[v & zm].mean() * 100, 2), ctrl_pct=round(big[v & ctrl].mean() * 100, 2)))
    df = pd.DataFrame(rows)
    df["excess_pct"] = df["zone_pct"] - df["ctrl_pct"]
    df.to_csv(out, index=False)
    print(df.to_string())
    h1 = df[df.date < "2025-07-01"]["excess_pct"]
    h2 = df[df.date >= "2025-07-01"]["excess_pct"]
    t, p = stats.ttest_ind(h2, h1, equal_var=False)
    print(f"B4: Jan-Jun 2025 mean {h1.mean():.2f} (n={len(h1)})  Jul-Nov 2025 mean {h2.mean():.2f} (n={len(h2)})"
          f"  t={t:+.2f} p={p:.3f}")


if __name__ == "__main__":
    if sys.argv[1] == "bright":
        bright(*sys.argv[2:5])
    elif sys.argv[1] == "change":
        change(*sys.argv[2:5], *(float(v) for v in sys.argv[5:6]))
    else:
        sys.exit(__doc__)
