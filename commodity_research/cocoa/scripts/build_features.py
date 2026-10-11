"""Build point-in-time weather/satellite features for the cocoa belt (as pre-registered in README.md).

Inputs (data/): chirps_monthly_zone.csv, power_monthly_zone.csv, modis_pixels.csv;
                <work>/modis/*.npz + <work>/modis_items.csv from extract_modis.py
Outputs:
  data/modis_evi_composites.csv  composite-level zone means (start, end, avail, zone, evi_mean, evi_z, cloud_frac)
  data/feature_windows.csv       window statistics per end-period with availability date and z-score
  data/features_monthly.csv      wide table: as-of = each month end 2003-10 .. last, zone, features + DRY/WETX
Functions `features_at(dates)` can be imported by evaluate.py for arbitrary as-of dates.

Point-in-time rules: CHIRPS month available on its posted date; POWER month available at month end + 7 d;
MODIS composite available at production date + 2 d (if produced within 30 d of composite end, else end + 20 d,
because C6.1 was reprocessed in 2020-21). z-scores use 2003–2021 window statistics for the
same calendar end-month; windows ending > 75 days before the as-of date are treated as missing (MODIS: pixel day-of-year climatology 2003–2021, then the window mean is
re-standardised by calendar month of the composite end date).
Usage: python build_features.py --work <scratch>
"""
import argparse, glob, os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
CLIM = (2003, 2021)
ZONES = ["ALL", "CIV_W", "CIV_E", "GHA"]
MAX_STALE_DAYS = 75  # a window whose last observation ends > 75 d before as-of counts as missing (e.g. the 2025 MODIS gap)


def zscore_by_month(df, col, date_col):
    m = df[date_col].dt.month
    base = df[(df[date_col].dt.year >= CLIM[0]) & (df[date_col].dt.year <= CLIM[1])]
    mu = base.groupby(base[date_col].dt.month)[col].mean(); sd = base.groupby(base[date_col].dt.month)[col].std()
    return (df[col] - m.map(mu)) / m.map(sd)


def chirps_windows():
    c = pd.read_csv(f"{DATA}/chirps_monthly_zone.csv", parse_dates=["month", "posted"])
    out = []
    for z, g in c.groupby("zone"):
        g = g.sort_values("month").reset_index(drop=True)
        for w in (3, 6):
            s = g.precip_mm.rolling(w).sum()
            d = pd.DataFrame({"end": g.month + pd.offsets.MonthEnd(0), "avail": g.posted, "zone": z, "var": f"rain_{w}m", "value": s})
            d["z"] = zscore_by_month(d, "value", "end"); out.append(d.dropna(subset=["value"]))
    return pd.concat(out)


def power_windows():
    p = pd.read_csv(f"{DATA}/power_monthly_zone.csv", parse_dates=["month"])
    out = []
    for (z, v), g in p.groupby(["zone", "var"]):
        name = {"gwetroot": "soil", "tmax": "tmax", "rh": "rh"}.get(v)
        if name is None:
            continue
        g = g.sort_values("month").reset_index(drop=True)
        s = g.value.rolling(3).mean()
        end = g.month + pd.offsets.MonthEnd(0)
        d = pd.DataFrame({"end": end, "avail": end + pd.Timedelta(days=7), "zone": z, "var": f"{name}_3m", "value": s})
        d["z"] = zscore_by_month(d, "value", "end"); out.append(d.dropna(subset=["value"]))
    return pd.concat(out)


