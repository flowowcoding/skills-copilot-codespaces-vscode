#!/usr/bin/env python3
"""Release dates (no files) of other USDA reports from the ESMIS listings:
  crop-progress  weekly Crop Progress (condition ratings; released Mondays 16:00 ET,
                 Tuesday after a federal holiday)
  grain-stocks   quarterly Grain Stocks (12:00 ET from 2013, 08:30 ET before)
Used (a) to timestamp crop-condition ratings point-in-time and (b) to remove all
USDA report days from the "normal day" sample.

Usage:
    python -I fetch_release_dates.py --out OUT.csv [--from-year 2004]
"""
import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_nass_reports import BASE, ROW, get  # noqa: E402


def dates(slug, from_year):
    out, page = [], 0
    while True:
        html = get(f"{BASE}/publication/{slug}?page={page}")
        found = ROW.findall(html)
        if not found:
            break
        out += [d for d, _ in found]
        if min(int(d[:4]) for d, _ in found) < from_year or page > 150:
            break
        page += 1
    return sorted({d for d in out if int(d[:4]) >= from_year})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--from-year", type=int, default=2004)
    a = ap.parse_args()
    rows = []
    for slug in ["crop-progress", "grain-stocks"]:
        ds = dates(slug, a.from_year)
        print(slug, len(ds), ds[:1], ds[-1:])
        rows += [{"slug": slug, "release_date": d} for d in ds]
    pd.DataFrame(rows).to_csv(a.out, index=False)


if __name__ == "__main__":
    main()
