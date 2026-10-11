"""Walk-forward, point-in-time US corn / soybean yield model from Aqua MODIS VI + gridMET weather.

For each crop (corn grain, soybeans), year Y and forecast slot (aug, sep):
  forecast_date T  = NASS Crop Production release date - 5 days (release dates: benchmark agent's table if
                     present, else Quick Stats load times; Aug 12 / Sep 12 for years with neither)
  inputs           = only rows with available_date <= T: Aqua composites with start DOY 169..217
                     (available = composite end + 14 d) and gridMET days <= T - 3 d
  features, per state (each de-meaned per state over the training years, then z-scored pooled):
    evi_int   mean over available composites of the per-composite EVI anomaly (vs the state's training-year
              mean at that composite slot)
    evi_peak  max EVI over the available composites, minus the training-year mean of the same quantity
              over the same composite set
    prcp_ja   precipitation Jul 1 .. T-3 / training-year mean over the same calendar window - 1
    hdd30     sum of daily max(Tmax - 30 C, 0), Jul 1 .. T-3, minus the training-year mean
  target           = ln(final yield / trend), trend = OLS line through the 20 final yields Y-20..Y-1
                     (all published by the January Crop Production Annual Summary of year Y)
  model            = one ridge regression pooled over the 12 states, alpha = 3 (fixed, not tuned), features
                     z-scored on the training set, unpenalised intercept; trained on 2008..Y-1 only
                     (first forecast year 2013)
  fallback         = if VI features are missing for a state (no composite available), a weather-only ridge
                     (prcp_ja, hdd30) with the same settings is used for that state; flagged in `vi_source`
  prediction       = trend_Y * exp(ridge); uncertainty (1 sd) = leave-one-year-out RMSE (log) within the
                     training years, times the prediction
  US               = US trend * exp(sum_s w_s * dev_s), w_s = state June-Acreage harvested area x state trend
                     / (US June-Acreage harvested area x US trend) (rest of US at trend); 1-sd from the
                     leave-one-year-out RMSE of that national aggregate
Outputs: signal/us_sat_signal_<tag>.csv, features/asof_features.csv
  Without --evaluate-holdout, rows for years >= --holdout-from go to signal/.sealed_holdout_<tag>.csv only.
Usage: python model.py [--evaluate-holdout] [--holdout-from 2022] [--feats evi_int,evi_peak,prcp_ja,hdd30] [--tag v1]
"""
import argparse, os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STATES = ["IA", "IL", "NE", "MN", "IN", "OH", "SD", "ND", "KS", "MO", "WI", "MI"]
FEATS = ["evi_int", "evi_peak", "prcp_ja", "hdd30"]
WFEATS = ["prcp_ja", "hdd30"]
ALPHA, TREND_N, FIRST_TRAIN, FIRST_FC = 3.0, 20, 2008, 2013
SLOTS = [169, 185, 201, 217]
WX_LAG = 3
MODEL_VERSION = "us_sat_v1"


def release_dates(root):
    r = pd.read_csv(f"{root}/data/release_dates.csv")
    bm = os.path.join(root, "..", "benchmark", "data", "reference", "crop_production_release_dates.csv")
    src = "quickstats_load_time"
    if os.path.exists(bm):
        b = pd.read_csv(bm)
        if {"year", "aug_release", "sep_release"} <= set(b.columns):
            r = r.set_index("year").combine_first(b.set_index("year")[["aug_release", "sep_release"]]).reset_index(); src = "benchmark+quickstats"
    out = {}
    for Y in range(FIRST_TRAIN, 2027):
        row = r[r.year == Y]
        for k, m in (("aug", 8), ("sep", 9)):
            v = row[f"{k}_release"].iloc[0] if len(row) else None
            out[(Y, k)] = (pd.Timestamp(v), src) if isinstance(v, str) else (pd.Timestamp(Y, m, 12), "assumed_12th")
    return out


def trend(vals, Y):
    ys = np.array([y for y in range(Y - TREND_N, Y) if y in vals])
    if len(ys) < 10:
        return np.nan
    b, a = np.polyfit(ys, [vals[y] for y in ys], 1)
    return a + b * Y


