"""Sentinel-2 true-colour chip with a lon/lat graticule, optionally with segment outlines.

Used to draw wall/heap segments in lon/lat from imagery only (never from radar results).

Usage:
  python basemap.py [--step 0.005] [--segments SEGMENTS.json --site NAME] -- LON0,LAT0,LON1,LAT1 DATES OUT.png
  (options go before "--" because the bbox may start with a minus sign)
"""
import argparse, json
import numpy as np, rasterio, planetary_computer as pc, pystac_client
from rasterio.warp import transform_bounds, reproject, Resampling
from rasterio.transform import from_bounds as tfb
from shapely.geometry import shape, box
from PIL import Image, ImageDraw

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("bbox"); ap.add_argument("dates"); ap.add_argument("out")
ap.add_argument("--step", type=float, default=0.005)
ap.add_argument("--segments"); ap.add_argument("--site")
ap.add_argument("--maxcloud", type=float, default=5)
ap.add_argument("--px", type=float, default=0.0001, help="output pixel size in degrees")
a = ap.parse_args()
bbox = [float(v) for v in a.bbox.split(",")]
cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
items = [i for i in cat.search(collections=["sentinel-2-l2a"], bbox=bbox, datetime=a.dates,
         query={"eo:cloud_cover": {"lt": a.maxcloud}}).items() if shape(i.geometry).contains(box(*bbox))]
it = min(items, key=lambda i: i.properties["eo:cloud_cover"]); print(it.id)
W = int(round((bbox[2] - bbox[0]) / a.px)); H = int(round((bbox[3] - bbox[1]) / a.px * 1.0))
dst_t = tfb(*bbox, W, H)
bands = []
for b in ["B04", "B03", "B02"]:
    with rasterio.open(it.assets[b].href) as src:
        out = np.zeros((H, W), np.float32)
        reproject(rasterio.band(src, 1), out, dst_transform=dst_t, dst_crs="EPSG:4326", resampling=Resampling.bilinear)
        bands.append(out - 1000 if int(it.properties.get("s2:processing_baseline", "04.00").split(".")[0]) >= 4 else out)
rgb = np.clip((np.clip(np.dstack(bands), 0, None) / 3500) ** 0.8 * 255, 0, 255).astype(np.uint8)
img = Image.fromarray(rgb); d = ImageDraw.Draw(img)
def px(lon, lat): return ((lon - bbox[0]) / a.px, (bbox[3] - lat) / a.px)
for lon in np.arange(np.ceil(bbox[0] / a.step) * a.step, bbox[2], a.step):
    x, _ = px(lon, 0); d.line([(x, 0), (x, H)], fill=(255, 255, 0)); d.text((x + 2, 2), f"{lon:.3f}", fill=(255, 255, 0))
for lat in np.arange(np.ceil(bbox[1] / a.step) * a.step, bbox[3], a.step):
    _, y = px(0, lat); d.line([(0, y), (W, y)], fill=(255, 255, 0)); d.text((2, y + 2), f"{lat:.3f}", fill=(255, 255, 0))
if a.segments:
    segs = json.load(open(a.segments))["sites"][a.site]["segments"]
    for name, poly in segs.items():
        pts = [px(lo, la) for lo, la in poly]
        d.polygon(pts, outline=(0, 255, 255)); d.line(pts + [pts[0]], fill=(0, 255, 255), width=2)
        cx = np.mean([p[0] for p in pts]); cy = np.mean([p[1] for p in pts])
        d.text((cx - 20, cy), name, fill=(0, 255, 255))
img.save(a.out); print(img.size)
