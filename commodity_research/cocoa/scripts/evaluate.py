"""Run the pre-registered tests (README.md): (a1) season arrivals, (a2) ICCO revisions, (b) futures returns.

Also computes benchmark-quality statistics (ICCO first-forecast vs latest estimate).
Inputs: data/*.csv (prices, arrivals, ICCO vintages, feature_windows). Outputs: results/*.csv, results/summary.json.
Usage: python evaluate.py
"""
import json, os
import numpy as np, pandas as pd
import statsmodels.api as sm
from build_features import features_at, load_windows

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data"); RES = os.path.join(HERE, "..", "results")
HOLD = pd.Timestamp("2022-10-01"); TRAIN0 = pd.Timestamp("2003-10-01")
EX0, EX1 = pd.Timestamp("2023-10-01"), pd.Timestamp("2024-09-30")  # season 2023/24
COST = 0.0015
os.makedirs(RES, exist_ok=True)
OUT = {}


def feat(dates, W=None, zones=("ALL",)):
    """features_at() aligned to the given (possibly duplicated / unsorted) dates."""
    dates = pd.to_datetime(pd.Series(list(dates)))
    F = features_at(dates.drop_duplicates(), W, zones=zones).drop_duplicates("as_of").set_index("as_of")
    return F.reindex(dates.values).reset_index(drop=True)


def season_of(d):
    d = pd.Timestamp(d); y = d.year if d.month >= 10 else d.year - 1
    return f"{y}/{str(y + 1)[2:]}"


def ols(y, X, hac=0):
    m = sm.OLS(y, sm.add_constant(X, has_constant="add"), missing="drop")
    return m.fit(cov_type="HAC", cov_kwds={"maxlags": hac}) if hac else m.fit()


def arrivals():
    a = pd.read_csv(f"{DATA}/civ_arrivals_reported.csv", parse_dates=["as_of"])
    a["yoy"] = a.yoy_pct_reported.where(a.yoy_pct_reported.notna(), 100 * (a.cum_kt / a.prev_cum_kt - 1))
    a["known"] = a.as_of + pd.Timedelta(days=1)
    a["season"] = a.as_of.map(season_of)
    return a.dropna(subset=["yoy"])


# ---------------------------------------------------------------- benchmark quality
def benchmark_quality():
    w = pd.read_csv(f"{DATA}/icco_world_vintages.csv", parse_dates=["pub_date"]).dropna(subset=["world_production_kt"])
    rows = []
    for s, g in w.groupby("season"):
        g = g.sort_values("pub_date")
        if "first_forecast" not in set(g.stage):
            continue
        f = g[g.stage == "first_forecast"].iloc[0]; last = g.iloc[-1]
        rows.append(dict(level="world", season=s, first=f.world_production_kt, latest=last.world_production_kt, latest_pub=last.pub_date.date(),
                         err_pct=100 * (f.world_production_kt / last.world_production_kt - 1), n_vintages=len(g)))
    c = pd.read_csv(f"{DATA}/icco_country_vintages.csv", parse_dates=["pub_date"]).dropna(subset=["civ_kt"])
    for col, lab in [("civ_kt", "CIV"), ("gha_kt", "GHA")]:
        for s, g in c.groupby("season"):
            g = g.sort_values("pub_date")
            if "first_forecast" not in set(g.stage):
                continue
            f = g[g.stage == "first_forecast"].iloc[0]; last = g.iloc[-1]
            rows.append(dict(level=lab, season=s, first=f[col], latest=last[col], latest_pub=last.pub_date.date(),
                             err_pct=100 * (f[col] / last[col] - 1), n_vintages=len(g)))
    B = pd.DataFrame(rows); B.to_csv(f"{RES}/benchmark_first_vs_latest.csv", index=False, float_format="%.2f")
    B = B[B.n_vintages >= 2]
    summ = B.groupby("level").err_pct.agg(lambda x: np.mean(np.abs(x))).round(2).to_dict()
    OUT["benchmark_mean_abs_first_forecast_error_pct_since_2018_19"] = B[B.season >= "2018/19"].groupby("level").err_pct.agg(lambda x: np.mean(np.abs(x))).round(2).to_dict()
    OUT["benchmark_mean_abs_first_forecast_error_pct"] = summ
    OUT["benchmark_n_seasons"] = B.groupby("level").size().to_dict()
    print("ICCO first forecast vs latest estimate, mean |error| %:", summ)
    return B