def raw_features(vi, wx, crop, Y, T):
    """per state: dict of composite EVI values available at T, and weather sums Jul 1..T-3 (also for the
    same calendar window in every year, for climatology)"""
    v = vi[(vi.crop == crop) & (vi.year == Y) & vi.doy.isin(SLOTS) & (pd.to_datetime(vi.available_date) <= T) & (vi.valid_frac >= 0.2) & vi.evi.notna()]
    comp = {s: dict(zip(g.doy, g.evi)) for s, g in v.groupby("state")}
    src = {s: "+".join(sorted(set(g.source))) for s, g in v.groupby("state")}
    cut = {s: g.end.max() for s, g in v.groupby("state")}
    return comp, src, cut


def wx_window(wx, Y, T):
    end = T - pd.Timedelta(days=WX_LAG)
    md0, md1 = (7, 1), (end.month, end.day)
    w = wx[(wx.md >= md0) & (wx.md <= md1)]
    return w.groupby(["state", "year"]).agg(prcp=("prcp_mm", "sum"), hdd=("hdd30", "sum"), nday=("prcp_mm", "size")), end


def ridge_fit(X, y, alpha):
    mu, sd = X.mean(0), X.std(0); sd[sd == 0] = 1
    Z = (X - mu) / sd
    ym = y.mean()
    beta = np.linalg.solve(Z.T @ Z + alpha * np.eye(Z.shape[1]), Z.T @ (y - ym))
    return dict(mu=mu, sd=sd, beta=beta, b0=ym)


def ridge_pred(m, X):
    return m["b0"] + ((X - m["mu"]) / m["sd"]) @ m["beta"]


