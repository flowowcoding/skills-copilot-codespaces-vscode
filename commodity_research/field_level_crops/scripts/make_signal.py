"""Assemble the deliverable signal file from the model runs.

Inputs : signal/field_signal_v1.csv (pre-registered primary `field_v1_ridge` + gbm / wx / vi variants),
         signal/field_signal_v1_fused.csv (secondary, Landsat + Sentinel-2 + red edge),
         signal/field_signal_v1_noint.csv (POST-HOC diagnostic, zero intercept; not pre-registered)
Output : signal/field_level_signal.csv, one row per forecast_date x crop x year x region x model_version:
         forecast_date, data_cutoff (latest input used = weather day T-3), imagery_cutoff (latest Landsat /
         S2 acquisition date allowed by the latency rule, DOY of the cutoff), report, crop, year, region
         (IA, IL, IA+IL, US = proxy), predicted_yield, uncertainty (1 sd, bu/ac), trend_yield, model_version,
         status (pre-registered primary / pre-registered secondary / post-hoc), usda_yield_at_release and
         consensus_yield (public only at / just before the release), final_yield_expost (evaluation only).
Usage  : python make_signal.py
"""
import argparse
import numpy as np, pandas as pd
from common import DATA, SIG, STATES


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args()
    parts = []
    for tag, suffix, status in [("v1", "", None), ("v1_fused", "_fused", "pre-registered secondary"), ("v1_noint", "_noint", "post-hoc diagnostic")]:
        s = pd.read_csv(f"{SIG}/field_signal_{tag}.csv")
        s["model_version"] = s.model_version + suffix
        s["status"] = status if status else np.where(s.model == "ridge", "pre-registered primary", "pre-registered secondary")
        parts.append(s)
    s = pd.concat(parts)
    s["imagery_cutoff"] = s.data_cutoff
    s["data_cutoff"] = (pd.to_datetime(s.forecast_date) - pd.Timedelta(days=3)).dt.date
    fin = pd.read_csv(f"{DATA}/finals_jan.csv"); usda = pd.read_csv(f"{DATA}/usda_forecasts.csv")
    cons = pd.read_csv(f"{DATA}/consensus.csv"); ha = pd.read_csv(f"{DATA}/state_harvested.csv")

    def agg(tab, col, crop, year, extra):
        t = tab[(tab.crop == crop) & (tab.year == year)]
        for k, v in extra.items():
            t = t[t[k] == v]
        t = t.set_index("region")[col]
        out = {r: t.get(r, np.nan) for r in STATES + ["US"]}
        w = {r: ha[(ha.crop == crop) & (ha.region == r) & (ha.year < year)].sort_values("year").acres.iloc[-1] for r in STATES}
        out["IA+IL"] = np.average([out[r] for r in STATES], weights=[w[r] for r in STATES]) if all(out[r] == out[r] for r in STATES) else np.nan
        return out
    u, f, c = [], [], []
    for r in s.itertuples():
        u.append(agg(usda, "usda_yield", r.crop, r.year, {"report": r.report})[r.region])
        f.append(agg(fin, "final_jan", r.crop, r.year, {})[r.region])
        cc = cons[(cons.crop == r.crop) & (cons.year == r.year) & (cons.report == r.report)].consensus_yield
        c.append(cc.iloc[0] if (r.region == "US" and len(cc)) else np.nan)
    s["usda_yield_at_release"] = u; s["consensus_yield"] = c; s["final_yield_expost"] = f
    cols = ["forecast_date", "data_cutoff", "imagery_cutoff", "report", "crop", "year", "region", "predicted_yield", "uncertainty", "trend_yield",
            "model_version", "status", "pred_dev_log", "n_counties", "us_beta", "alpha", "usda_yield_at_release", "consensus_yield", "final_yield_expost"]
    s = s[cols].sort_values(["model_version", "crop", "report", "year", "region"])
    s.to_csv(f"{SIG}/field_level_signal.csv", index=False, float_format="%.3f")
    p = s[(s.model_version == "field_v1_ridge") & (s.year == 2026)]
    print(p[["forecast_date", "crop", "region", "predicted_yield", "uncertainty", "trend_yield", "usda_yield_at_release", "consensus_yield"]].to_string(index=False))


if __name__ == "__main__":
    main()
