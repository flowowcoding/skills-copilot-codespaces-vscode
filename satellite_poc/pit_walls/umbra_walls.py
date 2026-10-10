"""Umbra open-data SAR (X-band spotlight, ~0.5 m) chips of one pit wall through time, for visual
wall-change inspection. Picks, for each requested date, the nearest Umbra GEC collect whose
viewing geometry matches (track, look side, azimuth +/- AZTOL deg, incidence +/- INCTOL deg),
reads only the window it needs from the cloud-optimised GeoTIFF (no full download) and tiles
the chips on one common UTM grid.

Note: GEC products are ellipsoid-geocoded, not terrain-corrected, so in a 1 km deep pit the
image is shifted by relief; chips are only comparable within one viewing geometry.

Usage:
  python umbra_walls.py --dates 2023-10-01,2024-01-10,... [--track ASC --look L
         --az 95 --aztol 30 --inc 35 --inctol 12 --res 1.5] -- INDEX.csv BBOX OUT.png
INDEX.csv: t, az, inc, track, look, gec (S3 key) built from the collects' METADATA.json.
"""
import argparse, urllib.parse
import numpy as np, pandas as pd, rasterio
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds
from rasterio.transform import from_origin
from rasterio.enums import Resampling
import matplotlib.pyplot as plt
import style

S3 = "https://umbra-open-data-catalog.s3.amazonaws.com/"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("index"); ap.add_argument("bbox"); ap.add_argument("out")
    ap.add_argument("--dates", required=True)
    ap.add_argument("--track", default="ASC"); ap.add_argument("--look", default="L")
    ap.add_argument("--az", type=float, default=95); ap.add_argument("--aztol", type=float, default=30)
    ap.add_argument("--inc", type=float, default=35); ap.add_argument("--inctol", type=float, default=12)
    ap.add_argument("--res", type=float, default=1.5); ap.add_argument("--title", default="")
    a = ap.parse_args()
    bbox = [float(v) for v in a.bbox.split(",")]
    idx = pd.read_csv(a.index, parse_dates=["t"]).dropna(subset=["gec"])
    ok = idx[(idx.track == a.track) & (idx.look == a.look) & ((idx.az - a.az).abs() <= a.aztol) & ((idx.inc - a.inc).abs() <= a.inctol)]
    picks = []
    for d in a.dates.split(","):
        d = pd.Timestamp(d); r = ok.iloc[(ok.t - d).abs().argsort()[:1]]
        if len(r) and r.t.iloc[0] not in [p.t for p in picks]:
            picks.append(r.iloc[0])
    dst_crs = "EPSG:32612"
    l, b, r_, t = transform_bounds("EPSG:4326", dst_crs, *bbox)
    W = int((r_ - l) / a.res); H = int((t - b) / a.res); tr = from_origin(l, t, a.res, a.res)
    chips = []
    for p in picks:
        with rasterio.open("/vsicurl/" + S3 + urllib.parse.quote(p.gec)) as src:
            with WarpedVRT(src, crs=dst_crs, transform=tr, width=W, height=H, resampling=Resampling.average) as v:
                chips.append(v.read(1).astype(np.float32))
        print(p.t, p.az, p.inc)
    style.apply()
    n = len(chips); cols = min(n, 4); rows = int(np.ceil(n / cols))
    fig, axs = plt.subplots(rows, cols, figsize=(3.2 * cols, 3.2 * rows * H / W + 0.4))
    axs = np.atleast_1d(axs).ravel()
    for ax, c, p in zip(axs, chips, picks):
        lo, hi = np.percentile(c[c > 0], [2, 98]) if (c > 0).any() else (0, 1)
        ax.imshow(c, cmap="gray", vmin=lo, vmax=hi, interpolation="nearest")
        ax.set_title(f"{p.t:%Y-%m-%d}  az {p.az:.0f}°, inc {p.inc:.0f}°", fontsize=8, color=style.INK)
        ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
    for ax in axs[n:]:
        ax.axis("off")
    fig.suptitle(a.title or "Umbra spotlight SAR, same viewing geometry", x=0.01, ha="left", fontsize=9.5, color=style.INK)
    fig.tight_layout(); fig.savefig(a.out, dpi=150); plt.close(fig); print(a.out)


if __name__ == "__main__":
    main()
