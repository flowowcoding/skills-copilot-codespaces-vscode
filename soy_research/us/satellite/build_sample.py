"""Stratified candidate pixel sample for the US corn / soybean satellite model.

Step 1 of the mask (the candidate superset; it only decides which MODIS pixels get downloaded):
  * counties of the 12 states (IA IL NE MN IN OH SD ND KS MO WI MI), Census 2020 cartographic boundaries
  * county corn+soy share = mean NASS planted acres (corn + soybeans) 2006-2010 / county land area.
    These county estimates were all published by Feb 2011, so the selection uses no information from the
    forecast years (2011+); for the 2008-2010 training years it is a mild, documented look-ahead that only
    affects which pixels are candidates, never the per-year mask.
  * selected counties: share >= 0.30, or, if a state has fewer than 25 such counties, its 25 highest-share
    counties with share >= 0.10
  * per state, N pixels (default 5000): county drawn with probability proportional to its 2006-10 corn+soy
    acres, then a uniform random point in the county, snapped to the MODIS 250 m sinusoidal grid cell
    centre (duplicates dropped)
The year-specific corn and soybean masks are built later from the previous years' CDL (build_cdl.py).

Outputs: data/counties_selected.csv, data/pixels.csv (pixel_id, state, fips, lon, lat, tile, row, col,
         x_5070, y_5070)
Usage: python build_sample.py --geo <scratch>/geo [--n 5000] [--seed 7]
"""
import argparse, os, zipfile
import numpy as np, pandas as pd, geopandas as gpd
from pyproj import Transformer
from shapely.geometry import Point

HERE = os.path.dirname(os.path.abspath(__file__))
STFIPS = {"IA": "19", "IL": "17", "NE": "31", "MN": "27", "IN": "18", "OH": "39", "SD": "46", "ND": "38", "KS": "20", "MO": "29", "WI": "55", "MI": "26"}
SIN = "+proj=sinu +R=6371007.181 +nadgrids=@null +wktext"
TILE, NPX = 1111950.5197665, 4800
CELL = TILE / NPX


def snap(lon, lat):
    tr = Transformer.from_crs("EPSG:4326", SIN, always_xy=True)
    x, y = tr.transform(lon, lat)
    h = np.floor((x + 18 * TILE) / TILE).astype(int); v = np.floor((9 * TILE - y) / TILE).astype(int)
    col = np.floor((x + 18 * TILE - h * TILE) / CELL).astype(int); row = np.floor((9 * TILE - y - v * TILE) / CELL).astype(int)
    xc = -18 * TILE + h * TILE + (col + 0.5) * CELL; yc = 9 * TILE - v * TILE - (row + 0.5) * CELL
    lo, la = Transformer.from_crs(SIN, "EPSG:4326", always_xy=True).transform(xc, yc)
    return h, v, row, col, lo, la


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--geo", required=True)
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--data", default=os.path.join(HERE, "data"))
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    co = gpd.read_file(f"zip://{a.geo}/cb_2020_us_county_500k.zip")
    co = co[co.STATEFP.isin(STFIPS.values())].copy()
    co["fips"] = co.GEOID; co["state"] = co.STATEFP.map({v: k for k, v in STFIPS.items()})
    cp = pd.read_csv(f"{a.data}/county_planted.csv", dtype={"fips": str})
    cp = cp[cp.year.between(2006, 2010)].groupby(["fips", "year"]).planted_ac.sum().groupby("fips").mean()
    co["cs_acres"] = co.fips.map(cp).fillna(0)
    co["share"] = co.cs_acres / (co.ALAND / 4046.86)
    sel = []
    for s, g in co.groupby("state"):
        g = g.sort_values("share", ascending=False)
        k = g[g.share >= 0.30]
        if len(k) < 25:
            k = g[g.share >= 0.10].head(25)
        sel.append(k)
    sel = pd.concat(sel)
    sel[["state", "fips", "NAME", "cs_acres", "share"]].sort_values(["state", "share"], ascending=[True, False]) \
        .to_csv(f"{a.data}/counties_selected.csv", index=False, float_format="%.4f")
    print(sel.groupby("state").agg(n=("fips", "size"), share=("share", "mean"), acres=("cs_acres", "sum")))
    print("selected share of 12-state corn+soy acres:", sel.cs_acres.sum() / co.cs_acres.sum())
    rows = []
    for s, g in sel.groupby("state"):
        p = (g.cs_acres / g.cs_acres.sum()).values
        draws = rng.choice(len(g), size=int(a.n * 1.3), p=p)
        pts = []
        for i in draws:
            geom = g.geometry.iloc[i]; x0, y0, x1, y1 = geom.bounds
            while True:
                lo, la = rng.uniform(x0, x1), rng.uniform(y0, y1)
                if geom.contains(Point(lo, la)):
                    break
            pts.append((g.fips.iloc[i], lo, la))
        df = pd.DataFrame(pts, columns=["fips", "lon", "lat"])
        h, v, r, c, lo, la = snap(df.lon.values, df.lat.values)
        df = df.assign(h=h, v=v, row=r, col=c, lon=lo, lat=la, state=s).drop_duplicates(["h", "v", "row", "col"]).head(a.n)
        rows.append(df)
    px = pd.concat(rows, ignore_index=True)
    px["tile"] = [f"h{h:02d}v{v:02d}" for h, v in zip(px.h, px.v)]
    x, y = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True).transform(px.lon.values, px.lat.values)
    px["x_5070"], px["y_5070"] = np.round(x, 1), np.round(y, 1)
    px.insert(0, "pixel_id", np.arange(len(px)))
    px[["pixel_id", "state", "fips", "lon", "lat", "tile", "row", "col", "x_5070", "y_5070"]].to_csv(f"{a.data}/pixels.csv", index=False, float_format="%.6f")
    print(px.groupby(["state"]).size(), px.groupby("tile").size())


if __name__ == "__main__":
    main()