# ---------------------------------------------------------------- test a1
def test_a1(W):
    a = arrivals(); rows = []
    for s in sorted(a.season.unique()):
        y0 = int(s[:4])
        rec = dict(season=s)
        for name, chk, lo, hi in [("MC_yoy", f"{y0+1}-03-31", f"{y0+1}-03-10", f"{y0+1}-04-30"),
                                  ("SEAS_yoy", f"{y0+1}-09-30", f"{y0+1}-08-15", f"{y0+1}-10-10")]:
            g = a[(a.as_of >= lo) & (a.as_of <= hi)]
            if len(g):
                k = (g.as_of - pd.Timestamp(chk)).abs().idxmin(); rec[name] = g.loc[k, "yoy"]; rec[name + "_date"] = g.loc[k, "as_of"].date()
        rows.append(rec)
    T = pd.DataFrame(rows)
    T["MID_delta"] = T.SEAS_yoy - T.MC_yoy
    T["y0"] = T.season.str[:4].astype(int)
    Foct = feat([f"{y}-10-15" for y in T.y0], W).set_index(T.index)
    Fmar = feat([f"{y+1}-03-31" for y in T.y0], W).set_index(T.index)
    for c in ["DRY", "WETX", "rain_6m_z", "rain_3m_z", "soil_3m_z", "tmax_3m_z", "rh_3m_z", "evi_3m_z"]:
        T[c + "_oct"] = Foct[c].values; T[c + "_mar"] = Fmar[c].values
    T["holdout"] = T.y0 >= 2022
    res = []
    for tgt, suf in [("MC_yoy", "_oct"), ("SEAS_yoy", "_oct"), ("MID_delta", "_mar")]:
        d = T.dropna(subset=[tgt]); tr = d[(~d.holdout) & (d.y0 >= 2003)]; ho = d[d.holdout]
        X = [f"DRY{suf}", f"WETX{suf}"]
        m = ols(tr[tgt], tr[X])
        pred = m.predict(sm.add_constant(ho[X], has_constant="add"))
        naive = tr[tgt].mean()
        for excl in (False, True):
            h = ho[ho.season != "2023/24"] if excl else ho; p = pred.loc[h.index]
            res.append(dict(target=tgt, excl_2023_24=excl, n_train=len(tr), n_hold=len(h), b_DRY=m.params[X[0]], t_DRY=m.tvalues[X[0]],
                            b_WETX=m.params[X[1]], t_WETX=m.tvalues[X[1]], r2_train=m.rsquared,
                            mae_model=np.mean(np.abs(h[tgt] - p)) if len(h) else np.nan, mae_naive=np.mean(np.abs(h[tgt] - naive)) if len(h) else np.nan,
                            sign_hits=int(np.sum(np.sign(p - 0) == np.sign(h[tgt]))) if len(h) else 0,
                            hold_detail="; ".join(f"{s}: actual {v:+.1f} pred {q:+.1f}" for s, v, q in zip(h.season, h[tgt], p))))
            if not excl:
                T.loc[ho.index, tgt + "_pred"] = pred
    R = pd.DataFrame(res); R.to_csv(f"{RES}/test_a1_season_arrivals.csv", index=False, float_format="%.3f")
    T.to_csv(f"{RES}/test_a1_sample.csv", index=False, float_format="%.3f")
    print(R.drop(columns="hold_detail").to_string()); print(R[~R.excl_2023_24][["target", "hold_detail"]].to_string())
    OUT["test_a1"] = R.to_dict(orient="records")
    return T


