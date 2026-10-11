"""Walk-forward county yield model (field-level Landsat/Sentinel-2 phenology + county weather), aggregated to
Iowa, Illinois, IA+IL and a US proxy. Writes the signal file; evaluation is in evaluate.py.

Unit: county x year, separately per crop (corn for grain, soybeans) and report (aug, sep).
Target: d = ln(county yield / county trend). Trend: Theil-Sen line through the state's January finals Y-20..Y-1,
        times the county's median ratio to the state final over Y-10..Y-1 (>= 5 years required).
Features at the forecast date (features/county_vi.csv, features/county_weather.csv), each expressed as the
        county's deviation from its own mean over the training years (weather: training years from 2005; VI:
        from 2013), then z-scored on the training rows.
Models (training rows: all county-years 2013..Y-1 with a NASS county yield; county yields of Y-1 are public in
        February of Y):
  ridge  (primary)  ridge regression, alpha chosen by leave-one-year-out CV inside the training years from
                    {1, 3, 10, 30, 100, 300} (rows standardised, unpenalised intercept)
  gbm               LightGBM (300 trees, learning rate 0.03, 8 leaves, min 20 rows per leaf, fixed)
  wx                ridge on weather features only (what imagery adds)
  vi                ridge on imagery features only
Aggregation: state dev = mean of county predicted devs weighted by county harvested acres of Y-1 (latest
        available); state forecast = state trend x exp(state dev). IA+IL = harvested-acre (state, Y-1) weighted
        mean of the two state forecasts. US proxy = US trend x exp(beta x IA+IL dev), beta = OLS slope through the
        origin of US on IA+IL log deviations of the January finals, Y-20..Y-1.
Uncertainty (1 sd, bu/ac): leave-one-year-out RMSE of the region's log deviation inside the training years
        (each training year predicted by a model fitted on the other training years), times the forecast.
Usage:  python model.py [--years 2016-2026] [--models ridge,gbm,wx,vi] [--tag v1] [--vi-file county_vi.csv] [--extra-vi ndre_jul]
        Outputs signal/field_signal_<tag>.csv (all regions) and features/county_predictions_<tag>.csv.
"""
import argparse, os
import numpy as np, pandas as pd
from scipy.stats import theilslopes
from common import DATA, FEAT, SIG, STATES

# frozen spec (chosen on 2016-2021 walk-forward only, see README): NIRv season integral, late-window NIRv, green-up
VI = {"corn": ["nirv_auc", "nirv_last", "gu_doy"], "soy": ["nirv_auc", "nirv_last", "gu_doy"]}
WX = {"aug": ["prcp_jul", "hdd_jul"], "sep": ["prcp_jul", "prcp_aug", "hdd_jul", "hdd_aug"]}
ALPHAS = [1, 3, 10, 30, 100, 300]
VERSION = "field_v1"


def theil_trend(yrs, vals, Y):
    s = theilslopes(vals, yrs)
    return s[1] + s[0] * Y


def load(vi_file="county_vi.csv"):
    fin = pd.read_csv(f"{DATA}/finals_jan.csv")
    cy = pd.read_csv(f"{DATA}/county_yield.csv", dtype={"fips": str})
    cy = cy[cy.state.isin(STATES)]
    vi = pd.read_csv(f"{FEAT}/{vi_file}", dtype={"fips": str})
    wx = pd.read_csv(f"{FEAT}/county_weather.csv", dtype={"fips": str})
    ha = pd.read_csv(f"{DATA}/state_harvested.csv")
    return fin, cy, vi, wx, ha


def state_trends(fin, Y):
    out = {}
    for (crop, reg), g in fin.groupby(["crop", "region"]):
        g = g[(g.year >= Y - 20) & (g.year <= Y - 1)]
        if len(g) >= 10:
            out[(crop, reg)] = theil_trend(g.year.values, g.final_jan.values, Y)
    return out


