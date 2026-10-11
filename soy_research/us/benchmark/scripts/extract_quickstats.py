#!/usr/bin/env python3
"""Extract US corn and soybean survey records (national + state) from the NASS
Quick Stats bulk crops file, which is free to download without an API key:

    https://www.nass.usda.gov/datasets/qs.crops_YYYYMMDD.txt.gz   (~1.1 GB)

(The Quick Stats *API*, https://quickstats.nass.usda.gov/api, returns
HTTP 401 {"error":["unauthorized"]} without a key, so the bulk file is used.)

Kept: SOURCE_DESC=SURVEY, COMMODITY_DESC in {CORN, SOYBEANS},
AGG_LEVEL_DESC in {NATIONAL, STATE}, YEAR >= --from-year, and SHORT_DESC in:
  yield / production / acres harvested / acres planted (all reference periods,
  including "YEAR - AUG FORECAST" ... "YEAR - NOV FORECAST", "YEAR - JUN ACREAGE",
  "YEAR - MAR ACREAGE" and "YEAR" = latest revised annual value), and
  weekly crop condition (PCT EXCELLENT/GOOD/FAIR/POOR/VERY POOR) and progress.

Forecast-period records are the values as published in that month's Crop
Production report (NASS does not revise forecast records), which makes them a
point-in-time source. This is checked against the Crop Production .txt reports in
parse_crop_production.py.

Usage:
    python extract_quickstats.py --bulk qs.crops_YYYYMMDD.txt.gz --out OUT.csv.gz [--from-year 2000]
"""
import argparse
import subprocess

import pandas as pd

SHORT = {
    "CORN, GRAIN - YIELD, MEASURED IN BU / ACRE", "CORN, GRAIN - PRODUCTION, MEASURED IN BU",
    "CORN, GRAIN - ACRES HARVESTED", "CORN - ACRES PLANTED",
    "SOYBEANS - YIELD, MEASURED IN BU / ACRE", "SOYBEANS - PRODUCTION, MEASURED IN BU",
    "SOYBEANS - ACRES HARVESTED", "SOYBEANS - ACRES PLANTED",
}
COND = ("CONDITION, MEASURED IN PCT", "PROGRESS, MEASURED IN PCT")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bulk", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--from-year", type=int, default=2000)
    a = ap.parse_args()
    # awk pre-filter on fixed columns (1 source, 4 commodity, 13 agg level, 31 year)
    prog = ('BEGIN{FS=OFS="\\t"} NR==1 || ($1=="SURVEY" && ($4=="CORN"||$4=="SOYBEANS") && '
            '($13=="NATIONAL"||$13=="STATE") && $31>=%d)' % a.from_year)
    z = subprocess.Popen(["zcat", a.bulk], stdout=subprocess.PIPE)
    p = subprocess.Popen(["awk", prog], stdin=z.stdout, stdout=subprocess.PIPE)
    df = pd.read_csv(p.stdout, sep="\t", dtype=str, quoting=3)
    keep = df.SHORT_DESC.isin(SHORT) | df.SHORT_DESC.str.contains("|".join(COND), regex=True)
    df = df[keep & (df.DOMAIN_DESC == "TOTAL")]
    cols = ["COMMODITY_DESC", "SHORT_DESC", "AGG_LEVEL_DESC", "STATE_ALPHA", "STATE_NAME", "YEAR", "FREQ_DESC",
            "REFERENCE_PERIOD_DESC", "WEEK_ENDING", "LOAD_TIME", "VALUE", "CV_%"]
    df = df[cols]
    df["value_num"] = pd.to_numeric(df.VALUE.str.replace(",", "").str.strip(), errors="coerce")
    df.to_csv(a.out, index=False, compression="gzip" if a.out.endswith(".gz") else None)
    print(len(df), "rows ->", a.out)
    print(df.groupby(["SHORT_DESC"]).size().sort_values().tail(30).to_string())


if __name__ == "__main__":
    main()