# ---------------------------------------------------------------- test a2
def test_a2(W):
    w = pd.read_csv(f"{DATA}/icco_world_vintages.csv", parse_dates=["pub_date"]).dropna(subset=["world_production_kt"])
    rows = []
    for s, g in w.groupby("season"):
        g = g.sort_values("pub_date").reset_index(drop=True)
        for i in range(len(g) - 1):
            rev_next = 100 * (g.world_production_kt[i + 1] / g.world_production_kt[i] - 1)
            rev_prev = 100 * (g.world_production_kt[i] / g.world_production_kt[i - 1] - 1) if i > 0 else 0.0
            rows.append(dict(season=s, pub=g.pub_date[i], next_pub=g.pub_date[i + 1], stage=g.stage[i], rev_prev=rev_prev, rev_next=rev_next))
    D = pd.DataFrame(rows)
    D = D[D.pub >= "2007-01-01"]
    F = feat(D.pub, W).set_index(D.index)
    D["DRY"] = F.DRY.values; D["WETX"] = F.WETX.values
    D["holdout"] = D.pub >= HOLD
    tr = D[~D.holdout].dropna(subset=["DRY"]); ho = D[D.holdout]
    mF = ols(tr.rev_next, tr[["rev_prev", "DRY", "WETX"]]); mP = ols(tr.rev_next, tr[["rev_prev"]])
    pF = mF.predict(sm.add_constant(ho[["rev_prev", "DRY", "WETX"]], has_constant="add")); pP = mP.predict(sm.add_constant(ho[["rev_prev"]], has_constant="add"))
    res = []
    for excl in (False, True):
        h = ho[ho.season != "2023/24"] if excl else ho
        res.append(dict(excl_2023_24=excl, n_train=len(tr), n_hold=len(h), b_rev_prev=mF.params.rev_prev, b_DRY=mF.params.DRY, t_DRY=mF.tvalues.DRY,
                        b_WETX=mF.params.WETX, t_WETX=mF.tvalues.WETX, mae_full=np.mean(np.abs(h.rev_next - pF.loc[h.index])),
                        mae_persist=np.mean(np.abs(h.rev_next - pP.loc[h.index])), mae_zero=np.mean(np.abs(h.rev_next)),
                        corr_DRY_rev_hold=h[["DRY", "rev_next"]].corr().iloc[0, 1]))
    D.loc[ho.index, "pred_full"] = pF; D.loc[ho.index, "pred_persist"] = pP
    D.to_csv(f"{RES}/test_a2_sample.csv", index=False, float_format="%.3f")
    R = pd.DataFrame(res); R.to_csv(f"{RES}/test_a2_icco_revisions.csv", index=False, float_format="%.3f")
    print(R.to_string()); print(mF.summary().tables[1])
    OUT["test_a2"] = R.to_dict(orient="records")
    # descriptive: country revisions
    c = pd.read_csv(f"{DATA}/icco_country_vintages.csv", parse_dates=["pub_date"]).dropna(subset=["civ_kt"])
    cr = []
    for s, g in c.groupby("season"):
        g = g.sort_values("pub_date").reset_index(drop=True)
        for i in range(len(g) - 1):
            cr.append(dict(season=s, pub=g.pub_date[i], civ_rev=100 * (g.civ_kt[i + 1] / g.civ_kt[i] - 1), gha_rev=100 * (g.gha_kt[i + 1] / g.gha_kt[i] - 1)))
    C = pd.DataFrame(cr); Fc = feat(C.pub, W).set_index(C.index)
    C["DRY"] = Fc.DRY.values; C["WETX"] = Fc.WETX.values
    C.to_csv(f"{RES}/country_revisions_descriptive.csv", index=False, float_format="%.3f")
    OUT["country_rev_corr_DRY"] = {"civ": C[["DRY", "civ_rev"]].corr().iloc[0, 1], "gha": C[["DRY", "gha_rev"]].corr().iloc[0, 1], "n": len(C)}
    return D


