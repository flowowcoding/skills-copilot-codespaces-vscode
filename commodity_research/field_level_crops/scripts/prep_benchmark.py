"""Copy the point-in-time benchmark inputs this study needs (IA, IL, US) from the previous US satellite study,
which built them from soy_research/us/benchmark/ (USDA PIT vintages, consensus) and the NASS Quick Stats bulk file.

Inputs  (soy_research/us/satellite/data/): finals_jan.csv (January Annual Summary = truth; before 2004 the
        revised Quick Stats final from nass_yield.csv, used only for trends), usda_forecasts.csv
        (USDA Aug/Sep state + US forecasts), release_dates.csv, consensus_events.csv (trade average before each
        report, US only), nass_area.csv (state harvested acres, finals), signal/us_sat_signal_v1.csv (MODIS model).
Outputs (data/): finals_jan.csv, usda_forecasts.csv, release_dates.csv, consensus.csv, state_harvested.csv,
        modis_v1.csv (previous model's predictions for IA, IL, US)
Usage:  python prep_benchmark.py
"""
import argparse
import pandas as pd
from common import DATA, PREV

REG = ["IA", "IL", "US"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    p = f"{PREV}/data"
    f = pd.read_csv(f"{p}/finals_jan.csv"); f = f[f.region.isin(REG)]
    # before 2004 (no January vintage in the benchmark) the revised Quick Stats final is used, as in the MODIS study
    q = pd.read_csv(f"{p}/nass_yield.csv")
    q = q[(q.period == "final") & q.region.isin(REG) & (q.year < f.year.min())]
    q = q.assign(release_date="", final_jan=q.yield_bu_ac)[["crop", "year", "region", "release_date", "final_jan"]]
    pd.concat([q, f]).sort_values(["crop", "region", "year"]).to_csv(f"{DATA}/finals_jan.csv", index=False)
    u = pd.read_csv(f"{p}/usda_forecasts.csv"); u[u.region.isin(REG)].to_csv(f"{DATA}/usda_forecasts.csv", index=False)
    pd.read_csv(f"{p}/release_dates.csv").to_csv(f"{DATA}/release_dates.csv", index=False)
    c = pd.read_csv(f"{p}/consensus_events.csv")
    c[["year", "crop", "report", "release_date", "usda_yield", "cons_yield_eff", "cons_source"]].rename(columns={"cons_yield_eff": "consensus_yield"}) \
        .to_csv(f"{DATA}/consensus.csv", index=False)
    a = pd.read_csv(f"{p}/nass_area.csv")
    a = a[(a["var"] == "harvested") & (a.period == "final") & a.region.isin(REG)][["crop", "year", "region", "acres"]]
    a.to_csv(f"{DATA}/state_harvested.csv", index=False)
    s = pd.read_csv(f"{PREV}/signal/us_sat_signal_v1.csv")
    s = s[s.region.isin(REG)][["forecast_date", "report", "crop", "year", "region", "predicted_yield", "uncertainty", "trend_yield", "model_version"]]
    s.to_csv(f"{DATA}/modis_v1.csv", index=False)
    print("ok", len(f), len(u), len(c), len(a), len(s))


if __name__ == "__main__":
    main()
