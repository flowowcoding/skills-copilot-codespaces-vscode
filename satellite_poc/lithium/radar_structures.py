"""Sentinel-1 bright-structure area in a zone over time (test A2, structure part).

Buildings, steel frames, tanks and parked equipment are strong radar reflectors. Per pass,
count the zone pixels whose VV backscatter is above a fixed threshold. The threshold is the
99.9th percentile of control pixels (everything more than 1 km outside the zone) over the
pre-construction passes, so it is set without looking at the zone. Expected false positives
(0.1% of zone pixels) are subtracted, and the result is reported as hectares of bright
structure. A 5-pass rolling median smooths out speckle and wet-snow passes.

Usage:
    python radar_structures.py S1STACK.npz LON0,LAT0,LON1,LAT1 PRE_END OUT.csv
S1STACK is the output of ../s1stack.py (RTC gamma0, linear power, UTM grid).
"""
import sys

import numpy as np
import pandas as pd
from pyproj import Transformer


def main():
    stack, zone, pre_end, out = sys.argv[1:5]
    d = np.load(stack)
    vv = d["vv"].astype(np.float32)
    dates = pd.to_datetime(d["dates"])
    a, _, x0, _, e, y0 = d["transform"][:6]
    T, H, W = vv.shape
    lon0, lat0, lon1, lat1 = [float(v) for v in zone.split(",")]
    tr = Transformer.from_crs("EPSG:4326", str(d["crs"]), always_xy=True)
    (ex0, ey0), (ex1, ey1) = tr.transform(lon0, lat0), tr.transform(lon1, lat1)
    c0, c1 = sorted([(ex0 - x0) / a, (ex1 - x0) / a])
    r0, r1 = sorted([(ey0 - y0) / e, (ey1 - y0) / e])
    yy, xx = np.mgrid[:H, :W]
    zm = (xx >= c0) & (xx <= c1) & (yy >= r0) & (yy <= r1)
    pad = 1000 / abs(a)
    ctrl = ~((xx >= c0 - pad) & (xx <= c1 + pad) & (yy >= r0 - pad) & (yy <= r1 + pad))
    pre = dates < pd.Timestamp(pre_end)
    thr = np.nanpercentile(vv[pre][:, ctrl], 99.9)
    px_ha = abs(a * e) / 1e4
    rows = []
    for i in range(T):
        v = vv[i]
        ok = np.isfinite(v)
        if ok[zm].mean() < 0.9:
            continue
        fz = (v[zm & ok] > thr).mean()
        fc = (v[ctrl & ok] > thr).mean()
        rows.append(dict(date=dates[i], zone_bright_ha=(fz - 0.001) * zm.sum() * px_ha,
                         ctrl_bright_pct=fc * 100, zone_median_db=10 * np.log10(np.nanmedian(v[zm]))))
    df = pd.DataFrame(rows).set_index("date")
    df["bright_ha_smooth"] = df["zone_bright_ha"].rolling(5, center=True, min_periods=3).median()
    df.round(4).to_csv(out)
    print(f"threshold {10 * np.log10(thr):.1f} dB, zone {zm.sum()} px")
    print(df.resample("QE").median().round(2).to_string())


if __name__ == "__main__":
    main()
