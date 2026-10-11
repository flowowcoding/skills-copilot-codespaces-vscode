"""Sentinel-2 SWIR hot-pixel signal for a smelter (Microsoft Planetary Computer, no account).

Physics: a surface at >~500 C emits enough at 2.2 um (B12) and, hotter, at 1.6 um (B11) to show
on top of reflected sunlight. Natural daytime surfaces almost never have B12 reflectance above
B11, so "B12 clearly above B11 and bright" flags molten slag, matte/converter mouths, anode
furnaces and hot slag dumps. Detection rule (fixed 2026-10-11 from the Kennecott/Altonorte/
Gresik chips in `figures/locate/`, before any time series was computed):

    TAI  =  (B12 - B11) / B8A                      (thermal anomaly index, Liu et al. 2021)
    hot  =  TAI >= 0.45 and B12 - B11 >= 0.05 and B12 >= 0.15 and B8A <= 0.30   (L2A reflectance)
         or B11 >= 0.80 and B12 >= 0.80 and B11 >= 1.5 * B8A and B8A <= 0.35  (SWIR near saturation)

A first rule (B12 >= 0.2 and B12 >= 1.1 x B11) was dropped after the chips: it lit up whole
roofs at Gresik and the wet edge of the Kennecott tailings dam every pass (B12/B11 ~1.13).
The B8A caps were added for the same reason: the persistent false positives at Gresik (jetty
stockpile sheds) are bright in the NIR (B8A 0.34-0.56) with a stable TAI (CV < 0.3), while the
real hot pixels at Altonorte and Kennecott sit on dark slag (B8A 0.10-0.26) with TAI CV 0.6-1.5.

Per scene and smelter box: n_hot (20 m pixels), hot_excess = sum(B12 - B11) over hot pixels,
and the cloud fraction of the box from the scene classification (SCL 8, 9, 10; hot pixels
themselves are excluded because SCL sometimes calls them cloud or "saturated").

Sub-commands:
    python s2_hot.py locate NAME LAT LON [--half-km 3] [--dates 2023-01-01/2023-12-31] [--out PNG]
        Hot-pixel frequency over the period on a SWIR false-colour background; prints the
        centroid of hot pixels so the smelter box can be centred on the furnaces.
    python s2_hot.py series NAME LAT LON [--half-km 1.5] [--dates 2017-01-01/2026-10-10] --out CSV
        One row per Sentinel-2 acquisition (all orbits; one tile per datatake), plus
        <out>_hotpix.npz with every hot pixel (scene row, y, x, B12-B11, B8A) so that pixel
        masks can be applied afterwards (see index.py).

Reflectance: DN / 10000, minus the 0.1 BOA offset ESA added from processing baseline 04.00
(25 Jan 2022) onward.
"""
import argparse, math, sys
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
import planetary_computer as pc
import pystac_client
from shapely.geometry import shape, box

STAC = "https://planetarycomputer.microsoft.com/api/stac/v1"
BANDS = ["B8A", "B11", "B12", "SCL"]


def bbox_of(lat, lon, half_km):
    dlat = half_km / 111.32
    dlon = half_km / (111.32 * math.cos(math.radians(lat)))
    return [lon - dlon, lat - dlat, lon + dlon, lat + dlat]


def search(bb, dates, max_cloud=None, collection="sentinel-2-l2a", tries=6):
    """STAC search with retries (the Planetary Computer API times out under load)."""
    import time
    q = {"eo:cloud_cover": {"lt": max_cloud}} if max_cloud is not None else None
    for k in range(tries):
        try:
            cat = pystac_client.Client.open(STAC, modifier=pc.sign_inplace)
            items = list(cat.search(collections=[collection], bbox=bb, datetime=dates, query=q).items())
            return [i for i in items if shape(i.geometry).contains(box(*bb))]
        except Exception as e:
            print("search retry", k, str(e)[:80], file=sys.stderr)
            time.sleep(5 * (k + 1))
    raise RuntimeError("STAC search failed")


