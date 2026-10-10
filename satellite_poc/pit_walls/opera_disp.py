"""Fetch OPERA DISP-S1 (NASA/JPL, Sentinel-1 InSAR displacement, 30 m) point time series
anonymously from ASF's displacement-portal API, on a grid of points around an open pit.

The ASF Vertex "displacement" view calls  POST https://d2qmcvu7qty7vn.cloudfront.net/timeseries
with {"wkt": "POINT(lon lat)", "bucket": "asf-cumulus-prod-opera-products", "polarization": "VV",
"flightDirection": "ASCENDING"|"DESCENDING"}. No Earthdata login is needed for this endpoint
(the NetCDF granules themselves do need one). Each answer holds, per acquisition, the
short-wavelength LOS displacement (m) of the 30 m pixel containing the point, re-referenced to
the first date of the frame, plus an is_masked flag (low temporal coherence etc.). Polygon
queries fail server-side (out of memory), so we sample points.

Points: a regular grid (SPACING m) inside the pit ring from prereg.json, labelled with the
compass sector, plus a sparser control ring (3.0-4.5 km).

Usage:
  python opera_disp.py SITE OUT.csv [--spacing 200] [--ctrl-spacing 400] [--cache DIR] [--workers 6]
Output CSV (long): pid, lon, lat, dist_m, sector, direction, frame, x, y, date, disp_mm, masked
"""
import argparse, json, os, math, time
import numpy as np, pandas as pd, requests
from concurrent.futures import ThreadPoolExecutor

API = "https://d2qmcvu7qty7vn.cloudfront.net/timeseries"
HERE = os.path.dirname(os.path.abspath(__file__))


def sector_of(az, sectors):
    for name, (a0, a1) in sectors.items():
        if (a0 <= a1 and a0 <= az < a1) or (a0 > a1 and (az >= a0 or az < a1)):
            return name
    return None


def grid(site, spacing, ctrl_spacing):
    lon0, lat0 = site["pit_bottom"]; r0, r1 = site["ring_m"]
    mlat = 111_320.0; mlon = 111_320.0 * math.cos(math.radians(lat0))
    pts = []
    for sp, rmin, rmax, kind in [(spacing, r0, r1, "pit"), (ctrl_spacing, 3000, 4500, "control")]:
        n = int(rmax // sp) + 1
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                dx, dy = i * sp, j * sp; r = math.hypot(dx, dy)
                if rmin <= r <= rmax:
                    az = (math.degrees(math.atan2(dx, dy)) + 360) % 360
                    sec = sector_of(az, site["sectors_deg_from_north"]) if kind == "pit" else "control"
                    pts.append((lon0 + dx / mlon, lat0 + dy / mlat, r, sec))
    return pd.DataFrame(pts, columns=["lon", "lat", "dist_m", "sector"])


def fetch(lon, lat, direction, cache):
    fn = os.path.join(cache, f"{direction[:3]}_{lon:.5f}_{lat:.5f}.json")
    if os.path.exists(fn):
        return json.load(open(fn))
    body = {"wkt": f"POINT({lon:.6f} {lat:.6f})", "bucket": "asf-cumulus-prod-opera-products",
            "polarization": "VV", "flightDirection": direction}
    for attempt in range(4):
        try:
            r = requests.post(API, json=body, timeout=180)
            if r.status_code == 200:
                d = r.json(); json.dump(d, open(fn, "w")); return d
            if r.status_code == 400:
                json.dump({"detail": r.text}, open(fn, "w")); return None
        except requests.RequestException:
            pass
        time.sleep(3 * (attempt + 1))
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site"); ap.add_argument("out")
    ap.add_argument("--spacing", type=float, default=200); ap.add_argument("--ctrl-spacing", type=float, default=400)
    ap.add_argument("--cache", default="opera_cache"); ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--directions", default="ASCENDING,DESCENDING")
    a = ap.parse_args()
    site = json.load(open(os.path.join(HERE, "prereg.json")))["sites"][a.site]
    os.makedirs(a.cache, exist_ok=True)
    pts = grid(site, a.spacing, a.ctrl_spacing); pts["pid"] = range(len(pts))
    print(len(pts), "points", pts.sector.value_counts().to_dict())
    rows = []
    for direction in a.directions.split(","):
        with ThreadPoolExecutor(a.workers) as ex:
            res = list(ex.map(lambda p: fetch(p.lon, p.lat, direction, a.cache), pts.itertuples()))
        for p, d in zip(pts.itertuples(), res):
            if not d or "detail" in d:
                continue
            for k, v in d.items():
                if not isinstance(v.get("secondary_datetime"), str):
                    continue   # summary row (means)
                rows.append((p.pid, p.lon, p.lat, p.dist_m, p.sector, direction, v.get("frame"), v.get("x"), v.get("y"),
                             v["secondary_datetime"][:10], v["short_wavelength_displacement"] * 1000, bool(v.get("is_masked")),
                             v["reference_datetime"][:10]))
        print(direction, "done", len(rows))
    df = pd.DataFrame(rows, columns=["pid", "lon", "lat", "dist_m", "sector", "direction", "frame", "x", "y",
                                     "date", "disp_mm", "masked", "ref_date"])
    df.to_csv(a.out, index=False, float_format="%.5g")
    print(df.groupby(["direction", "sector"]).pid.nunique())


if __name__ == "__main__":
    main()