def county_frame(fin, cy, crop, years):
    """county trend and log deviation for each county-year (trend uses only data before that year)"""
    rows = []
    c = cy[cy.crop == crop]
    sf = fin[fin.crop == crop].set_index(["region", "year"]).final_jan
    for Y in years:
        tr = state_trends(fin, Y)
        hist = c[(c.year >= Y - 10) & (c.year <= Y - 1) & c.yield_bu_ac.notna()].copy()
        hist["ratio"] = hist.yield_bu_ac / [sf.get((s, y), np.nan) for s, y in zip(hist.state, hist.year)]
        rat = hist.groupby("fips").ratio.agg(["median", "size"])
        rat = rat[rat["size"] >= 5]["median"]
        area = c[(c.year <= Y - 1) & c.harvested_ac.notna()].sort_values("year").groupby("fips").harvested_ac.last()
        cur = c[c.year == Y].set_index("fips")
        for fips, r in rat.items():
            st = cy[cy.fips == fips].state.iloc[0]
            if (crop, st) not in tr:
                continue
            t = tr[(crop, st)] * r
            yv = cur.yield_bu_ac.get(fips, np.nan) if fips in cur.index else np.nan
            rows.append(dict(year=Y, fips=fips, state=st, trend=t, state_trend=tr[(crop, st)], yield_=yv, dev=np.log(yv / t) if yv == yv else np.nan,
                             w_area=area.get(fips, np.nan)))
    return pd.DataFrame(rows)


def make_X(df, feats, train_mask):
    """county-demeaned features (county mean over the training rows' years), z-scored on training rows"""
    X = pd.DataFrame(index=df.index)
    for f in feats:
        v = df[f]
        mu_c = df[train_mask].groupby("fips")[f].mean()
        mu_all = df.loc[train_mask, f].mean()
        X[f] = v - df.fips.map(mu_c).fillna(mu_all)
    tr = X[train_mask]
    mu, sd = tr.mean(), tr.std().replace(0, 1)
    X = ((X - mu) / sd).fillna(0.0)
    return X


NO_INTERCEPT = False  # post-hoc diagnostic (--no-intercept): intercept fixed at 0 (pure anomaly model)


def ridge_fit(X, y, alpha):
    Xa = np.column_stack([np.ones(len(X)), X])
    P = np.eye(Xa.shape[1]) * alpha; P[0, 0] = 1e12 if NO_INTERCEPT else 0
    return np.linalg.solve(Xa.T @ Xa + P, Xa.T @ y)


def ridge_pred(b, X):
    return b[0] + X @ b[1:]


def fit_predict(kind, Xtr, ytr, gtr, Xte, alpha=None):
    if kind == "gbm":
        import lightgbm as lgb
        m = lgb.LGBMRegressor(n_estimators=300, learning_rate=0.03, num_leaves=8, min_child_samples=20, subsample=0.8, subsample_freq=1,
                              colsample_bytree=0.8, verbose=-1, random_state=0, n_jobs=1)
        m.fit(Xtr, ytr)
        return m.predict(Xte), None
    if alpha is None:
        best = None
        for a in ALPHAS:
            err = []
            for g in np.unique(gtr):
                k = gtr != g
                b = ridge_fit(Xtr[k], ytr[k], a)
                err.append(np.mean((ridge_pred(b, Xtr[~k]) - ytr[~k]) ** 2))
            if best is None or np.mean(err) < best[0]:
                best = (np.mean(err), a)
        alpha = best[1]
    b = ridge_fit(Xtr, ytr, alpha)
    return ridge_pred(b, Xte), (alpha, b)


def aggregate(df, pred_col):
    """state devs from county devs (acre weights)"""
    d = df[df[pred_col].notna() & df.w_area.notna()]
    return d.groupby("state").apply(lambda g: np.average(g[pred_col], weights=g.w_area), include_groups=False)


def us_beta(fin, crop, Y):
    rows = []
    for t in range(Y - 20, Y):
        tr = state_trends(fin, t)
        f = fin[(fin.crop == crop) & (fin.year == t)].set_index("region").final_jan
        ha = None
        if all(k in f.index for k in ["IA", "IL", "US"]) and all((crop, k) in tr for k in ["IA", "IL", "US"]):
            dev = {k: np.log(f[k] / tr[(crop, k)]) for k in ["IA", "IL", "US"]}
            rows.append((dev["US"], (dev["IA"] + dev["IL"]) / 2))
    a = np.array(rows)
    return float((a[:, 0] * a[:, 1]).sum() / (a[:, 1] ** 2).sum()) if len(a) >= 8 else 1.0