def modis_composites(work):
    px = pd.read_csv(f"{DATA}/modis_pixels.csv")
    items = pd.read_csv(f"{work}/modis_items.csv", dtype={"key": str, "produced": str})
    n = len(px)
    keys = sorted(items.key.unique())
    E = np.full((len(keys), n), np.nan, dtype="float32")
    meta = []
    for i, k in enumerate(keys):
        ii = items[items.key == k]
        for r in ii.itertuples():
            f = np.load(f"{work}/modis/{k}_{r.tile}.npz")
            ok = np.isin(f["rel"], [0, 1]) & (f["evi"] > -2000)
            v = np.where(ok, f["evi"] * 1e-4, np.nan)
            E[i, f["pixel_id"]] = v
        prod = pd.to_datetime(ii["produced"].max()[:7], format="%Y%j")
        end = pd.Timestamp(ii.end.iloc[0])
        # Collection 6.1 was bulk-reprocessed in 2020-21, so old production dates are not first-release dates.
        # If production came > 30 d after composite end, assume the original release was end + 20 d.
        avail = prod + pd.Timedelta(days=2) if (prod - end).days <= 30 else end + pd.Timedelta(days=20)
        meta.append(dict(key=k, start=pd.Timestamp(ii.start.iloc[0]), end=end, avail=avail))
    M = pd.DataFrame(meta)
    doy = M.start.dt.dayofyear.values
    yr = M.start.dt.year.values
    Z = np.full_like(E, np.nan)
    for d in np.unique(doy):
        rows = np.where(doy == d)[0]
        base = rows[(yr[rows] >= CLIM[0]) & (yr[rows] <= CLIM[1])]
        mu = np.nanmean(E[base], axis=0); sd = np.nanstd(E[base], axis=0)
        cnt = np.isfinite(E[base]).sum(0)
        sd = np.where((cnt >= 6) & (sd > 0.01), sd, np.nan)
        Z[rows] = (E[rows] - mu) / sd
    out = []
    for z in ZONES:
        m = np.ones(n, bool) if z == "ALL" else (px.zone.values == z)
        valid = np.isfinite(Z[:, m])
        out.append(M.assign(zone=z, evi_mean=np.nanmean(E[:, m], axis=1), evi_z=np.nanmean(Z[:, m], axis=1),
                            cloud_frac=1 - valid.mean(1)))
    return pd.concat(out)


def modis_windows(comp):
    out = []
    for z, g in comp.groupby("zone"):
        g = g.sort_values("start").reset_index(drop=True)
        s = g.evi_z.rolling(6, min_periods=3).mean()
        d = pd.DataFrame({"end": g.end, "avail": g.avail, "zone": z, "var": "evi_3m", "value": s})
        d["z"] = zscore_by_month(d, "value", "end"); out.append(d.dropna(subset=["value"]))
    return pd.concat(out)


def load_windows():
    return pd.read_csv(f"{DATA}/feature_windows.csv", parse_dates=["end", "avail"])


def features_at(dates, W=None, zones=("ALL",)):
    """Return DataFrame (as_of, zone, <var>_z..., <var>_cutoff..., DRY, WETX) using only windows with avail <= as_of."""
    W = load_windows() if W is None else W
    rows = []
    dates = pd.to_datetime(pd.Series(dates)).sort_values().values
    for z in zones:
        Wz = W[W.zone == z]
        rec = {pd.Timestamp(d): {"as_of": pd.Timestamp(d), "zone": z} for d in dates}
        for v, g in Wz.groupby("var"):
            g = g.sort_values("avail")
            j = pd.merge_asof(pd.DataFrame({"as_of": dates}), g[["avail", "end", "z", "value"]].rename(columns={"avail": "as_of_k"}),
                              left_on="as_of", right_on="as_of_k", direction="backward")
            for r in j.itertuples():
                stale = pd.isna(r.end) or (pd.Timestamp(r.as_of) - r.end).days > MAX_STALE_DAYS
                rec[pd.Timestamp(r.as_of)][f"{v}_z"] = np.nan if stale else r.z
                rec[pd.Timestamp(r.as_of)][f"{v}_cutoff"] = r.end
        rows += list(rec.values())
    F = pd.DataFrame(rows)
    comp = pd.concat([F["rain_6m_z"], F["soil_3m_z"], F["rh_3m_z"], -F["tmax_3m_z"], F["evi_3m_z"]], axis=1)
    F["DRY"] = comp.mean(axis=1, skipna=True)
    F["WETX"] = np.maximum(0, F["rain_3m_z"] - 1)
    return F


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    a = ap.parse_args()
    comp = modis_composites(a.work)
    comp.to_csv(f"{DATA}/modis_evi_composites.csv", index=False, float_format="%.4f")
    W = pd.concat([chirps_windows(), power_windows(), modis_windows(comp)])
    W = W[W.end >= "1990-01-01"]
    W.to_csv(f"{DATA}/feature_windows.csv", index=False, float_format="%.4f")
    me = pd.date_range("2003-10-31", pd.Timestamp.today(), freq="ME")
    F = features_at(me, W, zones=ZONES)
    F.to_csv(f"{DATA}/features_monthly.csv", index=False, float_format="%.4f", date_format="%Y-%m-%d")
    print(F[F.zone == "ALL"].tail(4).T)


if __name__ == "__main__":
    main()
