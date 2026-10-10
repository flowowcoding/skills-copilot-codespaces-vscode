"""Multi-band Sentinel-2 L2A stack for a bbox (one MGRS tile + relative orbit), clouds masked.

Generalises ../s2stack.py: any list of bands, any output resolution. Pixels flagged by the
scene classification layer as nodata, saturated, cloud shadow, cloud (medium/high), cirrus
or snow are set to 0 in every band. Reflectances are corrected for the +1000 offset of
processing baseline >= 04.00, so values are surface reflectance x 10000.

Usage:
    python s2bands.py LON0,LAT0,LON1,LAT1 DATES OUT.npz [--res 20] [--bands B02,B03,B04,B08,B11,B12]
                      [--maxcloud 40] [--maxbad 0.3]

DATES is a STAC interval like 2019-01-01/2026-10-01. Output npz: dates (YYYY-MM-DD),
refl (T, B, H, W) uint16, bands, bbox, badfrac (T,), tile.
"""
import argparse
import collections
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import planetary_computer as pc
import pystac_client
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from shapely.geometry import box, shape

BAD_SCL = [0, 1, 3, 8, 9, 10, 11]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bbox")
    ap.add_argument("dates")
    ap.add_argument("out")
    ap.add_argument("--res", type=float, default=20)
    ap.add_argument("--bands", default="B02,B03,B04,B08,B11,B12")
    ap.add_argument("--maxcloud", type=float, default=40, help="scene-level eo:cloud_cover filter")
    ap.add_argument("--maxbad", type=float, default=0.3, help="drop images with more masked bbox pixels")
    a = ap.parse_args()
    bbox = [float(v) for v in a.bbox.split(",")]
    bands = a.bands.split(",")

    cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1",
                                    modifier=pc.sign_inplace)
    items = [i for i in cat.search(collections=["sentinel-2-l2a"], bbox=bbox, datetime=a.dates,
                                   query={"eo:cloud_cover": {"lt": a.maxcloud}}).items()
             if shape(i.geometry).contains(box(*bbox))]
    key = lambda i: (i.properties["s2:mgrs_tile"], i.properties["sat:relative_orbit"])
    best = collections.Counter(map(key, items)).most_common(1)[0][0]
    items = sorted([i for i in items if key(i) == best], key=lambda i: i.datetime)
    print(len(items), "scenes on", best, flush=True)

    def read(it):
        for attempt in range(3):
            try:
                res = {}
                for b in bands + ["SCL"]:
                    with rasterio.open(it.assets[b].href) as src:
                        bb = transform_bounds("EPSG:4326", src.crs, *bbox)
                        w = from_bounds(*bb, src.transform)
                        h = round(w.height * src.res[0] / a.res)
                        wd = round(w.width * src.res[0] / a.res)
                        rs = Resampling.nearest if b == "SCL" or src.res[0] <= a.res else Resampling.bilinear
                        res[b] = src.read(1, window=w, out_shape=(h, wd), resampling=rs)
                bad = np.isin(res["SCL"], BAD_SCL)
                off = 1000 if it.properties.get("s2:processing_baseline", "00.00") >= "04.00" else 0
                st = np.stack([res[b] for b in bands]).astype(np.int32) - off
                st = np.clip(st, 1, 65535).astype(np.uint16)
                st[:, bad] = 0
                return it.datetime.strftime("%Y-%m-%d"), st, float(bad.mean())
            except (rasterio.errors.RasterioIOError, rasterio.errors.WindowError):
                continue
        return None

    with ThreadPoolExecutor(8) as ex:
        got = [g for g in ex.map(read, items) if g and g[2] < a.maxbad]
    shp = collections.Counter(g[1].shape for g in got).most_common(1)[0][0]
    got = [g for g in got if g[1].shape == shp]
    # same acquisition processed twice -> keep the last
    seen = {}
    for g in got:
        seen[g[0]] = g
    got = [seen[k] for k in sorted(seen)]
    np.savez_compressed(a.out, dates=np.array([g[0] for g in got]), refl=np.stack([g[1] for g in got]),
                        bands=np.array(bands), bbox=np.array(bbox), badfrac=np.array([g[2] for g in got]),
                        tile=str(best))
    print(len(got), "kept", shp)


if __name__ == "__main__":
    main()
