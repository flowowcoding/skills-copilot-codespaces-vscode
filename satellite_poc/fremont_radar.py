"""Radar car-lot test at Tesla Fremont: do factory/rail-yard pixels empty out at quarter end?

Input: npz from s1stack.py. Pixels that are bright (metal) and change a lot between passes
are kept; the factory and rail-yard boxes are compared with the same kind of pixels elsewhere
in the scene, each pixel measured against its own median, so sensor and weather drift cancel.
"""
import sys
import numpy as np
import pandas as pd
from scipy import stats

FACTORY = (205, 290, 190, 320)   # x0, x1, y0, y1 in the 10 m grid of the downloaded chip
RAIL = (291, 340, 190, 300)

d = np.load(sys.argv[1])
vv, dates = d["vv"], pd.to_datetime(d["dates"])
db = 10 * np.log10(np.clip(vv, 1e-4, None))
mean, std = np.nanmean(db, 0), np.nanstd(db, 0)
anom = db - np.nanmedian(db, 0)
H, W = mean.shape
yy, xx = np.mgrid[:H, :W]
box = lambda b: (xx >= b[0]) & (xx <= b[1]) & (yy >= b[2]) & (yy <= b[3])
hot = (mean > -6) & (std > np.nanpercentile(std, 92))
site = box((FACTORY[0], RAIL[1], FACTORY[2], FACTORY[3]))
ctrl = hot & ~site & (xx < 470) & (yy < 460)
c = np.nanmean(anom[:, ctrl], 1)
days_to_qend = (dates.to_period("Q").end_time.normalize() - dates.normalize()).days

out = {}
for name, b in [("factory", FACTORY), ("rail", RAIL)]:
    m = hot & box(b)
    s = pd.Series(np.nanmean(anom[:, m], 1) - c, index=dates)
    out[name] = s
    last, rest = s[days_to_qend <= 14], s[days_to_qend > 14]
    t = stats.ttest_ind(last, rest, equal_var=False)
    print(f"{name:8s} px={int(m.sum())}  last 2 weeks of quarter {last.mean():+.2f} dB  "
          f"rest {rest.mean():+.2f} dB  t={t.statistic:+.2f} p={t.pvalue:.2f}")
    print("   yearly mean (dB vs control):", s.groupby(dates.year).mean().round(2).to_dict())
pd.DataFrame(out).round(3).to_csv(sys.argv[2] if len(sys.argv) > 2 else "fremont_radar.csv")
