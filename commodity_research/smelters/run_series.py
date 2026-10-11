"""Run the Sentinel-2 hot-pixel series (s2_hot.py series) for every smelter in smelters.csv.

Usage:
    python run_series.py [--csv smelters.csv] [--out data/s2] [--jobs 3] [--dates 2017-01-01/2026-10-10] [ID ...]

Skips smelters whose output CSV already exists unless IDs are given explicitly.
Box = smelters.csv lat/lon (centre of the furnace/slag area) +- box_half_km.
"""
import argparse, csv, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--csv", default=os.path.join(HERE, "smelters.csv"))
    ap.add_argument("--out", default=os.path.join(HERE, "data", "s2"))
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--dates", default="2017-01-01/2026-10-10")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rows = list(csv.DictReader(open(a.csv)))

    def run(r):
        out = os.path.join(a.out, f"{r['id']}.csv")
        if a.ids and r["id"] not in a.ids:
            return
        if not a.ids and os.path.exists(out):
            return
        cmd = [sys.executable, "-W", "ignore", os.path.join(HERE, "s2_hot.py"), "series", r["id"], r["lat"], r["lon"],
               "--half-km", r["box_half_km"], "--dates", a.dates, "--out", out, "--threads", "16"]
        p = subprocess.run(cmd, capture_output=True, text=True)
        msg = [l for l in p.stderr.splitlines() if "retry" not in l][-2:]
        print(r["id"], p.returncode, " | ".join(msg), flush=True)

    with ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(run, rows))


if __name__ == "__main__":
    main()
