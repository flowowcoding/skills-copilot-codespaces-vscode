#!/usr/bin/env python3
"""Scrape the USDA ESMIS (Cornell Mann Library / NAL) release listings for NASS
crop reports and download the text (.txt) versions.

Publications (ESMIS slugs):
  crop-production                 monthly Crop Production (Aug-Nov yield forecasts)
  crop-production-annual-summary  January annual summary (final yields)
  acreage                         end-of-June Acreage (planted/harvested area)
  prospective-plantings           end-of-March Prospective Plantings (intentions)
  world-agricultural-supply-and-demand-estimates  WASDE (same-day US balance sheet)

Listing URL pattern: https://esmis.nal.usda.gov/publication/<slug>?page=N
(usda.library.cornell.edu/concern/publications/... redirects there).
Each row carries <time datetime="YYYY-MM-DDT12:00:00Z">; the "12:00" there is a
placeholder, NOT the release time. The real release time is read later from the
report text itself ("Released August 12, 2015, at 12:00 p.m. ET").

Usage:
    python fetch_nass_reports.py --out RAW_DIR [--from-year 2005] [--slugs crop-production acreage ...]
Writes RAW_DIR/manifest.csv (slug, release_date, file, url, local_path) and the
.txt files under RAW_DIR/<slug>/. Downloads are untrusted data: only parsed as text.
"""
import argparse
import os
import re
import subprocess
import time

import pandas as pd

BASE = "https://esmis.nal.usda.gov"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
DEFAULT_SLUGS = ["crop-production", "crop-production-annual-summary", "acreage", "prospective-plantings",
                 "world-agricultural-supply-and-demand-estimates"]
ROW = re.compile(r'<time datetime="(\d{4}-\d\d-\d\d)T[^"]*">[^<]*</time>\s*</td>\s*<td[^>]*>(.*?)</td>', re.S)


def get(url, out=None, tries=4):
    for i in range(tries):
        cmd = ["curl", "-sS", "-L", "-m", "120", "-A", UA, url]
        if out:
            cmd += ["-o", out]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode == 0:
            return r.stdout.decode("utf-8", "replace") if not out else out
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"failed {url}: {r.stderr[:200]}")


def listing(slug, from_year):
    rows, page = [], 0
    while True:
        html = get(f"{BASE}/publication/{slug}?page={page}")
        found = ROW.findall(html)
        # the first table on page 0 is "Latest Release" (duplicate); de-dup later
        if not found:
            break
        for d, cell in found:
            for href in re.findall(r'href="([^"]+\.txt)"', cell):
                rows.append({"slug": slug, "release_date": d, "file": os.path.basename(href), "url": BASE + href})
        years = [int(d[:4]) for d, _ in found]
        if min(years) < from_year or page > 120:
            break
        page += 1
    df = pd.DataFrame(rows).drop_duplicates(["slug", "url"])
    return df[df.release_date.str[:4].astype(int) >= from_year]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--from-year", type=int, default=2005)
    ap.add_argument("--slugs", nargs="*", default=DEFAULT_SLUGS)
    ap.add_argument("--months", nargs="*", type=int, default=None,
                    help="for crop-production/WASDE keep only these release months (default: all)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    man = []
    for s in a.slugs:
        df = listing(s, a.from_year)
        print(s, len(df), "txt files")
        man.append(df)
    man = pd.concat(man, ignore_index=True)
    if a.months:
        m = pd.to_datetime(man.release_date).dt.month
        keep = ~man.slug.isin(["crop-production", "world-agricultural-supply-and-demand-estimates"]) | m.isin(a.months)
        man = man[keep]
    paths = []
    for r in man.itertuples():
        d = os.path.join(a.out, r.slug)
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, f"{r.release_date}_{r.file}")
        if not os.path.exists(p) or os.path.getsize(p) < 1000:
            get(r.url, out=p)
        paths.append(p)
    man["local_path"] = paths
    man.to_csv(os.path.join(a.out, "manifest.csv"), index=False)
    print("wrote", len(man), "rows to", os.path.join(a.out, "manifest.csv"))


if __name__ == "__main__":
    main()
