#!/usr/bin/env python3
"""Cropland sampling frame on the MODIS 250 m sinusoidal grid for the Black Sea / Kazakh
wheat belt.

1. Regions. Natural Earth 10m admin-1 polygons (naciscdn.org) are grouped into the study
   regions below (federal-district style grouping; Crimea and Sevastopol are excluded
   because USDA excludes them from both Russia and Ukraine).
2. Cropland fraction. ESA WorldCover 2021 v200 (10 m; Planetary Computer `esa-worldcover`)
   is read at its 80 m overview (nearest-neighbour decimation by 8) and class 40
   ("cropland") pixels are binned into MODIS 250 m cells (h, v, row, col).
   WorldCover is a 2021 map applied to all years 2003-2026: it carries no yield
   information, but cropland that was abandoned or re-ploughed between 2003 and 2021
   is misclassified (documented in the README).
3. Sample. In each region, cells with cropland fraction >= --min-frac (default 0.75) and
   at least 6 overview pixels are drawn at random (--n per region, seed 42). The full
   count of such cells per region is kept as an area weight.

Winter vs spring separation is NOT done here (see build_masks.py: MODIS phenology,
calibrated on ESA WorldCereal 2021).

Usage: python build_frame.py --work SCRATCH --geo SCRATCH/raw/geo --out data/reference
Writes OUT/pixels.csv (pixel_id, region, country, oblast, tile, row, col, lon, lat, crop_frac),
       OUT/region_cropland_cells.csv, OUT/regions.csv
"""
import argparse
import os
from concurrent.futures import ThreadPoolExecutor

import geopandas as gpd
import numpy as np
import pandas as pd
import planetary_computer as pc
import pystac_client
import rasterio
from shapely.geometry import box

R = 6371007.181
T = 1111950.5197665
X0, Y0 = 20015109.354, 10007554.677
NPIX = 4800

REGIONS = {
    "RU_South": ["RU-KDA", "RU-ROS", "RU-STA", "RU-AD", "RU-KL", "RU-VGG", "RU-AST", "RU-DA", "RU-KB", "RU-KC",
                 "RU-SE", "RU-IN", "RU-CE"],
    "RU_Central": ["RU-BEL", "RU-VOR", "RU-KRS", "RU-LIP", "RU-TAM", "RU-ORL", "RU-TUL", "RU-RYA", "RU-BRY",
                   "RU-KLU", "RU-SMO", "RU-MOS", "RU-MOW", "RU-VLA", "RU-IVA", "RU-KOS", "RU-YAR", "RU-TVE"],
    "RU_Volga": ["RU-SAR", "RU-SAM", "RU-ULY", "RU-PNZ", "RU-TA", "RU-BA", "RU-ORE", "RU-MO", "RU-CU", "RU-NIZ",
                 "RU-ME", "RU-KIR", "RU-UD", "RU-PER"],
    "RU_UralsSiberia": ["RU-KGN", "RU-CHE", "RU-TYU", "RU-SVE", "RU-OMS", "RU-NVS", "RU-ALT", "RU-KEM", "RU-KYA",
                        "RU-TOM", "RU-KK"],
    "UA_South": ["UA-51", "UA-48", "UA-65", "UA-23", "UA-12", "UA-14", "UA-09"],
    "UA_CentralNorth": ["UA-35", "UA-53", "UA-63", "UA-05", "UA-71", "UA-32", "UA-30", "UA-59", "UA-74", "UA-18",
                        "UA-68", "UA-61", "UA-46", "UA-56", "UA-07", "UA-26", "UA-77", "UA-21"],
    "KZ_North": ["KZ-KUS", "KZ-SEV", "KZ-AKM", "KZ-PAV", "KZ-AST"],
    "KZ_Other": ["KZ-AKT", "KZ-ZAP", "KZ-KAR", "KZ-VOS"],
}
COUNTRY = {"RU": "Russia", "UA": "Ukraine", "KZ": "Kazakhstan"}


def sinu(lon, lat):
    la = np.radians(lat)
    return R * np.radians(lon) * np.cos(la), R * la


def inv_sinu(x, y):
    lat = np.degrees(y / R)
    lon = np.degrees(x / (R * np.cos(np.radians(lat))))
    return lon, lat


def cell_index(lon, lat):
    x, y = sinu(lon, lat)
    xs, ys = x + X0, Y0 - y
    h = np.floor(xs / T).astype(int); v = np.floor(ys / T).astype(int)
    col = np.floor((xs - h * T) / (T / NPIX)).astype(int); row = np.floor((ys - v * T) / (T / NPIX)).astype(int)
    return h, v, row, col


