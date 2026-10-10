"""Pre-registered evaluation of the Chilean pit activity index against production.

Usage:
    python evaluate.py RESULTS_DIR [--variant R] [--period dev|holdout|all] [--out OUT_PREFIX]

RESULTS_DIR holds <mine>_pairs.csv from activity_index.py. Ground truth CSVs are read from this
directory (cochilco_monthly_by_operation.csv, bhp_material_mined_quarterly.csv,
anglo_ore_mined_quarterly.csv). See README "Pre-registration" for the design:
  * quarterly index = mean of the quarter's pair values; monthly likewise;
  * YoY: index change in pts vs log change of production (same quarter a year earlier);
  * QoQ: same with the previous quarter;
  * aggregate: per-mine YoY index changes / development SD, weighted by 2018 production share;
  * development = 2019Q1-2024Q4 (YoY obs from 2020Q1), holdout = 2025Q1-2026Q2;
  * primary statistic Spearman, Pearson alongside; aggregate significance by circular shifts.
--period selects which quarters are scored. The holdout is run once, after the development
results are written into the README.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

HERE = Path(__file__).parent
DEV = ("2019Q1", "2024Q4")
HOLD = ("2025Q1", "2026Q2")
MIN_PAIRS_Q = 2          # quarters with fewer usable pairs are treated as missing


def load_index(res, variant):
    cfg = json.load(open(HERE / "mines.json"))["mines"]
    q, m = {}, {}
    for k in cfg:
        f = Path(res) / f"{k}_pairs.csv"
        if not f.exists():
            continue
        df = pd.read_csv(f, index_col=0, parse_dates=True)
        s = df[variant].where(df[f"n_{variant}"] >= 20)            # need >= 20 valid busy px
        g = s.groupby(s.index.to_period("Q"))
        q[k] = g.mean().where(g.count() >= MIN_PAIRS_Q)
        gm = s.groupby(s.index.to_period("M"))
        m[k] = gm.mean()
    return pd.DataFrame(q), pd.DataFrame(m), cfg


def load_production(cfg):
    gt = pd.read_csv(HERE / "cochilco_monthly_by_operation.csv")
    wide = gt.pivot(index="month", columns="operation", values="kt_cu")
    wide.index = pd.PeriodIndex(wide.index, freq="M")
    pm = pd.DataFrame({k: wide[v["cochilco"]].sum(axis=1, min_count=len(v["cochilco"])) for k, v in cfg.items()})
    pm["_chile"] = wide["TOTAL CHILE"]
    full = pm.groupby(pm.index.asfreq("Q")).count() == 3          # complete quarters only
    pq = pm.groupby(pm.index.asfreq("Q")).sum(min_count=3).where(full)
    return pq, pm


def corr(x, y):
    ok = x.notna() & y.notna() & np.isfinite(x) & np.isfinite(y)
    n = int(ok.sum())
    if n < 4:
        return dict(n=n, spearman=np.nan, pearson=np.nan, sign_hit=np.nan)
    return dict(n=n, spearman=spearmanr(x[ok], y[ok])[0], pearson=pearsonr(x[ok], y[ok])[0],
                sign_hit=float((np.sign(x[ok]) == np.sign(y[ok])).mean()))


def shift_p(x, y, nmin=4):
    """two-sided p of Spearman r from circular shifts of x against y (shifts >= nmin)."""
    ok = x.notna() & y.notna()
    xv, yv = x[ok].values, y[ok].values
    n = len(xv)
    r0 = spearmanr(xv, yv)[0]
    rs = [spearmanr(np.roll(xv, k), yv)[0] for k in range(nmin, n - nmin + 1)]
    return float((np.sum(np.abs(rs) >= abs(r0)) + 1) / (len(rs) + 1))


def window(s, period):
    lo, hi = {"dev": DEV, "holdout": HOLD, "all": (DEV[0], HOLD[1])}[period]
    return s[(s.index >= pd.Period(lo, "Q")) & (s.index <= pd.Period(hi, "Q"))]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results"); ap.add_argument("--variant", default="R")
    ap.add_argument("--period", default="dev", choices=["dev", "holdout", "all"])
    ap.add_argument("--out")
    a = ap.parse_args()
    iq, im, cfg = load_index(a.results, a.variant)
    cfg = {k: v for k, v in cfg.items() if k in iq}
    pq, pm = load_production(cfg)
    iq = iq.reindex(pd.period_range("2019Q1", "2026Q3", freq="Q"))

    rows = []
    yoy_i, yoy_p = iq - iq.shift(4), np.log(pq / pq.shift(4)).reindex(iq.index)
    qoq_i, qoq_p = iq - iq.shift(1), np.log(pq / pq.shift(1)).reindex(iq.index)
    for k in cfg:
        r1 = corr(window(yoy_i[k], a.period), window(yoy_p[k], a.period))
        r2 = corr(window(qoq_i[k], a.period), window(qoq_p[k], a.period))
        rows.append(dict(mine=k, yoy_n=r1["n"], yoy_spearman=r1["spearman"], yoy_pearson=r1["pearson"],
                         yoy_sign_hit=r1["sign_hit"], qoq_n=r2["n"], qoq_spearman=r2["spearman"],
                         qoq_pearson=r2["pearson"]))
    per_mine = pd.DataFrame(rows).set_index("mine")

    # aggregate: weights = 2018 production share among covered mines, scale = development SD
    p2018 = pm.loc["2018-01":"2018-12", list(cfg)].sum()
    w = p2018 / p2018.sum()
    sd = window(yoy_i, "dev")[list(cfg)].std()
    z = yoy_i[list(cfg)] / sd
    avail = z.notna()
    agg = (z.fillna(0) * w).sum(axis=1) / (avail * w).sum(axis=1).replace(0, np.nan)   # renormalise if a mine is missing
    agg_p = np.log(pq[list(cfg)].sum(axis=1, min_count=len(cfg)) / pq[list(cfg)].sum(axis=1, min_count=len(cfg)).shift(4)).reindex(iq.index)
    chile_p = np.log(pq["_chile"] / pq["_chile"].shift(4)).reindex(iq.index)
    A, P, C = window(agg, a.period), window(agg_p, a.period), window(chile_p, a.period)
    aggr = {"covered mines": corr(A, P), "total Chile": corr(A, C)}
    for k, y in [("covered mines", P), ("total Chile", C)]:
        aggr[k]["shift_p"] = shift_p(A, y) if aggr[k]["n"] >= 10 else np.nan
    # QoQ aggregate
    zq = qoq_i[list(cfg)] / window(qoq_i, "dev")[list(cfg)].std()
    aggq = (zq.fillna(0) * w).sum(axis=1) / (zq.notna() * w).sum(axis=1).replace(0, np.nan)
    aggq_p = np.log(pq[list(cfg)].sum(axis=1, min_count=len(cfg)) / pq[list(cfg)].sum(axis=1, min_count=len(cfg)).shift(1)).reindex(iq.index)
    aggr["covered mines, QoQ"] = corr(window(aggq, a.period), window(aggq_p, a.period))

    # monthly aggregate YoY (secondary)
    im = im.reindex(pd.period_range("2019-01", "2026-09", freq="M"))
    myoy = im - im.shift(12)
    mz = myoy[list(cfg)] / myoy.loc[:"2024-12", list(cfg)].std()
    magg = (mz.fillna(0) * w).sum(axis=1) / (mz.notna() * w).sum(axis=1).replace(0, np.nan)
    mp = pm[list(cfg)].sum(axis=1, min_count=len(cfg))
    mpy = np.log(mp / mp.shift(12)).reindex(im.index)
    lo, hi = {"dev": ("2019-01", "2024-12"), "holdout": ("2025-01", "2026-07"), "all": ("2019-01", "2026-07")}[a.period]
    aggr["covered mines, monthly YoY"] = corr(magg[lo:hi], mpy[lo:hi])

    # secondary ground truth: material / ore mined
    sec = []
    bhp = pd.read_csv(HERE / "bhp_material_mined_quarterly.csv")
    ang = pd.read_csv(HERE / "anglo_ore_mined_quarterly.csv")
    for mine, src, col, key in [("escondida", bhp, "material_mined_kt", "Escondida"), ("spence", bhp, "material_mined_kt", "Spence"),
                                ("los_bronces", ang, "ore_mined_t", "Los Bronces"), ("collahuasi", ang, "ore_mined_t", "Collahuasi")]:
        if mine not in iq:
            continue
        g = src[src.mine == key].set_index("quarter")[col]
        g.index = pd.PeriodIndex(g.index, freq="Q")
        g = g.reindex(iq.index)
        r1 = corr(window(yoy_i[mine], a.period), window(np.log(g / g.shift(4)), a.period))
        r2 = corr(window(qoq_i[mine], a.period), window(np.log(g / g.shift(1)), a.period))
        sec.append(dict(mine=mine, measure=col, yoy_n=r1["n"], yoy_spearman=r1["spearman"], yoy_pearson=r1["pearson"],
                        qoq_n=r2["n"], qoq_spearman=r2["spearman"], qoq_pearson=r2["pearson"]))
    sec = pd.DataFrame(sec).set_index("mine")

    pd.set_option("display.width", 160)
    print(f"variant {a.variant}, period {a.period}")
    print("\nPer mine vs Cochilco copper production:\n", per_mine.round(2).to_string())
    print("\nAggregate:\n", pd.DataFrame(aggr).T.round(3).to_string())
    print("\nSecondary ground truth (material / ore mined):\n", sec.round(2).to_string())
    print("\nWeights (2018 production share):\n", w.round(3).to_string())
    if a.out:
        per_mine.round(3).to_csv(f"{a.out}_per_mine.csv")
        iq.round(3).to_csv(Path(a.results) / f"index_quarterly_{a.variant}.csv")
        im.round(3).to_csv(Path(a.results) / f"index_monthly_{a.variant}.csv")
        pq.round(3).to_csv(Path(a.results) / "production_quarterly_kt.csv")
        pd.DataFrame(aggr).T.round(4).to_csv(f"{a.out}_aggregate.csv")
        sec.round(3).to_csv(f"{a.out}_secondary.csv")
        pd.DataFrame({"agg_index_yoy": agg, "covered_prod_yoy_log": agg_p, "chile_prod_yoy_log": chile_p}).to_csv(f"{a.out}_aggregate_series.csv")


if __name__ == "__main__":
    main()
