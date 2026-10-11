#!/usr/bin/env python3
"""US corn and soybean WASDE vintages (area planted/harvested, yield, production,
ending stocks) for every report 2005-2026.

Sources
  1. USDA OCE "Historical WASDE report data" CSVs (Apr-2010 onward), mirror
     https://usda.azureedge.us/historical-wasde-report-data-3 (original page:
     https://www.usda.gov/about-usda/general-information/staff-offices/office-chief-economist/commodity-markets/wasde-report)
     Tables "U.S. Feed Grain(s) and Corn Supply and Use" (Commodity=Corn) and
     "U.S. Soybeans and Products Supply and Use (Domestic Measure)" (Oilseed, Soybean).
  2. WASDE text reports from ESMIS (https://esmis.nal.usda.gov/publication/world-agricultural-supply-and-demand-estimates)
     for reports before Apr-2010: the CORN block of "U.S. Feed Grain and Corn Supply and Use"
     and the SOYBEANS block of "U.S. Soybeans and Products Supply and Use". Only the LAST
     column (current-month projection of the newest market year) is taken.

Release time: 08:30 ET before 11-Jan-2013, 12:00 ET after (the CSVs carry ReleaseTime 12:00
even for older reports; we override with the documented schedule).

Usage:
    python -I parse_wasde_us.py --csv-dir DIR --manifest ESMIS_MANIFEST.csv --out OUT.csv
"""
import argparse
import glob
import os
import re

import pandas as pd

ATTR = {"Area Planted": "planted_area", "Area Harvested": "harvested_area", "Yield per Harvested Acre": "yield",
        "Production": "production", "Ending Stocks": "ending_stocks"}
UNIT = {"planted_area": "million acres", "harvested_area": "million acres", "yield": "bu/acre",
        "production": "million bu", "ending_stocks": "million bu"}


def parse_csvs(d):
    fs = sorted(glob.glob(os.path.join(d, "*.csv")) + glob.glob(os.path.join(d, "*", "*.csv")))
    out = []
    for f in fs:
        x = pd.read_csv(f, dtype=str, encoding="latin1")
        corn = x.ReportTitle.str.match(r"U\.S\. Feed Grains? and Corn Supply and Use") & (x.Commodity == "Corn")
        soy = x.ReportTitle.str.startswith("U.S. Soybeans and Products Supply and Use") & (
            x.Commodity == "Oilseed, Soybean")
        x = x[(corn | soy) & x.Attribute.isin(ATTR)].copy()
        x["crop"] = x.Commodity.map({"Corn": "corn", "Oilseed, Soybean": "soybeans"})
        x["src"] = os.path.basename(f)
        out.append(x)
    x = pd.concat(out)
    x["release_date"] = pd.to_datetime(x.ReleaseDate, format="mixed").dt.strftime("%Y-%m-%d")
    x["variable"] = x.Attribute.map(ATTR)
    x["value"] = pd.to_numeric(x.Value, errors="coerce")
    x = x.sort_values("src").drop_duplicates(["release_date", "crop", "MarketYear", "variable"], keep="last")
    x = x.rename(columns={"MarketYear": "marketing_year", "ProjEstFlag": "proj_flag"})
    x["source_url"] = "https://usda.azureedge.us/sites/default/files/documents/" + x.src.str.replace(
        r"^(oce-wasde-report-data-\d{4}-\d\d-to-\d{4}-\d\d)\.csv$", r"\1.zip", regex=True)
    return x[["release_date", "crop", "marketing_year", "proj_flag", "variable", "value", "src", "source_url"]]


LINES = {"planted_area": r"^\s*(Area )?Planted\b", "harvested_area": r"^\s*(Area )?Harvested\b",
         "yield": r"^\s*(acre|Yield per Harvested Acre)\b", "production": r"^\s*Production\b",
         "ending_stocks": r"^\s*Ending stocks\b"}


def parse_txt(path, url):
    txt = open(path, encoding="latin1").read()
    rdate = re.search(r"(\d{4}-\d\d-\d\d)_", os.path.basename(path)).group(1)
    out = []
    for crop, title, sect in [("corn", r"U\.S\. Feed Grains? and Corn Supply and Use", "CORN"),
                              ("soybeans", r"U\.S\. Soybeans and Products Supply and Use", "SOYBEANS")]:
        m = re.search(title, txt)
        if not m:
            continue
        blk = txt[m.start(): m.start() + 6000]
        hdr = blk[:900]
        mys = re.findall(r"(\d{4}/\d{2})", hdr)
        if not mys:
            continue
        my = max(mys)
        s = re.search(rf"^{sect}\s*(:|$)", blk, re.M)
        if not s:
            continue
        sub = blk[s.end(): s.end() + 2500].splitlines()
        seen = set()
        for ln in sub:
            if ":" in ln:
                lab, nums = ln.split(":", 1)
            else:  # 2020s layout without colons: label, then numbers
                mm = re.match(r"^(\D*?)\s{2,}(-?[\d,].*)$", ln)
                if not mm:
                    continue
                lab, nums = mm.group(1), mm.group(2)
            for var, rx in LINES.items():
                if var in seen or not re.match(rx, lab, re.I):
                    continue
                v = re.findall(r"-?[\d,]+\.?\d*", nums.replace("*", " "))
                if v:
                    out.append({"release_date": rdate, "crop": crop, "marketing_year": my, "proj_flag": "Proj.",
                                "variable": var, "value": float(v[-1].replace(",", "")),
                                "src": os.path.basename(path), "source_url": url})
                    seen.add(var)
            if re.match(r"^\s*(SOYBEAN OIL|SORGHUM|BARLEY)", lab):
                break
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv-dir", required=True)
    ap.add_argument("--manifest", required=True, help="ESMIS manifest from fetch_nass_reports.py")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    c = parse_csvs(a.csv_dir)
    man = pd.read_csv(a.manifest)
    man = man[(man.slug == "world-agricultural-supply-and-demand-estimates") & ((man.release_date < c.release_date.min()) | (man.release_date > c.release_date.max()))]
    t = pd.DataFrame([r for m in man.itertuples() for r in parse_txt(m.local_path, m.url)])
    df = pd.concat([t, c], ignore_index=True)
    df["release_time_et"] = ["08:30" if d < "2013-01-11" else "12:00" for d in df.release_date]
    ts = pd.to_datetime(df.release_date + " " + df.release_time_et).dt.tz_localize("America/New_York")
    df["release_ts_utc"] = ts.dt.tz_convert("UTC").dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    df["unit"] = df.variable.map(UNIT)
    df["source"] = "usda_wasde"
    df["region"] = "US"
    df["crop_year"] = df.marketing_year.str[:4].astype(int)
    df = df.sort_values(["release_date", "crop", "marketing_year", "variable"])
    df.to_csv(a.out, index=False)
    p = df[(df.variable == "yield")].groupby("crop").release_date.agg(["nunique", "min", "max"])
    print(len(df), "rows\n", p)


if __name__ == "__main__":
    main()
