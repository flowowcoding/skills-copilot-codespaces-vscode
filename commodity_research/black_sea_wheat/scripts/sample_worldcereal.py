#!/usr/bin/env python3
"""Sample ESA WorldCereal 2021 v100 (10 m) winter-cereal and spring-cereal classifications at
the sample pixels (fraction of the ~250 m MODIS cell classified as the crop).

Source: Zenodo record 7875105 (https://zenodo.org/records/7875105), one zip per product, one
GeoTIFF per agro-ecological zone (AEZ) inside. The zips are 7-19 GB, so each needed AEZ member
is streamed out of the remote zip with HTTP range requests (central directory read remotely),
decompressed to a temporary file, sampled, and deleted. Only AEZs that contain sample pixels
are read (AEZ polygons: WorldCereal_AEZ.geojson from the same record).

Classification codes: 100 = crop present, 0 = other (cropland but not the crop, or non-crop),
255 = no data. Fraction = share of valid 10 m cells == 100 within +-120 m of the pixel centre.

Usage: python sample_worldcereal.py --pixels data/reference/pixels.csv --aez SCRATCH/raw/worldcereal/aez.geojson \
          --tmp SCRATCH/raw/worldcereal --out data/reference/worldcereal_2021_at_pixels.csv
"""
import argparse
import io
import os
import shutil
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.windows import Window

REC = "https://zenodo.org/records/7875105/files/"
# AEZs read per product (bandwidth): winter cereals where winter wheat is grown (south + north
# calibration zones); spring cereals in the spring-wheat zones only. 43134/22195 hold <130 pixels.
READ = {"winter": {6136, 22095, 22096, 22190, 22194}, "spring": {17135, 22194, 22095}}
PRODUCTS = {"winter": "WorldCereal_2021_tc-wintercereals_wintercereals_classification.zip",
            "spring": "WorldCereal_2021_tc-springcereals_springcereals_classification.zip"}


class HttpFile(io.RawIOBase):
    """Minimal seekable file over HTTP range requests (for zipfile)."""

    def __init__(self, url):
        r = requests.head(url, allow_redirects=True, timeout=60)
        self.url, self.size, self.pos = r.url, int(r.headers["Content-Length"]), 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def seek(self, off, wh=0):
        self.pos = off if wh == 0 else (self.pos + off if wh == 1 else self.size + off)
        return self.pos

    def tell(self):
        return self.pos

    def read(self, n=-1):
        if n < 0:
            n = self.size - self.pos
        if n == 0 or self.pos >= self.size:
            return b""
        end = min(self.size, self.pos + n) - 1
        for k in range(5):
            try:
                r = requests.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"}, timeout=600)
                b = r.content
                break
            except Exception:  # noqa
                if k == 4:
                    raise
        self.pos += len(b)
        return b

    def readinto(self, b):
        d = self.read(len(b))
        b[:len(d)] = d
        return len(d)


def sample_tif(path, px):
    out = np.full(len(px), np.nan)
    with rasterio.open(path) as s:
        if s.crs.to_epsg() != 4326:
            from pyproj import Transformer
            tr = Transformer.from_crs(4326, s.crs, always_xy=True)
            xs, ys = tr.transform(px.lon.values, px.lat.values)
            hw = int(round(120 / abs(s.transform.a)))
        else:
            xs, ys = px.lon.values, px.lat.values
            hw = None
        for i, (x, y, la) in enumerate(zip(xs, ys, px.lat.values)):
            r, c = s.index(x, y)
            if hw is None:
                hx = int(round(120 / (abs(s.transform.a) * 111320 * np.cos(np.radians(la)))))
                hy = int(round(120 / (abs(s.transform.e) * 110540)))
            else:
                hx = hy = hw
            if r + hy < 0 or c + hx < 0 or r - hy >= s.height or c - hx >= s.width:
                continue
            w = Window(c - hx, r - hy, 2 * hx + 1, 2 * hy + 1)
            a = s.read(1, window=w, boundless=True, fill_value=255)
            v = a[a != 255]
            if v.size >= 0.5 * a.size:
                out[i] = (v == 100).mean()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pixels", required=True)
    ap.add_argument("--aez", required=True)
    ap.add_argument("--tmp", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    px = pd.read_csv(a.pixels)
    aez = gpd.read_file(a.aez)
    pts = gpd.GeoDataFrame(px, geometry=gpd.points_from_xy(px.lon, px.lat), crs=4326)
    j = gpd.sjoin(pts, aez[["aez_id", "geometry"]].to_crs(4326), predicate="within", how="left")
    j = j[~j.index.duplicated()]
    px["aez_id"] = j.aez_id.values
    print(px.groupby("aez_id").size())
    res = px[["pixel_id", "aez_id"]].copy()
    if os.path.exists(a.out):  # resume
        old = pd.read_csv(a.out)
        res = res.merge(old.drop(columns="aez_id"), on="pixel_id", how="left")
    for prod, zname in PRODUCTS.items():
        if f"wc_{prod}_frac" not in res:
            res[f"wc_{prod}_frac"] = np.nan
        z = zipfile.ZipFile(HttpFile(REC + zname + "?download=1"))
        members = {int(os.path.basename(i.filename).split("_")[0]): i for i in z.infolist() if i.filename.endswith(".tif")}
        for aid, g in px.groupby("aez_id"):
            aid = int(aid)
            if aid not in READ[prod]:
                continue
            if aid not in members:
                print(prod, aid, "no member")
                continue
            if res.loc[g.index, f"wc_{prod}_frac"].notna().any():
                continue
            tmp = os.path.join(a.tmp, f"{prod}_{aid}.tif")
            if not os.path.exists(tmp):
                print("extract", prod, aid, members[aid].file_size // 1e6, "MB", flush=True)
                with z.open(members[aid]) as src, open(tmp + ".part", "wb") as dst:
                    shutil.copyfileobj(src, dst, 16 * 2**20)
                os.replace(tmp + ".part", tmp)
            v = sample_tif(tmp, g)
            res.loc[g.index, f"wc_{prod}_frac"] = v
            os.remove(tmp)
            print(prod, aid, len(g), "valid", np.isfinite(v).sum(), "mean", np.nanmean(v), flush=True)
            res.to_csv(a.out, index=False)
    res.to_csv(a.out, index=False)


if __name__ == "__main__":
    main()
