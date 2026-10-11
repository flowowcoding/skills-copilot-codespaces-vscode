"""Extract USDA Cropland Data Layer (30 m) windows around every sample pixel, for each year.

For each MODIS 250 m sample pixel we keep the 9 x 9 block of 30 m CDL cells (270 m) centred on the pixel
centre (projected to EPSG:5070, the CDL grid). The year-specific corn / soybean masks are derived from these
windows in build_features.py, using only CDLs that were public at forecast time (CDL year Y is released by
NASS around the end of January of Y+1).

Sources:
  2008-2021  Microsoft Planetary Computer `usda-cdl` (type cropland, 90 km COG tiles, no auth)
  2022-2025  NASS CropScape state files (https://nassgeodata.gmu.edu/axis2/services/CDLService/GetCDLFile),
             which are not on Planetary Computer (PC's CDL ends in 2021). Downloaded one at a time to
             scratch, sampled, deleted.
Cells outside every available raster are 0 (background).

Output: <work>/cdl/cdl_<year>.npz  (pixel_id, win uint8 [npix, 81])
Usage: python extract_cdl.py --work <scratch>/us_sat [--years 2008-2025] [--threads 8]
"""
import argparse, os, re, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd, requests, rasterio
import planetary_computer as pc, pystac_client

HERE = os.path.dirname(os.path.abspath(__file__))
STFIPS = {"IA": "19", "IL": "17", "NE": "31", "MN": "27", "IN": "18", "OH": "39", "SD": "46", "ND": "38", "KS": "20", "MO": "29", "WI": "55", "MI": "26"}
HALF = 4  # 9 x 9 window


def get(url, tries=6, stream_to=None):
    err = None
    for k in range(tries):
        try:
            r = requests.get(url, timeout=900); r.raise_for_status()
            if stream_to:
                open(stream_to, "wb").write(r.content); return stream_to
            return r.content
        except Exception as e:  # noqa
            err = e; time.sleep(5 * (k + 1))
    raise RuntimeError(f"{url}: {err}")


def fill(arr, T, px, win):
    """copy the part of each pixel window that falls inside raster arr (affine T) into win (in place)"""
    c0 = np.floor((px.x_5070.values - T.c) / T.a).astype(int) - HALF
    r0 = np.floor((px.y_5070.values - T.f) / T.e).astype(int) - HALF
    H, W = arr.shape
    k = 2 * HALF + 1
    hit = (r0 + k > 0) & (r0 < H) & (c0 + k > 0) & (c0 < W)
    for i in np.where(hit)[0]:
        rs, cs = max(r0[i], 0), max(c0[i], 0); re_, ce = min(r0[i] + k, H), min(c0[i] + k, W)
        blk = arr[rs:re_, cs:ce]
        w = win[i].reshape(k, k)
        sub = w[rs - r0[i]:re_ - r0[i], cs - c0[i]:ce - c0[i]]
        sub[:] = np.where(blk > 0, blk, sub)
    return hit.sum()


def pc_year(y, px, threads):
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    its = [it for it in cat.search(collections=["usda-cdl"], bbox=[-104.1, 36.9, -80.5, 49.1],
                                   query={"usda_cdl:type": {"eq": "cropland"}}).items() if it.id.startswith(f"cropland_{y}_")]
    win = np.zeros((len(px), (2 * HALF + 1) ** 2), np.uint8)
    pad = 300
    use = []
    for it in its:
        t = it.properties["proj:transform"]; x0, y1 = t[2], t[5]; x1, y0 = x0 + 90000, y1 - 90000
        m = (px.x_5070 > x0 - pad) & (px.x_5070 < x1 + pad) & (px.y_5070 > y0 - pad) & (px.y_5070 < y1 + pad)
        if m.any():
            use.append((it, m.values))

    def one(arg):
        it, m = arg
        with rasterio.MemoryFile(get(pc.sign(it.assets["cropland"].href))) as mf, mf.open() as s:
            return s.read(1), s.transform, m
    with ThreadPoolExecutor(threads) as ex:
        for arr, T, m in ex.map(one, use):
            sub = win[m]; fill(arr, T, px[m], sub); win[m] = sub
    print(y, "tiles", len(use), flush=True)
    return win


def cropscape_year(y, px, tmp):
    win = np.zeros((len(px), (2 * HALF + 1) ** 2), np.uint8)
    for st, f in STFIPS.items():
        xml = get(f"https://nassgeodata.gmu.edu/axis2/services/CDLService/GetCDLFile?year={y}&fips={f}").decode()
        url = re.search(r"<returnURL>(.*?)</returnURL>", xml).group(1)
        fn = f"{tmp}/cdl_{y}_{f}.tif"
        get(url, stream_to=fn)
        with rasterio.open(fn) as s:
            T = s.transform; b = s.bounds
            m = ((px.x_5070 > b.left - 300) & (px.x_5070 < b.right + 300) & (px.y_5070 > b.bottom - 300) & (px.y_5070 < b.top + 300)).values
            arr = s.read(1)
        sub = win[m]; n = fill(arr, T, px[m], sub); win[m] = sub
        del arr; os.remove(fn)
        print(y, st, "pixels touched", n, flush=True)
    return win


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--data", default=os.path.join(HERE, "data"))
    ap.add_argument("--years", default="2008-2025")
    ap.add_argument("--threads", type=int, default=6)
    a = ap.parse_args()
    px = pd.read_csv(f"{a.data}/pixels.csv").sort_values("pixel_id").reset_index(drop=True)
    out = f"{a.work}/cdl"; os.makedirs(out, exist_ok=True)
    y0, y1 = map(int, a.years.split("-"))
    for y in range(y0, y1 + 1):
        fn = f"{out}/cdl_{y}.npz"
        if os.path.exists(fn):
            continue
        t0 = time.time()
        win = pc_year(y, px, a.threads) if y <= 2021 else cropscape_year(y, px, out)
        np.savez_compressed(fn, pixel_id=px.pixel_id.values, win=win)
        c = win.reshape(-1)
        print(y, f"{time.time() - t0:.0f}s", "corn", round((c == 1).mean(), 3), "soy", round((c == 5).mean(), 3), "zero", round((c == 0).mean(), 3), flush=True)


if __name__ == "__main__":
    main()
