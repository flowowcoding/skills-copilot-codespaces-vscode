"""Download a Sentinel-2 L2A brightness stack (red B04 + SWIR B11, 20 m) for one stack box in
mines.json, from Microsoft Planetary Computer (no account needed).

Usage:
    python s2bright.py STACK_NAME DATES OUT.npz [--mines mines.json] [--maxbad 0.2]
    e.g. python s2bright.py escondida 2018-01-01/2026-10-10 escondida_s2.npz

Same recipe as ../s2stack.py, with three changes for 9-year, many-mine runs:
  * stores only brightness = B04 + B11 (uint16, 0 = masked) to halve the size;
  * B04 (10 m) is averaged to the 20 m B11 grid instead of nearest-neighbour;
  * asset URLs are signed at read time, so long downloads don't outlive their tokens.
One MGRS tile + relative orbit (the most frequent one that fully contains the box) is used so
that every image has the same viewing geometry. Pixels flagged by the scene classification
(no data, saturated, cloud shadow, cloud, cirrus, snow) are set to 0, and images with more than
MAXBAD of the box masked are dropped. Duplicate acquisitions (same date reprocessed) keep the
latest processing.
"""
import argparse
import collections
import json
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import planetary_computer as pc
import pystac_client
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from shapely.geometry import box, shape

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("stack"); ap.add_argument("dates"); ap.add_argument("out")
ap.add_argument("--mines", default="mines.json"); ap.add_argument("--maxbad", type=float, default=0.2)
a = ap.parse_args()
bbox = json.load(open(a.mines))["stacks"][a.stack]

cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
items = [i for i in cat.search(collections=["sentinel-2-l2a"], bbox=bbox, datetime=a.dates,
                               query={"eo:cloud_cover": {"lt": 40}}).items()
         if shape(i.geometry).contains(box(*bbox))]
key = lambda i: (i.properties["s2:mgrs_tile"], i.properties["sat:relative_orbit"])
best = collections.Counter(map(key, items)).most_common(1)[0][0]
items = sorted([i for i in items if key(i) == best], key=lambda i: i.datetime)
print(a.stack, len(items), "scenes on", best, flush=True)


def read_one(it):
    res = {}
    for b in ["B11", "SCL", "B04"]:
        with rasterio.open(pc.sign(it.assets[b].href)) as src:
            bb = transform_bounds("EPSG:4326", src.crs, *bbox)
            w = from_bounds(*bb, src.transform)
            if b == "B11":
                shp = (round(w.height), round(w.width))
            res[b] = src.read(1, window=w, out_shape=shp,
                              resampling=Resampling.average if b == "B04" else Resampling.nearest)
    bad = np.isin(res["SCL"], [0, 1, 3, 8, 9, 10, 11])
    off = 1000 if it.properties.get("s2:processing_baseline", "00.00") >= "04.00" else 0
    br = res["B04"].astype(np.int32) + res["B11"].astype(np.int32) - 2 * off
    br = np.clip(br, 1, 65535).astype(np.uint16)
    br[bad] = 0
    return it.datetime.strftime("%Y-%m-%d"), it.properties.get("s2:processing_baseline", ""), br, bad.mean()


def read(it):
    for attempt in range(4):
        try:
            return read_one(it)
        except Exception as e:          # network hiccups, expired tokens, broken COGs
            if attempt == 3:
                print("  skip", it.id, type(e).__name__, flush=True)
                return None
            time.sleep(5 * (attempt + 1))


t0 = time.time()
with ThreadPoolExecutor(8) as ex:
    got = [g for g in ex.map(read, items) if g and g[3] < a.maxbad]
shp = collections.Counter(g[2].shape for g in got).most_common(1)[0][0]
got = [g for g in got if g[2].shape == shp]
byday = {}
for g in got:                           # same date twice = reprocessing; keep the newest baseline
    if g[0] not in byday or g[1] >= byday[g[0]][1]:
        byday[g[0]] = g
got = [byday[k] for k in sorted(byday)]
np.savez_compressed(a.out, dates=np.array([g[0] for g in got]), bright=np.stack([g[2] for g in got]),
                    bbox=np.array(bbox), tile=str(best))
print(a.stack, "kept", len(got), "images", shp, f"{(time.time() - t0) / 60:.1f} min", flush=True)
