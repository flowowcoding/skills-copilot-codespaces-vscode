#!/usr/bin/env python3
"""Daily weather for the wheat-belt sample from NASA POWER (https://power.larc.nasa.gov,
daily point API, community AG): T2M_MAX, T2M_MIN (deg C), PRECTOTCORR (mm/day, bias-
corrected MERRA-2/IMERG blend), SNODP (MERRA-2 snow depth, cm). 2001-01-01 onward.

Why POWER: ERA5 on Planetary Computer ends in 2024; Open-Meteo's free tier caps a 26-year
multi-point pull far below what is needed (fractional call accounting); CHIRPS stops at
50 N, while about half of the sample pixels (all of the Volga north of Saratov, Urals,
Siberia, northern Kazakhstan, Kharkiv/Kyiv) lie north of 50 N (counted in the README).

Points: centres of 1 x 1 degree cells holding >= --min-px sample pixels of
data/reference/pixels.csv; each cell carries its pixel count per region as weight.
Latency: POWER served data through day d on about d+4 when checked on 2026-10-11; the
feature builder uses day d only from d+5. Values are the current (reprocessed) archive,
not the provisional near-real-time values that were visible at the time.

Usage: python fetch_weather.py --pixels data/reference/pixels.csv --raw SCRATCH/raw/power \
          --out data/features [--end 2026-10-10]
Writes OUT/weather_points.csv (cell, lat, lon, region, n_px) and
       SCRATCH/raw/power/<cell>.csv (one raw CSV per point)
"""
import argparse
import io
import os
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import requests

PARAMS = "T2M_MAX,T2M_MIN,PRECTOTCORR,SNODP"


def fetch(cell, lat, lon, raw, start, end):
    fn = os.path.join(raw, f"{cell}.csv")
    if os.path.exists(fn) and os.path.getsize(fn) > 1000:
        return 0
    url = (f"https://power.larc.nasa.gov/api/temporal/daily/point?parameters={PARAMS}&community=AG"
           f"&longitude={lon}&latitude={lat}&start={start}&end={end}&format=CSV")
    for k in range(6):
        try:
            r = requests.get(url, timeout=300)
            r.raise_for_status()
            t = r.text
            body = t[t.index("-END HEADER-") + len("-END HEADER-"):].strip()
            d = pd.read_csv(io.StringIO(body))
            d.to_csv(fn + ".tmp", index=False)
            os.replace(fn + ".tmp", fn)
            return 1
        except Exception as e:  # noqa
            err = e
            time.sleep(10 * (k + 1))
    print("FAILED", cell, err, flush=True)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pixels", required=True)
    ap.add_argument("--raw", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-px", type=int, default=15)
    ap.add_argument("--start", default="20010101")
    ap.add_argument("--end", default="20261010")
    ap.add_argument("--threads", type=int, default=4)
    a = ap.parse_args()
    os.makedirs(a.raw, exist_ok=True)
    os.makedirs(a.out, exist_ok=True)
    px = pd.read_csv(a.pixels)
    px["clat"] = np.floor(px.lat) + 0.5
    px["clon"] = np.floor(px.lon) + 0.5
    px["cell"] = [f"N{la:.1f}_E{lo:.1f}" for la, lo in zip(px.clat, px.clon)]
    pts = px.groupby(["cell", "clat", "clon", "region"]).size().rename("n_px").reset_index()
    keep = pts.groupby("cell").n_px.sum()
    pts = pts[pts.cell.isin(keep[keep >= a.min_px].index)]
    pts.rename(columns={"clat": "lat", "clon": "lon"}).to_csv(os.path.join(a.out, "weather_points.csv"), index=False)
    cells = pts.drop_duplicates("cell")
    print("points", len(cells), pts.groupby("region").cell.nunique().to_dict(), flush=True)
    with ThreadPoolExecutor(a.threads) as ex:
        n = sum(ex.map(lambda r: fetch(r.cell, r.clat, r.clon, a.raw, a.start, a.end), cells.itertuples()))
    print("downloaded", n)


if __name__ == "__main__":
    main()
