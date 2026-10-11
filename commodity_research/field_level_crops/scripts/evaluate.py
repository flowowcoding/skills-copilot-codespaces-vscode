"""Score the field-level signal against the January finals and the benchmarks (pre-registered metrics).

  --period dev      walk-forward years 2016-2021 (used while building the model)
  --period holdout  2022-2025 (run only after the pre-registration in README.md was written)

Metrics (per crop x report):
  1. Mean |error| (%) vs the January final for IA, IL (pooled = "states"), IA+IL and the US proxy:
     field model (ridge = primary; gbm, wx, vi variants), trend (the model's Theil-Sen trend), the previous
     MODIS model (us_sat_v1; IA+IL = its IA and IL forecasts weighted with the same acres), USDA in that
     report, and the trade consensus (US only).
  2. County skill: R^2 of detrended county yield anomalies (d = ln(yield / county trend)),
       pooled      1 - SSE / SST over all county-years
       within-year same after removing each year's mean from prediction and truth (spatial skill only)
     for the model variants and two baselines: trend (d = 0) and "USDA uniform" (every county gets USDA's
     state anomaly ln(USDA state forecast / state trend) from that report).
  3. Direction: share of region-years where the final moved from USDA toward the model (when |model - USDA|
     > 1 %).
Outputs: results/accuracy_<period>_<tag>.csv, results/county_skill_<period>_<tag>.csv,
         results/region_rows_<period>_<tag>.csv, results/direction_<period>_<tag>.csv
Usage:   python evaluate.py --period dev|holdout [--tag v1]
"""
import argparse
import numpy as np, pandas as pd
from common import DATA, FEAT, SIG, RES, STATES

PERIODS = {"dev": range(2016, 2022), "holdout": range(2022, 2026)}


