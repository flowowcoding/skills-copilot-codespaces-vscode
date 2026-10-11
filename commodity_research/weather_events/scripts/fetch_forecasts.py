"""Download point-in-time NHC forecast tracks (ATCF a-decks) and best tracks.

Sources
-------
* ATCF a-decks, NHC public archive: https://ftp.nhc.noaa.gov/atcf/archive/YYYY/aalNNYYYY.dat.gz
  (current season: https://ftp.nhc.noaa.gov/atcf/aid_public/). Each line is one forecast point of
  one "technique". We keep
    - OFCL  : the official NHC forecast track as issued in the advisory (the cone centreline),
    - AP01..AP30, AEMN : NCEP GEFS ensemble members and mean (raw model tracks, "late" guidance).
* HURDAT2 best tracks (https://www.nhc.noaa.gov/data/hurdat/) -- hindsight, used ONLY to classify
  hits vs misses and to measure verification error. 2026 storms use the operational b-decks
  (https://ftp.nhc.noaa.gov/atcf/btk/).

Output (scratch, not committed; large):  <scratch>/atcf_filtered.csv.gz, <scratch>/hurdat2.txt,
<scratch>/bdeck_2026/*.dat

Usage: python fetch_forecasts.py --scratch DIR [--years 2000 2026]

2000-2004 are fetched only to calibrate the 2005+ cone radii (5-year trailing errors).
"""
import argparse
import gzip
import io
import os
import re
import subprocess
import sys

import pandas as pd

ARCH = "https://ftp.nhc.noaa.gov/atcf/archive/{y}/"
PUBLIC = "https://ftp.nhc.noaa.gov/atcf/aid_public/"
BTK = "https://ftp.nhc.noaa.gov/atcf/btk/"
HURDAT = "https://www.nhc.noaa.gov/data/hurdat/hurdat2-1851-2025-02272026.txt"
KEEP = re.compile(r"^(OFCL|AP\d\d|AEMN)$")
COLS = ["basin", "num", "init", "technum", "tech", "tau", "lat", "lon", "vmax", "mslp", "ty"]


def curl(url, out=None, tries=6):
    """GET with retries (the NHC server drops connections now and then)."""
    import time
    cmd = ["curl", "-sS", "-f", "--retry", "3", "--retry-all-errors", url]
    for i in range(tries):
        if out:
            if subprocess.run(cmd + ["-o", out]).returncode == 0:
                return True
        else:
            r = subprocess.run(cmd, capture_output=True)
            if r.returncode == 0:
                return r.stdout
        time.sleep(2 + 3 * i)
    return None


def parse_ll(s):
    s = s.strip()
    v = float(s[:-1]) / 10.0
    return -v if s[-1] in "SW" else v


def parse_adeck(raw):
    rows = []
    for line in raw.decode("latin-1").splitlines():
        f = [x.strip() for x in line.split(",")]
        if len(f) < 11 or not KEEP.match(f[4]):
            continue
        try:
            rows.append([f[0], int(f[1]), f[2], f[3], f[4], int(f[5]), parse_ll(f[6]),
                         parse_ll(f[7]), int(f[8] or 0), int(f[9] or 0), f[10]])
        except (ValueError, IndexError):
            continue
    df = pd.DataFrame(rows, columns=COLS)
    # several wind-radii lines per point -> one row per (tech, init, tau)
    return df.drop_duplicates(["tech", "init", "tau"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--years", nargs=2, type=int, default=[2000, 2026])
    a = ap.parse_args()
    os.makedirs(a.scratch, exist_ok=True)
    out = []
    cdir = os.path.join(a.scratch, "adeck_cache")
    os.makedirs(cdir, exist_ok=True)
    for y in range(a.years[0], a.years[1] + 1):
        base = PUBLIC if y == 2026 else ARCH.format(y=y)
        listing = curl(base).decode()
        names = sorted(set(re.findall(r"aal(\d\d)%d\.dat\.gz" % y, listing)))
        names = [n for n in names if int(n) < 50]          # drop invests (90-99) and test ids
        for n in names:
            cache = os.path.join(cdir, f"AL{n}{y}.csv")
            if os.path.exists(cache):
                out.append(pd.read_csv(cache, dtype={"init": str}))
                continue
            raw = curl(f"{base}aal{n}{y}.dat.gz")
            if raw is None:
                print("missing", y, n, file=sys.stderr)
                continue
            df = parse_adeck(gzip.decompress(raw))
            df["storm_id"] = f"AL{n}{y}"
            df.to_csv(cache, index=False)
            out.append(df)
            print(y, n, len(df), file=sys.stderr)
    allf = pd.concat(out, ignore_index=True)
    allf.to_csv(os.path.join(a.scratch, "atcf_filtered.csv.gz"), index=False)
    curl(HURDAT, os.path.join(a.scratch, "hurdat2.txt"))
    bdir = os.path.join(a.scratch, "bdeck_2026")
    os.makedirs(bdir, exist_ok=True)
    for n in sorted(set(re.findall(r"bal(\d\d)2026\.dat", curl(BTK).decode()))):
        if int(n) < 50:
            curl(f"{BTK}bal{n}2026.dat", os.path.join(bdir, f"bal{n}2026.dat"))
    print("rows", len(allf))


if __name__ == "__main__":
    main()
