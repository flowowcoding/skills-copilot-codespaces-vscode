"""Activity index per mine zone. Zones are pixel boxes (x0, x1, y0, y1) on the radar grid,
drawn from before/after Sentinel-2 images (gridchip.py), not from the radar results.
Active pixels in each zone are picked on data before CALIB_END and scored after it.
Control = valid pixels at least BUF px away from every zone."""
import sys
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

ZONES = {
    "cobre": {"halt": "2023-11-24", "zones": {
        "pit (Botija)": (300, 560, 470, 650), "pits south": (280, 520, 650, 780),
        "waste dumps west": (90, 300, 500, 680), "plant": (280, 630, 340, 470), "tailings": (100, 500, 0, 350)}},
    "eagle": {"halt": "2024-06-24", "zones": {
        "pit": (195, 395, 425, 640), "heap leach pad": (200, 345, 245, 355), "plant": (110, 240, 355, 460)}},
    "copler": {"halt": "2024-02-13", "zones": {
        "pits south": (240, 440, 453, 622), "heap leach pad": (440, 578, 429, 586),
        "north benches": (264, 463, 345, 441), "plant": (450, 535, 260, 417),
        "valley / storage": (535, 716, 160, 500)}},
}
THRESH, BUF = 3.0, 25


def zone_index(stack, zones, calib_end):
    d = np.load(stack)
    vv, dates = d["vv"].astype(np.float32), pd.to_datetime(d["dates"])
    db = 10 * np.log10(np.clip(vv, 1e-4, None))
    db = sliding_window_view(np.pad(db, ((0, 0), (1, 1), (1, 1)), mode="edge"), (3, 3), axis=(1, 2)).mean(axis=(-1, -2))
    H, W = db.shape[1:]
    valid = np.isfinite(db).all(0) & (np.nanmean(db, 0) > -15)
    yy, xx = np.mgrid[:H, :W]
    masks, taken = {}, np.zeros((H, W), bool)
    for name, (x0, x1, y0, y1) in zones.items():     # earlier zones win overlaps
        m = (xx >= x0) & (xx <= x1) & (yy >= y0) & (yy <= y1) & ~taken
        masks[name] = m & valid; taken |= m
    near = np.zeros((H, W), bool)
    for name, (x0, x1, y0, y1) in zones.items():
        near |= (xx >= x0 - BUF) & (xx <= x1 + BUF) & (yy >= y0 - BUF) & (yy <= y1 + BUF)
    ctrl = valid & ~near
    diff = np.abs(np.diff(db, axis=0)) > THRESH
    dd = dates[1:]
    cal = dd < pd.Timestamp(calib_end)
    freq = diff[cal].mean(0)
    busy = freq > np.quantile(freq[ctrl], 0.9)
    c = diff[~cal][:, ctrl].mean(1)
    out = {}
    for name, m in masks.items():
        mm = m & busy
        out[name] = diff[~cal][:, mm].mean(1) - c if mm.sum() else np.full(len(c), np.nan)
        print(f"  {name:18s} active px {mm.sum():6d} of {m.sum()}")
    return pd.DataFrame(out, index=dd[~cal]) * 100


if __name__ == "__main__":
    stackdir = sys.argv[1] if len(sys.argv) > 1 else "."
    outdir = sys.argv[2] if len(sys.argv) > 2 else "."
    for mine, cfg in ZONES.items():
        print(mine)
        df = zone_index(f"{stackdir}/{mine}_s1.npz", cfg["zones"], "2022-01-01")
        df.round(2).to_csv(f"{outdir}/{mine}_zones.csv")
        h = pd.Timestamp(cfg["halt"])
        pre, post = df[:h - pd.Timedelta(days=30)], df[h + pd.Timedelta(days=30):]
        y1 = df[h + pd.Timedelta(days=30):h + pd.Timedelta(days=395)]
        y2 = df[h + pd.Timedelta(days=395):]
        sep = (pre.mean() - post.mean()) / np.sqrt((pre.var() + post.var()) / 2)
        print(pd.DataFrame({"operating": pre.mean(), "1st yr after": y1.mean(), "later": y2.mean(), "separation": sep}).round(1).to_string())
