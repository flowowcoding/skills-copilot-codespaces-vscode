"""Download a Sentinel-1 RTC VV/VH stack (one relative orbit) for a bbox. Saves npz."""
import sys, numpy as np, rasterio, planetary_computer as pc, pystac_client, collections
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from concurrent.futures import ThreadPoolExecutor
lon, lat, half, dates, out = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]), sys.argv[4], sys.argv[5]
bbox=[lon-half*1.25, lat-half, lon+half*1.25, lat+half]
cat=pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
items=list(cat.search(collections=["sentinel-1-rtc"], bbox=bbox, datetime=dates).items())
orb=collections.Counter((i.properties["sat:relative_orbit"], i.properties["sat:orbit_state"]) for i in items)
print(orb)
best=orb.most_common(1)[0][0]
items=[i for i in items if (i.properties["sat:relative_orbit"], i.properties["sat:orbit_state"])==best]
items.sort(key=lambda i: i.datetime)
ref=None
def read(it):
    res={}
    for pol in ["vv","vh"]:
        with rasterio.open(it.assets[pol].href) as src:
            bb=transform_bounds("EPSG:4326", src.crs, *bbox)
            w=from_bounds(*bb, src.transform)
            res[pol]=src.read(1, window=w, boundless=True, fill_value=np.nan).astype(np.float32)
            res["crs"]=str(src.crs); res["transform"]=tuple(src.window_transform(w))[:6]
    return it.datetime, res
with ThreadPoolExecutor(8) as ex:
    got=list(ex.map(read, items))
shape=collections.Counter(r["vv"].shape for _,r in got).most_common(1)[0][0]
got=[(d,r) for d,r in got if r["vv"].shape==shape]
np.savez_compressed(out, dates=np.array([d.strftime("%Y-%m-%dT%H:%M") for d,_ in got]),
    vv=np.stack([r["vv"] for _,r in got]), vh=np.stack([r["vh"] for _,r in got]),
    transform=np.array(got[0][1]["transform"]), crs=got[0][1]["crs"], bbox=np.array(bbox), orbit=str(best))
print(len(got), shape, best)
