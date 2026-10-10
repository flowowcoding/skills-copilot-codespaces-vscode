"""Mine activity index from a Sentinel-1 stack (from s1stack.py).

Index per pass = share of mine pixels whose backscatter moved more than THRESH dB since the
previous pass, minus the same share over surrounding natural ground (rain, snow, moisture
move both). Water is dropped (wind ripples change radar too).

Mine mask, either:
  NDVI.npy              bare ground (NDVI < 0.25) is mine, dense vegetation (> 0.7) is control
  box:LON0,LAT0,LON1,LAT1   pixels inside the box are mine, everything outside is control

Optional 4th arg CALIB_END (e.g. 2022-01-01): keep only mine pixels that changed often
before that date (busier than 90% of control pixels), and report the index after it only.
Selecting pixels on one period and scoring another keeps the selection from biasing the test.
"""
import sys
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

THRESH = 3.0
stack, mask_arg, out = sys.argv[1], sys.argv[2], sys.argv[3]
d = np.load(stack)
vv, dates, bbox = d["vv"].astype(np.float32), pd.to_datetime(d["dates"]), d["bbox"]
db = 10 * np.log10(np.clip(vv, 1e-4, None))
pad = np.pad(db, ((0, 0), (1, 1), (1, 1)), mode="edge")
db = sliding_window_view(pad, (3, 3), axis=(1, 2)).mean(axis=(-1, -2))   # 3x3 boxcar vs speckle
H, W = db.shape[1:]
valid = np.isfinite(db).all(0) & (np.nanmean(db, 0) > -15)   # water is radar-dark

if mask_arg.startswith("box:"):
    lon0, lat0, lon1, lat1 = map(float, mask_arg[4:].split(","))
    xx = (np.arange(W) + 0.5) / W * (bbox[2] - bbox[0]) + bbox[0]
    yy = bbox[3] - (np.arange(H) + 0.5) / H * (bbox[3] - bbox[1])
    inside = (xx[None, :] >= lon0) & (xx[None, :] <= lon1) & (yy[:, None] >= lat0) & (yy[:, None] <= lat1)
    mine, ctrl = inside & valid, ~inside & valid
else:
    ndvi = np.load(mask_arg)
    mine, ctrl = (ndvi < 0.25) & valid, (ndvi > 0.7) & valid

diff = np.abs(np.diff(db, axis=0))
ddates = dates[1:]
if len(sys.argv) > 4:
    cal = ddates < pd.Timestamp(sys.argv[4])
    freq = (diff[cal] > THRESH).mean(0)
    mine &= freq > np.quantile(freq[ctrl], 0.9)
    diff, ddates = diff[~cal], ddates[~cal]
m = (diff[:, mine] > THRESH).mean(1)
c = (diff[:, ctrl] > THRESH).mean(1)
s = pd.DataFrame({"mine": m, "control": c, "activity": m - c}, index=ddates)
s.round(4).to_csv(out)
print(f"mine px {mine.sum()}  control px {ctrl.sum()}  passes {len(s)}")
