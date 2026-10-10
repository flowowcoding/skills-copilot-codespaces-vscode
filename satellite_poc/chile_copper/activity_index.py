"""Optical (Sentinel-2) pit activity index for every mine in one stack (see mines.json).

Usage:
    python activity_index.py STACK.npz STACK_NAME OUT_DIR [--mines mines.json]
writes OUT_DIR/<mine>_pairs.csv (one row per image pair) for each mine in the stack.

Method (frozen before any comparison with production; see README "Pre-registration"):
  * brightness b = B04 + B11 (from s2bright.py); masked pixels are NaN.
  * lb = log(b) minus the median of lb over all non-pit pixels of the image (sun angle, haze).
  * consecutive clear images form a pair if they are at most MAXGAP = 12 days apart.
  * a pixel "changed" in a pair if |lb2 - lb1| > THRESH = 0.12, ignoring pixels darker than
    SHADOW = -0.3 (deep pit shadow) in either image.
  * control = pixels more than BUF = 15 px (300 m) from any pit polygon of any mine in the stack
    that were in the quieter half (change frequency <= median) during the calibration window,
    so dumps, pads and plants elsewhere in the box don't count as "natural ground".
  * busy pit pixels = pit pixels whose change frequency in the calibration window is above the
    90th percentile of control pixels (same rule as ../activity.py and ../optical_zones.py).
  * index per pair = (share of busy pit pixels changed - share of control pixels changed) x 100.
Three variants, all scored only outside their own calibration window:
  R (primary)  rolling: the calibration window for calendar year Y is year Y-1 (busy pixels
               follow the mining front as it moves). Scored from 2019.
  F            fixed: busy pixels and control picked once on 2018. Scored from 2019.
  A            all pit pixels (no busy selection), control as in R. Scored from 2019.
Pit polygons are rasterised by linear lon/lat interpolation over the stack box (UTM zone 19
grid, error well under 100 m at these sites).
"""
import argparse
import json

import numpy as np
import pandas as pd
from matplotlib.path import Path
from scipy.ndimage import distance_transform_edt

THRESH, SHADOW, MAXGAP, BUF, Q_BUSY = 0.12, -0.3, 12, 15, 0.9

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("stack"); ap.add_argument("name"); ap.add_argument("outdir")
ap.add_argument("--mines", default="mines.json")
a = ap.parse_args()
cfg = json.load(open(a.mines))
mines = {k: v for k, v in cfg["mines"].items() if v["stack"] == a.name}

d = np.load(a.stack)
dates = pd.to_datetime(d["dates"])
bbox = d["bbox"]
br = d["bright"]
T, H, W = br.shape
print(a.name, T, "images", (H, W), flush=True)

# pit masks
yy, xx = np.mgrid[:H, :W]
lon = bbox[0] + (xx + 0.5) / W * (bbox[2] - bbox[0])
lat = bbox[3] - (yy + 0.5) / H * (bbox[3] - bbox[1])
pts = np.c_[lon.ravel(), lat.ravel()]
pit = {}
for k, v in mines.items():
    m = np.zeros(H * W, bool)
    for poly in v["pit"]:
        m |= Path(poly).contains_points(pts)
    pit[k] = m.reshape(H, W)
anypit = np.any(list(pit.values()), axis=0)
far = distance_transform_edt(~anypit) > BUF

# normalised log brightness, one image at a time to limit memory
lb = np.empty((T, H, W), np.float32)
for t in range(T):
    x = br[t].astype(np.float32)
    x[x == 0] = np.nan
    x = np.log(x)
    lb[t] = x - np.nanmedian(x[~anypit])
del br

# pairs
gap = np.diff(dates).astype("timedelta64[D]").astype(int)
pairs = np.where(gap <= MAXGAP)[0]
pend = dates[pairs + 1]
print(f"  {len(pairs)} pairs with gap <= {MAXGAP} d (of {T - 1})", flush=True)
big = np.zeros((len(pairs), H, W), bool)
ok = np.zeros((len(pairs), H, W), bool)
for j, t in enumerate(pairs):
    a1, a2 = lb[t], lb[t + 1]
    o = np.isfinite(a1) & np.isfinite(a2) & (a1 > SHADOW) & (a2 > SHADOW)
    ok[j] = o
    big[j] = o & (np.abs(a2 - a1) > THRESH)
del lb


def calib(sel):
    """busy-pixel frequency map and control mask from the pairs in `sel`."""
    freq = big[sel].sum(0) / np.maximum(ok[sel].sum(0), 1)
    enough = ok[sel].sum(0) >= 5
    cf = freq[far & enough]
    ctrl = far & enough & (freq <= np.median(cf))
    thr = np.quantile(freq[ctrl], Q_BUSY)
    return freq, enough, ctrl, thr


def share(sel, mask):
    n = ok[sel][:, mask].sum(1)
    return np.where(n > 0, big[sel][:, mask].sum(1) / np.maximum(n, 1), np.nan), n


years = sorted(set(pend.year))
out = {k: [] for k in mines}
fixed = calib(pend.year == 2018)
for y in years:
    if y < 2019:
        continue
    sel = pend.year == y
    rol = calib(pend.year == y - 1)
    for k in mines:
        row = pd.DataFrame(index=pend[sel])
        for var, (freq, enough, ctrl, thr), allpix in [("R", rol, False), ("F", fixed, False), ("A", rol, True)]:
            busy = pit[k] & enough if allpix else pit[k] & enough & (freq > thr)
            s_pit, n_pit = share(sel, busy)
            s_ctl, _ = share(sel, ctrl)
            row[var] = (s_pit - s_ctl) * 100
            row[f"n_{var}"] = n_pit
            if var == "R":
                row["control"] = s_ctl * 100
        row["busy_px_R"] = int((pit[k] & rol[1] & (rol[0] > rol[3])).sum())
        out[k].append(row)
for k in mines:
    df = pd.concat(out[k])
    df.index.name = "date"
    df["pit_px"] = int(pit[k].sum())
    df.round(3).to_csv(f"{a.outdir}/{k}_pairs.csv")
    print(f"  {k:18s} pit px {pit[k].sum():6d}  busy(R, last yr) {df.busy_px_R.iloc[-1]:6d}  pairs {len(df)}", flush=True)
