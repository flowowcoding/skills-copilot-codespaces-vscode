"""Write the versioned point-in-time signal dataset (long format).

Columns: version, as_of (date the value could first be known), data_cutoff (end of the latest observation
period used), region, feature, value, source.
Contents:
  - weather/satellite features (z-scores) for ALL, CIV_W, CIV_E, GHA at each month end, plus DRY/WETX
  - benchmark estimates: ICCO world vintages (production, grindings, surplus) and CIV/GHA country vintages
    (as_of = release date), CIV reported arrivals y/y and Ghana purchases (as_of = data date + 1 day)
Output: signal/cocoa_pit_signal_v1.csv
Usage: python make_signal.py [--version v1]
"""
import argparse, os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data"); SIG = os.path.join(HERE, "..", "signal")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", default="v1")
    a = ap.parse_args()
    rows = []
    F = pd.read_csv(f"{DATA}/features_monthly.csv", parse_dates=["as_of"])
    feats = ["rain_3m", "rain_6m", "soil_3m", "tmax_3m", "rh_3m", "evi_3m"]
    for f in feats:
        d = F[["as_of", "zone", f"{f}_z", f"{f}_cutoff"]].dropna(subset=[f"{f}_z"])
        rows.append(pd.DataFrame({"as_of": d.as_of, "data_cutoff": pd.to_datetime(d[f"{f}_cutoff"]), "region": d.zone, "feature": f"{f}_z",
                                  "value": d[f"{f}_z"], "source": {"rain": "CHIRPS v2 monthly", "evi": "MODIS MYD13A1 v061"}.get(f.split("_")[0], "NASA POWER daily")}))
    cut = F[[c for c in F.columns if c.endswith("_cutoff")]].apply(pd.to_datetime).max(axis=1)
    for f in ["DRY", "WETX"]:
        d = F.assign(cut=cut).dropna(subset=[f])
        rows.append(pd.DataFrame({"as_of": d.as_of, "data_cutoff": d.cut, "region": d.zone, "feature": f, "value": d[f], "source": "composite (README)"}))
    w = pd.read_csv(f"{DATA}/icco_world_vintages.csv", parse_dates=["pub_date"]).dropna(subset=["world_production_kt"])
    for col in ["world_production_kt", "world_grindings_kt", "surplus_kt"]:
        rows.append(pd.DataFrame({"as_of": w.pub_date, "data_cutoff": w.pub_date.dt.to_period("M").dt.to_timestamp(), "region": "WORLD",
                                  "feature": "icco_" + col + "_" + w.season, "value": w[col], "source": "ICCO QBCS press release " + w.source_slug}))
    c = pd.read_csv(f"{DATA}/icco_country_vintages.csv", parse_dates=["pub_date"]).dropna(subset=["civ_kt"])
    for col, reg in [("civ_kt", "CIV"), ("gha_kt", "GHA")]:
        rows.append(pd.DataFrame({"as_of": c.pub_date, "data_cutoff": c.pub_date.dt.to_period("M").dt.to_timestamp(), "region": reg,
                                  "feature": "icco_production_kt_" + c.season, "value": c[col], "source": c.source_pdf}))
    for fn, reg, feat in [("civ_arrivals_reported.csv", "CIV", "arrivals"), ("gha_purchases_reported.csv", "GHA", "purchases")]:
        r = pd.read_csv(f"{DATA}/{fn}", parse_dates=["as_of"])
        r["yoy"] = r.yoy_pct_reported.where(r.yoy_pct_reported.notna(), 100 * (r.cum_kt / r.prev_cum_kt - 1))
        for col, name in [("cum_kt", f"{feat}_cum_kt"), ("yoy", f"{feat}_yoy_pct")]:
            d = r.dropna(subset=[col])
            rows.append(pd.DataFrame({"as_of": d.as_of + pd.Timedelta(days=1), "data_cutoff": d.as_of, "region": reg, "feature": name, "value": d[col], "source": d.source}))
    S = pd.concat(rows, ignore_index=True)
    S.insert(0, "version", a.version)
    S = S.sort_values(["as_of", "region", "feature"])
    os.makedirs(SIG, exist_ok=True)
    out = f"{SIG}/cocoa_pit_signal_{a.version}.csv"
    S.to_csv(out, index=False, float_format="%.4f", date_format="%Y-%m-%d")
    print(out, len(S), S.as_of.min().date(), S.as_of.max().date(), f"{os.path.getsize(out)/1e6:.2f} MB")


if __name__ == "__main__":
    main()
