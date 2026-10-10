"""Optical (Sentinel-2) mine activity index per zone, for dry sites with few clouds.
Per pair of consecutive clear images: share of zone pixels whose brightness (red + SWIR)
changed by more than THRESH in log terms, after normalising each image by the median of
the natural-ground control, minus the same share over control. Busy pixels are picked
before CALIB_END and scored after it, as in the radar version.
Usage: optical_zones.py STACK.npz ZONES_JSON CALIB_END OUT.csv"""
import json, sys
import numpy as np, pandas as pd

THRESH, BUF = 0.12, 15
SHADOW = float(sys.argv[5]) if len(sys.argv) > 5 else -9   # drop pixels darker than this (log, vs control) in either image
stack, zones, calib_end, out = sys.argv[1], json.loads(sys.argv[2]), sys.argv[3], sys.argv[4]
d = np.load(stack)
refl, dates = d["refl"].astype(np.float32), pd.to_datetime(d["dates"])
keep = ~dates.duplicated(keep="last")          # same scene processed twice -> keep one
refl, dates = refl[keep], dates[keep]
b = refl.sum(1); b[(refl == 0).any(1)] = np.nan            # brightness, NaN where masked
H, W = b.shape[1:]
yy, xx = np.mgrid[:H, :W]
masks, taken, near = {}, np.zeros((H, W), bool), np.zeros((H, W), bool)
for name, (x0, x1, y0, y1) in zones.items():
    m = (xx >= x0) & (xx <= x1) & (yy >= y0) & (yy <= y1)
    masks[name] = m & ~taken; taken |= m
    near |= (xx >= x0 - BUF) & (xx <= x1 + BUF) & (yy >= y0 - BUF) & (yy <= y1 + BUF)
ctrl = ~near
lb = np.log(b) - np.nanmedian(np.log(b)[:, ctrl], axis=1)[:, None, None]   # sun angle / haze
ch = np.abs(np.diff(lb, axis=0)); dark = (lb < SHADOW)
ok = np.isfinite(ch) & ~dark[1:] & ~dark[:-1]; big = (ch > THRESH) & ok
dd = dates[1:]
cal = dd < pd.Timestamp(calib_end)
freq = big[cal].sum(0) / np.maximum(ok[cal].sum(0), 1)
busy = freq > np.quantile(freq[ctrl], 0.9)
share = lambda m: big[~cal][:, m].sum(1) / np.maximum(ok[~cal][:, m].sum(1), 1)
c = share(ctrl)
res = {}
for name, m in masks.items():
    mm = m & busy
    res[name] = (share(mm) - c) * 100
    print(f"  {name:12s} busy px {mm.sum():5d} of {m.sum()}")
gap = pd.Series(dd[~cal]).diff().dt.days.values
df = pd.DataFrame(res, index=dd[~cal]); df["days_since_prev"] = (dd[~cal] - dates[:-1][~cal]).days
df.round(2).to_csv(out)
