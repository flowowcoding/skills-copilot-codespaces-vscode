"""Sample 30 m Landsat (7/8/9 Collection 2 Level-2) and 20 m Sentinel-2 L2A surface reflectance at the field
sample points of every window, for every clear acquisition of a season (Planetary Computer, no auth).

Why not HLS: Planetary Computer's HLS v2 (`hls2-l30`, `hls2-s30`) starts in 2020 and LP DAAC needs an
Earthdata login, so it would leave only 2020-21 for training. The same two sensor families are read here
directly from their Level-2 products on PC for 2013-2026 (an HLS-like, but not BRDF-normalised, stack);
sensor offsets are estimated and removed in build_features.py.

Points: in each 1.44 km window (data/windows.csv) every 2nd 30 m CDL cell centre (24 x 24 = 576 points,
60 m spacing). Only small windows around the points are read (COG range requests); nothing is stored but
the per-point values.

Per item (scene / tile-date) with eo:cloud_cover <= --max-cloud and DOY in [--doy0, --doy1]:
  * Landsat: QA_PIXEL read first; clear = bit 6 (clear) set and bits 0-5 (fill, dilated cloud, cirrus,
    cloud, shadow, snow) unset; if >= 15 % of a window's points are clear, red and nir08 are read.
    Reflectance = DN * 2.75e-5 - 0.2.
  * Sentinel-2: SCL read first (20 m); clear = SCL in {4 vegetation, 5 bare}; then B04 (read at 20 m),
    B8A (narrow NIR, as in HLS) and B05 (red edge 1). Reflectance = (DN - 1000) / 1e4 for processing
    baseline >= 04.00, DN / 1e4 before. Duplicate tile-dates keep the newest processing baseline.
  * points with red > 0.3 or nir <= 0 are treated as cloud residue.
Output: <work>/obs/<source>_<year>.npz with, per (window, acquisition) row: win_id, date (YYYYMMDD),
        sensor (7, 8, 9 = Landsat; 21, 22, 23 = S2A/B/C), and int16 arrays [rows, 576] red, nir, re1
        (reflectance x 1e4, -32768 = not clear; re1 only for S2).
Usage:  python extract_imagery.py --work <scratch>/field --source landsat|s2 --year 2019 [--threads 24]
"""
import argparse, os, time, warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd, rasterio
from rasterio.windows import Window
from pyproj import Transformer
from shapely.geometry import shape, Point
import planetary_computer as pc
from common import DATA, WIN, point_offsets, stac_items

