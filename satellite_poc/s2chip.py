import sys, numpy as np, rasterio, planetary_computer as pc, pystac_client
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from PIL import Image
lon, lat, half = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])  # half-size deg
date, out = sys.argv[4], sys.argv[5]
bbox=[lon-half*1.25, lat-half, lon+half*1.25, lat+half]
cat=pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
items=list(cat.search(collections=["sentinel-2-l2a"], bbox=bbox, datetime=date, query={"eo:cloud_cover":{"lt":5}}).items())
from shapely.geometry import shape, box
items=[i for i in items if shape(i.geometry).contains(box(*bbox))]
items.sort(key=lambda i: i.properties["eo:cloud_cover"])
it=items[0]; print(it.id, it.properties["eo:cloud_cover"])
bands=[]
for b in ["B04","B03","B02"]:
    with rasterio.open(it.assets[b].href) as src:
        bb=transform_bounds("EPSG:4326", src.crs, *bbox)
        bands.append(src.read(1, window=from_bounds(*bb, src.transform)).astype(float))
rgb=np.dstack(bands); rgb=np.clip((rgb/4500)**0.8*255,0,255).astype(np.uint8)
Image.fromarray(rgb).resize((rgb.shape[1]*int(sys.argv[6]), rgb.shape[0]*int(sys.argv[6])), Image.NEAREST).save(out); print(rgb.shape)
