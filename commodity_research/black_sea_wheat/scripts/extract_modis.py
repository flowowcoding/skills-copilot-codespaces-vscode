#!/usr/bin/env python3
"""Extract Aqua MODIS MYD13Q1 v061 (250 m, 16-day) EVI and pixel reliability at the sample
pixels of data/reference/pixels.csv (adapted from soy_research/us/satellite/extract_modis.py).

Why Aqua: Terra's (MOD) overpass has drifted since ~2022 (the Brazil holdout failure); Aqua's
composites are phased 8 days later than Terra's.

Composites (Aqua start day-of-year):
  spring/summer of the harvest year: 73 89 105 121 137 153 169 185 201 217 233 249
  autumn before the harvest (winter-crop establishment): 281 297 (stored under the
  calendar year in which they were acquired)
Point-in-time rule applied downstream: a composite is usable from its end date + 14 days.

Source: Microsoft Planetary Computer STAC `modis-13Q1-061` (no auth). Each tile asset is read
in memory, sample pixels are pulled out, the raster is discarded. Resumable. Reprocessed
duplicates: the most recently produced item wins.

Usage: python extract_modis.py --work SCRATCH [--pixels data/reference/pixels.csv] [--threads 6]
Outputs: SCRATCH/modis_MYD/<YYYYDDD>_<tile>.npz (pixel_id, evi, rel, start, end, item),
         SCRATCH/modis_MYD_items.csv
"""
import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import planetary_computer as pc
import pystac_client
import rasterio
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = {"evi": "250m_16_days_EVI", "rel": "250m_16_days_pixel_reliability"}
DOYS = [73, 89, 105, 121, 137, 153, 169, 185, 201, 217, 233, 249, 281, 297]


def list_items(tiles, first, last):
    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    rows = []
    for t in sorted(tiles):
        h, v = int(t[1:3]), int(t[4:6])
        for it in cat.search(collections=["modis-13Q1-061"], datetime=f"{first}-03-01/{last}-12-31",
                             query={"modis:horizontal-tile": {"eq": h}, "modis:vertical-tile": {"eq": v},
                                    "platform": {"eq": "aqua"}}).items():
            if not it.id.startswith("MYD13Q1"):
                continue
            doy = int(it.id.split(".")[1][5:8])
            if doy not in DOYS:
                continue
            rows.append(dict(item=it.id, tile=t, start=it.properties["start_datetime"][:10],
                             end=it.properties["end_datetime"][:10], key=it.id.split(".")[1][1:],
                             produced=it.id.split(".")[-1], **{k: it.assets[a].href for k, a in ASSETS.items()}))
        print("listed", t, len(rows), flush=True)
    d = pd.DataFrame(rows).sort_values("produced").drop_duplicates(["key", "tile"], keep="last")
    return d.sort_values(["key", "tile"])


def fetch(href, tries=6):
    err = None
    for k in range(tries):
        try:
            r = requests.get(pc.sign(href), timeout=300)
            r.raise_for_status()
            with rasterio.MemoryFile(r.content) as m, m.open() as s:
                return s.read(1)
        except Exception as e:  # noqa
            err = e
            time.sleep(4 * (k + 1))
    raise RuntimeError(f"{href}: {err}")


def task(row, px, outdir):
    fn = f"{outdir}/{row.key}_{row.tile}.npz"
    if os.path.exists(fn):
        return 0
    rr, cc = px.row.values, px.col.values
    out = {}
    for k in ASSETS:
        a = fetch(getattr(row, k))
        out[k] = a[rr, cc]
        del a
    np.savez(fn + ".tmp.npz", pixel_id=px.pixel_id.values.astype(np.int32), evi=out["evi"].astype(np.int16),
             rel=out["rel"].astype(np.int8), start=row.start, end=row.end, item=row.item)
    os.replace(fn + ".tmp.npz", fn)
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--pixels", default=os.path.join(HERE, "..", "data", "reference", "pixels.csv"))
    ap.add_argument("--threads", type=int, default=6)
    ap.add_argument("--first-year", type=int, default=2002)
    ap.add_argument("--last-year", type=int, default=2026)
    ap.add_argument("--relist", action="store_true")
    ap.add_argument("--years", default=None, help="comma list of calendar years to process (default all)")
    a = ap.parse_args()
    px = pd.read_csv(a.pixels)
    tiles = set(px.tile)
    outdir = f"{a.work}/modis_MYD"
    os.makedirs(outdir, exist_ok=True)
    lf = f"{a.work}/modis_MYD_items.csv"
    if os.path.exists(lf) and not a.relist:
        items = pd.read_csv(lf, dtype={"key": str})
    else:
        items = list_items(tiles, a.first_year, a.last_year)
        items.to_csv(lf, index=False)
    items = items[items.tile.isin(tiles)]
    if a.years:
        items = items[items.key.str[:4].astype(int).isin([int(y) for y in a.years.split(",")])]
    print("items", len(items), flush=True)
    groups = {t: g for t, g in px.groupby("tile")}
    t0 = time.time()
    n = 0
    with ThreadPoolExecutor(a.threads) as ex:
        futs = [ex.submit(task, r, groups[r.tile], outdir) for r in items.itertuples()]
        for i, f in enumerate(as_completed(futs)):
            try:
                n += f.result()
            except Exception as e:  # noqa
                print("FAILED", e, flush=True)
            if i % 25 == 0:
                print(i, len(futs), f"{time.time() - t0:.0f}s new={n}", flush=True)
    print("done", n, flush=True)


if __name__ == "__main__":
    main()
