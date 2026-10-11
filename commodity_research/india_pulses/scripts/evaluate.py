"""Pre-registered evaluation: (a) GoI revision test, (b) price tests. See README "Pre-registration".

(a) Revision test. Rows = every GoI advance estimate (AE1..AE4) of tur, gram, sugarcane with a public
    FINAL. y = log(FINAL / AE), gap = log(sat_pred / AE) with sat_pred computed the day before the AE
    release. Primary sample: each crop's first estimate (tur, cane: AE1; gram: AE2). Pooled OLS with crop
    intercepts, season-clustered s.e. Holdout: slope frozen from development; MAE of log(AE) vs
    log(AE)+b*gap against the final, and sign hit rate of gap vs y.
(b) Price tests. Targets: WPI Gram (gram), WPI Arhar (tur), ICE raw sugar SB=F roll-adjusted (sugarcane).
    As-of = month-ends in the crop window (signal asof_kind == month_end). Horizons h = 1, 2, 3 months.
    Baseline y ~ official_anom(0 if none) + momentum; full adds sat_anom. Walk-forward by season (fit on
    seasons < Y, >= 5 seasons). Metrics: out-of-sample R^2 vs the training mean, Delta R^2 (full-base),
    and an incremental trade: position = sign(yhat_full - yhat_base) for SB=F (cost 0.15% round trip);
    long-only for WPI (long if yhat_full > yhat_base; cost 2% + 1%/month carry), since physical pulses can't be
    shorted and NCDEX pulse futures are suspended.

Usage: python evaluate.py --mode dev|final [--data ../data --signal ../signal --out ../results]
"""
import argparse, json
import numpy as np, pandas as pd
import statsmodels.api as sm

HOLDOUT_FIRST = 2023
FIRST_STAGE = {"tur": "AE1", "sugarcane": "AE1", "gram": "AE2"}
PRICE = {"gram": ("wpi_gram", "monthly"), "tur": ("wpi_arhar", "monthly"), "sugarcane": ("sugar_tr", "daily")}
COST = {"monthly": dict(fixed=0.02, carry=0.01), "daily": dict(fixed=0.0015, carry=0.0)}


def load_signal(a):
    s = pd.read_csv(f"{a.signal}/india_signal_v1{'_dev' if a.mode == 'dev' else ''}.csv", parse_dates=["asof"])
    return s


def revision_test(a, s):
    v = pd.read_csv(f"{a.data}/ae_vintages.csv")
    fin = v[v.stage == "FINAL"].set_index(["crop", "season"]).value
    r = s[s.asof_kind.str.startswith("pre_AE")].copy()
    r["stage"] = r.asof_kind.str[4:]
    ae = v[v.stage.str.startswith("AE")].set_index(["crop", "season", "stage"]).value
    r["ae"] = [ae.get((c, se, st), np.nan) for c, se, st in zip(r.crop, r.season, r.stage)]
    r["final"] = [fin.get((c, se), np.nan) for c, se in zip(r.crop, r.season)]
    r = r.dropna(subset=["ae", "final", "sat_pred"])
    r["y"] = np.log(r.final / r.ae); r["gap"] = np.log(r.sat_pred / r.ae)
    r["first"] = [FIRST_STAGE[c] == st for c, st in zip(r.crop, r.stage)]
    r["period"] = np.where(r.Y >= HOLDOUT_FIRST, "holdout", "dev")
    out = {}
    for name, sub in [("first_stage", r[r["first"]]), ("all_stages", r)]:
        dv = sub[sub.period == "dev"]
        X = pd.get_dummies(dv.crop, dtype=float); X["gap"] = dv.gap
        m = sm.OLS(dv.y, X).fit(cov_type="cluster", cov_kwds={"groups": dv.Y})
        res = dict(n_dev=len(dv), b_gap=m.params["gap"], t_gap=m.tvalues["gap"], spearman_dev=dv[["gap", "y"]].corr("spearman").iloc[0, 1],
                   hit_dev=float(np.mean(np.sign(dv.gap) == np.sign(dv.y))))
        ho = sub[sub.period == "holdout"]
        if len(ho):
            b = m.params["gap"]
            res.update(n_hold=len(ho), hit_hold=float(np.mean(np.sign(ho.gap) == np.sign(ho.y))),
                       mae_ae_hold=float(np.mean(np.abs(ho.y))), mae_adj_hold=float(np.mean(np.abs(ho.y - b * ho.gap))),
                       spearman_hold=ho[["gap", "y"]].corr("spearman").iloc[0, 1])
        out[name] = res
    r.to_csv(f"{a.out}/revision_test_rows_{a.mode}.csv", index=False, float_format="%.4f")
    return out, r


