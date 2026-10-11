"""Evaluate the US satellite yield signal against trend, USDA's August / September forecasts and analyst consensus.

Reads signal/us_sat_signal_<tag>.csv (development years only unless the holdout has been unsealed by
running model.py --evaluate-holdout), data/nass_yield.csv (USDA Aug/Sep state + US forecasts and finals) and,
if present, the benchmark agent's analyst consensus (../benchmark/data/pit/ or ../benchmark/data/consensus/).

Outputs (results/):
  accuracy_<tag>.csv      mean |error| (%) vs final by crop, report, period, level: satellite / trend / USDA /
                          consensus (US only), and RMSE
  gaps_us_<tag>.csv       per year x crop x report: satellite, trend, USDA, consensus, final, gaps (log %),
                          later USDA move, whether the final moved toward the satellite
  gap_test_<tag>.csv      (final - USDA) regressed on (satellite - USDA), states pooled and US, by period;
                          slope, year-clustered t, sign hit rate when |gap| > 3 %
figures: fig_us_paths_<tag>.png, fig_accuracy_<tag>.png
Usage: python evaluate.py [--tag v1] [--holdout-from 2022]
"""
import argparse, glob, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def consensus(root):
    """national yield consensus (avg of the trade poll) per year, crop, report from the benchmark agent"""
    cands = sorted(glob.glob(os.path.join(root, "..", "benchmark", "data", "pit", "*consensus*.csv"))) + \
        sorted(glob.glob(os.path.join(root, "..", "benchmark", "data", "consensus", "*.csv")))
    for fn in cands:
        c = pd.read_csv(fn)
        cols = set(c.columns)
        if {"report_date", "crop", "variable", "avg"} <= cols:
            c = c[c.variable == "yield"].copy()
            c["report_date"] = pd.to_datetime(c.report_date)
            c = c[c.report_date.dt.month.isin([8, 9])]
            c["year"] = c.report_date.dt.year; c["report"] = np.where(c.report_date.dt.month == 8, "aug", "sep")
            c["crop"] = c.crop.replace({"soybeans": "soy"})
            c = c.drop_duplicates(["year", "crop", "report"], keep="last")
            return c[["year", "crop", "report", "avg"]].rename(columns={"avg": "consensus"}), os.path.relpath(fn, root)
    return pd.DataFrame(columns=["year", "crop", "report", "consensus"]), None


