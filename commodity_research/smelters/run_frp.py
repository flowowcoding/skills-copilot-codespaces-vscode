"""Run s3_frp.py (Sentinel-3 SLSTR night-time fire detections) for every smelter in smelters.csv.

Usage:
    python run_frp.py [--jobs 2] [--start 2020-08-08] [--end 2026-10-10] [ID ...]
Output: data/s3frp/<id>.csv (skips existing unless IDs are given).
"""
import argparse, csv, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ids", nargs="*"); ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--start", default="2020-08-08"); ap.add_argument("--end", default="2026-10-10")
    a = ap.parse_args()
    out_dir = os.path.join(HERE, "data", "s3frp"); os.makedirs(out_dir, exist_ok=True)
    rows = list(csv.DictReader(open(os.path.join(HERE, "smelters.csv"))))

    def run(r):
        out = os.path.join(out_dir, f"{r['id']}.csv")
        if (a.ids and r["id"] not in a.ids) or (not a.ids and os.path.exists(out)):
            return
        p = subprocess.run([sys.executable, "-W", "ignore", os.path.join(HERE, "s3_frp.py"), r["id"], r["lat"], r["lon"], a.start, a.end, out,
                            "--threads", "12"], capture_output=True, text=True, cwd=out_dir)
        print(r["id"], p.returncode, " | ".join(p.stderr.strip().splitlines()[-2:]), flush=True)

    with ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(run, rows))


if __name__ == "__main__":
    main()