warnings.filterwarnings("ignore")
os.environ.update(GDAL_HTTP_MULTIPLEX="YES", GDAL_HTTP_VERSION="2", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                  CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif", GDAL_CACHEMAX="256", GDAL_HTTP_MAX_RETRY="5", GDAL_HTTP_RETRY_DELAY="3")
NA = -32768
SENSOR = {"landsat-7": 7, "landsat-8": 8, "landsat-9": 9, "Sentinel-2A": 21, "Sentinel-2B": 22, "Sentinel-2C": 23}
BANDS = {"landsat": {"mask": "qa_pixel", "red": "red", "nir": "nir08"},
         "s2": {"mask": "SCL", "red": "B04", "nir": "B8A", "re1": "B05"}}
RES = {"landsat": 30, "s2": 20}


def points(w):
    r, c = point_offsets()
    x = w.x0.values[:, None] + (c[None, :] + 0.5) * 30
    y = w.y0.values[:, None] - (r[None, :] + 0.5) * 30
    return x, y  # [n_win, 576] in EPSG:5070


_tr_cache = {}


def to_crs(epsg, x, y):
    if epsg not in _tr_cache:
        t = Transformer.from_crs(5070, epsg, always_xy=True)
        _tr_cache[epsg] = t.transform(x, y)
    return _tr_cache[epsg]


def read_at(ds, X, Y, res):
    """values of band `ds` at points (X, Y) (item CRS), read through a window at resolution `res` metres"""
    T = ds.transform
    f = int(round(res / T.a))  # decimation factor (S2 B04: 2)
    gx = (X - T.c) / (T.a * f); gy = (T.f - Y) / (T.a * f)
    c = np.floor(gx).astype(int); r = np.floor(gy).astype(int)
    c0, r0, c1, r1 = c.min(), r.min(), c.max() + 1, r.max() + 1
    Wd, Hd = ds.width // f, ds.height // f
    if c1 <= 0 or r1 <= 0 or c0 >= Wd or r0 >= Hd:
        return None
    c0, r0, c1, r1 = max(c0, 0), max(r0, 0), min(c1, Wd), min(r1, Hd)
    a = ds.read(1, window=Window(c0 * f, r0 * f, (c1 - c0) * f, (r1 - r0) * f), out_shape=(r1 - r0, c1 - c0), boundless=False)
    ok = (c >= c0) & (c < c1) & (r >= r0) & (r < r1)
    v = np.zeros(X.shape, a.dtype)
    v[ok] = a[r[ok] - r0, c[ok] - c0]
    return v, ok


def open_retry(href, tries=5):
    err = None
    for k in range(tries):
        try:
            return rasterio.open(href)
        except Exception as e:  # noqa
            err = e; time.sleep(3 * (k + 1))
    raise RuntimeError(err)


def process_item(it, src, wins, X, Y, min_clear):
    """returns list of (win_id, date, sensor, red, nir, re1) for windows with enough clear points"""
    it = pc.sign(it)
    epsg = int(str(it.properties.get("proj:code") or f"EPSG:{it.properties.get('proj:epsg')}").split(":")[1])
    XX, YY = to_crs(epsg, X, Y)
    B = BANDS[src]; res = RES[src]
    date = int(pd.Timestamp(it.properties["datetime"]).strftime("%Y%m%d"))
    sensor = SENSOR.get(it.properties.get("platform"), 0)
    if src == "s2":
        pb = float(it.properties.get("s2:processing_baseline", "0"))
        off = 1000 if pb >= 4.0 else 0
    out = []
    with open_retry(it.assets[B["mask"]].href) as dm:
        keep = []
        for i in wins:
            rr = read_at(dm, XX[i], YY[i], res)
            if rr is None:
                continue
            m, ok = rr
            if src == "landsat":
                clear = ok & ((m & (1 << 6)) > 0) & ((m & 0b111111) == 0)
            else:
                clear = ok & np.isin(m, [4, 5])
            if clear.mean() >= min_clear:
                keep.append((i, clear))
    if not keep:
        return out
    vals = {}
    for k in [b for b in B if b != "mask"]:
        with open_retry(it.assets[B[k]].href) as ds:
            vals[k] = [read_at(ds, XX[i], YY[i], res)[0] for i, _ in keep]
    for j, (i, clear) in enumerate(keep):
        rec = {}
        for k in vals:
            dn = vals[k][j].astype(np.float32)
            rec[k] = dn * 2.75e-5 - 0.2 if src == "landsat" else (dn - off) / 1e4
        good = clear & (rec["red"] > 0) & (rec["red"] <= 0.3) & (rec["nir"] > 0) & (rec["nir"] <= 1)
        arr = {k: np.where(good, np.round(rec[k] * 1e4), NA).astype(np.int16) for k in rec}
        out.append((i, date, sensor, arr["red"], arr["nir"], arr.get("re1")))
    return out


def list_items(src, year, bbox, doy0, doy1, max_cloud):
    s = pd.Timestamp(year, 1, 1) + pd.Timedelta(days=doy0 - 1); e = pd.Timestamp(year, 1, 1) + pd.Timedelta(days=doy1 - 1)
    dt = f"{s:%Y-%m-%d}/{e:%Y-%m-%d}T23:59:59Z"
    if src == "landsat":
        its = stac_items(collections=["landsat-c2-l2"], bbox=bbox, datetime=dt,
                         query={"eo:cloud_cover": {"lte": max_cloud}, "platform": {"in": ["landsat-7", "landsat-8", "landsat-9"]}})
        return [it for it in its if it.properties.get("landsat:collection_category") == "T1"]
    its = stac_items(collections=["sentinel-2-l2a"], bbox=bbox, datetime=dt, query={"eo:cloud_cover": {"lte": max_cloud}})
    best = {}
    for it in its:
        key = (it.properties.get("s2:mgrs_tile"), it.properties["datetime"][:13])
        pb = float(it.properties.get("s2:processing_baseline", "0"))
        if key not in best or pb > best[key][0]:
            best[key] = (pb, it)
    return [v[1] for v in best.values()]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--source", choices=["landsat", "s2"], required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--doy0", type=int, default=100)
    ap.add_argument("--doy1", type=int, default=255)
    ap.add_argument("--max-cloud", type=float, default=80)
    ap.add_argument("--min-clear", type=float, default=0.15)
    ap.add_argument("--threads", type=int, default=24)
    ap.add_argument("--limit", type=int, default=0, help="debug: only the first N items")
    a = ap.parse_args()
    od = f"{a.work}/obs"; os.makedirs(od, exist_ok=True)
    fo = f"{od}/{a.source}_{a.year}.npz"
    if os.path.exists(fo):
        print("exists", fo); return
    w = pd.read_csv(f"{DATA}/windows.csv", dtype={"fips": str})
    X, Y = points(w)
    bbox = [w.lon.min() - 0.05, w.lat.min() - 0.05, w.lon.max() + 0.05, w.lat.max() + 0.05]
    its = list_items(a.source, a.year, bbox, a.doy0, a.doy1, a.max_cloud)
    its.sort(key=lambda it: it.properties["datetime"])
    if a.limit:
        its = its[:a.limit]
    cpts = [Point(lo, la) for lo, la in zip(w.lon, w.lat)]
    jobs = []
    for it in its:
        g = shape(it.geometry)
        wins = [i for i, p in enumerate(cpts) if g.contains(p)]
        if wins:
            jobs.append((it, wins))
    print(a.source, a.year, "items", len(its), "with windows", len(jobs), "window-items", sum(len(j[1]) for j in jobs), flush=True)
    rows = []; t0 = time.time(); nfail = 0
    with ThreadPoolExecutor(a.threads) as ex:
        futs = {ex.submit(process_item, it, a.source, wins, X, Y, a.min_clear): it.id for it, wins in jobs}
        for k, f in enumerate(as_completed(futs)):
            try:
                rows.extend(f.result())
            except Exception as e:  # noqa
                nfail += 1; print("FAIL", futs[f], str(e)[:200], flush=True)
            if (k + 1) % 50 == 0:
                print(f"{k + 1}/{len(jobs)} items, {len(rows)} window-obs, {time.time() - t0:.0f}s", flush=True)
    if not rows:
        print("no rows"); return
    rows.sort(key=lambda r: (r[1], r[0]))
    re1 = np.stack([r[5] for r in rows]) if a.source == "s2" else np.zeros((0, 0), np.int16)
    np.savez_compressed(fo, win_id=np.array([r[0] for r in rows], np.int16), date=np.array([r[1] for r in rows], np.int32),
                        sensor=np.array([r[2] for r in rows], np.uint8), red=np.stack([r[3] for r in rows]), nir=np.stack([r[4] for r in rows]),
                        re1=re1, n_items=len(jobs), n_fail=nfail)
    print("saved", fo, len(rows), "window-obs", f"{time.time() - t0:.0f}s", "fails", nfail, flush=True)


if __name__ == "__main__":
    main()