def cluster_ols(x, y, g):
    X = np.column_stack([np.ones_like(x), x])
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    e = y - X @ b
    XtX = np.linalg.inv(X.T @ X)
    meat = sum(np.outer(X[g == k].T @ e[g == k], X[g == k].T @ e[g == k]) for k in np.unique(g))
    G = len(np.unique(g)); n = len(y)
    V = XtX @ meat @ XtX * (G / max(G - 1, 1)) * ((n - 1) / max(n - 2, 1))
    return b[1], b[1] / np.sqrt(V[1, 1]) if V[1, 1] > 0 else np.nan


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", default="v1")
    ap.add_argument("--holdout-from", type=int, default=2022)
    a = ap.parse_args()
    root = HERE
    s = pd.read_csv(f"{root}/signal/us_sat_signal_{a.tag}.csv")
    ny = pd.read_csv(f"{root}/data/nass_yield.csv")
    usda = ny[ny.period.isin(["aug", "sep"])].rename(columns={"period": "report", "yield_bu_ac": "usda"})[["crop", "year", "region", "report", "usda"]]
    nxt = ny[ny.period.isin(["sep", "oct"])].copy(); nxt["report"] = nxt.period.map({"sep": "aug", "oct": "sep"})
    nxt = nxt.rename(columns={"yield_bu_ac": "usda_next"})[["crop", "year", "region", "report", "usda_next"]]
    d = s.merge(usda, on=["crop", "year", "region", "report"], how="left").merge(nxt, on=["crop", "year", "region", "report"], how="left")
    cons, csrc = consensus(root)
    d = d.merge(cons.assign(region="US"), on=["year", "crop", "report", "region"], how="left")
    d = d[d.year <= 2025]  # finals exist through 2025
    d["period"] = np.where(d.year >= a.holdout_from, "holdout", "dev")
    for k in ["predicted_yield", "trend_yield", "usda", "consensus"]:
        d[f"err_{k}"] = 100 * (d[k] / d.final_yield_expost - 1)
    d["level"] = np.where(d.region == "US", "US", "states")
    acc = []
    for (crop, rep, per, lev), g in d.groupby(["crop", "report", "period", "level"]):
        r = dict(crop=crop, report=rep, period=per, level=lev, n=len(g), years=f"{g.year.min()}-{g.year.max()}")
        for k, nm in [("predicted_yield", "sat"), ("trend_yield", "trend"), ("usda", "usda"), ("consensus", "consensus")]:
            e = g[f"err_{k}"].dropna()
            r[f"mae_{nm}"] = e.abs().mean() if len(e) else np.nan
            r[f"rmse_{nm}"] = np.sqrt((e ** 2).mean()) if len(e) else np.nan
            r[f"n_{nm}"] = len(e)
        # interval coverage
        r["cover_1sd"] = (np.abs(g.predicted_yield - g.final_yield_expost) <= g.uncertainty).mean()
        acc.append(r)
    acc = pd.DataFrame(acc)
    acc.to_csv(f"{root}/results/accuracy_{a.tag}.csv", index=False, float_format="%.3f")
    print(acc[["crop", "report", "period", "level", "n", "mae_sat", "mae_trend", "mae_usda", "mae_consensus", "cover_1sd"]].to_string())
    # gaps
    d["gap_sat_usda"] = 100 * np.log(d.predicted_yield / d.usda)
    d["gap_sat_cons"] = 100 * np.log(d.predicted_yield / d.consensus)
    d["final_vs_usda"] = 100 * np.log(d.final_yield_expost / d.usda)
    d["next_vs_usda"] = 100 * np.log(d.usda_next / d.usda)
    d["final_moved_toward_sat"] = np.sign(d.final_vs_usda) == np.sign(d.gap_sat_usda)
    d["sat_closer_than_usda"] = d.err_predicted_yield.abs() < d.err_usda.abs()
    us = d[d.region == "US"][["year", "crop", "report", "period", "forecast_date", "data_cutoff_date", "predicted_yield", "uncertainty", "trend_yield", "usda",
                              "consensus", "final_yield_expost", "gap_sat_usda", "gap_sat_cons", "next_vs_usda", "final_vs_usda", "final_moved_toward_sat",
                              "sat_closer_than_usda", "vi_source"]]
    us.sort_values(["crop", "report", "year"]).to_csv(f"{root}/results/gaps_us_{a.tag}.csv", index=False, float_format="%.3f")
    print(us[us.period == "holdout"].to_string())
    gt = []
    for (per, lev, rep), g in d.groupby(["period", "level", "report"]):
        g = g.dropna(subset=["gap_sat_usda", "final_vs_usda"])
        if len(g) < 4:
            continue
        b, t = cluster_ols(g.gap_sat_usda.values, g.final_vs_usda.values, g.year.values)
        b2, t2 = cluster_ols(g.gap_sat_usda.values, g.next_vs_usda.values, g.year.values) if g.next_vs_usda.notna().all() else (np.nan, np.nan)
        big = g[g.gap_sat_usda.abs() > 3]
        gt.append(dict(period=per, level=lev, report=rep, n=len(g), n_years=g.year.nunique(), slope_final=b, t_final=t, slope_next_report=b2, t_next=t2,
                       n_big=len(big), hit_big=(np.sign(big.gap_sat_usda) == np.sign(big.final_vs_usda)).mean() if len(big) else np.nan,
                       hit_all=(np.sign(g.gap_sat_usda) == np.sign(g.final_vs_usda)).mean()))
    gt = pd.DataFrame(gt)
    gt.to_csv(f"{root}/results/gap_test_{a.tag}.csv", index=False, float_format="%.3f")
    print(gt.to_string())
    if csrc:
        print("consensus from", csrc)
    # figures
    from plotstyle import setup, C, TEXT
    plt = setup()
    for crop, unit in [("corn", "bu/ac"), ("soy", "bu/ac")]:
        fig, ax = plt.subplots(figsize=(9, 4.2))
        g = d[(d.region == "US") & (d.crop == crop) & (d.report == "sep")].sort_values("year")
        ga = d[(d.region == "US") & (d.crop == crop) & (d.report == "aug")].sort_values("year")
        ax.plot(g.year, g.final_yield_expost, color=TEXT, lw=1.5, label="final (NASS)")
        ax.plot(ga.year, ga.predicted_yield, color=C[0], ls="--", lw=1.4, marker="o", ms=3, label="satellite, Aug date")
        ax.plot(g.year, g.predicted_yield, color=C[0], marker="o", ms=4, label="satellite, Sep date")
        ax.plot(g.year, g.usda, color=C[1], marker="s", ms=3.5, lw=1.4, label="USDA September")
        ax.plot(g.year, g.trend_yield, color=C[2], lw=1.2, label="trend")
        ax.axvspan(a.holdout_from - 0.5, g.year.max() + 0.5, color="#e6e5e1", alpha=0.5, lw=0)
        ax.text(a.holdout_from - 0.35, ax.get_ylim()[1], "holdout", va="top", color=TEXT)
        ax.set_title(f"US {'corn' if crop == 'corn' else 'soybean'} yield ({unit}): satellite vs USDA vs final ({a.tag})")
        ax.legend(ncol=3, loc="lower right")
        fig.tight_layout(); fig.savefig(f"{root}/figures/fig_us_paths_{crop}_{a.tag}.png", dpi=130); plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 4))
    lab, xs = [], 0
    names = [("mae_sat", "satellite"), ("mae_trend", "trend"), ("mae_usda", "USDA"), ("mae_consensus", "consensus")]
    sub = acc[acc.level == "US"].sort_values(["period", "crop", "report"])
    for i, r in enumerate(sub.itertuples()):
        for j, (k, nm) in enumerate(names):
            v = getattr(r, k)
            ax.bar(i + (j - 1.5) * 0.2, v if np.isfinite(v) else 0, width=0.19, color=C[j], label=nm if i == 0 else None)
        lab.append(f"{r.crop} {r.report}\n{r.period}")
    ax.set_xticks(range(len(sub))); ax.set_xticklabels(lab, fontsize=8)
    ax.set_ylabel("mean |error| vs final, %"); ax.set_title(f"US yield error by forecast date ({a.tag})"); ax.legend(ncol=4)
    ax.grid(axis="x", visible=False)
    fig.tight_layout(); fig.savefig(f"{root}/figures/fig_accuracy_{a.tag}.png", dpi=130)


if __name__ == "__main__":
    main()
