"""Point-in-time satellite + weather features per crop, season and as-of date.

Crops (ICRISAT weight key): gram (chickpea, rabi), tur (pigeonpea, kharif), sugarcane.
Season label Y = calendar year in which the agricultural year (Jul Y-1 .. Jun Y) ends; "2021-22" -> 2022.

Windows (fixed a priori from crop calendars, never tuned):
  gram : rain Aug(Y-1)-Mar(Y) [monsoon tail recharges the stored soil moisture rabi chickpea grows on],
         soil Oct 15 - Mar 31, EVI composites starting Nov 15 - Mar 15, heat (Tmax >= 35 C) Feb 1 - Mar 31
  tur  : rain Jun-Nov(Y-1), soil Jul 1 - Dec 31, EVI composites starting Aug 1 - Dec 31
  cane : rain Jun-Oct(Y-1), soil Jun 1 (Y-1) - Feb 28 (Y), EVI composites starting Aug 1 - Jan 31
Components at as-of t (only inputs with available_date <= t):
  evi  : crop-area-weighted mean over core districts of the mean district EVI anomaly of usable composites
  rain : crop-weighted CHIRPS total over usable months in the window
  soil : mean crop-weighted NASA POWER GWETROOT over window days <= t - 7
  heat : sum of crop-weighted share of area with Tmax >= 35 C over window days <= t - 7 (gram only)
Each component is z-scored against the same component for every earlier season evaluated at the same
calendar offset (as-of shifted by whole years), needing >= 5 earlier seasons. index = mean of available
z's with signs (+evi, +rain, +soil, -heat).

Usage (library): from build_features import Features; F = Features(data_dir); F.index('gram', 2022, '2022-02-14')
CLI: python build_features.py --data ../data --crop gram --season 2022 --asof 2022-02-14
"""
import argparse
from functools import lru_cache
import numpy as np, pandas as pd

WKEY = {"gram": "chickpea", "tur": "pigeonpea", "sugarcane": "sugarcane"}
WIN = {
    "gram": dict(rain=((-1, 8, 1), (0, 3, 31)), soil=((-1, 10, 15), (0, 3, 31)), evi=((-1, 11, 15), (0, 3, 15)), heat=((0, 2, 1), (0, 3, 31))),
    "tur": dict(rain=((-1, 6, 1), (-1, 11, 30)), soil=((-1, 7, 1), (-1, 12, 31)), evi=((-1, 8, 1), (-1, 12, 31)), heat=None),
    "sugarcane": dict(rain=((-1, 6, 1), (-1, 10, 31)), soil=((-1, 6, 1), (0, 2, 28)), evi=((-1, 8, 1), (0, 1, 31)), heat=None),
}
SIGN = {"evi": 1, "rain": 1, "soil": 1, "heat": -1}
FIRST_SEASON = 2001


def d(Y, spec):
    dy, m, day = spec
    return pd.Timestamp(Y + dy, m, day)


def shift(t, years):
    t = pd.Timestamp(t)
    try:
        return t.replace(year=t.year + years)
    except ValueError:  # Feb 29
        return t.replace(year=t.year + years, day=28)


class Features:
    def __init__(self, data):
        dw = pd.read_csv(f"{data}/district_weights.csv")
        self.w = {c: dw[dw[f"core_{k}"] == 1].set_index("dist_code")[f"share_{k}"] for c, k in WKEY.items()}
        e = pd.read_csv(f"{data}/evi_district_composite.csv", parse_dates=["start", "end", "available_date"])
        self.evi = e.dropna(subset=["evi_anom"])
        ch = pd.read_csv(f"{data}/chirps_district_monthly.csv", parse_dates=["available_date"])
        ch["mstart"] = pd.to_datetime(ch.month + "-01")
        self.ch = ch.dropna(subset=["precip_mm"])
        wd = pd.read_csv(f"{data}/weather_crop_daily.csv", parse_dates=["date"])
        self.wd = {c: g.set_index("date") for c, g in wd.groupby("crop")}

    def _wavg(self, s, crop):
        w = self.w[crop].reindex(s.index).dropna()
        s = s.reindex(w.index).dropna(); w = w.reindex(s.index)
        return float((s * w).sum() / w.sum()) if len(s) and w.sum() > 0 else np.nan

    @lru_cache(maxsize=None)
    def raw(self, crop, Y, asof):
        t = pd.Timestamp(asof); W = WIN[crop]; out = {}
        a, b = d(Y, W["evi"][0]), d(Y, W["evi"][1])
        e = self.evi[(self.evi.start >= a) & (self.evi.start <= b) & (self.evi.available_date <= t)]
        out["evi"] = self._wavg(e.groupby("dist_code").evi_anom.mean(), crop) if len(e) else np.nan
        a, b = d(Y, W["rain"][0]), d(Y, W["rain"][1])
        c = self.ch[(self.ch.mstart >= a) & (self.ch.mstart <= b) & (self.ch.available_date <= t)]
        out["rain"] = self._wavg(c.groupby("dist_code").precip_mm.sum(), crop) if len(c) else np.nan
        wd = self.wd[WKEY[crop]]
        a, b = d(Y, W["soil"][0]), min(d(Y, W["soil"][1]), t - pd.Timedelta(days=7))
        s = wd.loc[a:b, "gwetroot"] if b >= a else pd.Series(dtype=float)
        out["soil"] = float(s.mean()) if len(s) >= 7 else np.nan
        out["heat"] = np.nan
        if W["heat"]:
            a, b = d(Y, W["heat"][0]), min(d(Y, W["heat"][1]), t - pd.Timedelta(days=7))
            s = wd.loc[a:b, "heat35_share"] if b >= a else pd.Series(dtype=float)
            out["heat"] = float(s.sum()) if len(s) >= 5 else np.nan
        return out

    def z(self, crop, Y, asof, min_prior=5):
        cur = self.raw(crop, Y, str(pd.Timestamp(asof).date()))
        hist = [self.raw(crop, y, str(shift(asof, y - Y).date())) for y in range(FIRST_SEASON, Y)]
        zs = {}
        for k, v in cur.items():
            h = np.array([x[k] for x in hist], dtype=float); h = h[~np.isnan(h)]
            zs[k] = (v - h.mean()) / h.std(ddof=1) if (not np.isnan(v) and len(h) >= min_prior and h.std(ddof=1) > 0) else np.nan
        return zs, cur

    def index(self, crop, Y, asof):
        zs, cur = self.z(crop, Y, asof)
        vals = [SIGN[k] * v for k, v in zs.items() if not np.isnan(v)]
        return (float(np.mean(vals)) if vals else np.nan), zs, cur


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default="../data")
    ap.add_argument("--crop", required=True, choices=list(WKEY))
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--asof", required=True)
    a = ap.parse_args()
    print(Features(a.data).index(a.crop, a.season, a.asof))


if __name__ == "__main__":
    main()
