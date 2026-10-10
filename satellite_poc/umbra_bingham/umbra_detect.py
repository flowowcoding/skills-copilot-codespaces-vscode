"""Count compact bright objects (haul trucks, shovels, dozers) in Umbra GEC SAR images.

Two steps, so the slow download happens once and the detector can be re-run in seconds:

  fetch   Read each GEC GeoTIFF over HTTPS (full resolution, windowed to the ROI) and warp
          it onto one shared 1 m UTM 12N grid with MAX resampling, so bright point-like
          targets survive the downsampling. Saved as uint8 .npy (0 = no data). Umbra GECs
          use rotated geotransforms and some are in EPSG:4326; reading a pixel window from
          the projected ROI corners and warping with rasterio.warp.reproject handles both.

  detect  Per image, convert amplitudes to RANKS (percentile within the image's covered
          pixels). Umbra changed the GEC amplitude scaling in early 2024; ranks are immune
          to any monotonic rescaling, so one threshold works across the whole archive.
          A detection is a connected blob of pixels in the top TOP_Q of the image whose
          area is MIN_PX..MAX_PX m^2 and whose surroundings are dark: the mean rank in a
          ring (RING_IN..RING_OUT m) around its centroid must be below RING_MAX. This keeps
          isolated metal objects and rejects bright slopes, bench crests and rubble fields.
          The ring statistic is computed only at blob centroids (fast), not as a full
          median filter.

  render  PNG of one image with detection boxes, for visual checks.

Detections are stored as (row, col) on the shared grid, so they are comparable across
collects.

Usage:
  python umbra_detect.py fetch  INDEX.csv CACHE_DIR [--workers 6]
  python umbra_detect.py detect INDEX.csv CACHE_DIR DETS.json
  python umbra_detect.py render CACHE_DIR TIME OUT.png [--crop r0,c0,r1,c1]
"""
import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject, transform, transform_bounds
from rasterio.windows import Window
from scipy import ndimage

# Pit core, lon0, lat0, lon1, lat1
ROI = (-112.168, 40.508, -112.132, 40.537)
CRS = "EPSG:32612"
GRID_M = 1.0

# Detector parameters (chosen by visual inspection of boxes only)
TOP_Q = 0.002        # blob pixels must be in the brightest 0.2 % of the image
MIN_PX, MAX_PX = 6, 400
RING_IN, RING_OUT = 8, 16
RING_MAX = 0.80      # mean rank of the ring must be below this
MIN_COVER = 0.9

GDAL_ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MULTIPLEX="YES",
                GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES", GDAL_CACHEMAX=256,
                GDAL_HTTP_MAX_RETRY=4, GDAL_HTTP_RETRY_DELAY=2)


def grid(roi=ROI):
    x0, y0, x1, y1 = transform_bounds("EPSG:4326", CRS, *roi)
    w, h = int((x1 - x0) / GRID_M), int((y1 - y0) / GRID_M)
    return from_origin(x0, y1, GRID_M, GRID_M), w, h


def key(time):
    return pd.Timestamp(time).strftime("%Y%m%dT%H%M%S")


# ---------------------------------------------------------------- fetch
def fetch_one(url, roi=ROI, pad=50):
    tf, w, h = grid(roi)
    x0, y1 = tf.c, tf.f
    x1, y0 = x0 + w * GRID_M, y1 - h * GRID_M
    with rasterio.Env(**GDAL_ENV), rasterio.open(url) as src:
        xs, ys = transform(CRS, src.crs, [x0 - pad, x1 + pad, x1 + pad, x0 - pad],
                           [y0 - pad, y0 - pad, y1 + pad, y1 + pad])
        inv = ~src.transform
        cr = [inv * (x, y) for x, y in zip(xs, ys)]          # works for rotated transforms
        c0 = max(0, int(min(c for c, _ in cr)))
        c1 = min(src.width, int(max(c for c, _ in cr)) + 1)
        r0 = max(0, int(min(r for _, r in cr)))
        r1 = min(src.height, int(max(r for _, r in cr)) + 1)
        if c1 <= c0 or r1 <= r0:
            return None
        win = Window(c0, r0, c1 - c0, r1 - r0)
        a = src.read(1, window=win)
        stf, scrs = src.window_transform(win), src.crs
    out = np.zeros((h, w), np.uint8)
    reproject(a, out, src_transform=stf, src_crs=scrs, dst_transform=tf, dst_crs=CRS,
              resampling=Resampling.max, src_nodata=0, dst_nodata=0)
    return out


def fetch(index_csv, cache, workers=6):
    os.makedirs(cache, exist_ok=True)
    d = pd.read_csv(index_csv)

    def one(r):
        path = os.path.join(cache, key(r.time) + ".npy")
        if os.path.exists(path):
            return r.time, "cached"
        try:
            a = fetch_one(r.gec)
        except Exception as e:
            return r.time, "ERROR " + str(e)[:150]
        if a is None:
            return r.time, "no overlap"
        np.save(path, a)
        return r.time, f"ok cover={np.mean(a > 0):.2f}"

    with ThreadPoolExecutor(workers) as ex:
        for t, msg in ex.map(one, d.itertuples()):
            print(t, msg, flush=True)


