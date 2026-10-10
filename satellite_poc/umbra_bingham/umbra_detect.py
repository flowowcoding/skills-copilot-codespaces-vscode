"""Count compact bright objects (haul trucks, shovels, dozers) in Umbra GEC SAR images.

Two steps, so the slow download happens once and the detector can be re-run in seconds:

  fetch   Read each GEC GeoTIFF over HTTPS (full resolution, windowed to the ROI) and warp
          it onto one shared 1 m UTM 12N grid with MAX resampling, so bright point-like
          targets survive the downsampling. Saved as uint8 .npy (0 = no data). Umbra GECs
          use rotated geotransforms and some are in EPSG:4326; reading a pixel window from
          the projected ROI corners and warping with rasterio.warp.reproject handles both.

  detect  Per image, convert amplitudes to RANKS (percentile within the image's covered
          pixels). Umbra changed the GEC amplitude scaling in early 2024; ranks are immune
          to any monotonic rescaling, so one set of thresholds works across the archive.
          Candidates are connected blobs in the brightest 1 % of the image, 7-400 m^2,
          at most 25 m across, with a peak in the brightest 0.1 %. A candidate is kept
          as an object when it stands alone on darker ground:
            - few bright pixels in a ring 8-16 m from its centre (rejects rubble, crests),
            - a fairly dark ring on average (rejects bright textured slopes),
            - no bright line running through it and not a thin streak (major/minor
              axis ratio <= 4) (rejects bench crests and road edges),
          with looser line/ring limits for large, saturated targets (shovels, whose
          sidelobes draw a bright cross). Detections within 10 m are merged.
          Ring and line statistics are computed only at candidate centroids, so a whole
          image takes about a second (the old 21x21 median filter took minutes).

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

# Detector parameters (chosen by visual inspection of detections only, see README)
T_BLOB = 0.99          # blob pixels: brightest 1 % of the image
T_PEAK = 0.999         # blob peak must be in the brightest 0.1 %
MIN_PX, MAX_PX, MAX_EXT = 7, 400, 25   # blob area (m^2) and bounding-box extent (m)
RING_IN, RING_OUT = 8, 16              # ring around the centroid (m)
RING_HI_T = 0.97       # "bright" ring pixel
MAX_RING_HI = 0.06     # share of bright ring pixels (rejects bench crests, rubble)
MAX_RING_MEAN = 0.75   # mean ring rank (rejects bright textured slopes)
MAX_LINE = 0.30        # share of bright pixels along the best line through the blob
# big very bright targets (shovels, with sidelobe crosses) get looser line/ring limits
BIG_PX, BIG_PEAK, BIG_MAX_LINE, BIG_MAX_RING_MEAN = 25, 0.9999, 0.45, 0.70
MAX_ELONG = 4.0        # major/minor axis ratio (rejects thin crest segments)
MERGE_M = 10           # detections closer than this are one object
MIN_INCIDENCE = 20.0   # steeper collects are dropped (layover; see README)
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


_ANG = np.radians(np.arange(0, 180, 15))
_RS = np.concatenate([np.arange(8, 21), -np.arange(8, 21)])
_LINE_OFF = [(np.round(_RS * np.sin(a)).astype(int), np.round(_RS * np.cos(a)).astype(int))
             for a in _ANG]
_yy, _xx = np.mgrid[-RING_OUT:RING_OUT + 1, -RING_OUT:RING_OUT + 1]
_RING = (np.hypot(_yy, _xx) >= RING_IN) & (np.hypot(_yy, _xx) <= RING_OUT)
_RDY, _RDX = _yy[_RING], _xx[_RING]


def _sample(rank, covered, r, c, dy, dx):
    h, w = rank.shape
    ys, xs = r + dy, c + dx
    ok = (ys >= 0) & (ys < h) & (xs >= 0) & (xs < w)
    ys, xs = ys[ok], xs[ok]
    keep = covered[ys, xs]
    return rank[ys[keep], xs[keep]]


def candidate_features(a):
    """Blobs passing the size/peak gate, with their ring and line statistics."""
    rank, covered = to_rank(a)
    lab, n = ndimage.label(rank > T_BLOB)
    if n == 0:
        return [], rank, covered
    idx = np.arange(1, n + 1)
    sizes = ndimage.sum_labels(np.ones_like(rank), lab, idx)
    peaks = ndimage.maximum(rank, lab, idx)
    sel = idx[(sizes >= MIN_PX) & (sizes <= MAX_PX) & (peaks > T_PEAK)]
    if len(sel) == 0:
        return [], rank, covered
    slices = ndimage.find_objects(lab)
    cents = ndimage.center_of_mass(np.ones_like(rank), lab, sel)
    feats = []
    for (r, c), lb in zip(cents, sel):
        sl = slices[lb - 1]
        ext = max(sl[0].stop - sl[0].start, sl[1].stop - sl[1].start)
        ys, xs = np.nonzero(lab[sl] == lb)
        ev = np.sort(np.linalg.eigvalsh(np.cov(np.vstack([ys, xs]))))
        elong = float(np.sqrt(ev[1] / max(ev[0], 1e-3)))
        r, c = int(round(r)), int(round(c))
        ring = _sample(rank, covered, r, c, _RDY, _RDX)
        if len(ring) < 0.8 * _RING.sum():
            continue                                   # too close to the data edge
        line = max(((_sample(rank, covered, r, c, dy, dx) > 0.95).mean()
                    for dy, dx in _LINE_OFF), default=1.0)
        feats.append(dict(r=r, c=c, size=int(sizes[lb - 1]), ext=int(ext), elong=elong,
                          peak=float(peaks[lb - 1]), ring_hi=float((ring > RING_HI_T).mean()),
                          ring_mean=float(ring.mean()), line=float(line)))
    return feats, rank, covered


def is_object(f):
    if f["ext"] > MAX_EXT or f["elong"] > MAX_ELONG:
        return False
    small = f["line"] < MAX_LINE and f["ring_hi"] < MAX_RING_HI and f["ring_mean"] < MAX_RING_MEAN
    big = (f["size"] >= BIG_PX and f["peak"] >= BIG_PEAK and f["line"] < BIG_MAX_LINE
           and f["ring_mean"] < BIG_MAX_RING_MEAN)
    return small or big


def merge(dets):
    """Greedy merge: keep the largest blob, drop others within MERGE_M."""
    dets = sorted(dets, key=lambda d: -d[2])
    out = []
    for d in dets:
        if all((d[0] - o[0]) ** 2 + (d[1] - o[1]) ** 2 > MERGE_M ** 2 for o in out):
            out.append(d)
    return out


def detect_array(a, return_rejected=False):
    """Return list of (row, col, area_px) detections and the image coverage share."""
    feats, rank, covered = candidate_features(a)
    kept = merge([(f["r"], f["c"], f["size"]) for f in feats if is_object(f)])
    if return_rejected:
        rej = [(f["r"], f["c"], f["size"]) for f in feats if not is_object(f)]
        return kept, rej, float(covered.mean())
    return kept, float(covered.mean())


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
            "params": {k: v for k, v in globals().items()
                       if k.isupper() and isinstance(v, (int, float))},
            "images": out}
    json.dump(meta, open(out_json, "w"))
    good = [o for o in out if "error" not in o]
    print(f"{len(good)} usable images, {len(out) - len(good)} skipped; "
          f"median detections {np.median([len(o['rc']) for o in good]):.0f}")


# ---------------------------------------------------------------- render
def render(cache, time, out_png, crop=None):
    """Rank image with kept (red) and rejected (cyan) candidates."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    a = np.load(os.path.join(cache, key(time) + ".npy"))
    kept, rej, _ = detect_array(a, return_rejected=True)
    rank, _ = to_rank(a)
    r0, c0, r1, c1 = crop or (0, 0, a.shape[0], a.shape[1])
    fig, ax = plt.subplots(figsize=(12, 12 * (r1 - r0) / (c1 - c0)), dpi=100)
    ax.imshow(rank[r0:r1, c0:c1], cmap="gray", vmin=0.85, vmax=1.0,
              extent=(c0, c1, r1, r0), interpolation="nearest")
    for dets, col in ((rej, "#3ad1e0"), (kept, "#ff3b30")):
        for r, c, s in dets:
            if r0 <= r < r1 and c0 <= c < c1:
                ax.add_patch(Rectangle((c - 8, r - 8), 16, 16, fill=False, ec=col, lw=0.9))
    n_in = sum(r0 <= r < r1 and c0 <= c < c1 for r, c, _ in kept)
    ax.set_title(f"{time}   kept (red) {n_in} in view, {len(kept)} in image; cyan = rejected")
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
