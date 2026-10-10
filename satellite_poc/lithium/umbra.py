"""Umbra open-data SAR (X-band spotlight, ~0.5 m) for one site: catalogue and a resampled stack.

Data: public bucket https://umbra-open-data-catalog.s3.amazonaws.com/, prefix
"sar-data/tasks/<SITE>/". Each collect has a *_GEC.tif (uint8 amplitude, EPSG:4326, tiled with
overviews, so it can be read windowed over HTTPS) plus a STAC json and/or _METADATA.json.

Subcommands:
    python umbra.py index "SITE NAME" OUT.csv
        one row per collect: time, platform, orbit state, look direction, incidence, squint, url
    python umbra.py stack INDEX.csv LON0,LAT0,LON1,LAT1 RES_M OUT.npz
        every GEC warped (average) onto a common lat/lon grid of about RES_M metres, read from
        the COG overview closest to RES_M/2. Pixels outside a collect's footprint are 0. Saves amp (T,H,W) uint8, dates,
        and the geometry columns.

Umbra changed its amplitude scaling in early 2024, and gain differs between collects, so
compare collects in rank space (per-collect percentiles), not in raw DN.
"""
import re
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject

BUCKET = "https://umbra-open-data-catalog.s3.amazonaws.com/"


def list_keys(prefix):
    out, token = [], None
    while True:
        p = {"list-type": "2", "prefix": prefix}
        if token:
            p["continuation-token"] = token
        t = requests.get(BUCKET, params=p, timeout=60).text
        out += re.findall(r"<Key>([^<]*)</Key>", t)
        m = re.search(r"<NextContinuationToken>([^<]*)<", t)
        if not m:
            return out
        token = m.group(1)


def get_json(key):
    return requests.get(BUCKET + urllib.parse.quote(key), timeout=60).json()


def collect_row(keys):
    gec = [k for k in keys if k.endswith("_GEC.tif")]
    if not gec:
        return None
    row = dict(time=pd.to_datetime(re.search(r"/(\d{4}-\d\d-\d\d-\d\d-\d\d-\d\d)_", gec[0]).group(1),
                                   format="%Y-%m-%d-%H-%M-%S"),
               platform=re.search(r"_(UMBRA-\d+)_GEC", gec[0]).group(1),
               orbit=None, look=None, incidence=np.nan, squint=np.nan, azimuth=np.nan,
               url=BUCKET + urllib.parse.quote(gec[0]))
    stac = [k for k in keys if k.endswith(".stac.v2.json")]
    meta = [k for k in keys if k.endswith("_METADATA.json")]
    if stac:
        p = get_json(stac[0])["properties"]
        row.update(orbit=p.get("sat:orbit_state"), look=p.get("sar:observation_direction"),
                   incidence=90 - p.get("umbra:grazing_angle_degrees", np.nan),
                   squint=p.get("umbra:squint_angle_exploitation_degrees", np.nan))
    if meta:
        c = get_json(meta[0])["collects"][0]
        row.update(orbit=(row["orbit"] or c.get("satelliteTrack", "")).lower(),
                   look=(row["look"] or c.get("observationDirection", "")).lower(),
                   incidence=c.get("angleIncidenceDegrees", row["incidence"]),
                   squint=c.get("angleSquintDegrees", row["squint"]),
                   azimuth=c.get("angleAzimuthDegrees", np.nan))
    return row


def cmd_index(site, out):
    keys = list_keys(f"sar-data/tasks/{site}/")
    by = {}
    for k in keys:
        m = re.search(r"/(\d{4}-\d\d-\d\d-\d\d-\d\d-\d\d_UMBRA-\d+)/", k)
        if m:
            by.setdefault(m.group(1), []).append(k)
    with ThreadPoolExecutor(8) as ex:
        rows = [r for r in ex.map(collect_row, by.values()) if r]
    df = pd.DataFrame(rows).sort_values("time")
    df.to_csv(out, index=False)
    print(df.drop(columns="url").to_string())


def cmd_stack(index_csv, bbox, res, out):
    idx = pd.read_csv(index_csv, parse_dates=["time"])
    lon0, lat0, lon1, lat1 = [float(v) for v in bbox.split(",")]
    res = float(res)
    H = int(round((lat1 - lat0) * 111320 / res))
    W = int(round((lon1 - lon0) * 111320 * np.cos(np.radians((lat0 + lat1) / 2)) / res))

    dst_tr = from_origin(lon0, lat1, (lon1 - lon0) / W, (lat1 - lat0) / H)

    def read(url):
        # some GECs are stored south-up, so warp from the overview nearest to RES/2 instead of
        # cutting a window
        try:
            with rasterio.open(url) as src:
                px_m = abs(src.res[0]) * 111320 * np.cos(np.radians(lat0))
                facs = src.overviews(1)
                lvl = max([i for i, f in enumerate(facs) if f * px_m <= res / 2] or [-1])
            a = np.zeros((H, W), np.uint8)
            with rasterio.open(url, overview_level=lvl if lvl >= 0 else None) as src:
                reproject(rasterio.band(src, 1), a, dst_transform=dst_tr, dst_crs="EPSG:4326",
                          src_nodata=0, dst_nodata=0, resampling=Resampling.average)
            return a
        except Exception as e:                      # noqa: BLE001 - report and skip bad collects
            print("skip", url[-60:], e)
            return None

    with ThreadPoolExecutor(6) as ex:
        amps = list(ex.map(read, idx["url"]))
    keep = [i for i, a in enumerate(amps) if a is not None and (a > 0).mean() > 0.05]
    idx = idx.iloc[keep].reset_index(drop=True)
    np.savez_compressed(out, amp=np.stack([amps[i] for i in keep]), dates=idx["time"].astype(str).values.astype("U"),
                        orbit=idx["orbit"].astype(str).values.astype("U"), look=idx["look"].astype(str).values.astype("U"),
                        incidence=idx["incidence"].values, squint=idx["squint"].values,
                        bbox=np.array([lon0, lat0, lon1, lat1]), res=res)
    print(len(keep), "collects", (H, W))


if __name__ == "__main__":
    if sys.argv[1] == "index":
        cmd_index(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "stack":
        cmd_stack(*sys.argv[2:6])
    else:
        sys.exit(__doc__)
