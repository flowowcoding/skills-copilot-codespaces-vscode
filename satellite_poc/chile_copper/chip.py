"""Sentinel-2 true-colour chip with a lon/lat grid, for drawing and checking pit zones.

Usage:
    python chip.py [--zones mines.json --mine NAME] [--step 0.01] -- LON0,LAT0,LON1,LAT1 DATES OUT.png
(the "--" is needed because western/southern coordinates start with a minus sign)

Picks the least-cloudy L2A scene in DATES that fully covers the box. Grid lines every STEP
degrees are labelled with their longitude (top) and latitude (left). With --zones, the pit
polygon(s) of NAME from mines.json are drawn in orange so the zone can be checked by eye.
"""
import argparse
import json

import numpy as np
import planetary_computer as pc
import pystac_client
import rasterio
from PIL import Image, ImageDraw
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from shapely.geometry import box, shape

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("bbox"); ap.add_argument("dates"); ap.add_argument("out")
ap.add_argument("--zones"); ap.add_argument("--mine"); ap.add_argument("--step", type=float, default=0.01)
ap.add_argument("--scale", type=int, default=1)
a = ap.parse_args()
bbox = [float(v) for v in a.bbox.split(",")]
cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
items = [i for i in cat.search(collections=["sentinel-2-l2a"], bbox=bbox, datetime=a.dates,
                               query={"eo:cloud_cover": {"lt": 10}}).items()
         if shape(i.geometry).contains(box(*bbox))]
it = min(items, key=lambda i: i.properties["eo:cloud_cover"])
print(it.id)
off = 1000 if it.properties.get("s2:processing_baseline", "00.00") >= "04.00" else 0
bands = []
for b in ["B04", "B03", "B02"]:
    with rasterio.open(it.assets[b].href) as src:
        bb = transform_bounds("EPSG:4326", src.crs, *bbox)
        bands.append(src.read(1, window=from_bounds(*bb, src.transform)).astype(float) - off)
rgb = np.clip((np.clip(np.dstack(bands), 0, None) / 4000) ** 0.8 * 255, 0, 255).astype(np.uint8)
H, W = rgb.shape[:2]
s = a.scale
img = Image.fromarray(rgb).resize((W * s, H * s), Image.BILINEAR)
d = ImageDraw.Draw(img)
X = lambda lon: (lon - bbox[0]) / (bbox[2] - bbox[0]) * W * s
Y = lambda lat: (bbox[3] - lat) / (bbox[3] - bbox[1]) * H * s
for lon in np.arange(np.ceil(bbox[0] / a.step) * a.step, bbox[2], a.step):
    d.line([(X(lon), 0), (X(lon), H * s)], fill=(255, 255, 0), width=1)
    d.text((X(lon) + 2, 2), f"{lon:.2f}", fill=(255, 255, 0))
for lat in np.arange(np.ceil(bbox[1] / a.step) * a.step, bbox[3], a.step):
    d.line([(0, Y(lat)), (W * s, Y(lat))], fill=(255, 255, 0), width=1)
    d.text((2, Y(lat) + 2), f"{lat:.2f}", fill=(255, 255, 0))
if a.zones:
    z = json.load(open(a.zones))[a.mine]
    for poly in z["pit"]:
        d.line([(X(x), Y(y)) for x, y in poly + [poly[0]]], fill=(255, 110, 0), width=3)
img.save(out := a.out)
print("saved", out, W, H)
