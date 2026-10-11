"""County corn-for-grain and soybean yields / acres from the NASS Quick Stats bulk file (no API key).

Source: https://www.nass.usda.gov/datasets/qs.crops_<date>.txt.gz (streamed, filtered to SURVEY rows for
CORN and SOYBEANS with awk; the same pre-filtered file is reused if --raw is given).

County estimates for year Y are published by NASS in late February of Y+1 (after the January Annual
Summary), so they are only ever used as training targets for forecasts of later years, and as truth.
"OTHER (COMBINED) COUNTIES" rows (county code 998) are dropped.

Output: data/county_yield.csv  (crop, year, state, fips, county, yield_bu_ac, harvested_ac, planted_ac)
Usage:  python fetch_nass_county.py [--raw <prefiltered tsv>] [--date 20261010] [--states IA,IL,IN,NE]
"""
import argparse, os, subprocess
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data")
KEEP = {"CORN, GRAIN - YIELD, MEASURED IN BU / ACRE": ("corn", "yield_bu_ac"), "SOYBEANS - YIELD, MEASURED IN BU / ACRE": ("soy", "yield_bu_ac"),
        "CORN, GRAIN - ACRES HARVESTED": ("corn", "harvested_ac"), "SOYBEANS - ACRES HARVESTED": ("soy", "harvested_ac"),
        "CORN - ACRES PLANTED": ("corn", "planted_ac"), "SOYBEANS - ACRES PLANTED": ("soy", "planted_ac")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default=None)
    ap.add_argument("--date", default="20261010")
    ap.add_argument("--states", default="IA,IL,IN,NE")
    ap.add_argument("--y0", type=int, default=2000)
    a = ap.parse_args()
    raw = a.raw
    if raw is None:
        raw = f"/tmp/qs_corn_soy_{a.date}.tsv"
        cmd = (f"curl -sS https://www.nass.usda.gov/datasets/qs.crops_{a.date}.txt.gz | gzip -dc | "
               "awk -F'\\t' 'NR==1 || (($4==\"CORN\" || $4==\"SOYBEANS\") && $1==\"SURVEY\")' > " + raw)
        subprocess.run(cmd, shell=True, check=True)
    cols = ["SHORT_DESC", "DOMAIN_DESC", "AGG_LEVEL_DESC", "STATE_ANSI", "STATE_ALPHA", "COUNTY_ANSI", "COUNTY_NAME", "YEAR",
            "REFERENCE_PERIOD_DESC", "VALUE"]
    d = pd.read_csv(raw, sep="\t", dtype=str, usecols=cols)
    d = d[(d.AGG_LEVEL_DESC == "COUNTY") & d.SHORT_DESC.isin(KEEP) & (d.REFERENCE_PERIOD_DESC == "YEAR") & (d.DOMAIN_DESC == "TOTAL")
          & d.STATE_ALPHA.isin(a.states.split(",")) & d.COUNTY_ANSI.notna()]
    d = d[d.YEAR.astype(int) >= a.y0]
    d["crop"] = d.SHORT_DESC.map(lambda s: KEEP[s][0]); d["var"] = d.SHORT_DESC.map(lambda s: KEEP[s][1])
    d["value"] = pd.to_numeric(d.VALUE.str.replace(",", ""), errors="coerce")
    d["fips"] = d.STATE_ANSI.str.zfill(2) + d.COUNTY_ANSI.str.zfill(3)
    p = d.pivot_table(index=["crop", "YEAR", "STATE_ALPHA", "fips", "COUNTY_NAME"], columns="var", values="value", aggfunc="first").reset_index()
    p = p.rename(columns={"YEAR": "year", "STATE_ALPHA": "state", "COUNTY_NAME": "county"})
    p["year"] = p.year.astype(int)
    p = p[["crop", "year", "state", "fips", "county", "yield_bu_ac", "harvested_ac", "planted_ac"]].sort_values(["crop", "fips", "year"])
    os.makedirs(OUT, exist_ok=True)
    p.to_csv(f"{OUT}/county_yield.csv", index=False, float_format="%.1f")
    print(p[p.yield_bu_ac.notna()].groupby(["crop", "state", "year"]).size().unstack("year").iloc[:, -14:].to_string())


if __name__ == "__main__":
    main()