# ---------------------------------------------------------------- test b
def monthly_panel():
    p = pd.read_csv(f"{DATA}/prices_cc.csv", parse_dates=["date"]).set_index("date").close
    me = p.groupby(p.index.to_period("M")).apply(lambda s: s.index[-1])
    P = pd.DataFrame({"t": me.values, "px": p.loc[me.values].values})
    P["lp"] = np.log(P.px)
    for h in (1, 2, 3):
        P[f"r{h}"] = P.lp.shift(-h) - P.lp
    P["r_3m"] = P.lp - P.lp.shift(3); P["r_12m"] = P.lp - P.lp.shift(12)
    a = arrivals().sort_values("known")
    j = pd.merge_asof(P[["t"]], a[["known", "yoy", "season"]], left_on="t", right_on="known", direction="backward")
    fresh = ((j.t - j.known).dt.days <= 60) & (j.season == j.t.map(season_of))
    P["arr_yoy"] = np.where(fresh, j.yoy, 0.0); P["arr_missing"] = (~fresh).astype(float)
    F = feat(P.t).set_index(P.index)
    for c in ["DRY", "WETX", "rain_6m_z", "rain_3m_z", "soil_3m_z", "tmax_3m_z", "rh_3m_z", "evi_3m_z"]:
        P[c] = F[c].values
    P["WETX"] = P["WETX"].fillna(0.0)  # no rain window available (CHIRPS posting delay) -> no excess-rain signal
    # post-hoc sensitivity (NOT pre-registered): DRY without EVI (Aqua drift / 2025 gap)
    P["DRY_noevi"] = pd.concat([F.rain_6m_z, F.soil_3m_z, F.rh_3m_z, -F.tmax_3m_z], axis=1).mean(axis=1).values
    return P


def strat(pos, r):
    turn = np.abs(np.diff(np.r_[0, pos]))
    net = pos * r - COST * turn
    return net