def build_design(vi, wxw, crop, years, Y, T, feats, finals, trends):
    """feature matrix for training years (< Y) and year Y, using climatology from training years only.
    The VI composite set for every year is the one available at T in year Y (same calendar position)."""
    comp_by_year = {}
    for t in list(years) + [Y]:
        # year Y: only what was published by T; past years: every composite (they were all public by T),
        # restricted below to the composite slots that year Y has at T
        Tt = T if t == Y else pd.Timestamp(t + 1, 6, 30)
        comp_by_year[t] = raw_features(vi, None, crop, t, Tt)
    rows = []
    train_years = [t for t in years if t < Y]
    for s in STATES:
        compY = comp_by_year[Y][0].get(s, {})
        slots = sorted(compY)
        clim = {d: np.nanmean([comp_by_year[t][0].get(s, {}).get(d, np.nan) for t in train_years]) for d in slots}
        peak_clim = np.nanmean([max([comp_by_year[t][0].get(s, {}).get(d, np.nan) for d in slots], default=np.nan) for t in train_years]) if slots else np.nan
        p_clim = np.nanmean([wxw.loc[(s, t), "prcp"] for t in train_years if (s, t) in wxw.index])
        h_clim = np.nanmean([wxw.loc[(s, t), "hdd"] for t in train_years if (s, t) in wxw.index])
        for t in train_years + [Y]:
            c = comp_by_year[t][0].get(s, {})
            vals = [c.get(d, np.nan) - clim[d] for d in slots]
            pk = [c.get(d, np.nan) for d in slots]
            r = dict(state=s, year=t, n_comp=int(np.isfinite(vals).sum()) if slots else 0,
                     evi_int=np.nanmean(vals) if slots and np.isfinite(vals).any() else np.nan,
                     evi_peak=(np.nanmax(pk) - peak_clim) if slots and np.isfinite(pk).all() else np.nan,
                     prcp_ja=wxw.loc[(s, t), "prcp"] / p_clim - 1 if (s, t) in wxw.index else np.nan,
                     hdd30=wxw.loc[(s, t), "hdd"] - h_clim if (s, t) in wxw.index else np.nan,
                     vi_source=comp_by_year[t][1].get(s, "none"), vi_cutoff=comp_by_year[t][2].get(s, None),
                     vi_slots="/".join(map(str, slots)))
            tr = trends.get((s, t), np.nan); fin = finals.get((s, t), np.nan)
            r["trend"] = tr; r["final"] = fin; r["dev"] = np.log(fin / tr) if np.isfinite(fin) and np.isfinite(tr) else np.nan
            rows.append(r)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--evaluate-holdout", action="store_true")
    ap.add_argument("--holdout-from", type=int, default=2022)
    ap.add_argument("--feats", default=",".join(FEATS))
    ap.add_argument("--tag", default="v1")
    ap.add_argument("--last-year", type=int, default=2026)
    a = ap.parse_args()
    feats = a.feats.split(",")
    root = HERE
    vi = pd.read_csv(f"{root}/features/modis_state.csv")
    wx = pd.read_csv(f"{root}/features/weather_state_daily.csv")
    wx["date"] = pd.to_datetime(wx.date); wx["year"] = wx.date.dt.year; wx["md"] = list(zip(wx.date.dt.month, wx.date.dt.day))
    ny = pd.read_csv(f"{root}/data/nass_yield.csv")
    na = pd.read_csv(f"{root}/data/nass_area.csv")
    rel = release_dates(root)
    out, feat_rows = [], []
    crops = {"corn": "corn", "soy": "soy"}
    for crop in crops:
        fin = ny[(ny.crop == crop) & (ny.period == "final")]
        finals = {(r.region, r.year): r.yield_bu_ac for r in fin.itertuples()}
        trends = {}
        for reg in STATES + ["US"]:
            vals = {y: v for (rg, y), v in finals.items() if rg == reg}
            for Y in range(FIRST_TRAIN, a.last_year + 1):
                trends[(reg, Y)] = trend(vals, Y)
        for Y in range(FIRST_FC, a.last_year + 1):
            for slot in ["aug", "sep"]:
                R, rsrc = rel[(Y, slot)]
                T = R - pd.Timedelta(days=5)
                wxw, wend = wx_window(wx, Y, T)
                years = list(range(FIRST_TRAIN, Y))
                D = build_design(vi, wxw, crop, years, Y, T, feats, finals, trends)
                tr = D[(D.year < Y) & D.dev.notna()]
                te = D[D.year == Y].copy()
                full_ok = tr[feats].notna().all(1)
                m_full = ridge_fit(tr.loc[full_ok, feats].values, tr.loc[full_ok, "dev"].values, ALPHA)
                m_wx = ridge_fit(tr[WFEATS].values, tr["dev"].values, ALPHA)
                # leave-one-year-out residuals (state level and national aggregate)
                loyo = []
                for t in sorted(tr.year.unique()):
                    a_ = tr[full_ok & (tr.year != t)]; b_ = tr[full_ok & (tr.year == t)]
                    if len(b_) == 0:
                        continue
                    mm = ridge_fit(a_[feats].values, a_.dev.values, ALPHA)
                    loyo.append(b_.assign(pred=ridge_pred(mm, b_[feats].values)))
                loyo = pd.concat(loyo)
                rmse_state = float(np.sqrt(np.mean((loyo.pred - loyo.dev) ** 2)))
                use_full = te[feats].notna().all(1)
                te["pred_dev"] = np.where(use_full, ridge_pred(m_full, te[feats].fillna(0).values), ridge_pred(m_wx, te[WFEATS].fillna(0).values))
                te["model"] = np.where(use_full, "full", "weather_only")
                te["pred_yield"] = te.trend * np.exp(te.pred_dev)
                te["unc"] = te.pred_yield * rmse_state
                # national weights from June Acreage (else previous final harvested area)
                def harea(reg, yr):
                    r_ = na[(na.crop == crop) & (na.region == reg) & (na.year == yr) & (na["var"] == "harvested")]
                    j = r_[r_.period == "jun"]
                    if len(j):
                        return float(j.acres.iloc[0])
                    f_ = na[(na.crop == crop) & (na.region == reg) & (na.year == yr - 1) & (na["var"] == "harvested") & (na.period == "final")]
                    return float(f_.acres.iloc[0]) if len(f_) else np.nan
                def natdev(df, yr):
                    w = np.array([harea(s, yr) * trends[(s, yr)] for s in df.state])
                    return float(np.nansum(w * df["dev_"].values) / (harea("US", yr) * trends[("US", yr)])), float(np.nansum(w) / (harea("US", yr) * trends[("US", yr)]))
                ln = []
                for t, g in loyo.groupby("year"):
                    pdv, _ = natdev(g.assign(dev_=g.pred), t)
                    us_fin = finals.get(("US", t), np.nan)
                    ln.append(np.log(trends[("US", t)] * np.exp(pdv) / us_fin))
                rmse_us = float(np.sqrt(np.nanmean(np.square(ln))))
                us_dev, cover = natdev(te.assign(dev_=te.pred_dev), Y)
                coef = dict(zip([f"coef_{f}" for f in feats], m_full["beta"] / m_full["sd"]))
                cutoff_wx = min(wend, wx[wx.year == Y].date.max())
                for r in te.itertuples():
                    vic = r.vi_cutoff if isinstance(r.vi_cutoff, str) else None
                    cut = max([pd.Timestamp(x) for x in [vic, cutoff_wx] if x is not None])
                    out.append(dict(forecast_date=T.date(), data_cutoff_date=cut.date(), vi_cutoff_date=vic, weather_cutoff_date=cutoff_wx.date(),
                                    release_date=R.date(), release_date_source=rsrc, report=slot, crop=crop, year=Y, region=r.state,
                                    predicted_yield=round(r.pred_yield, 2), uncertainty=round(r.unc, 2), trend_yield=round(r.trend, 2),
                                    pred_dev_log=round(r.pred_dev, 4), model=r.model, vi_source=r.vi_source, vi_slots=r.vi_slots,
                                    model_version=f"{MODEL_VERSION}_{a.tag}" if a.tag != "v1" else MODEL_VERSION,
                                    **{f: (round(getattr(r, f), 4) if np.isfinite(getattr(r, f)) else np.nan) for f in feats}, **{k: round(v, 5) for k, v in coef.items()},
                                    final_yield_expost=r.final))
                us_pred = trends[("US", Y)] * np.exp(us_dev)
                out.append(dict(forecast_date=T.date(), data_cutoff_date=max(pd.Timestamp(x) for x in [cutoff_wx] + [v for v in te.vi_cutoff if isinstance(v, str)]).date(),
                                vi_cutoff_date=max([v for v in te.vi_cutoff if isinstance(v, str)], default=None), weather_cutoff_date=cutoff_wx.date(),
                                release_date=R.date(), release_date_source=rsrc, report=slot, crop=crop, year=Y, region="US",
                                predicted_yield=round(us_pred, 2), uncertainty=round(us_pred * rmse_us, 2), trend_yield=round(trends[("US", Y)], 2),
                                pred_dev_log=round(us_dev, 4), model="aggregate", vi_source="+".join(sorted(set(te.vi_source))), vi_slots=te.vi_slots.iloc[0],
                                model_version=f"{MODEL_VERSION}_{a.tag}" if a.tag != "v1" else MODEL_VERSION, coverage_12_states=round(cover, 3),
                                final_yield_expost=finals.get(("US", Y), np.nan)))
                feat_rows.append(D[D.year == Y].assign(crop=crop, report=slot, forecast_date=T.date()))
                print(crop, Y, slot, T.date(), "US", round(us_pred, 1), "trend", round(trends[("US", Y)], 1), "final", finals.get(("US", Y)), "rmse", round(rmse_state, 3), round(rmse_us, 3), flush=True)
    sig = pd.DataFrame(out)
    tag = a.tag
    sig_dev = sig if a.evaluate_holdout else sig[sig.year < a.holdout_from]
    sig_dev.to_csv(f"{root}/signal/us_sat_signal_{tag}.csv", index=False)
    if not a.evaluate_holdout:
        sig[sig.year >= a.holdout_from].to_csv(f"{root}/signal/.sealed_holdout_{tag}.csv", index=False)
    if tag == "v1":
        F = pd.concat(feat_rows)
        if not a.evaluate_holdout:
            F = F[F.year < a.holdout_from]
        F.to_csv(f"{root}/features/asof_features.csv", index=False, float_format="%.4f")


if __name__ == "__main__":
    main()
