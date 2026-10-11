"""Fetch NASA POWER daily meteorology at the cocoa sample points and aggregate to monthly zone means.

Source: https://power.larc.nasa.gov/api/temporal/daily/point (no key; MERRA-2 / GEOS based, ~0.5°).
Parameters: T2M_MAX, T2M_MIN (°C), RH2M (%), QV2M (g/kg), PRECTOTCORR (mm/d), GWETROOT, GWETTOP
(soil wetness 0-1, root zone / surface), ALLSKY_SFC_SW_DWN (MJ/m2/d), WS2M (m/s).
Points: data/sample_points.csv (10 weighted k-means centres per zone, weights = cocoa ha).

Point-in-time caveat: POWER fills the most recent days from GEOS-FP-IT and later back-fills with
MERRA-2; old vintages are not archived, so the history used here is the *current* vintage. Latency was
~3-4 days on 2026-10-11; we model a monthly value as available 7 days after month end.

Outputs: <scratch>/power/<point>.csv (daily raw), <out>/power_monthly_zone.csv
  (month, zone, var, value)  where value = cocoa-ha weighted mean of point monthly means, plus
  derived: tmax_hot_days (days Tmax>=33°C), rh_min_days (days RH2M < 60%: Harmattan proxy).
Usage: python fetch_power.py --points ../data/sample_points.csv --scratch <scratch> --out ../data
"""
import argparse, io, os, time
import numpy as np, pandas as pd, requests

PARAMS = "T2M_MAX,T2M_MIN,RH2M,QV2M,PRECTOTCORR,GWETROOT,GWETTOP,ALLSKY_SFC_SW_DWN,WS2M"
URL = "https://power.larc.nasa.gov/api/temporal/daily/point"


def get(lat, lon, start, end):
    for k in range(6):
        try:
            r = requests.get(URL, params=dict(parameters=PARAMS, community="AG", latitude=lat, longitude=lon,
                                              start=start, end=end, format="CSV"), timeout=300)
            r.raise_for_status()
            txt = r.text
            body = txt.split("-END HEADER-")[1].strip()
            d = pd.read_csv(io.StringIO(body))
            d["date"] = pd.to_datetime(d.YEAR.astype(str) + d.DOY.astype(str).str.zfill(3), format="%Y%j")
            return d.drop(columns=["YEAR", "DOY"]).replace(-999.0, np.nan)
        except Exception as e:  # noqa
            err = e; time.sleep(10 * (k + 1))
    raise RuntimeError(err)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--points", required=True)
    ap.add_argument("--scratch", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", default="19840101")
    ap.add_argument("--end", default=pd.Timestamp.today().strftime("%Y%m%d"))
    a = ap.parse_args()
    P = pd.read_csv(a.points)
    os.makedirs(f"{a.scratch}/power", exist_ok=True)
    rows = []
    for p in P.itertuples():
        fn = f"{a.scratch}/power/{p.point}.csv"
        if not os.path.exists(fn):
            get(p.lat, p.lon, a.start, a.end).to_csv(fn, index=False); print("got", p.point, flush=True)
        d = pd.read_csv(fn, parse_dates=["date"])
        d["month"] = d.date.dt.to_period("M").dt.to_timestamp()
        d["hot"] = (d.T2M_MAX >= 33).astype(float).where(d.T2M_MAX.notna())
        d["dry"] = (d.RH2M < 60).astype(float).where(d.RH2M.notna())
        m = d.groupby("month").agg(tmax=("T2M_MAX", "mean"), tmin=("T2M_MIN", "mean"), rh=("RH2M", "mean"), qv=("QV2M", "mean"),
                                   precip_power=("PRECTOTCORR", "sum"), gwetroot=("GWETROOT", "mean"), gwettop=("GWETTOP", "mean"),
                                   srad=("ALLSKY_SFC_SW_DWN", "mean"), ws=("WS2M", "mean"), tmax_hot_days=("hot", "sum"),
                                   rh_dry_days=("dry", "sum"), ndays=("T2M_MAX", "count"))
        m = m.assign(point=p.point, zone=p.zone, w=p.w_ha).reset_index()
        rows.append(m)
    M = pd.concat(rows)
    M = M[M.ndays >= 25]  # complete months only
    out = []
    for z in ["CIV_W", "CIV_E", "GHA", "ALL"]:
        g = M if z == "ALL" else M[M.zone == z]
        vars_ = [c for c in g.columns if c not in ("month", "point", "zone", "w", "ndays")]
        agg = g.groupby("month").apply(lambda x: pd.Series({v: np.average(x[v], weights=x.w) for v in vars_}), include_groups=False)
        agg = agg.reset_index().melt(id_vars="month", var_name="var", value_name="value").assign(zone=z)
        out.append(agg)
    O = pd.concat(out)[["month", "zone", "var", "value"]].sort_values(["var", "zone", "month"])
    O.to_csv(f"{a.out}/power_monthly_zone.csv", index=False, float_format="%.4f")
    print(O.month.min(), O.month.max(), len(O))


if __name__ == "__main__":
    main()