# ---------------------------------------------------------------- detect
def to_rank(a):
    """Percentile rank (0..1] of each covered pixel within the image; 0 where no data."""
    covered = a > 0
    hist = np.bincount(a[covered], minlength=256).astype(np.float64)
    cdf = np.cumsum(hist) / hist.sum()
    rank = cdf[a].astype(np.float32)
    rank[~covered] = 0
    return rank, covered


def detect_array(a):
    """Return list of (row, col, area_px) detections and the image coverage share."""
    rank, covered = to_rank(a)
    cover = covered.mean()
    # uint8 ties: threshold on the amplitude level whose rank first exceeds 1-TOP_Q
    lab, n = ndimage.label(rank > 1 - TOP_Q)
    if n == 0:
        return [], cover
    idx = np.arange(1, n + 1)
    sizes = ndimage.sum_labels(np.ones_like(rank), lab, idx)
    keep = idx[(sizes >= MIN_PX) & (sizes <= MAX_PX)]
    if len(keep) == 0:
        return [], cover
    cents = ndimage.center_of_mass(np.ones_like(rank), lab, keep)
    # ring offsets
    yy, xx = np.mgrid[-RING_OUT:RING_OUT + 1, -RING_OUT:RING_OUT + 1]
    rr = np.hypot(yy, xx)
    ring = (rr >= RING_IN) & (rr <= RING_OUT)
    dy, dx = yy[ring], xx[ring]
    h, w = rank.shape
    out = []
    for (r, c), lb in zip(cents, keep):
        r, c = int(round(r)), int(round(c))
        ys, xs = r + dy, c + dx
        ok = (ys >= 0) & (ys < h) & (xs >= 0) & (xs < w)
        ys, xs = ys[ok], xs[ok]
        vals = rank[ys, xs]
        vals = vals[covered[ys, xs]]
        if len(vals) < 0.8 * ring.sum():
            continue                                  # too close to the data edge
        if vals.mean() < RING_MAX:
            out.append((r, c, int(sizes[lb - 1])))
    return out, cover


def detect(index_csv, cache, out_json):
    d = pd.read_csv(index_csv)

    def one(t):
        path = os.path.join(cache, key(t) + ".npy")
        if not os.path.exists(path):
            return {"time": t, "error": "not fetched"}
        a = np.load(path)
        dets, cover = detect_array(a)
        rec = {"time": t, "cover": round(float(cover), 4), "rc": [list(x) for x in dets]}
        if cover < MIN_COVER:
            rec["error"] = f"coverage {cover:.2f}"
        return rec

    with ThreadPoolExecutor(4) as ex:
        out = list(ex.map(one, d.time))
    tf, w, h = grid()
    meta = {"grid": {"crs": CRS, "transform": list(tf)[:6], "width": w, "height": h},
            "params": dict(TOP_Q=TOP_Q, MIN_PX=MIN_PX, MAX_PX=MAX_PX, RING_IN=RING_IN,
                           RING_OUT=RING_OUT, RING_MAX=RING_MAX, MIN_COVER=MIN_COVER),
            "images": out}
    json.dump(meta, open(out_json, "w"))
    good = [o for o in out if "error" not in o]
    print(f"{len(good)} usable images, {len(out) - len(good)} skipped; "
          f"median detections {np.median([len(o['rc']) for o in good]):.0f}")


# ---------------------------------------------------------------- render
def render(cache, time, out_png, crop=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    a = np.load(os.path.join(cache, key(time) + ".npy"))
    dets, _ = detect_array(a)
    rank, _ = to_rank(a)
    r0, c0, r1, c1 = crop or (0, 0, a.shape[0], a.shape[1])
    fig, ax = plt.subplots(figsize=(14, 14 * (r1 - r0) / (c1 - c0)), dpi=110)
    ax.imshow(rank[r0:r1, c0:c1], cmap="gray", vmin=0.3, vmax=1.0,
              extent=(c0, c1, r1, r0), interpolation="nearest")
    for r, c, s in dets:
        if r0 <= r < r1 and c0 <= c < c1:
            half = max(5, np.sqrt(s))
            ax.add_patch(Rectangle((c - half, r - half), 2 * half, 2 * half,
                                   fill=False, ec="#ff3b30", lw=0.8))
    ax.set_title(f"{time}  detections in view: "
                 f"{sum(r0 <= r < r1 and c0 <= c < c1 for r, c, _ in dets)} / {len(dets)}")
    ax.set_xticks([]); ax.set_yticks([])
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch"); f.add_argument("index"); f.add_argument("cache")
    f.add_argument("--workers", type=int, default=6)
    d = sub.add_parser("detect"); d.add_argument("index"); d.add_argument("cache"); d.add_argument("out")
    r = sub.add_parser("render"); r.add_argument("cache"); r.add_argument("time"); r.add_argument("out")
    r.add_argument("--crop", default=None)
    a = p.parse_args()
    if a.cmd == "fetch":
        fetch(a.index, a.cache, a.workers)
    elif a.cmd == "detect":
        detect(a.index, a.cache, a.out)
    else:
        render(a.cache, a.time, a.out,
               [int(v) for v in a.crop.split(",")] if a.crop else None)
