"""Night-time hot-spot detections at a smelter from Sentinel-3 SLSTR Fire Radiative Power (FRP)
Level-2 product (Planetary Computer collection sentinel-3-slstr-frp-l2-netcdf, from Aug 2020; free).

SLSTR's 1 km MWIR channels see furnaces and hot slag at night, when there is no reflected sun.
For every FRP granule covering the smelter whose local solar time is between 20:00 and 05:00, the
file's fire list is read and fires within --radius-km of the smelter are counted.
Caveat: the product lists detections only; it does not say whether the smelter pixel was cloudy,
so a granule with no detection is "no detection", not "inactive". Use for dry sites.

Usage:
    python s3_frp.py NAME LAT LON START END OUT.csv [--radius-km 1.5] [--threads 8]
"""
import argparse, math, sys
from concurrent.futures import ThreadPoolExecutor
import numpy as np, requests, netCDF4, pandas as pd
import planetary_computer as pc, pystac_client


def km(lat1, lon1, lat2, lon2):
    dy = (lat2 - lat1) * 111.32
    dx = (lon2 - lon1) * 111.32 * math.cos(math.radians(lat1))
    return np.hypot(dx, dy)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name"); ap.add_argument("lat", type=float); ap.add_argument("lon", type=float)
    ap.add_argument("start"); ap.add_argument("end"); ap.add_argument("out")
    ap.add_argument("--radius-km", type=float, default=1.5); ap.add_argument("--threads", type=int, default=8)
    a = ap.parse_args()
    d = 0.01
    bb = [a.lon - d, a.lat - d, a.lon + d, a.lat + d]
    items = []
    for k in range(6):
        try:
            cat = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
            items = list(cat.search(collections=["sentinel-3-slstr-frp-l2-netcdf"], bbox=bb, datetime=f"{a.start}/{a.end}").items())
            break
        except Exception as e:
            print("retry", e, file=sys.stderr)
    def lst(it):
        t = pd.Timestamp(it.properties["datetime"])
        return (t.hour + t.minute / 60 + a.lon / 15) % 24
    night = [it for it in items if lst(it) >= 20 or lst(it) <= 5]
    # NT (non-time-critical) and NR duplicates: keep NT when both exist
    by = {}
    for it in night:
        key = it.properties["datetime"][:16]
        if key not in by or it.properties.get("s3:processing_timeliness") == "NT":
            by[key] = it
    night = list(by.values())
    print(a.name, len(items), "granules,", len(night), "night", file=sys.stderr)

    def fetch(it):
        for k in range(3):
            try:
                r = requests.get(it.assets["frp-in"].href, timeout=60)
                if r.ok:
                    return it, r.content
            except Exception:
                pass
        return it, None

    rows = []
    with ThreadPoolExecutor(a.threads) as ex:          # download in threads, parse in this thread
        for it, b in ex.map(fetch, night):              # (the netCDF/HDF5 library is not thread-safe)
            if b is None:
                continue
            try:
                ds = netCDF4.Dataset("frp.nc", memory=b)
            except Exception:
                continue
            n, fmax = 0, 0.0
            if "latitude" in ds.variables and ds.variables["latitude"].shape[0] > 0:
                la = np.ma.filled(ds.variables["latitude"][:], np.nan).astype(float)
                lo = np.ma.filled(ds.variables["longitude"][:], np.nan).astype(float)
                frp = np.ma.filled(ds.variables["FRP_MWIR"][:], np.nan).astype(float)
                near = km(a.lat, a.lon, la, lo) <= a.radius_km
                n, fmax = int(near.sum()), float(np.nanmax(frp[near])) if near.any() else 0.0
            ds.close()
            rows.append(dict(smelter=a.name, datetime=it.properties["datetime"][:19], platform=it.properties.get("platform"),
                             local_solar_hour=round(lst(it), 1), n_fire=n, frp_max_mw=round(fmax, 2)))
    df = pd.DataFrame(rows).sort_values("datetime")
    df.to_csv(a.out, index=False)
    print(a.name, len(df), "night granules,", int((df.n_fire > 0).sum()), "with a detection", file=sys.stderr)


if __name__ == "__main__":
    main()
