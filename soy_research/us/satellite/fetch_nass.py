"""Minimal NASS yield / acreage fetch for the US satellite yield model (corn grain and soybeans).

Source: the NASS Quick Stats bulk file (https://www.nass.usda.gov/datasets/qs.crops_<date>.txt.gz, no API
key). It is streamed and filtered on the fly; only survey rows for corn and soybeans are kept.

Outputs (soy_research/us/satellite/data/):
  nass_yield.csv   state + national rows: crop, year, region (state alpha or US), period
                   (final | aug | sep | oct | nov; jun = June Acreage, area only), yield_bu_ac, load_time (the Quick Stats load
                   time; for forecast periods it equals the Crop Production release time)
  nass_area.csv    state + national harvested and planted acres (final and Aug/Sep forecasts)
  county_planted.csv  county planted acres, corn and soybeans, 12 states, all years
  release_dates.csv   Crop Production release date per year for Aug and Sep (from load_time of the
                      national yield forecast rows)

"final" is the latest published annual value (the January Annual Summary, plus any later revision).
For the current year the annual row is the latest forecast, so it is dropped for years >= --current-year.
Usage: python fetch_nass.py [--date 20261010] [--raw <path to a pre-filtered tsv>]
"""
import argparse, gzip, io, os, subprocess
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STATES = ["IA", "IL", "NE", "MN", "IN", "OH", "SD", "ND", "KS", "MO", "WI", "MI"]
KEEP = {"CORN, GRAIN - YIELD, MEASURED IN BU / ACRE": ("corn", "yield"), "SOYBEANS - YIELD, MEASURED IN BU / ACRE": ("soy", "yield"),
        "CORN, GRAIN - ACRES HARVESTED": ("corn", "harvested"), "SOYBEANS - ACRES HARVESTED": ("soy", "harvested"),
        "CORN - ACRES PLANTED": ("corn", "planted"), "SOYBEANS - ACRES PLANTED": ("soy", "planted")}
PER = {"YEAR": "final", "YEAR - AUG FORECAST": "aug", "YEAR - SEP FORECAST": "sep", "YEAR - OCT FORECAST": "oct", "YEAR - NOV FORECAST": "nov",
       "YEAR - JUN ACREAGE": "jun"}


def load(date, raw):
    if raw is None:
        raw = f"/tmp/qs_corn_soy_{date}.tsv"
        cmd = (f"curl -sS https://www.nass.usda.gov/datasets/qs.crops_{date}.txt.gz | gzip -dc | "
               "awk -F'\\t' 'NR==1 || (($4==\"CORN\" || $4==\"SOYBEANS\") && $1==\"SURVEY\")' > " + raw)
        subprocess.run(cmd, shell=True, check=True)
    d = pd.read_csv(raw, sep="\t", dtype=str)
    d = d[d.SHORT_DESC.isin(KEEP) & d.REFERENCE_PERIOD_DESC.isin(PER) & (d.DOMAIN_DESC == "TOTAL")]
    d["crop"] = d.SHORT_DESC.map(lambda s: KEEP[s][0]); d["var"] = d.SHORT_DESC.map(lambda s: KEEP[s][1])
    d["period"] = d.REFERENCE_PERIOD_DESC.map(PER)
    d["value"] = pd.to_numeric(d.VALUE.str.replace(",", ""), errors="coerce")
    d["year"] = d.YEAR.astype(int)
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", default="20261010")
    ap.add_argument("--raw", default=None)
    ap.add_argument("--current-year", type=int, default=2026)
    ap.add_argument("--out", default=os.path.join(HERE, "data"))
    a = ap.parse_args()
    d = load(a.date, a.raw)
    st = d[d.AGG_LEVEL_DESC.isin(["STATE", "NATIONAL"])].copy()
    st["region"] = st.STATE_ALPHA.where(st.AGG_LEVEL_DESC == "STATE", "US")
    st = st[st.region.isin(STATES + ["US"]) & (st.year >= 1990)]
    st = st[~((st.period == "final") & (st.year >= a.current_year))]
    cols = ["crop", "year", "region", "period", "value", "LOAD_TIME"]
    y = st[st["var"] == "yield"][cols].rename(columns={"value": "yield_bu_ac", "LOAD_TIME": "load_time"})
    y = y.sort_values("load_time").drop_duplicates(["crop", "year", "region", "period"], keep="last")
    y.sort_values(["crop", "region", "year", "period"]).to_csv(f"{a.out}/nass_yield.csv", index=False)
    ar = st[st["var"].isin(["harvested", "planted"])][cols + ["var"]].rename(columns={"value": "acres", "LOAD_TIME": "load_time"})
    ar = ar.sort_values("load_time").drop_duplicates(["crop", "year", "region", "period", "var"], keep="last")
    ar.sort_values(["crop", "region", "year", "var", "period"]).to_csv(f"{a.out}/nass_area.csv", index=False)
    co = d[(d.AGG_LEVEL_DESC == "COUNTY") & (d["var"] == "planted") & (d.period == "final") & d.STATE_ALPHA.isin(STATES)].copy()
    co = co[co.COUNTY_ANSI.notna() & (co.COUNTY_ANSI != "")]
    co["fips"] = co.STATE_ANSI.str.zfill(2) + co.COUNTY_ANSI.str.zfill(3)
    co[["crop", "year", "fips", "STATE_ALPHA", "value"]].rename(columns={"value": "planted_ac", "STATE_ALPHA": "state"}) \
        .sort_values(["crop", "fips", "year"]).to_csv(f"{a.out}/county_planted.csv", index=False)
    r = y[(y.region == "US") & y.period.isin(["aug", "sep"])].copy()
    r["release_date"] = r.load_time.str[:10]
    r = r.pivot_table(index="year", columns="period", values="release_date", aggfunc="min").reset_index()
    r.columns = ["year", "aug_release", "sep_release"]
    for c in ["aug_release", "sep_release"]:  # pre-2012 rows carry the bulk-load time, not the release
        r.loc[r[c].astype(str).str.startswith("2012-01-01"), c] = None
    r.to_csv(f"{a.out}/release_dates.csv", index=False)
    print(r.tail(25).to_string())


if __name__ == "__main__":
    main()
