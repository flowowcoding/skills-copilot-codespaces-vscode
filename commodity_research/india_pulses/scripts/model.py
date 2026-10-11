"""Satellite production model and versioned point-in-time signal dataset (v1).

For crop c, season Y and as-of date t:
  trend(Y,t)  OLS line through log(final) of the last 10 seasons before Y whose FINAL was public at t
              (ae_vintages.csv), evaluated at Y (>= 6 finals needed).
  x(Y,t)      satellite/weather index (build_features.Features.index).
  fit         y_s = log(final_s) - trend(s,t) on x(s, t shifted to season s) for seasons 2006..Y-1 with
              finals public at t (>= 5 needed); OLS with intercept.
  sat_pred    exp(trend(Y,t) + a + b * x(Y,t)); 90% band from the training residual s.d.
  official    latest GoI estimate of season Y public at t (stage, value, date); gap = log(sat_pred/official).
As-of grids: (1) month-ends in each crop's season window; (2) the day before every GoI release for the
crop (for the revision test).

Development mode (--mode dev) writes rows of the held-out seasons (2022-23 .. 2025-26, i.e. Y >= 2023)
only to ../signal/.sealed_holdout_v1.csv, which evaluation code in dev mode never reads.
--mode final writes everything to ../signal/india_signal_v1.csv.

Usage: python model.py --data ../data --out ../signal --mode dev|final
"""
import argparse, datetime as dt, hashlib, os
import numpy as np, pandas as pd
from build_features import Features, shift

VERSION = "v1"
HOLDOUT_FIRST = 2023          # season label: 2022-23 and later are held out
MONTHS = {"gram": [(-1, 11), (-1, 12), (0, 1), (0, 2), (0, 3), (0, 4)],
          "tur": [(-1, 8), (-1, 9), (-1, 10), (-1, 11), (-1, 12), (0, 1)],
          "sugarcane": [(-1, 7), (-1, 8), (-1, 9), (-1, 10), (-1, 11), (-1, 12), (0, 1)]}
SEASONS = range(2006, 2027)


def season_label(Y):
    return f"{Y - 1}-{str(Y)[2:]}"


def season_year(lbl):
    return int(lbl[:4]) + 1


class Model:
    def __init__(self, data):
        self.F = Features(data)
        v = pd.read_csv(f"{data}/ae_vintages.csv", parse_dates=["release_date"])
        v["Y"] = v.season.map(season_year)
        self.v = v

    def finals(self, crop, t):
        f = self.v[(self.v.crop == crop) & (self.v.stage == "FINAL") & (self.v.release_date <= t)]
        return f.sort_values("release_date").groupby("Y").value.last()

    def trend(self, fin, Y):
        h = fin[(fin.index < Y) & (fin.index >= Y - 10)]
        if len(h) < 6:
            return np.nan
        b, a = np.polyfit(h.index.values.astype(float), np.log(h.values), 1)
        return a + b * Y

    def official(self, crop, Y, t):
        o = self.v[(self.v.crop == crop) & (self.v.Y == Y) & (self.v.release_date <= t)]
        if not len(o):
            return None, np.nan, None
        r = o.sort_values("release_date").iloc[-1]
        return r.stage, r.value, r.release_date.date()

    def predict(self, crop, Y, t):
        t = pd.Timestamp(t)
        fin = self.finals(crop, t)
        trY = self.trend(fin, Y)
        xY, zs, raw = self.F.index(crop, Y, t)
        X, y = [], []
        for s in range(2006, Y):
            if s in fin.index:
                ts = self.trend(fin, s); xs = self.F.index(crop, s, shift(t, s - Y))[0]
                if not (np.isnan(ts) or np.isnan(xs)):
                    X.append(xs); y.append(np.log(fin[s]) - ts)
        out = dict(trend_log=trY, index=xY, n_train=len(X), **{f"z_{k}": v for k, v in zs.items()})
        if len(X) >= 5 and not np.isnan(xY) and not np.isnan(trY):
            b, a = np.polyfit(X, y, 1)
            res = np.array(y) - (a + b * np.array(X)); sd = res.std(ddof=2) if len(X) > 2 else np.nan
            p = trY + a + b * xY
            out.update(coef_a=a, coef_b=b, resid_sd=sd, sat_pred=np.exp(p), sat_lo=np.exp(p - 1.645 * sd), sat_hi=np.exp(p + 1.645 * sd),
                       sat_anom=a + b * xY)
        st, val, rd = self.official(crop, Y, t)
        out.update(official_stage=st, official_value=val, official_date=rd,
                   official_anom=(np.log(val) - trY) if st else np.nan)
        out["gap_log"] = np.log(out["sat_pred"] / val) if (st and "sat_pred" in out) else np.nan
        return out


def sha(fn):
    return hashlib.sha256(open(fn, "rb").read()).hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="../data")
    ap.add_argument("--out", default="../signal")
    ap.add_argument("--mode", choices=["dev", "final"], required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    M = Model(a.data)
    here = os.path.dirname(os.path.abspath(__file__))
    shas = {f: sha(os.path.join(here, f)) for f in ["model.py", "build_features.py", "build_evi.py"]}
    rows = []
    today = pd.Timestamp("2026-10-11")
    for crop, months in MONTHS.items():
        for Y in SEASONS:
            grid = [("month_end", (pd.Timestamp(Y + dy, m, 1) + pd.offsets.MonthEnd(0))) for dy, m in months]
            rel = M.v[(M.v.crop == crop) & (M.v.Y == Y) & (M.v.date_approx == 0)]
            grid += [(f"pre_{r.stage}", r.release_date - pd.Timedelta(days=1)) for r in rel.itertuples()]
            for kind, t in grid:
                if t > today:
                    continue
                r = M.predict(crop, Y, t)
                rows.append(dict(crop=crop, season=season_label(Y), Y=Y, asof=t.date(), asof_kind=kind, **r))
        print(crop, "done", flush=True)
    d = pd.DataFrame(rows)
    d["model_version"] = VERSION
    d["code_sha"] = ";".join(f"{k}:{v}" for k, v in shas.items())
    d["created_utc"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cols = ["crop", "season", "Y", "asof", "asof_kind", "official_stage", "official_value", "official_date", "z_evi", "z_rain", "z_soil",
            "z_heat", "index", "n_train", "trend_log", "coef_a", "coef_b", "resid_sd", "sat_anom", "sat_pred", "sat_lo", "sat_hi",
            "official_anom", "gap_log", "model_version", "code_sha", "created_utc"]
    d = d.reindex(columns=cols)
    if a.mode == "dev":
        d[d.Y < HOLDOUT_FIRST].to_csv(f"{a.out}/india_signal_{VERSION}_dev.csv", index=False, float_format="%.5f")
        d[d.Y >= HOLDOUT_FIRST].to_csv(f"{a.out}/.sealed_holdout_{VERSION}.csv", index=False, float_format="%.5f")
    else:
        d.to_csv(f"{a.out}/india_signal_{VERSION}.csv", index=False, float_format="%.5f")
    print(len(d), shas)


if __name__ == "__main__":
    main()