def run(crop, rep, years, kinds, fin, cy, vi, wx, ha, fdates):
    allyears = list(range(2013, max(years) + 1))
    cf = county_frame(fin, cy, crop, allyears)
    v = vi[(vi.crop == crop) & (vi.report == rep)]
    w = wx[wx.report == rep]
    df = cf.merge(v, on=["year", "fips"], how="left").merge(w, on=["year", "fips"], how="left")
    # weather county means need a longer history: attach full weather table for demeaning
    out_rows, county_out = [], []
    for Y in years:
        trn = df[(df.year < Y) & df.dev.notna() & df[VI[crop][0]].notna()]
        te = df[(df.year == Y) & df[VI[crop][0]].notna()]
        if trn.year.nunique() < 3 or te.empty:
            continue
        sub = pd.concat([trn, te])
        trm = (sub.year < Y).values
        tr_states = state_trends(fin, Y)
        for kind in kinds:
            feats = {"ridge": VI[crop] + WX[rep], "gbm": VI[crop] + WX[rep], "wx": WX[rep], "vi": VI[crop]}[kind]
            # weather demeaned on 2005..Y-1 county means (longer record)
            X = make_X(sub, feats, trm)
            if kind in ("ridge", "wx", "gbm"):
                wh = w[w.year < Y].groupby("fips")[WX[rep]].mean()
                whs = w[w.year < Y][WX[rep]].std()
                for f in WX[rep]:
                    if f in feats:
                        X[f] = ((sub[f] - sub.fips.map(wh[f])) / whs[f]).fillna(0.0).values
            Xtr, ytr, gtr = X[trm].values, sub.dev.values[trm], sub.year.values[trm]
            p, info = fit_predict(kind, Xtr, ytr, gtr, X[~trm].values)
            alpha = info[0] if info else None
            tes = te.assign(pred=p)
            sdev = aggregate(tes, "pred")
            # leave-one-year-out inside training -> region RMSE
            loyo = {}
            for g in np.unique(gtr):
                k = gtr != g
                pg, _ = fit_predict(kind, Xtr[k], ytr[k], gtr[k], Xtr[~k], alpha=alpha)
                tg = trn[trn.year == g].assign(pred=pg)
                for s, dv in aggregate(tg, "pred").items():
                    fy = fin[(fin.crop == crop) & (fin.year == g) & (fin.region == s)].final_jan
                    trs = state_trends(fin, g).get((crop, s))
                    if len(fy) and trs:
                        loyo.setdefault(s, []).append(dv - np.log(fy.iloc[0] / trs))
                        loyo.setdefault("_pair", []).append((g, s, dv, np.log(fy.iloc[0] / trs)))
            fdt = fdates[(fdates.year == Y) & (fdates.report == rep)]
            T = fdt.forecast_date.iloc[0].date() if len(fdt) else None
            cut = te.cut_doy.iloc[0] if "cut_doy" in te else np.nan
            data_cut = (pd.Timestamp(Y, 1, 1) + pd.Timedelta(days=int(cut) - 1)).date() if cut == cut else None
            base = dict(forecast_date=T, data_cutoff=data_cut, crop=crop, report=rep, year=Y, model=kind, model_version=f"{VERSION}_{kind}", alpha=alpha)
            acres = {}
            for s in STATES:
                hs = ha[(ha.crop == crop) & (ha.region == s) & (ha.year < Y)].sort_values("year")
                acres[s] = hs.acres.iloc[-1] if len(hs) else np.nan
            preds = {}
            for s, dv in sdev.items():
                t = tr_states[(crop, s)]
                rm = np.sqrt(np.mean(np.square(loyo.get(s, [np.nan]))))
                preds[s] = (t * np.exp(dv), dv, rm, t)
                out_rows.append(dict(base, region=s, predicted_yield=t * np.exp(dv), uncertainty=t * np.exp(dv) * rm, trend_yield=t, pred_dev_log=dv,
                                     n_counties=int((tes.state == s).sum())))
            if all(s in preds for s in STATES):
                wts = np.array([acres[s] for s in STATES])
                y_ag = np.average([preds[s][0] for s in STATES], weights=wts)
                t_ag = np.average([preds[s][3] for s in STATES], weights=wts)
                dv_ag = np.log(y_ag / t_ag)
                # IA+IL LOYO error: weighted mean of state LOYO errors per training year
                pr = pd.DataFrame(loyo.get("_pair", []), columns=["g", "s", "p", "a"])
                if len(pr):
                    pr["w"] = pr.s.map(dict(zip(STATES, wts)))
                    e = pr.groupby("g").apply(lambda q: np.average(q.p - q.a, weights=q.w), include_groups=False)
                    rm_ag = float(np.sqrt(np.mean(e ** 2)))
                else:
                    rm_ag = np.nan
                out_rows.append(dict(base, region="IA+IL", predicted_yield=y_ag, uncertainty=y_ag * rm_ag, trend_yield=t_ag, pred_dev_log=dv_ag,
                                     n_counties=len(tes)))
                beta = us_beta(fin, crop, Y)
                tus = tr_states[(crop, "US")]
                yus = tus * np.exp(beta * dv_ag)
                out_rows.append(dict(base, region="US", predicted_yield=yus, uncertainty=yus * beta * rm_ag, trend_yield=tus, pred_dev_log=beta * dv_ag,
                                     n_counties=len(tes), us_beta=beta))
            county_out.append(tes[["year", "fips", "state", "trend", "yield_", "dev", "pred", "w_area", "npix"]].assign(crop=crop, report=rep, model=kind))
            print(crop, rep, Y, kind, "alpha", alpha, {s: round(float(v), 4) for s, v in sdev.items()}, flush=True)
    return out_rows, county_out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--years", default="2016-2026")
    ap.add_argument("--models", default="ridge,gbm,wx,vi")
    ap.add_argument("--tag", default="v1")
    ap.add_argument("--vi-file", default="county_vi.csv", help="county VI table (county_vi.csv = Landsat-only primary; county_vi_fused.csv = Landsat+S2)")
    ap.add_argument("--vi-feats", default="", help="override the VI feature list")
    ap.add_argument("--wx-aug", default="", help="override the August weather feature list")
    ap.add_argument("--wx-sep", default="", help="override the September weather feature list")
    ap.add_argument("--no-intercept", action="store_true", help="post-hoc diagnostic: ridge intercept fixed at 0")
    ap.add_argument("--extra-vi", default="", help="comma list of extra VI features (e.g. ndre_jul)")
    a = ap.parse_args()
    global NO_INTERCEPT
    NO_INTERCEPT = a.no_intercept
    if a.vi_feats:
        for c in VI:
            VI[c] = a.vi_feats.split(",")
    if a.wx_aug:
        WX["aug"] = a.wx_aug.split(",")
    if a.wx_sep:
        WX["sep"] = a.wx_sep.split(",")
    for c in VI:
        VI[c] = VI[c] + [f for f in a.extra_vi.split(",") if f]
    from build_features import forecast_dates
    fin, cy, vi, wx, ha = load(a.vi_file)
    fd = forecast_dates()
    y0, y1 = map(int, a.years.split("-"))
    rows, cty = [], []
    for crop in ["corn", "soy"]:
        for rep in ["aug", "sep"]:
            r, c = run(crop, rep, list(range(y0, y1 + 1)), a.models.split(","), fin, cy, vi, wx, ha, fd)
            rows += r; cty += c
    s = pd.DataFrame(rows)
    os.makedirs(SIG, exist_ok=True)
    s.to_csv(f"{SIG}/field_signal_{a.tag}.csv", index=False, float_format="%.4f")
    pd.concat(cty).to_csv(f"{FEAT}/county_predictions_{a.tag}.csv", index=False, float_format="%.4f")
    print("wrote", len(s), "signal rows")


if __name__ == "__main__":
    main()