def test_b():
    P = monthly_panel(); P.to_csv(f"{RES}/test_b_panel.csv", index=False, float_format="%.5f", date_format="%Y-%m-%d")
    B1 = ["r_3m", "r_12m", "arr_yoy", "arr_missing"]; B2 = B1 + ["DRY", "WETX"]
    res = []; strat_rows = []
    for dry_col, tag in [("DRY", "prereg"), ("DRY_noevi", "posthoc_noevi")]:
        b2 = B1 + [dry_col, "WETX"]
        for h in (1, 2, 3):
            d = P.dropna(subset=[f"r{h}"] + B1 + [dry_col])
            tr = d[(d.t >= TRAIN0) & (d.t < HOLD)]; ho = d[d.t >= HOLD]
            m1 = ols(tr[f"r{h}"], tr[B1], hac=h); m2 = ols(tr[f"r{h}"], tr[b2], hac=h)
            p1 = m1.predict(sm.add_constant(ho[B1], has_constant="add")); p2 = m2.predict(sm.add_constant(ho[b2], has_constant="add"))
            # expanding refit (secondary)
            pe1, pe2 = [], []
            for i, r in ho.iterrows():
                trx = d[(d.t >= TRAIN0) & (d.t + pd.DateOffset(months=h) <= r.t)]
                e1 = ols(trx[f"r{h}"], trx[B1]); e2 = ols(trx[f"r{h}"], trx[b2])
                pe1.append(e1.predict(sm.add_constant(ho.loc[[i], B1], has_constant="add")).iloc[0])
                pe2.append(e2.predict(sm.add_constant(ho.loc[[i], b2], has_constant="add")).iloc[0])
            pe1 = pd.Series(pe1, index=ho.index); pe2 = pd.Series(pe2, index=ho.index)
            for excl in (False, True):
                k = ~((ho.t >= EX0) & (ho.t <= EX1)) if excl else np.ones(len(ho), bool)
                y = ho[f"r{h}"][k]
                sse = lambda p: np.sum((y - p[k]) ** 2)
                rec = dict(variant=tag, h=h, excl_2023_24=excl, n_train=len(tr), n_hold=int(k.sum()),
                           b_DRY=m2.params[dry_col], t_DRY=m2.tvalues[dry_col], b_WETX=m2.params.WETX, t_WETX=m2.tvalues.WETX,
                           r2_train_B1=m1.rsquared, r2_train_B2=m2.rsquared,
                           oos_r2_B2_vs_B1=1 - sse(p2) / sse(p1), oos_r2_B1_vs_zero=1 - np.sum((y - p1[k]) ** 2) / np.sum(y ** 2),
                           oos_r2_B2_vs_B1_expanding=1 - sse(pe2) / sse(pe1))
                if h == 1:
                    for lab, pr in [("B1", p1), ("B2", p2), ("B2exp", pe2), ("B1exp", pe1)]:
                        net = strat(np.sign(pr.values), ho.r1.values)[k.values if hasattr(k, "values") else k]
                        rec[f"{lab}_net_mean_pct"] = 100 * net.mean(); rec[f"{lab}_net_sharpe"] = net.mean() / net.std() * np.sqrt(12)
                        rec[f"{lab}_hit"] = np.mean(np.sign(pr.values)[k.values if hasattr(k, "values") else k] == np.sign(y.values))
                    diff = (strat(np.sign(p2.values), ho.r1.values) - strat(np.sign(p1.values), ho.r1.values))[k.values if hasattr(k, "values") else k]
                    rec["diff_B2_B1_mean_pct"] = 100 * diff.mean(); rec["diff_t"] = diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff))) if diff.std() > 0 else np.nan
                    rec["buyhold_mean_pct"] = 100 * y.mean()
                    if not excl and tag == "prereg":
                        strat_rows = pd.DataFrame({"t": ho.t, "r1": ho.r1, "pred_B1": p1, "pred_B2": p2, "pos_B1": np.sign(p1), "pos_B2": np.sign(p2),
                                                   "net_B1": strat(np.sign(p1.values), ho.r1.values), "net_B2": strat(np.sign(p2.values), ho.r1.values)})
                res.append(rec)
    R = pd.DataFrame(res); R.to_csv(f"{RES}/test_b_returns.csv", index=False, float_format="%.4f")
    strat_rows.to_csv(f"{RES}/test_b_holdout_positions.csv", index=False, float_format="%.5f", date_format="%Y-%m-%d")
    cols = ["variant", "h", "excl_2023_24", "n_hold", "b_DRY", "t_DRY", "b_WETX", "t_WETX", "oos_r2_B2_vs_B1", "oos_r2_B2_vs_B1_expanding", "oos_r2_B1_vs_zero"]
    print(R[cols].to_string())
    print(R[R.h == 1][["variant", "excl_2023_24", "B1_net_mean_pct", "B2_net_mean_pct", "B2_net_sharpe", "B2_hit", "diff_B2_B1_mean_pct", "diff_t", "buyhold_mean_pct"]].to_string())
    # descriptive univariate correlations
    U = []
    for c in ["DRY", "WETX", "rain_6m_z", "rain_3m_z", "soil_3m_z", "tmax_3m_z", "rh_3m_z", "evi_3m_z", "arr_yoy", "r_3m"]:
        for lab, sub in [("train", P[(P.t >= TRAIN0) & (P.t < HOLD)]), ("holdout", P[P.t >= HOLD])]:
            U.append(dict(feature=c, sample=lab, corr_r1=sub[[c, "r1"]].corr().iloc[0, 1], corr_r3=sub[[c, "r3"]].corr().iloc[0, 1], n=sub[c].notna().sum()))
    pd.DataFrame(U).to_csv(f"{RES}/test_b_univariate_corr.csv", index=False, float_format="%.3f")
    OUT["test_b"] = R.to_dict(orient="records")
    return P, R


def main():
    W = load_windows()
    benchmark_quality(); print()
    test_a1(W); print()
    test_a2(W); print()
    test_b()
    json.dump(OUT, open(f"{RES}/summary.json", "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
