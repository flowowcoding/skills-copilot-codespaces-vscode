"""Tests 2-4 (pre-registered in README): output tracking, China vs NBS, markets.

Test 2  Kennecott quarterly concentrate smelted (Rio Tinto) vs quarterly active share / intensity.
Test 3  China capacity-weighted active share (3-month mean, YoY change) vs NBS refined copper YoY.
Test 4  Global index 3-month change vs next-month COMEX copper (HG=F) return; threshold rule.

Usage:
    python evaluate_output.py [--index data/index] [--out results]
Development / holdout split: quarters to 2024Q4 / 2025Q1-2026Q2; months to 2024-12 / 2025-01 on.
"""
import argparse, json, os
import numpy as np
import pandas as pd
from scipy.stats import spearmanr, pearsonr

HERE = os.path.dirname(os.path.abspath(__file__))
HOLD_Q, HOLD_M = "2025Q1", "2025-01"


def circ_perm_p(x, y, n_min=6):
    """One-sided p for Spearman >= observed under circular shifts of y (keeps autocorrelation)."""
    x, y = np.asarray(x), np.asarray(y)
    obs = spearmanr(x, y)[0]
    sh = [spearmanr(x, np.roll(y, k))[0] for k in range(n_min, len(y) - n_min)]
    return float((np.sum(np.array(sh) >= obs) + 1) / (len(sh) + 1)) if sh else float("nan")


def corr_block(df, xcol, ycol, split_col, split_val):
    out = {}
    for name, d in {"dev": df[df[split_col] < split_val], "holdout": df[df[split_col] >= split_val], "all": df}.items():
        d = d[[xcol, ycol]].dropna()
        if len(d) >= 4:
            out[name] = dict(n=len(d), spearman=round(spearmanr(d[xcol], d[ycol])[0], 3), pearson=round(pearsonr(d[xcol], d[ycol])[0], 3),
                             sign_agree=round(float((np.sign(d[xcol]) == np.sign(d[ycol])).mean()), 2))
            if name == "dev" and len(d) >= 15:
                out[name]["circ_perm_p"] = round(circ_perm_p(d[xcol].values, d[ycol].values), 3)
        else:
            out[name] = dict(n=len(d))
    return out


