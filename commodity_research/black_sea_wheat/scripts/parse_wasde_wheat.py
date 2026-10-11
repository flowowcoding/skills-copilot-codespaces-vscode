#!/usr/bin/env python3
"""Point-in-time USDA WASDE vintages of wheat production (and the rest of the
world wheat balance sheet) for Russia, Ukraine, Kazakhstan, plus United States,
EU, World and other exporters as context.

Sources
  1. USDA OCE "Historical WASDE Report Data" CSVs, Apr-2010 onward, as published
     at each report (mirror https://usda.azureedge.us/historical-wasde-report-data-3
     of the usda.gov WASDE page). Table "World Wheat Supply and Use".
  2. WASDE text reports, 2004 to Mar-2010, Cornell/NAL ESMIS archive
     https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates
     Table "World Wheat Supply and Use 1/". For a projected year printed with two
     months (previous / current) the LAST (current-month) line is taken.

Release time: 12:00 ET (08:30 ET before 2013-01-11; the time is recorded).

Usage
    python parse_wasde_wheat.py --csv-dir RAW/csv --txt-dir RAW/txt --out data/benchmark
Writes OUT/wasde_wheat_vintages.csv:
    release_date, release_time_et, region, market_year, crop_year,
    attribute, value_mmt, proj_flag, src
(src: "oce:<file>" = OCE CSV, "wasde-mm-dd-yyyy" = ESMIS text report;
crop_year = first year of the market year = harvest year for the Northern
Hemisphere countries used here.)
"""
import argparse
import glob
import os
import re

import pandas as pd

COLS = ["Beginning Stocks", "Production", "Imports", "Domestic Feed", "Domestic Total", "Exports", "Ending Stocks"]
REG_MAP = {"European Union": "EU", "EU-27": "EU", "EU-25": "EU", "EU-28": "EU", "EU-27+UK": "EU",
           "Total Foreign": "Total foreign", "Major Exporters": "Major exporters", "Major Importers": "Major importers"}
KEEP = ["Russia", "Ukraine", "Kazakhstan", "United States", "EU", "World", "FSU-12", "Canada", "Australia",
        "Argentina"]
MON = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December"
TXT_REG = r"(World|United States|Argentina|Australia|Canada|EU-2[578]|EU-27\+UK|European Union|FSU-12|Russia|Kazakhstan|Ukraine)"


def rel_time(d):
    return "08:30" if pd.Timestamp(d) < pd.Timestamp("2013-01-11") else "12:00"


def parse_csvs(d):
    fs = sorted(set(glob.glob(os.path.join(d, "*.csv")) + glob.glob(os.path.join(d, "*", "*.csv"))))
    out = []
    for f in fs:
        x = pd.read_csv(f, dtype=str, encoding="latin1")
        x = x[x.ReportTitle == "World Wheat Supply and Use"].assign(src=os.path.basename(f))
        out.append(x)
    x = pd.concat(out)
    x["Region"] = x.Region.replace(REG_MAP)
    x = x[x.Region.isin(KEEP) & x.Attribute.isin(COLS)]
    x["release_date"] = pd.to_datetime(x.ReleaseDate, format="mixed").dt.date
    x["value_mmt"] = pd.to_numeric(x.Value, errors="coerce")
    x = x.rename(columns={"ReportDate": "report", "MarketYear": "market_year", "Attribute": "attribute",
                          "ProjEstFlag": "proj_flag", "Region": "region"})
    x = x.sort_values("src").drop_duplicates(["release_date", "region", "market_year", "attribute"], keep="last")
    return x[["release_date", "report", "region", "market_year", "attribute", "value_mmt", "proj_flag", "src"]]


def parse_txt_file(path):
    txt = open(path, encoding="latin1").read()
    m = re.search(r"wasde-(\d\d)-(\d\d)-(\d{4})", os.path.basename(path))
    rdate = pd.Timestamp(f"{m.group(3)}-{m.group(1)}-{m.group(2)}").date()
    rows = {}
    for blk in re.finditer(r"World Wheat Supply and Use\s+1/(.*?)(?=World Coarse Grain|\Z)", txt, re.S):
        year, flag, cur = None, "", None
        for line in blk.group(1).splitlines():
            h = re.search(r":\s+(\d{4}/\d{2})\s*(\(?[A-Za-z]*\.?\)?)?\s*$", line)
            if h and not re.search(r"\d+\.\d\d", line):
                year, flag = h.group(1), (h.group(2) or "").strip("()")
                cur = None
                continue
            nums = re.findall(r"-?\d+\.\d\d", line)
            reg = re.match(rf"^\s*{TXT_REG}", line)
            if reg:
                cur = REG_MAP.get(reg.group(1), reg.group(1))
                if len(nums) == 7 and year:
                    rows[(cur, year)] = (nums, flag)
                continue
            if cur and re.match(rf"^\s*({MON})\s*:", line) and len(nums) == 7 and year:
                rows[(cur, year)] = (nums, flag)  # continuation line = later (current) month
                continue
            if re.match(rf"^\s*({MON})\s*:", line) or re.match(r"^\s*:?\s*$", line):
                continue
            cur = None
    out = []
    for (reg, y), (nums, flag) in rows.items():
        for c, v in zip(COLS, nums):
            out.append(dict(release_date=rdate, report=rdate.strftime("%B %Y"), region=reg, market_year=y,
                            attribute=c, value_mmt=float(v), proj_flag=flag, src=os.path.basename(path)))
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
        if "Announcement" in f:
            continue
        t += parse_txt_file(f)
    t = pd.DataFrame(t)
    t["_rev"] = t.src.str.contains("revision|correct", case=False).astype(int)
    t = t.sort_values("_rev").drop_duplicates(["release_date", "region", "market_year", "attribute"], keep="first")
    t = t.drop(columns="_rev")
    ov = t.merge(c, on=["release_date", "region", "market_year", "attribute"], suffixes=("_txt", "_csv"))
    if len(ov):
        bad = ov[(ov.value_mmt_txt - ov.value_mmt_csv).abs() > 0.011]
        print(f"txt/csv overlap rows {len(ov)}, mismatches {len(bad)}")
    t = t[~t.release_date.isin(set(c.release_date))]
    x = pd.concat([t, c])
    x = x[x.region.isin(KEEP)]
    x["release_time_et"] = x.release_date.map(rel_time)
    x["crop_year"] = x.market_year.str[:4].astype(int)
    x = x.sort_values(["release_date", "region", "market_year", "attribute"])
    x["src"] = x.src.str.replace("oce-wasde-report-data-", "oce:").str.replace(".csv", "", regex=False) \
        .str.replace(".txt", "", regex=False)
    x = x[["release_date", "release_time_et", "region", "market_year", "crop_year", "attribute",
           "value_mmt", "proj_flag", "src"]]
    os.makedirs(a.out, exist_ok=True)
    x.to_csv(os.path.join(a.out, "wasde_wheat_vintages.csv"), index=False)
    p = x[(x.attribute == "Production") & (x.region == "Russia")]
    print(p.release_date.nunique(), "reports with Russia", p.release_date.min(), p.release_date.max())
    for r in ["Russia", "Ukraine", "Kazakhstan", "United States"]:
        print(r, x[(x.region == r) & (x.attribute == "Production")].release_date.nunique())


if __name__ == "__main__":
    main()
