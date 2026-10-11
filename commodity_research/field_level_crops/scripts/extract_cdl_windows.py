"""Extract the USDA Cropland Data Layer (30 m, EPSG:5070) for every sampling window and year.

Each window (data/windows.csv) is read as a (48 + 2*2) x (48 + 2*2) block of CDL cells: the 1.44 km window plus
a 2-cell margin used by the field-interior test.
Sources: 2008-2021 Planetary Computer `usda-cdl` (90 km COG tiles, window reads);
         2022-2025 NASS CropScape state GeoTIFFs (downloaded one at a time to scratch, read, deleted).
CDL year Y is released around the end of January of Y+1; build_features.py only uses CDL Y for forecasts of
years > Y (masks) and as a training label for the crop classifier of later years.

Output: <work>/cdl/cdl_<year>.npz  (win_id, cdl uint8 [n_win, 52, 52])
Usage:  python extract_cdl_windows.py --work <scratch>/field [--years 2011-2025]
"""
import argparse, os, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd, rasterio
from rasterio.windows import Window
import planetary_computer as pc
from common import DATA, WIN, MARGIN, cdl_tiles, cropscape_state, get

K = WIN + 2 * MARGIN


def fill_from(src, T, w, out):
    """copy the part of each window inside raster `src` (open rasterio dataset with affine T) into out"""
    H, W = src.height, src.width
    for i, r in enumerate(w.itertuples()):
        c0 = int(round((r.x0 - MARGIN * 30 - T.c) / 30)); r0 = int(round((T.f - (r.y0 + MARGIN * 30)) / 30))
        if c0 + K <= 0 or r0 + K <= 0 or c0 >= W or r0 >= H:
            continue
        rs, cs = max(r0, 0), max(c0, 0); re_, ce = min(r0 + K, H), min(c0 + K, W)
        blk = src.read(1, window=Window(cs, rs, ce - cs, re_ - rs))
        sub = out[i, rs - r0:re_ - r0, cs - c0:ce - c0]
        sub[:] = np.where(blk > 0, blk, sub)


def pc_year(y, w, threads):
    its = cdl_tiles(y)
    out = np.zeros((len(w), K, K), np.uint8)
    jobs = []
    for it in its:
        t = it.properties["proj:transform"]; tx, ty = t[2], t[5]
        m = ((w.x0 + WIN * 30 + 100 > tx) & (w.x0 - 100 < tx + 90000) & (w.y0 + 100 > ty - 90000) & (w.y0 - WIN * 30 - 100 < ty)).values
        if m.any():
            jobs.append((it, np.where(m)[0]))

    def one(job):
        it, idx = job
        sub = np.zeros((len(idx), K, K), np.uint8)
        with rasterio.open(pc.sign(it.assets["cropland"].href)) as s:
            fill_from(s, s.transform, w.iloc[idx], sub)
        return idx, sub
    with ThreadPoolExecutor(threads) as ex:
        for idx, sub in ex.map(one, jobs):
            out[idx] = np.where(sub > 0, sub, out[idx])
    return out


def cropscape_year(y, w, tmp):
    out = np.zeros((len(w), K, K), np.uint8)
    for st in sorted(w.state.unique()):
        fn = cropscape_state(y, st, tmp)
        with rasterio.open(fn) as s:
            fill_from(s, s.transform, w, out)
        os.remove(fn)
        print(y, st, "done", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--years", default="2011-2025")
    ap.add_argument("--threads", type=int, default=8)
    a = ap.parse_args()
    w = pd.read_csv(f"{DATA}/windows.csv", dtype={"fips": str})
    od = f"{a.work}/cdl"; os.makedirs(od, exist_ok=True)
    y0, y1 = map(int, a.years.split("-"))
    for y in range(y0, y1 + 1):
        fn = f"{od}/cdl_{y}.npz"
        if os.path.exists(fn):
            continue
        t0 = time.time()
        arr = pc_year(y, w, a.threads) if y <= 2021 else cropscape_year(y, w, od)
        np.savez_compressed(fn, win_id=w.win_id.values, cdl=arr)
        core = arr[:, MARGIN:-MARGIN, MARGIN:-MARGIN]
        print(y, f"{time.time() - t0:.0f}s corn {np.mean(core == 1):.3f} soy {np.mean(core == 5):.3f} zero {np.mean(core == 0):.3f}", flush=True)


if __name__ == "__main__":
    main()