def r2(y, p):
    y, p = np.asarray(y), np.asarray(p)
    return 1 - np.sum((y - p) ** 2) / np.sum((y - y.mean()) ** 2)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--period", choices=["dev", "holdout"], required=True)
    ap.add_argument("--tag", default="v1")
    a = ap.parse_args()
    yrs = list(PERIODS[a.period])
    s = pd.read_csv(f"{SIG}/field_signal_{a.tag}.csv")
    s = s[s.year.isin(yrs)]
    fin = pd.read_csv(f"{DATA}/finals_jan.csv")
    usda = pd.read_csv(f"{DATA}/usda_forecasts.csv")
    cons = pd.read_csv(f"{DATA}/consensus.csv")
    modis = pd.read_csv(f"{DATA}/modis_v1.csv")
    ha = pd.read_csv(f"{DATA}/state_harvested.csv")

    def acres(crop, Y):
        out = {}
        for st in STATES:
            h = ha[(ha.crop == crop) & (ha.region == st) & (ha.year < Y)].sort_values("year")
            out[st] = h.acres.iloc[-1]
        return out

    # benchmark rows per region (IA, IL, IA+IL, US)
    bench = []
    for (crop, rep, Y), g in s[s.model == "ridge"].groupby(["crop", "report", "year"]):
        w = acres(crop, Y)
        f = fin[(fin.crop == crop) & (fin.year == Y)].set_index("region").final_jan
        u = usda[(usda.crop == crop) & (usda.year == Y) & (usda.report == rep)].set_index("region").usda_yield
        m = modis[(modis.crop == crop) & (modis.year == Y) & (modis.report == rep)].set_index("region").predicted_yield
        tr = g.set_index("region").trend_yield
        c = cons[(cons.crop == crop) & (cons.year == Y) & (cons.report == rep)].consensus_yield
        for reg in STATES + ["IA+IL", "US"]:
            if reg == "IA+IL":
                wt = np.array([w[x] for x in STATES])
                agg = lambda ser: np.average([ser[x] for x in STATES], weights=wt) if all(x in ser.index for x in STATES) else np.nan
                fv, uv, mv = agg(f), agg(u), agg(m)
            else:
                fv, uv, mv = f.get(reg, np.nan), u.get(reg, np.nan), m.get(reg, np.nan)
            bench.append(dict(crop=crop, report=rep, year=Y, region=reg, final=fv, usda=uv, modis=mv, trend=tr.get(reg, np.nan),
                              consensus=c.iloc[0] if (reg == "US" and len(c)) else np.nan))
    b = pd.DataFrame(bench)
    piv = s.pivot_table(index=["crop", "report", "year", "region"], columns="model", values="predicted_yield").reset_index()
    rows = b.merge(piv, on=["crop", "report", "year", "region"], how="left")
    srcs = [c for c in ["ridge", "gbm", "wx", "vi", "trend", "modis", "usda", "consensus"] if c in rows]
    for c in srcs:
        rows[f"ape_{c}"] = 100 * np.abs(rows[c] / rows.final - 1)
    rows.to_csv(f"{RES}/region_rows_{a.period}_{a.tag}.csv", index=False, float_format="%.3f")
    acc = []
    for (crop, rep), g in rows.groupby(["crop", "report"]):
        for lvl, sel in [("states (IA, IL)", g.region.isin(STATES)), ("IA+IL", g.region == "IA+IL"), ("US proxy", g.region == "US")]:
            q = g[sel]
            acc.append(dict(crop=crop, report=rep, level=lvl, n=len(q), **{c: q[f"ape_{c}"].mean() for c in srcs}))
    acc = pd.DataFrame(acc)
    acc.to_csv(f"{RES}/accuracy_{a.period}_{a.tag}.csv", index=False, float_format="%.2f")
    print("Mean |error| % vs January final,", a.period)
    print(acc.round(2).to_string(index=False))

    # direction test
    d = rows.copy()
    d["gap"] = 100 * np.log(d.ridge / d.usda); d["move"] = 100 * np.log(d.final / d.usda)
    d = d[d.gap.abs() > 1]
    dirr = d.groupby(["crop", "report"]).apply(lambda q: pd.Series(dict(n=len(q), toward=(np.sign(q.gap) == np.sign(q.move)).mean())), include_groups=False)
    dirr.to_csv(f"{RES}/direction_{a.period}_{a.tag}.csv", float_format="%.3f")
    print(dirr)

    # county skill
    cp = pd.read_csv(f"{FEAT}/county_predictions_{a.tag}.csv", dtype={"fips": str})
    cp = cp[cp.year.isin(yrs) & cp.dev.notna()]
    out = []
    for (crop, rep), g in cp.groupby(["crop", "report"]):
        base = g[g.model == "ridge"].copy()
        # USDA-uniform baseline: USDA's state anomaly vs the model's state trend
        sig = s[(s.crop == crop) & (s.report == rep) & (s.model == "ridge")].set_index(["year", "region"]).trend_yield
        base["usda_dev"] = [np.log(usda[(usda.crop == crop) & (usda.year == r.year) & (usda.report == rep) & (usda.region == r.state)].usda_yield.iloc[0]
                                   / sig.get((r.year, r.state), np.nan)) for r in base.itertuples()]
        preds = {m: g[g.model == m].set_index(["year", "fips"]).pred for m in g.model.unique()}
        base = base.set_index(["year", "fips"])
        cand = {**{m: preds[m].reindex(base.index) for m in preds}, "trend": pd.Series(0.0, index=base.index), "usda_uniform": base.usda_dev}
        y = base.dev
        ym = y.groupby(level=0).transform("mean")
        for m, p in cand.items():
            ok = p.notna() & y.notna()
            pm = p[ok].groupby(level=0).transform("mean")
            out.append(dict(crop=crop, report=rep, model=m, n=int(ok.sum()), years=len(set(y[ok].index.get_level_values(0))),
                            r2_pooled=r2(y[ok], p[ok]), r2_within_year=r2(y[ok] - ym[ok], p[ok] - pm) if m not in ("trend", "usda_uniform") else 0.0,
                            corr_pooled=np.corrcoef(y[ok], p[ok])[0, 1] if p[ok].std() > 0 else np.nan,
                            corr_within=np.corrcoef(y[ok] - ym[ok], p[ok] - pm)[0, 1] if (p[ok] - pm).std() > 1e-9 else np.nan,
                            rmse_pct=100 * np.sqrt(np.mean((y[ok] - p[ok]) ** 2))))
    cs = pd.DataFrame(out)
    cs.to_csv(f"{RES}/county_skill_{a.period}_{a.tag}.csv", index=False, float_format="%.3f")
    print(cs.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