def weighted_index(monthly, smelters, ids):
    """Capacity-weighted active share; missing smelter-month -> own 2017-2024 calendar-month mean."""
    m = monthly[monthly.smelter.isin(ids)].pivot(index="month", columns="smelter", values="active_share")
    allm = pd.period_range("2017-01", m.index.max(), freq="M").astype(str)
    m = m.reindex(allm)
    cal = m.index.str[5:7]
    dev = m[m.index <= "2024-12"]
    clim = dev.groupby(dev.index.str[5:7]).mean()
    filled = m.copy()
    for c in m.columns:
        filled[c] = m[c].fillna(pd.Series(cal, index=m.index).map(clim[c]))
    w = smelters.set_index("id").approx_capacity_kt_cu.reindex(m.columns).astype(float)
    idx_ = (filled * w).sum(axis=1) / w.sum()
    coverage = (m.notna() * w).sum(axis=1) / w.sum()
    out = pd.DataFrame({"index": idx_, "observed_capacity_share": coverage})
    out.index.name = "month"
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", default=os.path.join(HERE, "data", "index"))
    ap.add_argument("--out", default=os.path.join(HERE, "results"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    res = {}
    sm = pd.read_csv(os.path.join(HERE, "smelters.csv"))
    monthly = pd.read_csv(os.path.join(a.index, "monthly.csv"))

    # ---- Test 2: Kennecott
    sc = pd.read_csv(os.path.join(a.index, "kennecott_scenes.csv"))
    sc = sc[sc.valid]
    sc["quarter"] = pd.PeriodIndex(sc.date, freq="Q").astype(str)
    q = sc.groupby("quarter").agg(n_valid=("active", "size"), active_share=("active", "mean"), intensity=("n_mask_hot", "mean")).reset_index()
    rep = pd.read_csv(os.path.join(HERE, "data", "reported", "kennecott_quarterly.csv"))
    kq = rep.merge(q, on="quarter", how="inner")
    kq = kq[kq.quarter >= "2017Q1"]
    kq.to_csv(os.path.join(a.out, "kennecott_quarterly_vs_index.csv"), index=False)
    res["kennecott_level"] = {x: corr_block(kq, x, "conc_smelted_kt", "quarter", HOLD_Q) for x in ["active_share", "intensity"]}

    # ---- Test 3: China vs NBS
    cn = sm[sm.country == "China"].id.tolist()
    ci = weighted_index(monthly, sm, cn)
    ci["idx3"] = ci["index"].rolling(3).mean()
    ci["yoy_pts"] = ci.idx3 - ci.idx3.shift(12)
    ci["mom_pts"] = ci["index"] - ci["index"].shift(1)
    nbs = pd.read_csv(os.path.join(HERE, "data", "china_nbs_refined_copper_monthly.csv")).set_index("month")
    ci = ci.join(nbs[["kt", "yoy_pct"]], how="left")
    ci["nbs_mom_pct"] = 100 * (ci.kt / ci.kt.shift(1) - 1)
    ci = ci.reset_index()
    ci.to_csv(os.path.join(a.out, "china_index_vs_nbs.csv"), index=False)
    res["china_yoy"] = corr_block(ci, "yoy_pts", "yoy_pct", "month", HOLD_M)
    res["china_mom"] = corr_block(ci, "mom_pts", "nbs_mom_pct", "month", HOLD_M)
    res["china_observed_capacity_share_mean"] = round(float(ci.observed_capacity_share.mean()), 2)
    # exploratory (post hoc, not pre-registered): intensity instead of active share, because the
    # active share of the big Chinese smelters sits at 1.0 almost every month (no variance)
    mi = monthly.copy()
    devmean = mi[mi.month <= "2024-12"].groupby("smelter").intensity.mean()
    mi["active_share"] = mi.intensity / mi.smelter.map(devmean)
    cii = weighted_index(mi, sm, cn)
    cii["idx3"] = cii["index"].rolling(3).mean(); cii["yoy_pts"] = cii.idx3 / cii.idx3.shift(12) - 1
    cii = cii.join(nbs[["yoy_pct"]], how="left").reset_index()
    res["china_intensity_yoy_exploratory"] = corr_block(cii, "yoy_pts", "yoy_pct", "month", HOLD_M)
    # exploratory: does the index lead NBS YoY by k months?
    lead = {}
    for k in [1, 2, 3]:
        d = ci.assign(x=ci.yoy_pts.shift(k))
        lead[f"index_leads_by_{k}m"] = corr_block(d, "x", "yoy_pct", "month", HOLD_M)
    res["china_yoy_lead_exploratory"] = lead

    # ---- secondary: Sentinel-3 SLSTR night detections (monthly share of night granules with a detection)
    frp_rows = []
    for sid in sm.id:
        f = os.path.join(HERE, "data", "s3frp", f"{sid}.csv")
        if os.path.exists(f):
            fr = pd.read_csv(f)
            if len(fr):
                fr["month"] = fr.datetime.str[:7]
                g = fr.groupby("month").agg(n_valid=("n_fire", "size"), active_share=("n_fire", lambda x: float((x > 0).mean())))
                g = g[g.n_valid >= 5].reset_index(); g.insert(0, "smelter", sid); frp_rows.append(g)
    if frp_rows:
        fm = pd.concat(frp_rows)
        fm.to_csv(os.path.join(a.out, "s3frp_monthly.csv"), index=False)
        cnf = [c for c in cn if c in set(fm.smelter)]
        fpiv = fm[fm.smelter.isin(cnf)].pivot(index="month", columns="smelter", values="active_share")
        w = sm.set_index("id").approx_capacity_kt_cu.reindex(fpiv.columns).astype(float)
        fidx = (fpiv.fillna(fpiv.mean()) * w).sum(axis=1) / w.sum()
    if frp_rows and len(fidx):
        res["china_frp_smelters"] = cnf
        fc = pd.DataFrame({"frp_index": fidx}).reindex(pd.period_range(fidx.index.min(), fidx.index.max(), freq="M").astype(str))
        fc["idx3"] = fc.frp_index.rolling(3).mean(); fc["yoy_pts"] = fc.idx3 - fc.idx3.shift(12)
        fc.index.name = "month"
        fc = fc.join(nbs[["yoy_pct"]], how="left").reset_index()
        fc.to_csv(os.path.join(a.out, "china_frp_index_vs_nbs.csv"), index=False)
        res["china_frp_yoy"] = corr_block(fc, "yoy_pts", "yoy_pct", "month", HOLD_M)
        # Kennecott quarterly night detections vs concentrate smelted
        if "kennecott" in set(fm.smelter):
            kf = pd.read_csv(os.path.join(HERE, "data", "s3frp", "kennecott.csv"))
            kf["quarter"] = pd.PeriodIndex(kf.datetime.str[:10], freq="Q").astype(str)
            kfq = kf.groupby("quarter").n_fire.apply(lambda x: float((x > 0).mean())).rename("frp_share").reset_index()
            kk = rep.merge(kfq, on="quarter")
            res["kennecott_frp_level"] = corr_block(kk, "frp_share", "conc_smelted_kt", "quarter", HOLD_Q)

    # ---- Test 4: global index vs copper
    gi = weighted_index(monthly, sm, sm.id.tolist())
    gi["chg3"] = gi["index"] - gi["index"].shift(3)
    px = pd.read_csv(os.path.join(HERE, "data", "market", "hg_f_daily.csv"))
    px["month"] = px.date.str[:7]
    # tradeable return for month m+1: from the close of the 3rd trading day of m+1 to the last close of m+1
    g = px.groupby("month")
    entry = g.close.apply(lambda s: s.iloc[min(2, len(s) - 1)]); exit_ = g.close.last()
    ret_next = (exit_ / entry - 1).shift(-1)       # aligned to signal month m
    gi = gi.join(ret_next.rename("hg_ret_next"), how="left").reset_index()
    sd = gi[gi.month <= "2024-12"].chg3.std()
    gi["pos"] = np.where(gi.chg3 < -sd, 1, np.where(gi.chg3 > sd, -1, 0))
    gi["trade_ret"] = gi.pos * gi.hg_ret_next - (gi.pos != 0) * 0.001
    gi.to_csv(os.path.join(a.out, "global_index_vs_copper.csv"), index=False)
    res["global_chg3_vs_next_month_hg"] = corr_block(gi, "chg3", "hg_ret_next", "month", HOLD_M)
    rule = {}
    for name, d in {"dev": gi[gi.month < HOLD_M], "holdout": gi[gi.month >= HOLD_M]}.items():
        t = d[(d.pos != 0) & d.hg_ret_next.notna()]
        rule[name] = dict(n_trades=len(t), hit_rate=round(float((t.trade_ret > 0).mean()), 2) if len(t) else None,
                          mean_net_ret_pct=round(100 * t.trade_ret.mean(), 2) if len(t) else None,
                          months=int(d.hg_ret_next.notna().sum()))
    res["global_rule"] = rule
    tc = pd.read_csv(os.path.join(HERE, "data", "market", "tc_benchmarks.csv"))
    ann = gi.assign(year=gi.month.str[:4].astype(int)).groupby("year")["index"].mean()
    tcj = tc.set_index("year").join(ann.rename("global_index_mean"))
    res["tc_vs_index_descriptive"] = tcj.reset_index().round(3).to_dict("records")
    json.dump(res, open(os.path.join(a.out, "output_tests.json"), "w"), indent=1, default=str)
    print(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
