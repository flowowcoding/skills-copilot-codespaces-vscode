"""Least-cloudy Sentinel-2 NDVI for a bbox, resized to a target shape. Usage: s2ndvi.py bbox dates H W out.npy"""
import sys, numpy as np, rasterio, planetary_computer as pc, pystac_client
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from rasterio.enums import Resampling
from shapely.geometry import shape, box
bbox=[float(v) for v in sys.argv[1].split(",")]; dates=sys.argv[2]; H,W=int(sys.argv[3]),int(sys.argv[4])
cat=pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
items=[i for i in cat.search(collections=["sentinel-2-l2a"], bbox=bbox, datetime=dates, query={"eo:cloud_cover":{"lt":20}}).items() if shape(i.geometry).contains(box(*bbox))]
it=min(items,key=lambda i:i.properties["eo:cloud_cover"]); print(it.id)
b={}
for k in ["B04","B08"]:
    with rasterio.open(it.assets[k].href) as src:
        bb=transform_bounds("EPSG:4326", src.crs, *bbox)
        b[k]=src.read(1, window=from_bounds(*bb, src.transform), out_shape=(H,W), resampling=Resampling.bilinear).astype(float) - 1000  # L2A BOA offset (baseline 04.00+)
np.save(sys.argv[5], (b["B08"]-b["B04"])/(b["B08"]+b["B04"]+1e-6))