def read_item(it, bb, shape20=None):
    """Return dict of reflectance arrays on a 20 m grid (B8A, B11, B12) + SCL, or None."""
    out = {}
    try:
        for b in BANDS:
            with rasterio.open(it.assets[b].href) as src:
                w = from_bounds(*transform_bounds("EPSG:4326", src.crs, *bb), src.transform)
                h, wd = (shape20 if shape20 else (max(1, round(w.height * src.res[0] / 20)), max(1, round(w.width * src.res[0] / 20))))
                out[b] = src.read(1, window=w, out_shape=(h, wd), resampling=Resampling.nearest, boundless=True, fill_value=0)
    except Exception:
        return None
    off = 0.1 if it.properties.get("s2:processing_baseline", "00.00") >= "04.00" else 0.0
    nod = out["B12"] == 0
    for b in ["B8A", "B11", "B12"]:
        out[b] = out[b].astype(np.float32) / 10000.0 - off
    out["nodata"] = nod
    return out


def hot_mask(r):
    b8, b11, b12 = r["B8A"], r["B11"], r["B12"]
    tai = (b12 - b11) / np.maximum(b8, 0.01)          # thermal anomaly index (Liu et al. 2021)
    m1 = (tai >= 0.45) & (b12 - b11 >= 0.05) & (b12 >= 0.15) & (b8 <= 0.30)
    m2 = (b11 >= 0.80) & (b12 >= 0.80) & (b11 >= 1.5 * np.maximum(b8, 0.01)) & (b8 <= 0.35)
    return (m1 | m2) & ~r["nodata"]


def scene_stats(it, bb):
    r = read_item(it, bb)
    if r is None:
        return None
    hot = hot_mask(r)
    valid = ~r["nodata"]
    cloud = np.isin(r["SCL"], [8, 9, 10]) & ~hot & valid
    nv = valid.sum()
    if nv == 0:
        return None
    exc = np.where(hot, r["B12"] - r["B11"], 0).sum()
    yy, xx = np.nonzero(hot)
    pix = dict(shape=hot.shape, y=yy.astype(np.int16), x=xx.astype(np.int16),
               exc=(r["B12"][hot] - r["B11"][hot]).astype(np.float32),
               b8=r["B8A"][hot].astype(np.float32))
    return pix, dict(date=it.datetime.strftime("%Y-%m-%d"), time=it.datetime.strftime("%H:%M"), item=it.id,
                tile=it.properties.get("s2:mgrs_tile"), orbit=it.properties.get("sat:relative_orbit"),
                baseline=it.properties.get("s2:processing_baseline"), valid_frac=round(nv / valid.size, 3),
                cloud_frac=round(cloud.sum() / nv, 3), n_hot=int(hot.sum()), hot_excess=round(float(exc), 3),
                b12_max=round(float(np.where(valid, r["B12"], 0).max()), 3))


def cmd_series(a):
    bb = bbox_of(a.lat, a.lon, a.half_km)
    items = search(bb, a.dates)
    # one item per acquisition: the same datatake is often cut into two MGRS tiles
    import collections
    tiles = collections.Counter(i.properties.get("s2:mgrs_tile") for i in items)
    items.sort(key=lambda i: -tiles[i.properties.get("s2:mgrs_tile")])
    seen, keep = set(), []
    for i in items:
        k = (i.datetime.strftime("%Y-%m-%d"), i.properties.get("sat:relative_orbit"))
        if k not in seen:
            seen.add(k); keep.append(i)
    print(a.name, len(items), "items,", len(keep), "acquisitions", file=sys.stderr)
    items = keep
    with ThreadPoolExecutor(a.threads) as ex:
        res = [r for r in ex.map(lambda it: scene_stats(it, bb), items) if r]
    import pandas as pd, collections
    shp = collections.Counter(p["shape"] for p, _ in res).most_common(1)[0][0]
    res = [(p, r) for p, r in res if p["shape"] == shp]       # same grid for the pixel archive
    res.sort(key=lambda pr: (pr[1]["date"], pr[1]["item"]))
    df = pd.DataFrame([r for _, r in res])
    df.insert(0, "smelter", a.name)
    df.to_csv(a.out, index=False)
    # sparse archive of every hot pixel: scene (row index in the CSV), y, x, B12-B11, B8A
    cat = lambda k, dt: np.concatenate([p[k] for p, _ in res]).astype(dt) if res else np.zeros(0, dt)
    sc = np.concatenate([np.full(len(p["y"]), k, np.int32) for k, (p, _) in enumerate(res)]) if res else np.zeros(0, np.int32)
    np.savez_compressed(a.out.replace(".csv", "_hotpix.npz"), shape=np.array(shp), bbox=np.array(bb), scene=sc,
                        y=cat("y", np.int16), x=cat("x", np.int16), exc=cat("exc", np.float32), b8=cat("b8", np.float32))
    print(a.name, len(df), "scenes,", (df.n_hot > 0).mean().round(3), "with hot pixels", file=sys.stderr)


