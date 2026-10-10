"""Sentinel-2 true-colour chip for an exact bbox with a labelled pixel grid (10 m px).
Usage: gridchip.py lon0,lat0,lon1,lat1 DATES OUT.png [maxcloud]"""
import sys, numpy as np, rasterio, planetary_computer as pc, pystac_client
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from shapely.geometry import shape, box
from PIL import Image, ImageDraw
bbox=[float(v) for v in sys.argv[1].split(",")]; dates=sys.argv[2]; out=sys.argv[3]
mc=float(sys.argv[4]) if len(sys.argv)>4 else 10
cat=pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
items=[i for i in cat.search(collections=["sentinel-2-l2a"], bbox=bbox, datetime=dates, query={"eo:cloud_cover":{"lt":mc}}).items() if shape(i.geometry).contains(box(*bbox))]
it=min(items,key=lambda i:i.properties["eo:cloud_cover"]); print(it.id)
bands=[]
for b in ["B04","B03","B02"]:
    with rasterio.open(it.assets[b].href) as src:
        bb=transform_bounds("EPSG:4326", src.crs, *bbox)
        bands.append(src.read(1, window=from_bounds(*bb, src.transform)).astype(float)-1000)
rgb=np.clip((np.clip(np.dstack(bands),0,None)/3500)**0.8*255,0,255).astype(np.uint8)
H,W=rgb.shape[:2]; print("shape",H,W)
img=Image.fromarray(rgb).resize((W*2,H*2),Image.NEAREST); d=ImageDraw.Draw(img)
for x in range(0,W,50):
    d.line([(2*x,0),(2*x,2*H)],fill=(255,255,0),width=1); d.text((2*x+2,2),str(x),fill=(255,255,0))
for y in range(0,H,50):
    d.line([(0,2*y),(2*W,2*y)],fill=(255,255,0),width=1); d.text((2,2*y+2),str(y),fill=(255,255,0))
img.save(out)
