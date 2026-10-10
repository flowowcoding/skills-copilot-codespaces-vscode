"""Sentinel-2 L2A stack (B04 red, B11 SWIR) at 20 m for a bbox, one tile + relative orbit,
cloud/shadow pixels set to 0 via the scene classification layer. Saves npz (uint16).
Usage: s2stack.py lon0,lat0,lon1,lat1 DATES OUT.npz"""
import sys, collections
import numpy as np, rasterio, planetary_computer as pc, pystac_client
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from rasterio.enums import Resampling
from shapely.geometry import shape, box
from concurrent.futures import ThreadPoolExecutor

bbox = [float(v) for v in sys.argv[1].split(",")]; dates, out = sys.argv[2], sys.argv[3]
cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
items = [i for i in cat.search(collections=["sentinel-2-l2a"], bbox=bbox, datetime=dates,
                               query={"eo:cloud_cover": {"lt": 30}}).items()
         if shape(i.geometry).contains(box(*bbox))]
key = lambda i: (i.properties["s2:mgrs_tile"], i.properties["sat:relative_orbit"])
best = collections.Counter(map(key, items)).most_common(1)[0][0]
items = sorted([i for i in items if key(i) == best], key=lambda i: i.datetime)
print(len(items), best)
shape_ = None

def read(it):
    try:
        res = {}
        for b in ["B04", "B11", "SCL"]:
            with rasterio.open(it.assets[b].href) as src:
                bb = transform_bounds("EPSG:4326", src.crs, *bbox)
                w = from_bounds(*bb, src.transform)
                h, wd = round(w.height * src.res[0] / 20), round(w.width * src.res[0] / 20)
                res[b] = src.read(1, window=w, out_shape=(h, wd), resampling=Resampling.nearest)
        bad = np.isin(res["SCL"], [0, 1, 3, 8, 9, 10, 11])   # nodata, saturated, shadow, cloud, cirrus, snow
        off = 1000 if it.properties.get("s2:processing_baseline", "00.00") >= "04.00" else 0
        st = np.stack([res["B04"], res["B11"]]).astype(np.int32) - off
        st = np.clip(st, 1, 65535).astype(np.uint16); st[:, bad] = 0
        return it.datetime.strftime("%Y-%m-%d"), st, bad.mean()
    except rasterio.errors.RasterioIOError:
        return None

with ThreadPoolExecutor(8) as ex:
    got = [g for g in ex.map(read, items) if g and g[2] < 0.2]
shp = collections.Counter(g[1].shape for g in got).most_common(1)[0][0]
got = [g for g in got if g[1].shape == shp]
np.savez_compressed(out, dates=np.array([g[0] for g in got]), refl=np.stack([g[1] for g in got]), bbox=np.array(bbox))
print(len(got), shp)
