"""Mine activity index from a Sentinel-1 stack: share of mine pixels whose backscatter changed
by more than THRESH dB since the previous pass, minus the same share over forest (rain, moisture)."""
import sys, numpy as np, pandas as pd
stack, ndvi_f, out = sys.argv[1], sys.argv[2], sys.argv[3]
THRESH = 3.0
d = np.load(stack); vv = d["vv"].astype(np.float32); dates = pd.to_datetime(d["dates"])
ndvi = np.load(ndvi_f)
db = 10 * np.log10(np.clip(vv, 1e-4, None))
# 3x3 boxcar to tame speckle
from numpy.lib.stride_tricks import sliding_window_view
pad = np.pad(db, ((0, 0), (1, 1), (1, 1)), mode="edge")
db = sliding_window_view(pad, (3, 3), axis=(1, 2)).mean(axis=(-1, -2))
mean_db = np.nanmean(db, 0)
mine = (ndvi < 0.25) & (mean_db > -15)   # bare ground, not water (water is radar-dark)
forest = ndvi > 0.7
valid = np.isfinite(db).all(0)
mine &= valid; forest &= valid
diff = np.abs(np.diff(db, axis=0))
m = (diff[:, mine] > THRESH).mean(1); f = (diff[:, forest] > THRESH).mean(1)
s = pd.DataFrame({"mine": m, "forest": f, "activity": m - f}, index=dates[1:])
s.round(4).to_csv(out)
print("mine px", mine.sum(), "forest px", forest.sum())
print(s.groupby(s.index.to_period("Q")).activity.mean().mul(100).round(2).to_string())
