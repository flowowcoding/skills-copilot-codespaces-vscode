#!/usr/bin/env python3
"""Walk-forward satellite + weather wheat production model for Russia, Ukraine and Kazakhstan
(pre-registered spec in README.md), producing the point-in-time signal dataset.

Unit: country c, harvest year Y, forecast date T. Forecast dates:
  * "wasde": every WASDE release R from May(Y) to Jan(Y+1); T = R - 1 day.
  * "weekly": T = Apr 1 + 7k days of year Y (k = 0..39, to Dec 30).
Training years for the same calendar offset (T - Jan 1 of Y) are used, so a model is always
trained on features observable at the same point of the season.

Inputs at T (point-in-time):
  * MODIS Aqua composites whose end date + 14 days <= T.
  * Weather (NASA POWER) days <= T - 5.
  * Winter mask: w121 (Apr 15-May 16 EVI) when its composites are usable at T, else w89.
  * Truth for training years and the trend: the latest USDA WASDE estimate published before T
    (USDA PSD current values for years before 2002, which no WASDE vintage covers).

Features (country level = area-weighted over regions; weights = WorldCover cropland cells x
share of sample pixels in the winter (or spring) mask that year):
  evi_w   mean over usable winter-window composites (Y-1 DOY 281, 297; Y DOY 73..185) of the
          winter-mask EVI minus a country x composite linear trend fitted on training years
  prcp_w  winter zones, Apr 1 .. min(T-5, Jun 30) precipitation / training mean - 1
  hdd_w   winter zones, May 1 .. min(T-5, Jun 30) sum max(Tmax - 30 C, 0), minus training mean
  frost_w winter zones, cell-days with Tmin <= -18 C and snow depth < 5 cm (Dec 1 .. Mar 31) plus
          cell-days with Tmin <= -2 C (Apr 20 .. May 31), up to T-5 (computed per POWER cell, then
          averaged), minus training mean
  evi_s   as evi_w for the spring mask, composites DOY 153..233, spring-wheat regions only
          (RU_Volga, RU_UralsSiberia, KZ_North, KZ_Other)
  prcp_s  spring regions, May 1 .. min(T-5, Jul 31) precipitation / training mean - 1
  hdd_s   spring regions, Jun 1 .. min(T-5, Aug 10) heat degree days minus training mean
  Ukraine has no spring features (0); Kazakhstan has no winter features (0).
Target: ln(truth / trend), trend = Theil-Sen line through truth of years Y-15..Y-1.
Model: pooled ridge over the three countries, features z-scored within country on the training
years (v1: winsorised at +-3), target scaled by its within-country training sd (v1), country
intercepts unpenalised, alpha = 3, training years 2003..Y-1. Ukraine 2022+
(war: area loss and occupied territory) is excluded from training.
Estimate: S = trend x exp(prediction); uncertainty = leave-one-year-out RMSE in training (per country).
Spec history: v0 = first coded version (no target scaling, no winsorising); v1 = the two changes,
made after the first development run (see README disclosure). Both are scored on the holdout
(signal tags v0_first and v1).

Usage: python model.py [--feats evi_w,prcp_w,...] [--tag v1]
Writes data/signal/bsw_signal_<tag>.csv (+ MANIFEST json)
"""
import argparse
import datetime as dt
import hashlib
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "..", "data")
COUNTRIES = ["Russia", "Ukraine", "Kazakhstan"]
SPRING_REG = {"RU_Volga", "RU_UralsSiberia", "KZ_North", "KZ_Other"}
WIN_DOYS = [(-1, 281), (-1, 297), (0, 73), (0, 89), (0, 105), (0, 121), (0, 137), (0, 153), (0, 169), (0, 185)]
SPR_DOYS = [153, 169, 185, 201, 217, 233]
ALL_FEATS = ["evi_w", "prcp_w", "hdd_w", "frost_w", "evi_s", "prcp_s", "hdd_s"]
ALPHA = 3.0
FIRST_TRAIN = 2003
VERSION = "bsw_sat_v1"


