"""Index an Umbra open-data site: one row per collect with its GEC GeoTIFF url and geometry.

Geometry comes from the collect's `_METADATA.json` (collects[0]) or, when that file is
missing (most 2025 tasks), from the STAC item (`*.stac.v2.json` / `*STAC-METADATA.json`).
The two sources give identical values where both exist. Fields that cannot be found are NaN.

Usage:  python umbra_index.py "Bingham Copper Mine" bingham_index.csv
"""
import re
import sys
import urllib.parse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

BUCKET = "https://umbra-open-data-catalog.s3.amazonaws.com/"


def list_keys(prefix):
    """All object keys under a prefix (S3 ListObjectsV2, anonymous)."""
    out, token = [], None
    while True:
        params = {"list-type": "2", "prefix": prefix}
        if token:
            params["continuation-token"] = token
        text = requests.get(BUCKET, params=params, timeout=60).text
        out += re.findall(r"<Key>([^<]*)</Key>", text)
        m = re.search(r"<NextContinuationToken>([^<]*)<", text)
        if not m:
            return out
        token = m.group(1)


def get_json(key):
    return requests.get(BUCKET + urllib.parse.quote(key), timeout=60).json()


def task_row(keys):
    gec = [k for k in keys if k.endswith("_GEC.tif")]
    if not gec:
        return None
    row = {"time": re.search(r"/(\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})_", gec[0]).group(1),
           "azimuth": float("nan"), "incidence": float("nan"), "look": None,
           "res_m": float("nan"), "geom_source": None,
           "gec": BUCKET + urllib.parse.quote(gec[0])}
    meta = [k for k in keys if k.endswith("_METADATA.json") and "STAC" not in k]
    stac = [k for k in keys if "stac" in k.lower() and k.endswith(".json")]
    try:
        if meta:
            c = get_json(meta[0])["collects"][0]
            row.update(azimuth=c["angleAzimuthDegrees"], incidence=c["angleIncidenceDegrees"],
                       look=c["observationDirection"].upper(),
                       res_m=c["maxGroundResolution"]["rangeMeters"], geom_source="metadata")
        elif stac:
            p = get_json(stac[0])
            p = p.get("properties", p)
            row.update(azimuth=p["view:azimuth"], incidence=p["view:incidence_angle"],
                       look=p["sar:observation_direction"].upper(),
                       res_m=p.get("sar:resolution_range", float("nan")), geom_source="stac")
    except Exception as e:  # keep the collect, geometry stays NaN
        print("geometry missing for", gec[0], e, file=sys.stderr)
    return row


def main(site, out_csv):
    tasks = defaultdict(list)
    for k in list_keys(f"sar-data/tasks/{site}/"):
        tasks[k.split("/")[3]].append(k)
    with ThreadPoolExecutor(16) as ex:
        rows = [r for r in ex.map(task_row, tasks.values()) if r]
    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], format="%Y-%m-%d-%H-%M-%S")
    df = df.sort_values("time").drop_duplicates("time")
    df.to_csv(out_csv, index=False)
    print(f"{len(df)} collects, {df.azimuth.isna().sum()} without geometry -> {out_csv}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
