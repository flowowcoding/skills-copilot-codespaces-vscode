"""Build the MODIS 500 m sample-pixel grid around core crop districts.

For each district that is "core" for chickpea, pigeonpea or sugarcane (build_districts.py), take MODIS
sinusoidal 500 m pixels on a regular grid (every --stride pixels, i.e. 1.5 km by default) within
--radius km of the ICRISAT district centroid. There is no free MODIS land-cover product on Planetary
Computer (MCD12Q1 is absent and esa-cci-lc search times out), so the cropland filter is applied later
from the EVI time series itself, using only the first seasons (see build_features.py).

Output: <out>/pixels.csv (pixel_id, dist_code, tile, row, col, lat, lon)
Usage:  python build_pixels.py --districts ../data/district_weights.csv --out <scratch>/india
"""
import argparse, os
import numpy as np, pandas as pd

R = 6371007.181
TILE = 1111950.5197665
PIX = TILE / 2400
X0, Y0 = -20015109.355798, 10007554.677899


def to_sin(lat, lon):
    return np.radians(lon) * R * np.cos(np.radians(lat)), np.radians(lat) * R


def from_sin(x, y):
    lat = np.degrees(y / R)
    return lat, np.degrees(x / (R * np.cos(np.radians(lat))))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--districts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--radius", type=float, default=25.0)
    ap.add_argument("--stride", type=int, default=3)
    a = ap.parse_args()
    d = pd.read_csv(a.districts)
    d = d[(d.core_chickpea + d.core_pigeonpea + d.core_sugarcane) > 0]
    rows = []
    for r in d.itertuples():
        cx, cy = to_sin(r.lat, r.lon)
        n = int(a.radius * 1000 / PIX)
        gc = np.floor((cx - X0) / PIX).astype(int); gr = np.floor((Y0 - cy) / PIX).astype(int)
        off = np.arange(-n, n + 1, a.stride)
        dc, dr = np.meshgrid(off, off)
        keep = (dc ** 2 + dr ** 2) * PIX ** 2 <= (a.radius * 1000) ** 2
        C, Rr = gc + dc[keep], gr + dr[keep]
        x = X0 + (C + 0.5) * PIX; y = Y0 - (Rr + 0.5) * PIX
        lat, lon = from_sin(x, y)
        for c, rr, la, lo in zip(C, Rr, lat, lon):
            rows.append((r.dist_code, f"h{c // 2400:02d}v{rr // 2400:02d}", rr % 2400, c % 2400, la, lo))
    px = pd.DataFrame(rows, columns=["dist_code", "tile", "row", "col", "lat", "lon"])
    px.insert(0, "pixel_id", np.arange(len(px)))
    os.makedirs(a.out, exist_ok=True)
    px.to_csv(f"{a.out}/pixels.csv", index=False, float_format="%.5f")
    print(len(d), "districts", len(px), "pixels", px.tile.value_counts().to_dict())


if __name__ == "__main__":
    main()
