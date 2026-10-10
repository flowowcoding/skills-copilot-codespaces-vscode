"""Walk-forward, point-in-time state soybean yield model from satellite + weather features.

For every season Y and as-of date T (1st and 16th of each month, Nov 1 .. Jun 1):
  features (state s, using only rows with available_date <= T, from season Y):
    evi_cum     mean EVI anomaly of composites in the crop window to date (starting ~Nov 1 .. ~Feb 18;
                PR shifted +16 d, RS/SC +32 d)
    ndvi_recent mean NDVI anomaly of the last two available composites inside the crop window
    precip_cum  CHIRPS Oct..latest available month, total / climatology - 1
    lst_cum     mean daytime LST anomaly (deg C) of 8-day composites starting Dec 1 .. Mar 22 (south +16/32 d)
  (a feature with no data yet is 0 = climatology)
  target      final yield / PIT trend - 1, trend = OLS line over the last 15 yields KNOWN at T
              (PAM if published by Sep 30 of the following year, else the latest released IBGE LSPA
              vintage), evaluated at Y
  model       one pooled ridge regression across the 12 states per as-of slot, features z-scored on
              the training set, alpha = 3 (fixed, not tuned), unpenalised intercept; trained on seasons
              2004..Y-1 only, with training targets as known at T
  prediction  yield = trend_Y * (1 + ridge); production = yield * PIT harvested-area estimate
              (latest released LSPA area for Y, else last known area grown at its 3-yr mean rate)
  uncertainty 1-sigma: leave-one-season-out RMSE on the training seasons (relative), times prediction
Brazil = sum of the 12 modelled states + other states at trend yield x PIT area.

Outputs: signal/soy_sat_signal_v1.csv, features/asof_features.csv
Usage: python model.py [--holdout-from 2023] [--evaluate-holdout]
  Without --evaluate-holdout, rows for seasons >= holdout-from are written to a separate file
  that the evaluation step does not read (development mode).
"""
import argparse, os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STATES = ["MT", "PR", "RS", "GO", "MS", "BA", "MG", "MA", "TO", "PI", "SP", "SC"]
FEATS = ["evi_cum", "ndvi_recent", "precip_cum", "lst_cum"]
ALPHA, TREND_N, FIRST_FEAT, MIN_TRAIN = 3.0, 15, 2004, 7
VERSION = "v1"


def asof_dates(Y):
    d = []
    for m, y in [(11, Y - 1), (12, Y - 1), (1, Y), (2, Y), (3, Y), (4, Y), (5, Y), (6, Y)]:
        d.append(pd.Timestamp(y, m, 1))
        if m != 6:
            d.append(pd.Timestamp(y, m, 16))
    return d


def asof_label(T):
    return f"{T.month:02d}-{T.day:02d}"


