"""Extract weather drivers at the sample pixels.

  chirps : CHIRPS v2.0 monthly precipitation (0.05 deg, data.chc.ucsb.edu), Jul 2000 - latest.
           Point-in-time rule used downstream: month M is treated as available on day 20 of M+1
           (CHIRPS final is released in the third week of the following month).
  lst    : MODIS Terra MOD11A2 v061 8-day daytime land-surface temperature (1 km, Planetary Computer),
           composites starting late Aug .. early May. Available downstream at composite end + 10 days.

Rasters are read in memory and discarded; only pixel values are kept.
Outputs: <work>/chirps/<YYYYMM>.npz (precip mm x10, uint16)
         <work>/lst/<YYYYDDD>_<tile>.npz (LST K x50 raw uint16, 0 = no clear-sky obs)
Usage: python extract_weather.py --work <scratch>/soy_sat --what chirps|lst [--threads 16]
"""
import argparse, gzip, os, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, pandas as pd, requests, rasterio
import planetary_computer as pc, pystac_client

HERE = os.path.dirname(os.path.abspath(__file__))
CHIRPS = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_monthly/tifs/chirps-v2.0.{y}.{m:02d}.tif.gz"


def get(url, tries=5):
    for k in range(tries):
        try:
            r = requests.get(url, timeout=300); r.raise_for_status(); return r.content
        except Exception as e:  # noqa
            err = e; time.sleep(4 * (k + 1))
    raise RuntimeError(f"{url}: {err}")


def chirps_task(y, m, px, out):
    fn = f"{out}/{y}{m:02d}.npz"
    if os.path.exists(fn):
        return 0
    raw = gzip.decompress(get(CHIRPS.format(y=y, m=m)))
    with rasterio.MemoryFile(raw) as mf, mf.open() as s:
        T = s.transform
        cc = np.floor((px.lon.values - T.c) / T.a).astype(int); rr = np.floor((px.lat.values - T.f) / T.e).astype(int)
        win_r0, win_r1 = rr.min(), rr.max() + 1; win_c0, win_c1 = cc.min(), cc.max() + 1
        arr = s.read(1, window=((win_r0, win_r1), (win_c0, win_c1)))
        v = arr[rr - win_r0, cc - win_c0].astype(float)
    v[v < 0] = np.nan
    np.savez(fn, p10=np.where(np.isnan(v), 65535, np.round(v * 10)).astype(np.uint16))
    return 1


def lst_items(tiles, first, last):
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    rows = []
    for y in range(first, last + 1):
        for it in cat.search(collections=["modis-11A2-061"], datetime=f"{y}-01-01/{y}-12-31", bbox=[-62, -34, -38, -2]).items():
            if not it.id.startswith("MOD11A2"):
                continue
            t = f"h{int(it.properties['modis:horizontal-tile']):02d}v{int(it.properties['modis:vertical-tile']):02d}"
            doy = int(it.id.split(".")[1][5:8])
            if t in tiles and (doy >= 241 or doy <= 121):
                rows.append(dict(key=it.id.split(".")[1][1:], tile=t, start=it.properties["start_datetime"][:10],
                                 end=it.properties["end_datetime"][:10], href=it.assets["LST_Day_1km"].href))
        print("listed", y, len(rows), flush=True)
    return pd.DataFrame(rows)


def lst_task(row, px, out):
    fn = f"{out}/{row.key}_{row.tile}.npz"
    if os.path.exists(fn):
        return 0
    with rasterio.MemoryFile(get(pc.sign(row.href))) as mf, mf.open() as s:
        a = s.read(1)
    np.savez(fn, lst=a[px.row.values // 2, px.col.values // 2], start=row.start, end=row.end)
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--what", choices=["chirps", "lst"], required=True)
    ap.add_argument("--data", default=os.path.join(HERE, "data"))
    ap.add_argument("--threads", type=int, default=16)
    a = ap.parse_args()
    px = pd.read_csv(f"{a.data}/pixels.csv")
    out = f"{a.work}/{a.what}"; os.makedirs(out, exist_ok=True)
    with ThreadPoolExecutor(a.threads) as ex:
        if a.what == "chirps":
            months = [(y, m) for y in range(2000, 2027) for m in range(1, 13) if (2000, 7) <= (y, m) <= (2026, 8)]
            futs = [ex.submit(chirps_task, y, m, px, out) for y, m in months]
        else:
            lf = f"{a.work}/lst_items.csv"
            items = pd.read_csv(lf) if os.path.exists(lf) else lst_items(set(px.tile), 2000, 2026)
            items = items[items.start >= "2000-08-01"]; items.to_csv(lf, index=False)
            g = {t: d for t, d in px.groupby("tile")}
            futs = [ex.submit(lst_task, r, g[r.tile], out) for r in items.itertuples()]
        for i, f in enumerate(as_completed(futs)):
            try:
                f.result()
            except Exception as e:  # noqa
                print("FAILED", e, flush=True)
            if i % 50 == 0:
                print(i, len(futs), flush=True)


if __name__ == "__main__":
    main()
