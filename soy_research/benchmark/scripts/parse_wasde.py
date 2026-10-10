#!/usr/bin/env python3
"""Build USDA WASDE vintages of Brazil soybean production (plus the rest of the
soybean balance sheet for Brazil, United States, Argentina and World) from:

  1. USDA OCE "Historical WASDE Report Data" CSVs (Apr-2010 onward), as
     published at the time of each report:
     https://www.usda.gov/about-usda/general-information/staff-offices/office-chief-economist/commodity-markets/wasde-report
     (mirror used: https://usda.azureedge.us/historical-wasde-report-data-3)
  2. WASDE text reports (2005-2010) from the Cornell/NAL ESMIS archive:
     https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates
     parsed from the "World Soybean Supply and Use" table. Where a report shows
     two months (previous / current) for a projected year, the CURRENT-month
     line (last line) is taken.

Release time: WASDE is published 12:00 ET (during the CBOT day session).

Usage:
    python parse_wasde.py --csv-dir DIR --txt-dir DIR --out OUT_DIR
Writes OUT_DIR/wasde_brazil_soy.csv with columns
    release_date, release_time_et, report, region, market_year, attribute, value_mt, proj_flag, src
"""
import argparse
import glob
import os
import re

import pandas as pd

COLS = ["Beginning Stocks", "Production", "Imports", "Domestic Crush", "Domestic Total", "Exports", "Ending Stocks"]
REGIONS = ["Brazil", "United States", "Argentina", "World"]
MON = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December"


def parse_csvs(d):
    fs = sorted(glob.glob(os.path.join(d, "*.csv"))) + sorted(glob.glob(os.path.join(d, "*", "*.csv")))
    out = []
    for f in fs:
        x = pd.read_csv(f, dtype=str, encoding="latin1")
        x = x[(x.Region.isin(REGIONS)) & (x.Commodity == "Oilseed, Soybean")
              & (x.ReportTitle == "World Soybean Supply and Use")]
        x = x.assign(src=os.path.basename(f))
        out.append(x)
    x = pd.concat(out)
    x["release_date"] = pd.to_datetime(x.ReleaseDate, format="mixed").dt.date
    x = x[x.Attribute.isin(COLS)]
    x["value_mt"] = pd.to_numeric(x.Value, errors="coerce")
    x = x.rename(columns={"ReportDate": "report", "MarketYear": "market_year", "Attribute": "attribute",
                          "ProjEstFlag": "proj_flag", "Region": "region"})
    x["release_time_et"] = "12:00"
    # a few months appear in two files (corrected V2 reissues); keep the last file
    x = x.sort_values("src").drop_duplicates(["release_date", "region", "market_year", "attribute"], keep="last")
    return x[["release_date", "release_time_et", "report", "region", "market_year", "attribute", "value_mt",
              "proj_flag", "src"]]


def parse_txt_file(path):
    txt = open(path, encoding="latin1").read()
    m = re.search(r"wasde-(\d\d)-(\d\d)-(\d{4})", os.path.basename(path))
    rdate = pd.Timestamp(f"{m.group(3)}-{m.group(1)}-{m.group(2)}").date()
    rows = {}
    for blk in re.finditer(r"World Soybean Supply and Use(.*?)(?=World Soybean Meal|\Z)", txt, re.S):
        year, flag, cur = None, "", None
        for line in blk.group(1).splitlines():
            h = re.search(r":\s+(\d{4}/\d{2})\s*(\(?\w*\.?\)?)?\s*$", line)
            if h and not re.search(r"\d+\.\d\d", line):
                year, flag = h.group(1), (h.group(2) or "").strip("()")
                cur = None
                continue
            nums = re.findall(r"-?\d+\.\d\d", line)
            reg = re.match(r"^\s*(World|United States|Argentina|Brazil)\b", line)
            if reg:
                cur = reg.group(1)
                if len(nums) == 7 and year:
                    rows[(cur, year)] = (nums, flag)
                continue
            if cur and re.match(rf"^\s*({MON})\s*:", line) and len(nums) == 7 and year:
                rows[(cur, year)] = (nums, flag)  # continuation line = later (current) month
                continue
            cur = None
    out = []
    for (reg, y), (nums, flag) in rows.items():
        for c, v in zip(COLS, nums):
            out.append(dict(release_date=rdate, release_time_et="12:00", report=rdate.strftime("%B %Y"),
                            region=reg, market_year=y, attribute=c, value_mt=float(v), proj_flag=flag,
                            src=os.path.basename(path)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv-dir", required=True)
    ap.add_argument("--txt-dir", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    c = parse_csvs(a.csv_dir)
    t = []
    for f in sorted(glob.glob(os.path.join(a.txt_dir, "wasde-*.txt"))):
        t += parse_txt_file(f)
    t = pd.DataFrame(t)
    # validation on overlap (Apr-2010)
    ov = t.merge(c, on=["release_date", "region", "market_year", "attribute"], suffixes=("_txt", "_csv"))
    if len(ov):
        bad = ov[(ov.value_mt_txt - ov.value_mt_csv).abs() > 0.011]
        print(f"overlap rows {len(ov)}, mismatches {len(bad)}")
    t = t[~t.release_date.isin(set(c.release_date))]
    # drop special/corrected same-month duplicates with identical Brazil numbers
    x = pd.concat([t, c]).sort_values(["release_date", "region", "market_year", "attribute"])
    os.makedirs(a.out, exist_ok=True)
    x.to_csv(os.path.join(a.out, "wasde_brazil_soy.csv"), index=False)
    p = x[(x.attribute == "Production") & (x.region == "Brazil")]
    print(p.release_date.nunique(), "reports", p.release_date.min(), p.release_date.max())


if __name__ == "__main__":
    main()
