"""Download CHIRPS v2.0 Africa monthly rainfall (0.05°) and reduce it to cocoa-weighted zone totals.

Source: https://data.chc.ucsb.edu/products/CHIRPS-2.0/africa_monthly/tifs/chirps-v2.0.YYYY.MM.tif.gz
Each file is downloaded in memory, cropped to the cocoa belt (mask_grid.csv cells), and discarded.

Point-in-time: the CHC directory listing gives each file's server timestamp. For files posted after
2016 that timestamp is used as the publication time (monthly finals appear ~11-15 days after month end,
e.g. 2026-08 posted 2026-09-11). Older files were bulk-(re)posted in 2015, so for those the
publication time is modelled as month end + 15 days (the median recent lag rounded up). CHIRPS v2 is not
revised after the final monthly release, so values == first-release values from that date.

Output: <out>/chirps_monthly_zone.csv  (month, zone, precip_mm [cocoa-area weighted], posted)
Usage: python fetch_chirps.py --mask ../data/mask_grid.csv --out ../data [--first 1981] [--threads 8]
"""
import argparse, gzip, io, os, re, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd, requests, rasterio
from rasterio.windows import from_bounds

BASE = "https://data.chc.ucsb.edu/products/CHIRPS-2.0/africa_monthly/tifs/"


def listing():
    h = requests.get(BASE, timeout=120).text
    rows = re.findall(r'(chirps-v2\.0\.(\d{4})\.(\d{2})\.tif\.gz)</a></td><td class="size">[^<]*</td><td class="date">([^<]*)<', h)
    return pd.DataFrame([dict(file=f, month=pd.Timestamp(int(y), int(m), 1), server=pd.to_datetime(d)) for f, y, m, d in rows])


def one(row, mask, bounds):
    for k in range(6):
        try:
            r = requests.get(BASE + row.file, timeout=300); r.raise_for_status()
            raw = gzip.decompress(r.content)
            with rasterio.MemoryFile(raw) as mf, mf.open() as s:
                win = from_bounds(*bounds, s.transform)
                a = s.read(1, window=win).astype("float64")
                tr = s.window_transform(win)
            a[a < 0] = np.nan
            cols = ((mask.lon.values - tr.c) / tr.a).astype(int)
            rws = ((mask.lat.values - tr.f) / tr.e).astype(int)
            v = a[rws, cols]
            out = []
            for z in ["CIV_W", "CIV_E", "GHA", "ALL"]:
                m = (mask.zone.values == z) if z != "ALL" else np.ones(len(mask), bool)
                ok = m & np.isfinite(v)
                out.append(dict(month=row.month, zone=z, precip_mm=np.average(v[ok], weights=mask.w_ha.values[ok])))
            return out
        except Exception as e:  # noqa
            err = e; time.sleep(5 * (k + 1))
    raise RuntimeError(f"{row.file}: {err}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mask", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--first", type=int, default=1981)
    ap.add_argument("--threads", type=int, default=8)
    a = ap.parse_args()
    mask = pd.read_csv(a.mask)
    bounds = (mask.lon.min() - 0.1, mask.lat.min() - 0.1, mask.lon.max() + 0.1, mask.lat.max() + 0.1)
    L = listing(); L = L[L.month.dt.year >= a.first]
    print("files", len(L), L.month.min().date(), L.month.max().date(), flush=True)
    res = []
    with ThreadPoolExecutor(a.threads) as ex:
        for i, o in enumerate(ex.map(lambda r: one(r, mask, bounds), L.itertuples())):
            res += o
            if i % 50 == 0:
                print(i, flush=True)
    d = pd.DataFrame(res).merge(L[["month", "server"]], on="month")
    month_end = d.month + pd.offsets.MonthEnd(0)
    d["posted"] = np.where(d.server.dt.year >= 2016, d.server.dt.normalize(), month_end + pd.Timedelta(days=15))
    d["posted"] = pd.to_datetime(d.posted).dt.date
    d[["month", "zone", "precip_mm", "posted"]].sort_values(["zone", "month"]).to_csv(f"{a.out}/chirps_monthly_zone.csv", index=False, float_format="%.2f")
    lag = (pd.to_datetime(d.server) - month_end).dt.days[d.server.dt.year >= 2016]
    print("lag days (post-2016 files): median", lag.median(), "max", lag.max())


if __name__ == "__main__":
    main()