def cell_center(h, v, row, col):
    x = h * T + (col + 0.5) * T / NPIX - X0
    y = Y0 - (v * T + (row + 0.5) * T / NPIX)
    return inv_sinu(x, y)


def load_regions(geo):
    g = gpd.read_file(os.path.join(geo, "ne_10m_admin_1_states_provinces.shp"))
    rows = []
    for reg, codes in REGIONS.items():
        for c in codes:
            m = g[g.iso_3166_2 == c]
            if m.empty:
                raise SystemExit(f"missing {c}")
            for _, r in m.iterrows():
                rows.append(dict(region=reg, country=COUNTRY[reg[:2]], oblast=c, name=r["name_en"], geometry=r.geometry))
    return gpd.GeoDataFrame(rows, crs=g.crs)


def tile_counts(item):
    href = pc.sign(item.assets["map"].href)
    for k in range(5):
        try:
            with rasterio.open(href) as s:
                a = s.read(1, out_shape=(4500, 4500))
                tr = s.transform
            break
        except Exception:  # noqa
            if k == 4:
                raise
    rr, cc = np.nonzero(a > 0)
    sub = slice(None)
    lon = tr.c + (cc + 0.5) * tr.a * 8
    lat = tr.f + (rr + 0.5) * tr.e * 8
    crop = (a[rr, cc] == 40)
    h, v, row, col = cell_index(lon[sub], lat[sub])
    key = ((h * 100 + v).astype(np.int64) * NPIX + row) * NPIX + col
    d = pd.DataFrame({"key": key, "crop": crop})
    out = d.groupby("key").crop.agg(["sum", "size"])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--geo", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=3000)
    ap.add_argument("--min-frac", type=float, default=0.75)
    ap.add_argument("--threads", type=int, default=6)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    regs = load_regions(a.geo)
    regs.drop(columns="geometry").to_csv(os.path.join(a.out, "regions.csv"), index=False)
    cache = os.path.join(a.work, "worldcover_cells.parquet")
    if os.path.exists(cache):
        cells = pd.read_parquet(cache)
    else:
        cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
        union = regs.union_all()
        items = []
        for it in cat.search(collections=["esa-worldcover"], bbox=list(union.bounds),
                             query={"esa_worldcover:product_version": {"eq": "2.0.0"}}).items():
            if box(*it.bbox).intersects(union):
                items.append(it)
        print("worldcover tiles", len(items), flush=True)
        parts = []
        with ThreadPoolExecutor(a.threads) as ex:
            for i, p in enumerate(ex.map(tile_counts, items)):
                parts.append(p)
                if i % 10 == 0:
                    print(i, flush=True)
        cells = pd.concat(parts).groupby(level=0).sum().reset_index()
        cells.to_parquet(cache)
    cells["frac"] = cells["sum"] / cells["size"]
    k = cells.key.values
    col = k % NPIX; row = (k // NPIX) % NPIX; hv = k // NPIX // NPIX; h = hv // 100; v = hv % 100
    cells["h"], cells["v"], cells["row"], cells["col"] = h, v, row, col
    good = cells[(cells.frac >= a.min_frac) & (cells["size"] >= 6)].copy()
    lon, lat = cell_center(good.h.values, good.v.values, good.row.values, good.col.values)
    good["lon"], good["lat"] = lon, lat
    pts = gpd.GeoDataFrame(good, geometry=gpd.points_from_xy(lon, lat), crs=regs.crs)
    j = gpd.sjoin(pts, regs[["region", "country", "oblast", "geometry"]], predicate="within", how="inner")
    j = j[~j.index.duplicated()]
    counts = j.groupby(["country", "region", "oblast"]).size().rename("cropland_cells").reset_index()
    counts.to_csv(os.path.join(a.out, "region_cropland_cells.csv"), index=False)
    rng = np.random.default_rng(42)
    samp = []
    for reg, g in j.groupby("region"):
        n = min(a.n, len(g))
        samp.append(g.iloc[rng.choice(len(g), n, replace=False)])
    s = pd.concat(samp)
    s["tile"] = [f"h{int(x):02d}v{int(y):02d}" for x, y in zip(s.h, s.v)]
    s = s.sort_values(["region", "tile", "row", "col"]).reset_index(drop=True)
    s["pixel_id"] = np.arange(len(s))
    s = s.rename(columns={"frac": "crop_frac"})
    s[["pixel_id", "region", "country", "oblast", "tile", "row", "col", "lon", "lat", "crop_frac"]].round(
        {"lon": 5, "lat": 5, "crop_frac": 3}).to_csv(os.path.join(a.out, "pixels.csv"), index=False)
    print(counts.groupby("region").cropland_cells.sum())
    print(s.groupby(["region", "tile"]).size())


if __name__ == "__main__":
    main()
