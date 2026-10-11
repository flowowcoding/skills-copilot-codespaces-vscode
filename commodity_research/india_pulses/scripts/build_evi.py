"""District EVI anomalies from the extracted MODIS Aqua MYD13A1 pixels.

Steps
 1. QA: keep pixel_reliability 0 (good) or 1 (marginal); EVI fill (-3000) -> NaN.
 2. Cropland filter (there is no free MODIS land-cover product on Planetary Computer): a pixel is
    cropland if, over the seasons Jul 2002 - Jun 2007 only (never used for evaluation), its EVI p95 - p5
    >= 0.20, p5 <= 0.25 and p95 >= 0.35 (strong seasonal cycle, bare between crops; excludes forest,
    water, desert, towns).
 3. Pixel anomaly = EVI - mean of the same composite (start day-of-year) over the previous 8 seasons
    (at least 3 required). The rolling baseline limits the drift from the long-run greening of Indian
    farmland (irrigation, double cropping).
 4. District value = mean over its cropland pixels with a valid observation (>= 15 pixels, else NaN).
Point-in-time: a composite is usable from end date + 14 days (available_date).

Output: ../data/evi_district_composite.csv
        (dist_code, key YYYYDDD, start, end, available_date, evi, evi_anom, n_valid, n_crop)
Usage:  python build_evi.py --work <scratch>/india --out ../data
"""
import argparse, glob, os
import numpy as np, pandas as pd


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    px = pd.read_csv(f"{a.work}/pixels.csv")
    files = sorted(glob.glob(f"{a.work}/modis_MYD/*.npz"))
    meta = pd.DataFrame({"fn": files})
    meta["key"] = meta.fn.str.extract(r"/(\d{7})_h")[0]
    meta["tile"] = meta.fn.str.extract(r"_(h\d\dv\d\d)\.npz")[0]
    keys = sorted(meta.key.unique())
    tile_idx = {t: g.pixel_id.values for t, g in px.groupby("tile")}
    E = np.full((len(keys), len(px)), np.nan, dtype=np.float32)
    starts, ends = {}, {}
    for r in meta.itertuples():
        z = np.load(r.fn)
        e = z["evi"].astype(np.float32) / 1e4; rel = z["rel"]
        e[(rel < 0) | (rel > 1) | (z["evi"] <= -2000)] = np.nan
        E[keys.index(r.key), tile_idx[r.tile]] = e
        starts[r.key] = str(z["start"]); ends[r.key] = str(z["end"])
    st = pd.to_datetime(pd.Series([starts[k] for k in keys]))
    # cropland mask from Jul 2002 - Jun 2007
    base = ((st >= "2002-07-01") & (st < "2007-07-01")).values
    p5 = np.nanpercentile(E[base], 5, axis=0); p95 = np.nanpercentile(E[base], 95, axis=0)
    crop = (p95 - p5 >= 0.20) & (p5 <= 0.25) & (p95 >= 0.35)
    px["crop"] = crop
    print("cropland share of sample pixels", crop.mean().round(3))
    # rolling same-DOY baseline over previous 8 seasons
    doy = np.array([int(k[4:]) for k in keys]); yr = np.array([int(k[:4]) for k in keys])
    A = np.full_like(E, np.nan)
    for i in range(len(keys)):
        prev = np.where((doy == doy[i]) & (yr < yr[i]) & (yr >= yr[i] - 8))[0]
        if len(prev) >= 3:
            cnt = np.sum(~np.isnan(E[prev]), axis=0)
            mu = np.nanmean(E[prev], axis=0) if True else None
            mu[cnt < 3] = np.nan
            A[i] = E[i] - mu
    rows = []
    for d, g in px[px.crop].groupby("dist_code"):
        idx = g.pixel_id.values
        ev = E[:, idx]; an = A[:, idx]
        nv = np.sum(~np.isnan(an), axis=1)
        m_e = np.nanmean(ev, axis=1); m_a = np.nanmean(an, axis=1)
        m_a[nv < 15] = np.nan
        for i, k in enumerate(keys):
            rows.append((d, k, starts[k], ends[k], m_e[i], m_a[i], int(nv[i]), len(idx)))
    o = pd.DataFrame(rows, columns=["dist_code", "key", "start", "end", "evi", "evi_anom", "n_valid", "n_crop"])
    o["available_date"] = (pd.to_datetime(o.end) + pd.Timedelta(days=14)).dt.date
    o.to_csv(f"{a.out}/evi_district_composite.csv", index=False, float_format="%.4f")
    px[["pixel_id", "dist_code", "tile", "lat", "lon", "crop"]].to_csv(f"{a.work}/pixels_crop.csv", index=False)
    print(o.shape, o.evi_anom.notna().mean().round(3))


if __name__ == "__main__":
    main()