def price_frame(a, s, crop):
    col, freq = PRICE[crop]
    sig = s[(s.crop == crop) & (s.asof_kind == "month_end")].copy()
    if freq == "monthly":
        P = pd.read_csv(f"{a.data}/prices_monthly.csv", parse_dates=["month"]).set_index("month")[col]
        lp = np.log(P)
        m = sig["asof"].dt.to_period("M").dt.to_timestamp()
        sig["mom"] = [lp.get(x - pd.DateOffset(months=1), np.nan) - lp.get(x - pd.DateOffset(months=4), np.nan) for x in m]
        for h in (1, 2, 3):
            sig[f"y{h}"] = [lp.get(x + pd.DateOffset(months=h), np.nan) - lp.get(x, np.nan) for x in m]
    else:
        D = pd.read_csv(f"{a.data}/prices_daily.csv", parse_dates=["date"]).set_index("date")[col].dropna()
        lp = np.log(D); idx = lp.index
        pos = idx.searchsorted(sig["asof"].values, side="right") - 1
        sig["mom"] = [lp.iloc[p] - lp.iloc[p - 63] if p >= 63 else np.nan for p in pos]
        for h in (1, 2, 3):
            sig[f"y{h}"] = [lp.iloc[p + 21 * h] - lp.iloc[p] if p + 21 * h < len(lp) else np.nan for p in pos]
    sig["off"] = sig.official_anom.fillna(0.0)
    return sig, freq


def walk_forward(df, h, freq):
    rows = []
    for Y in sorted(df.Y.unique()):
        tr = df[(df.Y < Y)].dropna(subset=[f"y{h}", "sat_anom", "mom"])
        te = df[(df.Y == Y)].dropna(subset=[f"y{h}", "sat_anom", "mom"])
        if tr.Y.nunique() < 5 or not len(te):
            continue
        yb = sm.OLS(tr[f"y{h}"], sm.add_constant(tr[["off", "mom"]])).fit()
        yf = sm.OLS(tr[f"y{h}"], sm.add_constant(tr[["sat_anom", "off", "mom"]])).fit()
        pb = yb.predict(sm.add_constant(te[["off", "mom"]], has_constant="add"))
        pf = yf.predict(sm.add_constant(te[["sat_anom", "off", "mom"]], has_constant="add"))
        for i, r in te.iterrows():
            rows.append(dict(Y=Y, asof=r["asof"], y=r[f"y{h}"], ybar=tr[f"y{h}"].mean(), pb=pb[i], pf=pf[i], b_sat=yf.params["sat_anom"]))
    o = pd.DataFrame(rows)
    if not len(o):
        return o
    c = COST[freq]
    inc = o.pf - o.pb
    if freq == "daily":
        o["pos"] = np.sign(inc); o["pnl"] = o.pos * o.y - c["fixed"] * (o.pos != 0)
    else:
        o["pos"] = (inc > 0).astype(float); o["pnl"] = o.pos * (o.y - c["fixed"] - c["carry"] * h)
    return o


def summarise(o):
    if not len(o):
        return {}
    sse = lambda p: float(((o.y - p) ** 2).sum())
    sst = sse(o.ybar)
    tr = o[o.pos != 0]
    return dict(n=len(o), r2_base=1 - sse(o.pb) / sst, r2_full=1 - sse(o.pf) / sst, d_r2=(sse(o.pb) - sse(o.pf)) / sst,
                n_trades=len(tr), hit=float(np.mean(np.sign(tr.y) == np.sign(tr.pos))) if len(tr) else np.nan,
                mean_pnl=float(tr.pnl.mean()) if len(tr) else np.nan, sum_pnl=float(o.pnl.sum()), b_sat_last=float(o.b_sat.iloc[-1]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["dev", "final"], required=True)
    ap.add_argument("--data", default="../data")
    ap.add_argument("--signal", default="../signal")
    ap.add_argument("--out", default="../results")
    a = ap.parse_args()
    s = load_signal(a)
    rev, _ = revision_test(a, s)
    res = {"revision": rev, "price": {}}
    prow = []
    for crop in PRICE:
        df, freq = price_frame(a, s, crop)
        for h in (1, 2, 3):
            o = walk_forward(df, h, freq)
            if not len(o):
                continue
            o["crop"] = crop; o["h"] = h
            o["period"] = np.where(o.Y >= 2024, "holdout", np.where(o.Y == 2023, "extra_2022_23", "dev"))
            prow.append(o)
            for per in ["dev", "holdout", "extra_2022_23"]:
                res["price"][f"{crop}_h{h}_{per}"] = summarise(o[o.period == per])
    if prow:
        pd.concat(prow).to_csv(f"{a.out}/price_test_rows_{a.mode}.csv", index=False, float_format="%.5f")
    json.dump(res, open(f"{a.out}/results_{a.mode}.json", "w"), indent=1, default=float)
    print(json.dumps(res, indent=1, default=lambda x: round(float(x), 4)))


if __name__ == "__main__":
    main()
