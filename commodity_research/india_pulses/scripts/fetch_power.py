"""Fetch NASA POWER daily point data (MERRA-2 based) at core-district centroids.

Parameters: T2M_MAX (deg C), PRECTOTCORR (mm/day), GWETROOT (root-zone soil wetness, 0-1), GWETTOP.
Source: https://power.larc.nasa.gov/api/temporal/daily/point (no auth). POWER's latency is ~2-5 days;
recent days come from GEOS FP-IT and are later replaced by MERRA-2, so values for the last few weeks of
any as-of date may differ slightly from what was visible in real time (documented caveat). Downstream
rule: a day is usable from day + 7.

Output: <work>/power/<dist_code>.csv  (date, T2M_MAX, PRECTOTCORR, GWETROOT, GWETTOP)
Usage:  python fetch_power.py --districts ../data/district_weights.csv --work <scratch>/india
"""
import argparse, os, time
from concurrent.futures import ThreadPoolExecutor
import pandas as pd, requests

URL = ("https://power.larc.nasa.gov/api/temporal/daily/point?parameters=T2M_MAX,PRECTOTCORR,GWETROOT,GWETTOP"
       "&community=AG&longitude={lon}&latitude={lat}&start=20010101&end={end}&format=JSON")


def task(r, out, end):
    fn = f"{out}/{r.dist_code}.csv"
    if os.path.exists(fn):
        return
    for k in range(6):
        try:
            j = requests.get(URL.format(lon=r.lon, lat=r.lat, end=end), timeout=300).json()
            p = j["properties"]["parameter"]; break
        except Exception as e:  # noqa
            print("retry", r.dist_code, e); time.sleep(10 * (k + 1))
    d = pd.DataFrame(p); d.index = pd.to_datetime(d.index, format="%Y%m%d"); d = d.where(d > -900)
    d.rename_axis("date").to_csv(fn, float_format="%.3f")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--districts", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--end", default="20261008")
    a = ap.parse_args()
    d = pd.read_csv(a.districts)
    d = d[(d.core_chickpea + d.core_pigeonpea + d.core_sugarcane) > 0]
    out = f"{a.work}/power"; os.makedirs(out, exist_ok=True)
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(lambda r: task(r, out, a.end), d.itertuples()))
    print("done", len(os.listdir(out)))


if __name__ == "__main__":
    main()
