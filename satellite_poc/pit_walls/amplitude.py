"""Pre-registered Sentinel-1 amplitude (RTC backscatter) test on wall / heap segments.

Change index per pass = share of segment pixels whose VV dB (3x3 boxcar) differs from the
median of that pixel's previous 5 passes by more than 2 dB, minus the same share over control
pixels. Detection rule: detect.py "amplitude" (baseline mean + 3 SD, 2 consecutive passes,
start in [D-12mo, D-4wk]), plus the same rule at every 1 Jan / 1 Jul as a false-alarm check.

Usage:
  python amplitude.py SITE STACK.npz OUT_PREFIX FIG.png
STACK.npz from ../s1stack.py. SITE is a prereg.json key: "bingham" (compass sectors) or a site
with polygon segments ("copler", "eagle").
"""
import sys, os, json, math, re
import numpy as np, pandas as pd
from numpy.lib.stride_tricks import sliding_window_view
from rasterio.transform import Affine
from pyproj import Transformer
from matplotlib.path import Path
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from detect import detect, pseudo_dates
import style

HERE = os.path.dirname(os.path.abspath(__file__))


def lonlat_grid(d, H, W):
    T = Affine(*d["transform"]); tr = Transformer.from_crs(str(d["crs"]), "EPSG:4326", always_xy=True)
    cols, rows = np.meshgrid(np.arange(W) + 0.5, np.arange(H) + 0.5)
    x, y = T * (cols, rows)
    return tr.transform(x, y)


def masks(site, cfg, LON, LAT):
    out = {}
    if site == "bingham":
        lon0, lat0 = cfg["pit_bottom"]; r0, r1 = cfg["ring_m"]
        dx = (LON - lon0) * 111320 * math.cos(math.radians(lat0)); dy = (LAT - lat0) * 111320
        r = np.hypot(dx, dy); az = (np.degrees(np.arctan2(dx, dy)) + 360) % 360
        for name, (a0, a1) in cfg["sectors_deg_from_north"].items():
            ins = (az >= a0) & (az < a1) if a0 < a1 else (az >= a0) | (az < a1)
            out[name] = ins & (r >= r0) & (r <= r1)
        ctrl = (r >= 3000) & (r <= 4500)
    else:
        for name, poly in cfg["segments"].items():
            out[name] = Path(poly).contains_points(np.c_[LON.ravel(), LAT.ravel()]).reshape(LON.shape)
        nums = [float(v) for v in re.findall(r"(?<![\d])-?\d+\.\d+", cfg["control"])]
        o = (nums[0], nums[2], nums[1], nums[3]); i = (nums[4], nums[6], nums[5], nums[7])
        ctrl = ((LON >= o[0]) & (LON <= o[2]) & (LAT >= o[1]) & (LAT <= o[3]) &
                ~((LON >= i[0]) & (LON <= i[2]) & (LAT >= i[1]) & (LAT <= i[3])))
    return out, ctrl


def main():
    site, stack, prefix, fig_fn = sys.argv[1:5]
    cfg = json.load(open(os.path.join(HERE, "prereg.json")))["sites"][site]
    d = np.load(stack); dates = pd.to_datetime(d["dates"])
    db = 10 * np.log10(np.clip(d["vv"].astype(np.float32), 1e-4, None))
    db = sliding_window_view(np.pad(db, ((0, 0), (1, 1), (1, 1)), mode="edge"), (3, 3), axis=(1, 2)).mean(axis=(-1, -2))
    N, H, W = db.shape
    LON, LAT = lonlat_grid(d, H, W)
    valid = np.isfinite(db).all(0) & (np.nanmean(db, 0) > -15)
    segs, ctrl = masks(site, cfg, LON, LAT); ctrl &= valid
    rows = []
    for t in range(5, N):
        ref = np.nanmedian(db[t - 5:t], 0)
        big = np.abs(db[t] - ref) > 2.0
        c = big[ctrl].mean(); r = {"date": dates[t], "control": c}
        for name, m in segs.items():
            m = m & valid
            r[name] = big[m].mean() - c if m.sum() > 20 else np.nan
        rows.append(r)
    S = pd.DataFrame(rows).set_index("date")
    S.round(4).to_csv(f"{prefix}_amplitude_index.csv")
    det, fa = [], []
    for ev in cfg["events"]:
        for seg in [ev["segment"]] + ev.get("also_check", []):
            r = detect(S[seg], ev["D"], "amplitude"); r.update(event=ev["name"], segment=seg); det.append(r)
    for seg in segs:
        for P in pseudo_dates(S.index):
            q = detect(S[seg], P, "amplitude")
            fa.append({"segment": seg, "D": P.date(), "fired": q["first_alarm"] is not None, "first_alarm": q["first_alarm"]})
    det = pd.DataFrame(det); fa = pd.DataFrame(fa)
    det.to_csv(f"{prefix}_amplitude_detections.csv", index=False); fa.to_csv(f"{prefix}_amplitude_false_alarms.csv", index=False)
    print(det[["event", "segment", "n_base", "base_mean", "base_sd", "first_alarm", "lead_days", "alarm_value", "late_alarm"]].to_string())
    print("pseudo-date windows firing:", fa.groupby("segment").fired.mean().round(2).to_dict())

    style.apply()
    ev = cfg["events"][0]; seg = ev["segment"]; D = pd.Timestamp(ev["D"])
    fig, ax = plt.subplots(figsize=(8.5, 3.4))
    z = S[(S.index >= D - pd.DateOffset(months=30)) & (S.index <= D + pd.DateOffset(months=6))]
    ax.plot(z.index, 100 * z[seg], color=style.PRIMARY, lw=1.6, marker=".", ms=3)
    r = det[(det.segment == seg)].iloc[0]
    if r.n_base >= 8:
        thr = 100 * (r.base_mean + 3 * r.base_sd)
        ax.axhline(thr, color=style.INK, lw=0.8, ls=":")
        ax.text(z.index[0], thr, " pre-registered threshold", color=style.INK, fontsize=7.5, va="bottom")
    ax.axvspan(D - pd.DateOffset(months=24), D - pd.DateOffset(months=12), color="#efeee9", lw=0)
    ax.text(D - pd.DateOffset(months=24), 0.03, " baseline", transform=ax.get_xaxis_transform(), fontsize=7, color=style.INK)
    if r.first_alarm is not None and not pd.isna(r.first_alarm):
        style.mark(ax, pd.Timestamp(r.first_alarm), "rule fires", y=0.88, ls=":")
    style.mark(ax, D, "event")
    ax.set_ylabel("changed pixels, segment minus control (pct pts)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.set_title(f"{site.capitalize()} {seg}{' wall' if site == 'bingham' else ''}: Sentinel-1 amplitude change index")
    fig.tight_layout(); fig.savefig(fig_fn, dpi=150); plt.close(fig); print(fig_fn)


if __name__ == "__main__":
    main()