def cmd_locate(a):
    from PIL import Image
    bb = bbox_of(a.lat, a.lon, a.half_km)
    items = search(bb, a.dates, max_cloud=40)
    items = sorted(items, key=lambda i: i.properties["eo:cloud_cover"])[: a.max_items]
    first = None
    for it in items:
        first = read_item(it, bb)
        if first is not None:
            break
    shp = first["B12"].shape
    with ThreadPoolExecutor(a.threads) as ex:
        rs = [r for r in ex.map(lambda it: read_item(it, bb, shp), items) if r is not None]
    freq = np.zeros(shp, np.float32); n = np.zeros(shp, np.float32); stack = []
    for r in rs:
        clear = ~np.isin(r["SCL"], [8, 9, 10]) & ~r["nodata"]
        h = hot_mask(r)
        freq += h; n += clear | h
        stack.append(np.dstack([r["B12"], r["B11"], r["B8A"]]))
    f = freq / np.maximum(n, 1)
    bg = np.nanmedian(np.stack(stack), axis=0)
    rgb = np.clip(bg / 0.6, 0, 1) ** 0.8 * 255
    hotpix = f > 0.02
    rgb[hotpix] = [255, 30, 30] * np.ones((hotpix.sum(), 3)) * np.clip(0.4 + f[hotpix, None] * 3, 0, 1) + rgb[hotpix] * 0
    img = Image.fromarray(rgb.astype(np.uint8)).resize((shp[1] * a.zoom, shp[0] * a.zoom), Image.NEAREST)
    img.save(a.out)
    ys, xs = np.nonzero(f > 0.05)
    if len(ys):
        wts = f[ys, xs]
        cy, cx = (ys * wts).sum() / wts.sum(), (xs * wts).sum() / wts.sum()
        lat = bb[3] - (cy + 0.5) / shp[0] * (bb[3] - bb[1]); lon = bb[0] + (cx + 0.5) / shp[1] * (bb[2] - bb[0])
        sy, sx = ys.std() * 20 / 1000, xs.std() * 20 / 1000
        print(f"{a.name}: {len(rs)} scenes, {len(ys)} px hot>5%, peak freq {f.max():.2f}, centroid {lat:.5f},{lon:.5f}, spread {sy:.2f}x{sx:.2f} km")
    else:
        print(f"{a.name}: {len(rs)} scenes, no pixel hot in >5% of scenes (max freq {f.max():.3f})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ["locate", "series"]:
        p = sub.add_parser(c)
        p.add_argument("name"); p.add_argument("lat", type=float); p.add_argument("lon", type=float)
        p.add_argument("--half-km", type=float, default=3.0 if c == "locate" else 1.5)
        p.add_argument("--dates", default="2023-01-01/2023-12-31" if c == "locate" else "2017-01-01/2026-10-10")
        p.add_argument("--out", required=(c == "series"), default=None)
        p.add_argument("--threads", type=int, default=12)
        if c == "locate":
            p.add_argument("--max-items", type=int, default=40)
            p.add_argument("--zoom", type=int, default=3)
    a = ap.parse_args()
    if a.cmd == "locate" and a.out is None:
        a.out = f"locate_{a.name}.png"
    (cmd_locate if a.cmd == "locate" else cmd_series)(a)


if __name__ == "__main__":
    main()
