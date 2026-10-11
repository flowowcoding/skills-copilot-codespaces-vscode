"""Pull what the satellite model needs from the benchmark agent's point-in-time dataset (../benchmark/).

Inputs: ../benchmark/data/pit/pit_us_corn_soy.parquet, ../benchmark/results/events.csv
Outputs (data/):
  release_dates.csv     actual Aug / Sep Crop Production release dates 2005-2026 (overwrites the Quick Stats
                        load-time version written by fetch_nass.py)
  finals_jan.csv        January Annual Summary yields (crop_year 2004-2025), US + 12 states: the truth
  usda_forecasts.csv    USDA Aug / Sep Crop Production yield forecasts, US + 12 states, with release date
  jun_harvested.csv     June Acreage harvested-for-grain area (million acres), US + 12 states
  consensus_events.csv  per Aug / Sep report and crop: USDA yield, trade consensus yield (cons_yield_eff:
                        poll yield, or production poll / USDA area when only production was polled),
                        report-day return (r_main %, r_main_cbu cents/bu, source), previous settlement
Crop label 'soybeans' is renamed 'soy'.
Usage: python prep_benchmark.py
"""
import os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BM = os.path.join(HERE, "..", "benchmark")
REG = ["US", "IA", "IL", "NE", "MN", "IN", "OH", "SD", "ND", "KS", "MO", "WI", "MI"]


def main():
    p = pd.read_parquet(f"{BM}/data/pit/pit_us_corn_soy.parquet")
    p["crop"] = p.crop.replace({"soybeans": "soy"})
    p = p[p.region.isin(REG)]
    p["month"] = pd.to_datetime(p.release_date).dt.month
    cp = p[(p.report == "crop_production") & (p.variable == "yield") & p.month.isin([8, 9])].copy()
    cp["report"] = cp.month.map({8: "aug", 9: "sep"})
    cp[["crop", "crop_year", "region", "report", "release_date", "release_time_et", "value"]].rename(
        columns={"crop_year": "year", "value": "usda_yield"}).sort_values(["crop", "region", "year", "report"]).to_csv(f"{HERE}/data/usda_forecasts.csv", index=False)
    rd = cp[cp.region == "US"].pivot_table(index="crop_year", columns="report", values="release_date", aggfunc="min").reset_index()
    rd.columns = ["year", "aug_release", "sep_release"]
    rd.to_csv(f"{HERE}/data/release_dates.csv", index=False)
    fa = p[(p.report == "crop_production_annual") & (p.variable == "yield")]
    fa[["crop", "crop_year", "region", "release_date", "value"]].rename(columns={"crop_year": "year", "value": "final_jan"}) \
        .sort_values(["crop", "region", "year"]).to_csv(f"{HERE}/data/finals_jan.csv", index=False)
    ac = p[(p.report == "acreage") & (p.variable == "harvested_area")]
    ac[["crop", "crop_year", "region", "release_date", "value"]].rename(columns={"crop_year": "year", "value": "harvested_mac"}) \
        .sort_values(["crop", "region", "year"]).to_csv(f"{HERE}/data/jun_harvested.csv", index=False)
    e = pd.read_csv(f"{BM}/results/events.csv")
    e = e[e.report.eq("crop_production") & e.month.isin(["Aug", "Sep"])].copy()
    e["crop"] = e.crop.replace({"soybeans": "soy"}); e["report"] = e.month.str.lower(); e["year"] = e.crop_year
    e[["year", "crop", "report", "release_date", "usda_yield", "cons_yield", "cons_yield_eff", "cons_yield_implied", "cons_source", "surp_pct",
       "r_main", "r_main_cbu", "src_main", "price_cbu"]].to_csv(f"{HERE}/data/consensus_events.csv", index=False)
    print(rd.tail(5).to_string()); print(len(cp), len(fa), len(ac), len(e))


if __name__ == "__main__":
    main()
