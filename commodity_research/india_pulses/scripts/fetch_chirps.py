"""Download CHIRPS v2.0 monthly precipitation (0.05 deg) and keep only an India window.

Source: https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_monthly/tifs/ (no auth).
Point-in-time rule used downstream: month M is available on day 20 of month M+1 (CHIRPS final is
published in the third week of the following month).

Output: <work>/chirps/<YYYYMM>.npz with p10 (uint16, precip mm x10, 65535 = missing) on the window
lon 68..98 E, lat 6..37 N, plus the window transform (west, north, res).
Usage:  python fetch_chirps.py --work <scratch>/india [--first 2000-01 --last 2026-08 --threads 8]
"""
import argparse, gzip, os, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np, requests, rasterio

URL = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_monthly/tifs/chirps-v2.0.{y}.{m:02d}.tif.gz"
W, E, S, N = 68.0, 98.0, 6.0, 37.0


def get(url, tries=6):
    err = None
    for k in range(tries):
        try:
            r = requests.get(url, timeout=600); r.raise_for_status(); return r.content
        except Exception as e:  # noqa
            err = e; time.sleep(5 * (k + 1))
    raise RuntimeError(f"{url}: {err}")


def task(y, m, out):
    fn = f"{out}/{y}{m:02d}.npz"
    if os.path.exists(fn):
        return 0
    raw = gzip.decompress(get(URL.format(y=y, m=m)))
    with rasterio.MemoryFile(raw) as mf, mf.open() as s:
        T = s.transform
        c0, c1 = int(round((W - T.c) / T.a)), int(round((E - T.c) / T.a))
        r0, r1 = int(round((N - T.f) / T.e)), int(round((S - T.f) / T.e))
        a = s.read(1, window=((r0, r1), (c0, c1))).astype(float)
    a[a < 0] = np.nan
    np.savez_compressed(fn, p10=np.where(np.isnan(a), 65535, np.round(a * 10)).astype(np.uint16), west=W, north=N, res=0.05)
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--first", default="2000-01")
    ap.add_argument("--last", default="2026-08")
    ap.add_argument("--threads", type=int, default=8)
    a = ap.parse_args()
    out = f"{a.work}/chirps"; os.makedirs(out, exist_ok=True)
    f0 = tuple(map(int, a.first.split("-"))); f1 = tuple(map(int, a.last.split("-")))
    months = [(y, m) for y in range(f0[0], f1[0] + 1) for m in range(1, 13) if f0 <= (y, m) <= f1]
    with ThreadPoolExecutor(a.threads) as ex:
        futs = {ex.submit(task, y, m, out): (y, m) for y, m in months}
        for i, f in enumerate(as_completed(futs)):
            try:
                f.result()
            except Exception as e:  # noqa
                print("FAILED", futs[f], e, flush=True)
            if i % 20 == 0:
                print(i, len(futs), flush=True)


if __name__ == "__main__":
    main()
