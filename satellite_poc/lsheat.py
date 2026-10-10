"""Landsat 8/9 surface-temperature stack for a bbox; saves npz of ST (K) with cloud mask applied."""
import sys, numpy as np, rasterio, planetary_computer as pc, pystac_client
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from shapely.geometry import shape, box
from concurrent.futures import ThreadPoolExecutor
lon, lat, half, dates, out = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]), sys.argv[4], sys.argv[5]
bbox=[lon-half*1.25, lat-half, lon+half*1.25, lat+half]
cat=pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
items=[i for i in cat.search(collections=["landsat-c2-l2"], bbox=bbox, datetime=dates,
        query={"eo:cloud_cover":{"lt":40},"platform":{"in":["landsat-8","landsat-9"]}}).items()
       if shape(i.geometry).contains(box(*bbox))]
print(len(items))
def read(it):
    try:
        with rasterio.open(it.assets["lwir11"].href) as src:
            bb=transform_bounds("EPSG:4326", src.crs, *bbox); w=from_bounds(*bb, src.transform)
            st=src.read(1, window=w).astype(np.float32)
        with rasterio.open(it.assets["qa_pixel"].href) as src:
            qa=src.read(1, window=from_bounds(*bb, src.transform))
    except rasterio.errors.RasterioIOError:
        return None
    bad=((qa & 0b11111)>0) | (st==0)   # fill, dilated cloud, cirrus, cloud, shadow
    st=st*0.00341802+149.0; st[bad]=np.nan
    return it.datetime.strftime("%Y-%m-%d"), st
with ThreadPoolExecutor(8) as ex:
    got=[g for g in ex.map(read, items) if g]
from collections import Counter
shp=Counter(g[1].shape for g in got).most_common(1)[0][0]
got=sorted([g for g in got if g[1].shape==shp])
np.savez_compressed(out, dates=np.array([g[0] for g in got]), st=np.stack([g[1] for g in got]), bbox=np.array(bbox))
print(len(got), shp)