def theil_sen(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    i, j = np.triu_indices(len(x), 1)
    s = np.median((y[j] - y[i]) / (x[j] - x[i]))
    b = np.median(y - s * x)
    return b, s


class Truth:
    """Latest USDA estimate of (country, year) published before a date."""

    def __init__(self):
        w = pd.read_csv(os.path.join(D, "benchmark", "wasde_wheat_vintages.csv"), parse_dates=["release_date"])
        w = w[(w.attribute == "Production") & w.region.isin(COUNTRIES + ["United States"])]
        self.v = {k: g.sort_values("release_date")[["release_date", "value_mmt"]].values
                  for k, g in w.groupby(["region", "crop_year"])}
        f = pd.read_csv(os.path.join(D, "benchmark", "final_outturns.csv"))
        f = f[(f.source == "usda_psd_current") & (f.variable == "production")]
        self.psd = {(r.country, r.crop_year): r.value for r in f.itertuples()}
        self.releases = np.array(sorted(w.release_date.unique()))

    def asof(self, c, y, t):
        a = self.v.get((c, y))
        if a is not None:
            m = a[:, 0] < np.datetime64(t)
            if m.any():
                return float(a[m][-1, 1])
            return None
        if y < 2002:
            return self.psd.get((c, y))
        return None

    def final(self, c, y):
        a = self.v.get((c, y))
        return float(a[-1, 1]) if a is not None else None


class Feats:
    def __init__(self):
        r = pd.read_csv(os.path.join(D, "features", "modis_region.csv"), parse_dates=["available_date"])
        self.evi = {(x.region, x.year, x.doy, x.mask): (x.evi_mean, x.available_date.to_datetime64(), x.n_valid)
                    for x in r.itertuples()}
        cls = pd.read_csv(os.path.join(D, "features", "pixel_class.csv.gz"))
        px = pd.read_csv(os.path.join(D, "reference", "pixels.csv"))
        cls = cls.merge(px[["pixel_id"]], on="pixel_id")
        sh = {}
        for (reg, y), g in cls.groupby(["region", "year"]):
            n = len(px[px.region == reg])
            sh[(reg, y, "w89")] = (g.w89 == 1).sum() / n
            sh[(reg, y, "w121")] = (g.w121.fillna(g.w89) == 1).sum() / n
        self.share = sh
        cells = pd.read_csv(os.path.join(D, "reference", "region_cropland_cells.csv")).groupby(["country", "region"]).cropland_cells.sum()
        self.cells = cells
        self.regions = {c: list(cells.loc[c].index) for c in COUNTRIES}
        w = pd.read_csv(os.path.join(D, "features", "weather_region_daily.csv"), parse_dates=["date"])
        self.wx, self.cum = {}, {}
        for reg, g in w.groupby("region"):
            g = g.sort_values("date")
            self.wx[reg] = g.date.values.astype("datetime64[D]")
            self.cum[reg] = {c: np.concatenate([[0.0], np.cumsum(g[c].fillna(0).values)]) for c in ["prcp", "hdd", "wk", "fr"]}
        self.cache = {}

    def wsum(self, reg, col, a, b):
        """Sum of a daily weather column over [a, b] (inclusive) via cumulative sums."""
        if b < a:
            return 0.0
        d = self.wx[reg]
        i = np.searchsorted(d, np.datetime64(pd.Timestamp(a).date()), "left")
        j = np.searchsorted(d, np.datetime64(pd.Timestamp(b).date()), "right")
        if j <= i:
            return np.nan
        c = self.cum[reg][col]
        return float(c[j] - c[i])

    def region(self, reg, y, t):
        """Raw region features at cutoff t for harvest year y."""
        t = pd.Timestamp(t)
        cut = t - pd.Timedelta(days=5)
        Y = lambda m, d, yy=y: pd.Timestamp(yy, m, d)  # noqa
        # winter mask definition usable at t
        e121 = self.evi.get((reg, y, 121, "winter121"))
        use121 = e121 is not None and e121[1] <= np.datetime64(t)
        mk = "winter121" if use121 else "winter89"
        ew = {}
        for off, doy in WIN_DOYS:
            v = self.evi.get((reg, y, doy, mk))
            if v is not None and v[1] <= np.datetime64(t) and v[2] >= 20:
                ew[(off, doy)] = v[0]
        es = {}
        for doy in SPR_DOYS:
            v = self.evi.get((reg, y, doy, "spring"))
            if v is not None and v[1] <= np.datetime64(t) and v[2] >= 20:
                es[doy] = v[0]
        f = dict(
            prcp_w=self.wsum(reg, "prcp", Y(4, 1), min(cut, Y(6, 30))) if cut >= Y(4, 1) else np.nan,
            hdd_w=self.wsum(reg, "hdd", Y(5, 1), min(cut, Y(6, 30))) if cut >= Y(5, 1) else 0.0,
            frost_w=self.wsum(reg, "wk", Y(12, 1, y - 1), min(cut, Y(3, 31))) +
            (self.wsum(reg, "fr", Y(4, 20), min(cut, Y(5, 31))) if cut >= Y(4, 20) else 0.0),
            prcp_s=self.wsum(reg, "prcp", Y(5, 1), min(cut, Y(7, 31))) if cut >= Y(5, 1) else np.nan,
            hdd_s=self.wsum(reg, "hdd", Y(6, 1), min(cut, Y(8, 10))) if cut >= Y(6, 1) else 0.0)
        wsh = self.share.get((reg, y, "w121" if use121 else "w89"), np.nan)
        return f, ew, es, wsh

    def country(self, c, y, t):
        key = (c, y, pd.Timestamp(t))
        if key in self.cache:
            return self.cache[key]
        regs = [r for r in self.regions[c] if r in self.wx]
        num = {k: 0.0 for k in ["prcp_w", "hdd_w", "frost_w", "prcp_s", "hdd_s"]}
        den = {"w": 0.0, "s": 0.0}
        ew, es, wew, wes = {}, {}, {}, {}
        for reg in regs:
            f, e1, e2, wsh = self.region(reg, y, t)
            if not np.isfinite(wsh):
                wsh = 0.0
            ww = self.cells.loc[(c, reg)] * wsh if c != "Kazakhstan" else 0.0
            sw = self.cells.loc[(c, reg)] * (1 - wsh) if reg in SPRING_REG else 0.0
            for k in ["prcp_w", "hdd_w", "frost_w"]:
                num[k] += ww * (f[k] if np.isfinite(f[k]) else 0.0)
            for k in ["prcp_s", "hdd_s"]:
                num[k] += sw * (f[k] if np.isfinite(f[k]) else 0.0)
            den["w"] += ww
            den["s"] += sw
            for k, v in e1.items():
                ew[k] = ew.get(k, 0.0) + ww * v
                wew[k] = wew.get(k, 0.0) + ww
            for k, v in e2.items():
                es[k] = es.get(k, 0.0) + sw * v
                wes[k] = wes.get(k, 0.0) + sw
        out = {}
        for k in ["prcp_w", "hdd_w", "frost_w"]:
            out[k] = num[k] / den["w"] if den["w"] > 0 else np.nan
        for k in ["prcp_s", "hdd_s"]:
            out[k] = num[k] / den["s"] if den["s"] > 0 else np.nan
        out["ew"] = {k: ew[k] / wew[k] for k in ew if wew[k] > 0}
        out["es"] = {k: es[k] / wes[k] for k in es if wes[k] > 0}
        self.cache[key] = out
        return out


def build_X(rows, train_mask, feats):
    """rows: list of dicts with raw country features; returns design matrix (z-scored within
    country on training rows) for the requested features."""
    df = pd.DataFrame(rows)
    X = pd.DataFrame(index=df.index)
    for c in COUNTRIES:
        ic = df.country == c
        tr = ic & train_mask
        if not tr.any():
            continue
        # EVI: detrended composite anomalies averaged over composites usable at T
        for fe, key in [("evi_w", "ew"), ("evi_s", "es")]:
            comps = sorted({k for d in df.loc[tr, key] for k in d})
            target_comps = df.loc[ic & ~train_mask, key]
            res = pd.DataFrame(index=df.index[ic])
            for k in comps:
                yv = df.loc[ic, key].map(lambda d: d.get(k, np.nan))
                trv = yv[tr].dropna()
                if len(trv) < 4:
                    continue
                yrs = df.loc[trv.index, "year"].astype(float)
                sl, ic0 = np.polyfit(yrs, trv.values, 1)
                res[k] = yv - (ic0 + sl * df.loc[ic, "year"])
            X.loc[ic, fe] = res.mean(axis=1) if res.shape[1] else 0.0
        for fe in ["prcp_w", "prcp_s"]:
            m = df.loc[tr, fe].mean()
            X.loc[ic, fe] = df.loc[ic, fe] / m - 1 if np.isfinite(m) and m > 0 else 0.0
        for fe in ["hdd_w", "frost_w", "hdd_s"]:
            X.loc[ic, fe] = df.loc[ic, fe] - df.loc[tr, fe].mean()
    X = X.reindex(columns=ALL_FEATS).astype(float)
    # z-score within country on training rows; features with no variance -> 0
    for c in COUNTRIES:
        ic = df.country == c
        tr = ic & train_mask
        for fe in ALL_FEATS:
            sd = X.loc[tr, fe].std()
            if not np.isfinite(sd) or sd < 1e-9:
                X.loc[ic, fe] = 0.0
            else:
                X.loc[ic, fe] = (X.loc[ic, fe] - X.loc[tr, fe].mean()) / sd
    X = X[feats].fillna(0.0)
    if SPEC[0] == "v1":  # SPEC v1: winsorise z-scores at +-3 (one extreme heat/frost season set the 2009-10 forecasts)
        X = X.clip(-3, 3)
    return X


def ridge_fit(X, y, g, alpha):
    """Country intercepts unpenalised (features are within-country demeaned on training).
    SPEC v1: the target is also scaled by its within-country training sd before the pooled fit, so the
    volatile Kazakh/Ukrainian targets do not set the coefficients applied to Russia; predictions are
    mu_c + sd_c * X beta. SPEC v0: no scaling (sd_c = 1)."""
    mu = y.groupby(g).mean()
    sd = y.groupby(g).std() if SPEC[0] == "v1" else y.groupby(g).std() * 0 + 1.0
    sd = sd.fillna(1.0).replace(0, 1.0)
    yc = (y - g.map(mu)) / g.map(sd)
    A = X.values
    beta = np.linalg.solve(A.T @ A + alpha * np.eye(A.shape[1]), A.T @ yc.values)
    return (mu, sd), beta


def forecast(F, T, Y, t, cutoff_offset, feats, alpha):
    """Train on years FIRST_TRAIN..Y-1 at the same seasonal offset; predict all countries for Y."""
    rows = []
    for y in range(FIRST_TRAIN, Y + 1):
        ty = pd.Timestamp(y, 1, 1) + pd.Timedelta(days=cutoff_offset) if y < Y else pd.Timestamp(t)
        for c in COUNTRIES:
            if c == "Ukraine" and y >= 2022 and y < Y:
                continue
            truth = T.asof(c, y, t) if y < Y else None
            hist = [(k, T.asof(c, k, t)) for k in range(y - 15, y)]
            hist = [(k, v) for k, v in hist if v is not None]
            if len(hist) < 8:
                continue
            b, s = theil_sen([k for k, _ in hist], [v for _, v in hist])
            trend = b + s * y
            fr = F.country(c, y, ty)
            rows.append(dict(country=c, year=y, t=ty, trend=trend, truth=truth,
                             target=np.log(truth / trend) if truth else np.nan, **{k: fr[k] for k in fr}))
    df = pd.DataFrame(rows)
    train = (df.year < Y) & df.target.notna()
    X = build_X(df.to_dict("records"), train.values, feats)
    (mu, sd), beta = ridge_fit(X[train], df.target[train], df.country[train], alpha)

    def pred_of(m, s_, b, idx):
        g = df.country[idx]
        return g.map(m).fillna(0).values + g.map(s_).fillna(1.0).values * (X[idx].values @ b)

    # leave-one-year-out RMSE within training, per country
    errs = {c: [] for c in COUNTRIES}
    for yy in sorted(df.year[train].unique()):
        tr2 = train & (df.year != yy)
        if tr2.sum() < 6:
            continue
        (m2, s2), b2 = ridge_fit(X[tr2], df.target[tr2], df.country[tr2], alpha)
        te = train & (df.year == yy)
        for c, e in zip(df.country[te], df.target[te].values - pred_of(m2, s2, b2, te)):
            errs[c].append(e)
    rmse = {c: float(np.sqrt(np.mean(np.square(v)))) if v else np.nan for c, v in errs.items()}
    out = []
    te = df.year == Y
    pred = pred_of(mu, sd, beta, te)
    for i, p in zip(df.index[te], pred):
        r = df.loc[i]
        out.append(dict(country=r.country, year=Y, forecast_date=pd.Timestamp(t).date(), pred_dev_log=p,
                        trend_mmt=r.trend, sat_estimate_mmt=r.trend * np.exp(p), uncertainty_log=rmse[r.country],
                        n_train=int(train.sum()), n_train_years=int(df.year[train].nunique()),
                        n_evi_w_comps=len(r.ew), n_evi_s_comps=len(r.es),
                        **{f"x_{k}": X.loc[i, k] for k in feats}, **{f"b_{k}": b for k, b in zip(feats, beta)}))
    return out


_FT = {}


def run_year(arg):
    """All forecasts for one harvest year (worker for multiprocessing)."""
    Y, js, feats, alpha = arg
    if "F" not in _FT:
        _FT["T"], _FT["F"] = Truth(), Feats()
    T, F = _FT["T"], _FT["F"]
    today = pd.Timestamp("2026-10-11")
    out = []
    for (Y_, t, kind, rel) in js:
        if t > today:
            continue
        off = (t - pd.Timestamp(Y, 1, 1)).days
        for r in forecast(F, T, Y, t, off, feats, alpha):
            usda = T.asof(r["country"], Y, t + pd.Timedelta(days=1))  # latest USDA published on or before T
            r.update(kind=kind, next_release=rel, data_cutoff_vi=(t - pd.Timedelta(days=14)).date(),
                     data_cutoff_weather=(t - pd.Timedelta(days=5)).date(), usda_latest_mmt=usda,
                     gap_sat_usda_pct=100 * np.log(r["sat_estimate_mmt"] / usda) if usda else np.nan,
                     final_usda_expost=T.final(r["country"], Y), model_version=f"{VERSION}_{TAG[0]}",
                     ukraine_war_flag=int(r["country"] == "Ukraine" and Y >= 2022))
            out.append(r)
    print("year done", Y, len(out), flush=True)
    return out


TAG = ["v1"]
SPEC = ["v1"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--feats", default=",".join(ALL_FEATS))
    ap.add_argument("--tag", default="v1")
    ap.add_argument("--alpha", type=float, default=ALPHA)
    ap.add_argument("--years", default="2006-2026")
    ap.add_argument("--no-weekly", action="store_true")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--spec", default="v1", choices=["v0", "v1"],
                    help="v1 (default, pre-registered): per-country target scaling + z-score winsorising; v0: as first coded")
    a = ap.parse_args()
    feats = a.feats.split(",")
    y0, y1 = [int(x) for x in a.years.split("-")]
    TAG[0] = a.tag
    SPEC[0] = a.spec
    T = Truth()
    jobs = []
    for Y in range(y0, y1 + 1):
        for r in T.releases:
            r = pd.Timestamp(r)
            sm = (r.year - Y) * 12 + r.month - 4
            if 1 <= sm <= 9:
                jobs.append((Y, r - pd.Timedelta(days=1), "wasde", r.date()))
        if not a.no_weekly:
            for k in range(40):
                jobs.append((Y, pd.Timestamp(Y, 4, 1) + pd.Timedelta(days=7 * k), "weekly", None))
    by_year = {}
    for j in jobs:
        by_year.setdefault(j[0], []).append(j)
    args = [(Y, js, feats, a.alpha) for Y, js in sorted(by_year.items())]
    if a.jobs > 1:
        import multiprocessing as mp
        with mp.Pool(a.jobs) as pool:
            parts = pool.map(run_year, args)
    else:
        parts = [run_year(x) for x in args]
    out = [r for p in parts for r in p]
    o = pd.DataFrame(out)
    os.makedirs(os.path.join(D, "signal"), exist_ok=True)
    fn = os.path.join(D, "signal", f"bsw_signal_{a.tag}.csv")
    o.to_csv(fn, index=False, float_format="%.5f")
    man = dict(dataset=f"{VERSION}_{a.tag}", spec=a.spec, built_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               rows=len(o), feats=feats, alpha=a.alpha,
               sha256={os.path.basename(fn): hashlib.sha256(open(fn, "rb").read()).hexdigest(),
                       "model.py": hashlib.sha256(open(__file__, "rb").read()).hexdigest()})
    json.dump(man, open(os.path.join(D, "signal", f"MANIFEST_{a.tag}.json"), "w"), indent=1)
    print("rows", len(o))


if __name__ == "__main__":
    main()