class Known:
    """What yield / area figures were public at a date."""

    def __init__(self, pam, lspa, rel):
        self.pam = pam.set_index(["state", "year"])
        l = lspa.copy(); l["year"] = l.survey_month // 100
        l["release"] = l.survey_month.map(rel).fillna(
            l.survey_month.map(lambda m: pd.Timestamp(m // 100, m % 100, 1) + pd.Timedelta(days=40)))
        self.lspa = l.sort_values("release")

    def yields(self, state, T, upto):
        out = {}
        for y in range(upto - TREND_N - 2, upto + 1):
            if T >= pd.Timestamp(y + 1, 9, 30) and (state, y) in self.pam.index:
                out[y] = self.pam.loc[(state, y), "yield_kg_ha"]
            else:
                v = self.lspa_latest(state, y, T, "yield_kg_ha")
                if v is not None:
                    out[y] = v
                elif y < 2007 and (state, y) in self.pam.index:  # pre-LSPA-table gap (training-only years)
                    out[y] = self.pam.loc[(state, y), "yield_kg_ha"]
        return out

    def lspa_latest(self, state, y, T, col):
        l = self.lspa[(self.lspa.state == state) & (self.lspa.year == y) & (self.lspa.release <= T)]
        if len(l) == 0 or not np.isfinite(l[col].iloc[-1]):
            return None
        return float(l[col].iloc[-1])

    def area(self, state, Y, T):
        v = self.lspa_latest(state, Y, T, "area_harvested_ha")
        if v is not None:
            return v, "lspa"
        hist = {}
        for y in range(Y - 5, Y):
            if T >= pd.Timestamp(y + 1, 9, 30) and (state, y) in self.pam.index:
                hist[y] = self.pam.loc[(state, y), "area_harvested_ha"]
            else:
                w = self.lspa_latest(state, y, T, "area_harvested_ha")
                if w is not None:
                    hist[y] = w
                elif (state, y) in self.pam.index and y < 2007:
                    hist[y] = self.pam.loc[(state, y), "area_harvested_ha"]
        ys = sorted(hist)
        if not ys:
            return np.nan, "none"
        g = [hist[b] / hist[a] - 1 for a, b in zip(ys[:-1], ys[1:]) if hist[a] > 0][-3:]
        return hist[ys[-1]] * (1 + (np.mean(g) if g else 0)) ** (Y - ys[-1]), "trend"


def trend_at(yd, Y):
    ys = sorted(k for k in yd if k < Y)[-TREND_N:]
    if len(ys) < 5:
        return np.nan
    b = np.polyfit(ys, [yd[k] for k in ys], 1)
    return float(np.polyval(b, Y))


# crop window per state, in MOD13 16-day slots (slot 7 = composite starting ~Nov 1, 14 = ~Feb 18):
# centre-north crops are planted Sep-Nov and harvested Jan-Mar; PR one slot later; RS/SC two slots later.
SHIFT = {"PR": 1, "RS": 2, "SC": 2}


def make_features(vi, lst, pr, T, Y, state):
    f = {}; cut = {}
    sh = SHIFT.get(state, 0)
    v = vi[(vi.season == Y) & (vi.state == state) & (vi.available_date <= T)].sort_values("slot")
    v = v[v.anom_cov > 0.2]
    if len(v):
        cut["vi"] = v.end.max()
    e = v[(v.slot >= 7 + sh) & (v.slot <= 14 + sh)]
    f["evi_cum"] = e.evi_anom.mean() if len(e) else 0.0
    r = v[(v.slot >= 5 + sh) & (v.slot <= 14 + sh)].tail(2)
    f["ndvi_recent"] = r.ndvi_anom.mean() if len(r) else 0.0
    p = pr[(pr.season == Y) & (pr.state == state) & (pr.available_date <= T) & (pr.slot >= 2)]
    if len(p):
        cut["precip"] = (pd.Timestamp(str(p.month.max()) + "01") + pd.offsets.MonthEnd(0)).date().isoformat()
    f["precip_cum"] = p.precip_mm.sum() / p.precip_clim_mm.sum() - 1 if len(p) and p.precip_clim_mm.sum() > 0 else 0.0
    l = lst[(lst.season == Y) & (lst.state == state) & (lst.available_date <= T) & (lst.anom_cov > 0.2)]
    if len(l):
        cut["lst"] = l.end.max()
    l = l[(l.slot >= 12 + 2 * sh) & (l.slot <= 25 + 2 * sh)]
    f["lst_cum"] = l.lst_anom.mean() if len(l) else 0.0
    return f, cut


def ridge_fit(X, y, alpha=ALPHA):
    mu, sd = X.mean(0), X.std(0); sd[sd < 1e-9] = 1
    Z = (X - mu) / sd; ym = y.mean()
    beta = np.linalg.solve(Z.T @ Z + alpha * np.eye(Z.shape[1]), Z.T @ (y - ym))
    return lambda Xn: ym + ((Xn - mu) / sd) @ beta, beta


def main():
    global FEATS, VERSION
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--holdout-from", type=int, default=2023)
    ap.add_argument("--evaluate-holdout", action="store_true")
    ap.add_argument("--last-season", type=int, default=2026)
    ap.add_argument("--feats", default=",".join(FEATS), help="EXPLORATORY ONLY: feature subset (pre-registered = all four)")
    ap.add_argument("--tag", default=VERSION, help="output tag; anything other than v1 is a non-pre-registered variant")
    a = ap.parse_args()
    FEATS = a.feats.split(","); VERSION = a.tag
    F = f"{HERE}/features"
    vi = pd.read_csv(f"{F}/modis_vi_state.csv"); lst = pd.read_csv(f"{F}/lst_state.csv"); pr = pd.read_csv(f"{F}/precip_state.csv")
    for d in (vi, lst, pr):
        d["available_date"] = pd.to_datetime(d.available_date)
    pam = pd.read_csv(f"{HERE}/data/pam_state.csv"); lspa = pd.read_csv(f"{HERE}/data/lspa_state.csv")
    rel = {}
    rf = f"{HERE}/../benchmark/data/interim/ibge_lspa_release_dates.csv"
    if os.path.exists(rf):
        r = pd.read_csv(rf); rel = dict(zip(r.ref_month, pd.to_datetime(r.release_datetime_brt).dt.normalize()))
    # "OTH" = Brazil minus the 12 modelled states (PAM and LSPA), so Brazil totals close exactly
    def add_oth(df, key, cols):
        br = df[df.state == "BR"].set_index(key)[cols]
        tw = df[df.state.isin(STATES)].groupby(key)[cols].sum()
        o = (br - tw.reindex(br.index)).clip(lower=0).reset_index(); o["state"] = "OTH"
        o["yield_kg_ha"] = o.production_t / o.area_harvested_ha * 1000
        return pd.concat([df, o], ignore_index=True)
    cols = ["area_harvested_ha", "production_t"]
    pam = add_oth(pam, "year", cols); lspa = add_oth(lspa, "survey_month", cols)
    K = Known(pam, lspa, rel)
    others = ["OTH"]

    # 1. features + PIT targets for every (season, as-of, state)
    recs = []
    for Y in range(FIRST_FEAT, a.last_season + 1):
        for T in asof_dates(Y):
            for s in STATES:
                f, cut = make_features(vi, lst, pr, T, Y, s)
                yd = K.yields(s, T, Y - 1)
                tr = trend_at(yd, Y)
                final = pam.set_index(["state", "year"]).yield_kg_ha.get((s, Y), np.nan)
                if not np.isfinite(final):  # current season: latest LSPA vintage (provisional final)
                    final = K.lspa_latest(s, Y, pd.Timestamp.today(), "yield_kg_ha") or np.nan
                recs.append(dict(season=Y, as_of=T, asof_slot=asof_label(T), state=s, trend_yield=tr, final_yield=final,
                                 data_cutoff_vi=cut.get("vi"), data_cutoff_precip=cut.get("precip"), data_cutoff_lst=cut.get("lst"), **f))
    D = pd.DataFrame(recs)
    D["data_cutoff_date"] = D[["data_cutoff_vi", "data_cutoff_precip", "data_cutoff_lst"]].max(axis=1)
    os.makedirs(F, exist_ok=True)
    D.to_csv(f"{F}/asof_features.csv", index=False, float_format="%.5f")

    # 2. walk-forward ridge
    out = []
    for Y in range(FIRST_FEAT + MIN_TRAIN, a.last_season + 1):
        for T in asof_dates(Y):
            lab = asof_label(T)
            cur = D[(D.season == Y) & (D.as_of == T)]
            tr_rows = []
            for Yp in range(FIRST_FEAT, Y):
                Tp = pd.Timestamp(T.year - (Y - Yp), T.month, T.day)
                q = D[(D.season == Yp) & (D.as_of == Tp)].copy()
                # training target as known at T (PAM if published, else latest LSPA)
                for i, rw in q.iterrows():
                    kn = K.yields(rw.state, T, Yp).get(Yp)
                    q.loc[i, "y_known"] = kn
                tr_rows.append(q)
            Tr = pd.concat(tr_rows)
            Tr = Tr[np.isfinite(Tr.trend_yield) & np.isfinite(Tr.y_known)]
            Tr["dev"] = Tr.y_known / Tr.trend_yield - 1
            X, y = Tr[FEATS].values, Tr.dev.values
            fit, beta = ridge_fit(X, y)
            # LOSO residuals for uncertainty (state level and Brazil level)
            res, br_res = [], []
            for Yp in sorted(Tr.season.unique()):
                m = (Tr.season == Yp).values
                f2, _ = ridge_fit(X[~m], y[~m])
                e = f2(X[m]) - y[m]; res.extend(e)
                tw = Tr[m]
                ar = np.array([K.pam.area_harvested_ha.get((s, Yp), np.nan) for s in tw.state])
                pk = tw.trend_yield.values * (1 + f2(X[m])); ok = np.isfinite(ar)
                br_res.append((pk[ok] * ar[ok]).sum() / (tw.y_known.values[ok] * ar[ok]).sum() - 1)
            sig, sig_br = float(np.sqrt(np.mean(np.square(res)))), float(np.sqrt(np.mean(np.square(br_res))))
            pred = fit(cur[FEATS].values)
            tot_p = tot_a = tot_f = 0.0; srcs = set()
            for (i, rw), dv in zip(cur.iterrows(), pred):
                py = rw.trend_yield * (1 + dv)
                ar, src = K.area(rw.state, Y, T); srcs.add(src)
                out.append(dict(as_of_date=T.date().isoformat(), data_cutoff_date=rw.data_cutoff_date, crop_year=f"{Y - 1}/{str(Y)[2:]}",
                                season=Y, asof_slot=lab, state=rw.state, predicted_yield=round(py, 1), trend_yield=round(rw.trend_yield, 1),
                                predicted_dev_vs_trend=round(dv, 4), area_ha_used=round(ar), area_source=src,
                                predicted_production=round(py * ar / 1000), uncertainty_yield_1sd=round(py * sig, 1),
                                final_yield_expost=rw.final_yield, n_train_seasons=Tr.season.nunique(),
                                **{f"coef_{k}": round(b, 5) for k, b in zip(FEATS, beta)}, **{k: round(rw[k], 5) for k in FEATS}))
                tot_p += py * ar / 1000; tot_a += ar
            # other states: trend yield x PIT area
            for s in others:
                ar, _ = K.area(s, Y, T); yd = K.yields(s, T, Y - 1); ty = trend_at(yd, Y)
                if np.isfinite(ar) and np.isfinite(ty):
                    tot_p += ar * ty / 1000; tot_a += ar
            byl = tot_p * 1000 / tot_a
            fin_br = pam.set_index(["state", "year"]).yield_kg_ha.get(("BR", Y), np.nan)
            if not np.isfinite(fin_br):
                fin_br = K.lspa_latest("BR", Y, pd.Timestamp.today(), "yield_kg_ha") or np.nan
            out.append(dict(as_of_date=T.date().isoformat(), data_cutoff_date=cur.data_cutoff_date.max(), crop_year=f"{Y - 1}/{str(Y)[2:]}",
                            season=Y, asof_slot=lab, state="BR", predicted_yield=round(byl, 1), area_ha_used=round(tot_a),
                            area_source="+".join(sorted(srcs)), predicted_production=round(tot_p), uncertainty_yield_1sd=round(byl * sig_br, 1),
                            final_yield_expost=fin_br, n_train_seasons=Tr.season.nunique()))
        print("season", Y, flush=True)
    S = pd.DataFrame(out)
    S.insert(0, "signal_version", VERSION)
    S["uncertainty_production_1sd"] = (S.uncertainty_yield_1sd * S.area_ha_used / 1000).round()
    os.makedirs(f"{HERE}/signal", exist_ok=True)
    dev = S[S.season < a.holdout_from]; hold = S[S.season >= a.holdout_from]
    if a.evaluate_holdout:
        S.to_csv(f"{HERE}/signal/soy_sat_signal_{VERSION}.csv", index=False)
    else:
        dev.to_csv(f"{HERE}/signal/dev_only_signal_{VERSION}.csv", index=False)
        hold.to_csv(f"{HERE}/signal/.sealed_holdout_{VERSION}.csv", index=False)  # not read in dev mode
    print("rows", len(S))


if __name__ == "__main__":
    main()
