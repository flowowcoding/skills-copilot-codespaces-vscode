"""Aggregate CHIRPS and NASA POWER to districts and to crop-weighted national series.

Inputs (scratch): chirps/<YYYYMM>.npz (fetch_chirps.py), power/<dist>.csv (fetch_power.py),
                  ../data/district_weights.csv (build_districts.py).
District rainfall = mean CHIRPS over a 0.25 x 0.25 deg box (5 x 5 cells) centred on the ICRISAT centroid.
Crop-weighted series use the crop's core districts, weights = 2008-2017 mean ICRISAT area (renormalised).

Outputs (--out, committed, each < 5 MB):
  chirps_district_monthly.csv : dist_code, month (YYYY-MM), precip_mm, available_date (= 20th of next month)
  weather_crop_daily.csv      : crop, date, tmax_c, heat35_share (area share with Tmax >= 35 C), gwetroot,
                                gwettop, prcp_mm  (POWER; available_date = date + 7 days)
Usage:  python build_weather.py --work <scratch>/india --out ../data
"""
import argparse, glob, os
import numpy as np, pandas as pd

CROPS = ["chickpea", "pigeonpea", "sugarcane"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    dw = pd.read_csv(f"{a.out}/district_weights.csv")
    dw = dw[(dw.core_chickpea + dw.core_pigeonpea + dw.core_sugarcane) > 0]
    # CHIRPS
    rows = []
    for fn in sorted(glob.glob(f"{a.work}/chirps/*.npz")):
        z = np.load(fn); p = z["p10"].astype(float); p[p == 65535] = np.nan; p /= 10
        W, N, res = float(z["west"]), float(z["north"]), float(z["res"])
        ym = os.path.basename(fn)[:6]
        for r in dw.itertuples():
            c = int((r.lon - W) / res); rr = int((N - r.lat) / res)
            box = p[rr - 2:rr + 3, c - 2:c + 3]
            if np.isnan(box).all():  # centroid on a coast / outside the CHIRPS land mask: widen to 0.55 deg
                box = p[rr - 5:rr + 6, c - 5:c + 6]
            rows.append((r.dist_code, f"{ym[:4]}-{ym[4:]}", np.nanmean(box)))
    ch = pd.DataFrame(rows, columns=["dist_code", "month", "precip_mm"])
    m = pd.to_datetime(ch.month + "-01")
    ch["available_date"] = (m + pd.offsets.MonthBegin(1) + pd.Timedelta(days=19)).dt.date
    ch.to_csv(f"{a.out}/chirps_district_monthly.csv", index=False, float_format="%.1f")
    print("chirps", ch.shape, ch.month.min(), ch.month.max())
    # POWER
    P = {}
    for r in dw.itertuples():
        f = f"{a.work}/power/{r.dist_code}.csv"
        if os.path.exists(f):
            P[r.dist_code] = pd.read_csv(f, index_col=0, parse_dates=True)
    out = []
    for crop in CROPS:
        w = dw[dw[f"core_{crop}"] == 1].set_index("dist_code")[f"share_{crop}"]
        w = w[w.index.isin(P)]; w = w / w.sum()
        stack = lambda col: pd.concat({d: P[d][col] for d in w.index}, axis=1)
        tmax = stack("T2M_MAX")
        wavg = lambda df: (df * w).sum(axis=1, min_count=1) / (df.notna() * w).sum(axis=1)
        o = pd.DataFrame({"tmax_c": wavg(tmax), "heat35_share": wavg((tmax >= 35).astype(float).where(tmax.notna())),
                          "gwetroot": wavg(stack("GWETROOT")), "gwettop": wavg(stack("GWETTOP")),
                          "prcp_mm": wavg(stack("PRECTOTCORR"))})
        o = o.dropna(how="all").rename_axis("date").reset_index(); o.insert(0, "crop", crop)
        out.append(o)
    o = pd.concat(out); o.to_csv(f"{a.out}/weather_crop_daily.csv", index=False, float_format="%.3f")
    print("power", o.shape)


if __name__ == "__main__":
    main()
